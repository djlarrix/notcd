"""El servidor MCP de notcd: las herramientas que ve el asistente."""

import asyncio
import functools
import json
import logging
import re
import subprocess
import sys
import time
from collections import OrderedDict
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from notcd import __version__, actualizacion, entorno_login, formato, registro, rutas, verificacion
from notcd.conexion import SIN_SESION, Conexion, explicar
from notcd.trabajos import ESPERA, Trabajos

log = logging.getLogger("notcd")

INSTRUCCIONES = """\
notcd te conecta con NotebookLM (Gemini Notebook) de la cuenta de Google del usuario. \
Son dos IAs con papeles distintos y conviene no confundirlos:

- NotebookLM LEE. Retiene corpus enormes (expedientes de cientos de páginas, decenas de contratos, \
transcripciones) y responde anclado a esas fuentes, devolviendo el pasaje textual que respalda cada \
afirmación. También genera resúmenes en audio, mapas mentales, tablas comparativas y presentaciones.
- TÚ PIENSAS Y ESCRIBES. Decides qué preguntar, contrastas lo que NotebookLM encontró, razonas \
jurídicamente y redactas. NotebookLM es el lector; tú eres el abogado.

Reglas:
1. Todo hecho que saques de NotebookLM va con su fuente y el pasaje textual que devolvió `preguntar` \
o `buscar_pasajes`. Una respuesta sin citas no está verificada y se dice así.
2. Lo que decide el asunto (fechas, montos, plazos, quién dijo qué, el texto de una cláusula) se \
comprueba con `buscar_pasajes` o `leer_fuente` antes de afirmarlo: NotebookLM puede atribuir mal o \
resumir de más.
3. Toda cita entre comillas que vayas a entregar pasa antes por `verificar_citas`; la que no salga \
LITERAL se corrige con el texto real o se saca de las comillas.
4. En tu respuesta separa lo que dicen las fuentes de tu propio análisis.
5. Pregunta en serie y acotado: varias preguntas específicas rinden más que una general. Repregunta \
con el mismo conversacion_id.
6. `agregar_fuentes` envía documentos a Google, y `compartir_cuaderno` da acceso a otras personas. \
Si el usuario no lo pidió expresamente para esos documentos o esas personas, confírmalo antes.
7. NotebookLM no es fuente del derecho vigente. El texto de una ley, un fallo o un dictamen se trae \
de las herramientas de fuentes oficiales que haya (por ejemplo Responsa); si sirve, súbelo después \
al cuaderno como texto.
8. Si una herramienta devuelve un trabajo_id, la operación sigue en segundo plano: no la repitas, \
pide el resultado con `ver_trabajo`.
9. Si una herramienta dice que no hay sesión, que expiró o que está incompleta, usa `iniciar_sesion` \
y pide al usuario que entre con su cuenta de Google en la ventana que se abre.

Antes de un trabajo de varios pasos (leer un expediente, comparar contratos, preparar una audiencia, \
revisar un escrito, investigar un tema), lee la guía con `guia_de_metodo`, salvo que la skill notcd ya esté cargada.
"""

mcp = MCPServer(
    name="notcd",
    title="notcd — NotebookLM",
    version=__version__,
    instructions=INSTRUCCIONES,
)
conexion = Conexion()
trabajos = Trabajos()
# httpx anota cada petición (con la cuenta en la URL): sólo advertencias.
for _ruidoso in ("httpx", "httpcore", "notebooklm"):
    logging.getLogger(_ruidoso).setLevel(logging.WARNING)
# Las esperas entre consultas a NotebookLM (las pruebas la reemplazan para no esperar).
dormir = asyncio.sleep

# Más de esto en una sola llamada suele ser un error (la carpeta equivocada).
MAX_ARCHIVOS = 50
# Tope de NotebookLM por fuente.
MAX_BYTES = 200 * 1024 * 1024
EXTENSIONES = {
    ".pdf", ".txt", ".md", ".markdown", ".docx", ".pptx", ".xlsx", ".csv", ".epub",
    ".mp3", ".m4a", ".wav", ".aac", ".ogg", ".mp4", ".mov", ".png", ".jpg", ".jpeg", ".webp",
}
CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PERSONA_LECTOR = (
    "Actúas como lector de documentos para abogados en Chile. Responde exclusivamente con lo que consta "
    "en las fuentes de este cuaderno; no uses conocimiento externo ni completes con suposiciones. Si algo "
    "no consta, dilo expresamente («no consta en las fuentes»). Cita textualmente, entre comillas, los "
    "pasajes decisivos. Cuando existan, indica fechas, fojas o páginas, números de cláusula y el documento "
    "del que sale cada dato. Distingue lo que afirma cada parte de lo que resolvió el tribunal o consta en "
    "documentos. No des opiniones, estrategia ni conclusiones jurídicas que no estén en las fuentes. "
    "Ve directo a lo preguntado: no repitas la individualización del documento ni de las partes, ni "
    "agregues secciones que no se pidieron; si algo no consta, basta una línea que lo diga. No "
    "termines con preguntas ni ofrecimientos. Responde en español."
)


def herramienta(titulo: str, *, lectura: bool, destructiva: bool = False):
    """Registra una herramienta y convierte cualquier falla en un mensaje que el asistente pueda usar."""

    def registrar(fn):
        @functools.wraps(fn)
        async def envuelta(*args: Any, **kwargs: Any) -> str:
            inicio = time.monotonic()
            try:
                resultado = await fn(*args, **kwargs)
                log.info("%s ok %.1fs", fn.__name__, time.monotonic() - inicio)
                return resultado
            except ToolError:
                log.info("%s rechazada %.1fs", fn.__name__, time.monotonic() - inicio)
                raise
            except Exception as error:
                log.info("%s error %s %.1fs", fn.__name__, type(error).__name__, time.monotonic() - inicio)
                raise ToolError(await explicacion(error)) from error

        mcp.tool(
            title=titulo,
            annotations=ToolAnnotations(
                title=titulo,
                readOnlyHint=lectura,
                destructiveHint=destructiva,
                idempotentHint=lectura,
                openWorldHint=True,
            ),
            structured_output=False,
        )(envuelta)
        return fn

    return registrar


async def explicacion(error: BaseException) -> str:
    if isinstance(error, ToolError):
        return str(error)  # ya viene redactado para el asistente
    mensaje, descartar = explicar(error)
    if descartar:
        await conexion.cerrar()
    return mensaje


# ──────────────────────────────────────────────────────────────── memorias

_titulos: dict[str, tuple[float, dict[str, str]]] = {}
_nombres_cuaderno: dict[str, str] = {}
# Texto completo de las fuentes ya leídas (para leer por tramos y verificar citas).
_textos: "OrderedDict[tuple[str, str], verificacion.Fuente]" = OrderedDict()
MAX_CARACTERES_EN_MEMORIA = 40_000_000


async def titulos_fuentes(cliente: Any, cuaderno_id: str, *, refrescar: bool = False) -> dict[str, str]:
    guardado = _titulos.get(cuaderno_id)
    if guardado and not refrescar and time.monotonic() - guardado[0] < 120:
        return guardado[1]
    lista = await cliente.sources.list(cuaderno_id)
    titulos = {s.id: s.title or "sin título" for s in lista}
    _titulos[cuaderno_id] = (time.monotonic(), titulos)
    return titulos


async def nombre_cuaderno(cliente: Any, cuaderno_id: str) -> str:
    if cuaderno_id not in _nombres_cuaderno:
        nb = await cliente.notebooks.get(cuaderno_id)
        _nombres_cuaderno[cuaderno_id] = nb.title or "sin título"
    return _nombres_cuaderno[cuaderno_id]


async def texto_fuente(cliente: Any, cuaderno_id: str, fuente_id: str, titulo: str | None = None) -> verificacion.Fuente:
    clave = (cuaderno_id, fuente_id)
    if clave in _textos:
        _textos.move_to_end(clave)
        return _textos[clave]
    completo = await cliente.sources.get_fulltext(cuaderno_id, fuente_id)
    texto = completo.rendered_content or completo.content or ""
    fuente = verificacion.Fuente(id=fuente_id, titulo=titulo or completo.title or "sin título", texto=texto)
    _textos[clave] = fuente
    while sum(len(f.texto) for f in _textos.values()) > MAX_CARACTERES_EN_MEMORIA and len(_textos) > 1:
        _textos.popitem(last=False)
    return fuente


def olvidar_cuaderno(cuaderno_id: str) -> None:
    _titulos.pop(cuaderno_id, None)
    for clave in [c for c in _textos if c[0] == cuaderno_id]:
        _textos.pop(clave, None)


# ─────────────────────────────────────────────────────────── sesión de Google

_proceso_login: subprocess.Popen | None = None


def login_en_curso() -> bool:
    return _proceso_login is not None and _proceso_login.poll() is None


@herramienta("Estado de la conexión con NotebookLM", lectura=True)
async def estado_conexion() -> str:
    """Comprueba si notcd está conectado a NotebookLM, con qué cuenta y si hay correcciones pendientes.

    Úsala al empezar si no sabes si hay sesión, después de `iniciar_sesion`, o cuando algo
    que antes funcionaba empieza a fallar.
    """
    import notebooklm

    version = f"notcd {__version__} · notebooklm-py {notebooklm.__version__}"
    if login_en_curso():
        return "Hay una ventana de inicio de sesión abierta esperando que el usuario entre con Google. " + version
    if not rutas.sesion_google().is_file():
        return SIN_SESION + f"\n({version})"
    cliente = await conexion.cliente()
    cuadernos = await cliente.notebooks.list()
    lineas = [f"Conectado a NotebookLM como {rutas.cuenta_conectada() or 'cuenta sin correo registrado'}."]
    lineas.append(f"{len(cuadernos)} cuaderno(s) en la cuenta.")
    try:
        limites = await cliente.settings.get_account_limits()
        if limites.notebook_limit or limites.source_limit:
            lineas.append(
                f"Límites del plan: {limites.notebook_limit or '?'} cuadernos, "
                f"{limites.source_limit or '?'} fuentes por cuaderno."
            )
    except Exception:  # los límites son informativos; no deben tumbar el diagnóstico
        log.debug("sin límites de cuenta", exc_info=True)
    if aviso := await actualizacion.aviso():
        lineas.append(aviso)
    lineas.append(version)
    return "\n".join(lineas)


@herramienta("Iniciar sesión en Google para NotebookLM", lectura=False)
async def iniciar_sesion(
    navegador: Annotated[
        Literal["automatico", "chrome", "edge"],
        Field(description="'automatico' usa el navegador de notcd y, si falla, Google Chrome. "
              "'chrome' o 'edge' fuerzan ese navegador."),
    ] = "automatico",
) -> str:
    """Abre una ventana de navegador con el formulario de Google para que el usuario inicie sesión.

    La sesión queda guardada en este computador y notcd la usa para hablar con
    NotebookLM. Úsala cuando otra herramienta diga que no hay sesión, que expiró o que está
    incompleta. Después de llamarla, pide al usuario que entre en la ventana y te avise cuando
    termine; entonces confirma con `estado_conexion`.
    """
    global _proceso_login
    if login_en_curso():
        return "Ya hay una ventana de inicio de sesión abierta. Pide al usuario que termine de entrar en ella."

    argumentos = [sys.executable, "-m", "notcd", "login"]
    if navegador == "chrome":
        argumentos.append("--chrome")
    elif navegador == "edge":
        argumentos.append("--edge")

    salida_log = rutas.registro_login()
    salida_log.parent.mkdir(parents=True, exist_ok=True)
    opciones: dict[str, Any] = {}
    if sys.platform == "win32":
        opciones["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        opciones["start_new_session"] = True
    with open(salida_log, "w", encoding="utf-8") as salida:
        # stdout a un archivo: el stdout de este proceso es el canal MCP y no se toca.
        _proceso_login = subprocess.Popen(
            argumentos, stdin=subprocess.DEVNULL, stdout=salida, stderr=subprocess.STDOUT,
            env={**entorno_login(), "NO_COLOR": "1", "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"}, **opciones,
        )
    await conexion.cerrar()

    for _ in range(8):
        await dormir(0.5)
        if _proceso_login.poll() is not None:
            break
    if _proceso_login.poll() == 0:
        return "La sesión ya estaba iniciada y quedó guardada. Confirma con `estado_conexion`."
    if _proceso_login.poll() is not None:
        detalle = salida_log.read_text(encoding="utf-8", errors="replace")[-1500:]
        return f"No se pudo abrir el inicio de sesión. Detalle:\n{detalle}"
    return (
        "Se está abriendo una ventana con el formulario de Google (la primera vez puede tardar un "
        "minuto porque descarga el navegador). Pide al usuario que entre con la cuenta de Google "
        "que usa en NotebookLM; cuando aparezca NotebookLM, la ventana se cierra sola. Tiene 10 "
        "minutos. Luego confirma con `estado_conexion`."
    )


# ──────────────────────────────────────────────────────────────── cuadernos


@herramienta("Listar cuadernos de NotebookLM", lectura=True)
async def listar_cuadernos(
    filtro: Annotated[str | None, Field(description="Texto a buscar en el título (opcional).")] = None,
) -> str:
    """Lista los cuadernos (notebooks) de NotebookLM de la cuenta, con su id y número de fuentes."""
    cliente = await conexion.cliente()
    lista = await cliente.notebooks.list()
    for nb in lista:
        _nombres_cuaderno[nb.id] = nb.title or "sin título"
    return formato.cuadernos(lista, filtro)


@herramienta("Ver un cuaderno: resumen y fuentes", lectura=True)
async def ver_cuaderno(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno (de listar_cuadernos).")],
) -> str:
    """Muestra un cuaderno: el resumen que hizo NotebookLM, sus fuentes (con ids) y sus notas.

    Úsala antes de preguntar para saber qué documentos hay y cuáles siguen procesándose.
    """
    cliente = await conexion.cliente()
    nb = await cliente.notebooks.get(cuaderno_id)
    _nombres_cuaderno[cuaderno_id] = nb.title or "sin título"
    lista = await cliente.sources.list(cuaderno_id)
    _titulos[cuaderno_id] = (time.monotonic(), {s.id: s.title or "sin título" for s in lista})

    partes = [f"Cuaderno «{nb.title}» (id: {nb.id})", "", f"FUENTES ({len(lista)}):", formato.fuentes(lista)]
    if lista:
        try:
            descripcion = await cliente.notebooks.get_description(cuaderno_id)
            if descripcion.summary:
                partes += ["", "RESUMEN DE NOTEBOOKLM:", formato.recortar(descripcion.summary, 3000)]
            temas = [t.question for t in descripcion.suggested_topics if t.question]
            if temas:
                partes += ["", "Preguntas que sugiere NotebookLM:"] + [f"  - {t}" for t in temas[:6]]
        except Exception:
            log.debug("sin descripción", exc_info=True)
    try:
        notas = await cliente.notes.list(cuaderno_id)
        if notas:
            partes += ["", f"NOTAS ({len(notas)}):"] + [f"  - «{n.title}» · id: {n.id}" for n in notas[:20]]
    except Exception:
        log.debug("sin notas", exc_info=True)
    return "\n".join(partes)


async def aplicar_lector(cliente: Any, cuaderno_id: str, extra: str | None, largo: str) -> None:
    import notebooklm as nlm

    largos = {
        "corto": nlm.ChatResponseLength.SHORTER,
        "normal": nlm.ChatResponseLength.DEFAULT,
        "largo": nlm.ChatResponseLength.LONGER,
    }
    instrucciones = PERSONA_LECTOR + (f"\n\nAdemás: {extra.strip()}" if extra and extra.strip() else "")
    await cliente.chat.configure(
        cuaderno_id, goal=nlm.ChatGoal.CUSTOM, response_length=largos[largo], custom_prompt=instrucciones
    )


@herramienta("Crear cuaderno en NotebookLM", lectura=False)
async def crear_cuaderno(
    titulo: Annotated[str, Field(description="Título, p. ej. «Pérez con Banco X · C-1234-2025 · 3° Civil Stgo».")],
    lector_juridico: Annotated[
        bool, Field(description="Configurar a NotebookLM como lector jurídico (sólo lo que consta, cita textual).")
    ] = True,
) -> str:
    """Crea un cuaderno vacío en NotebookLM, configurado para responder como lector jurídico.

    Después se le agregan fuentes con `agregar_fuentes`.
    """
    cliente = await conexion.cliente()
    nb = await cliente.notebooks.create(titulo)
    _nombres_cuaderno[nb.id] = nb.title or titulo
    texto = f"Cuaderno creado: «{nb.title or titulo}» · id: {nb.id}"
    if lector_juridico:
        try:
            await aplicar_lector(cliente, nb.id, None, "normal")
            texto += "\nConfigurado como lector jurídico: responderá sólo con lo que consta, citando."
        except Exception:
            log.info("crear_cuaderno: no se pudo configurar el lector", exc_info=True)
            texto += "\n(No se pudo configurar el lector jurídico; se puede reintentar con configurar_lector.)"
    return texto


@herramienta("Configurar cómo responde NotebookLM en un cuaderno", lectura=False)
async def configurar_lector(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno.")],
    instrucciones_extra: Annotated[
        str | None, Field(description="Indicaciones adicionales para este cuaderno (opcional).")
    ] = None,
    largo: Annotated[
        Literal["corto", "normal", "largo"],
        Field(description="Largo de las respuestas. 'largo' es más exhaustivo pero bastante más lento."),
    ] = "normal",
    quitar: Annotated[bool, Field(description="True para volver a la configuración normal de NotebookLM.")] = False,
) -> str:
    """Configura a NotebookLM como lector jurídico en un cuaderno existente (o lo devuelve a lo normal).

    Lector jurídico: responde sólo con lo que consta en las fuentes, dice «no consta» cuando
    falta algo, cita textual y señala fechas, fojas, páginas y cláusulas. Los cuadernos que
    crea notcd ya vienen así.
    """
    import notebooklm as nlm

    cliente = await conexion.cliente()
    if quitar:
        await cliente.chat.configure(
            cuaderno_id, goal=nlm.ChatGoal.DEFAULT, response_length=nlm.ChatResponseLength.DEFAULT, custom_prompt=None
        )
        return "Listo: el cuaderno vuelve a la configuración normal de NotebookLM."
    await aplicar_lector(cliente, cuaderno_id, instrucciones_extra, largo)
    return "Listo: NotebookLM responderá en este cuaderno como lector jurídico" + (
        " con las indicaciones adicionales." if instrucciones_extra else "."
    )


@herramienta("Compartir un cuaderno con otras personas", lectura=False)
async def compartir_cuaderno(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno.")],
    correos: Annotated[list[str], Field(description="Correos de Google de las personas.")],
    rol: Annotated[
        Literal["lector", "editor"],
        Field(description="lector: ve y pregunta. editor: además agrega o quita fuentes y notas."),
    ] = "lector",
    avisar: Annotated[bool, Field(description="Que Google les envíe un correo avisando.")] = True,
    mensaje: Annotated[str | None, Field(description="Mensaje para el correo de aviso (opcional).")] = None,
) -> str:
    """Da acceso a un cuaderno a otras personas (por su correo de Google). Confirma antes con el usuario."""
    import notebooklm as nlm

    validos = [c.strip() for c in correos if CORREO.match(c.strip())]
    invalidos = [c for c in correos if not CORREO.match(c.strip())]
    if not validos:
        raise ToolError("Ninguno de los correos es válido: " + ", ".join(invalidos))
    permiso = nlm.SharePermission.EDITOR if rol == "editor" else nlm.SharePermission.VIEWER
    cliente = await conexion.cliente()
    hechos, fallas = [], []
    for correo in validos:
        try:
            await cliente.sharing.add_user(cuaderno_id, correo, permiso, notify=avisar, welcome_message=mensaje or "")
            hechos.append(correo)
        except Exception as error:
            fallas.append(f"{correo}: {explicar(error)[0]}")
    lineas = []
    if hechos:
        lineas.append(f"Compartido como {rol} con: {', '.join(hechos)}" + (" (se les avisó por correo)." if avisar else "."))
    if fallas:
        lineas.append("No se pudo compartir con: " + "; ".join(fallas))
    if invalidos:
        lineas.append("Correos no válidos, omitidos: " + ", ".join(invalidos))
    return "\n".join(lineas)


# ───────────────────────────────────────────────────────────────── fuentes


def expandir_rutas(entradas: list[str]) -> tuple[list[Path], list[str]]:
    """Convierte rutas de archivos y carpetas en la lista de archivos a subir.

    Devuelve (archivos, avisos). Las carpetas se recorren completas, sólo con las
    extensiones que NotebookLM acepta; un archivo nombrado explícitamente se intenta
    siempre.
    """
    archivos: list[Path] = []
    avisos: list[str] = []
    for entrada in entradas:
        texto = entrada.strip().strip('"').strip("'")
        if not texto:
            continue
        ruta = Path(texto).expanduser()
        if not ruta.is_absolute():
            ruta = Path.home() / ruta
        if rutas.es_ruta_prohibida(ruta):
            avisos.append(f"omitido (credenciales, no se sube): {ruta}")
            continue
        if ruta.is_dir():
            encontrados = sorted(
                p for p in ruta.rglob("*")
                if p.is_file()
                and p.suffix.lower() in EXTENSIONES
                and not any(parte.startswith((".", "~$")) for parte in p.relative_to(ruta).parts)
            )
            if not encontrados:
                avisos.append(f"la carpeta no tiene archivos que NotebookLM acepte: {ruta}")
            archivos.extend(encontrados)
        elif ruta.is_file():
            if ruta.suffix.lower() == ".doc":
                avisos.append(f"Word antiguo (.doc) no se acepta; guárdalo como .docx o PDF: {ruta.name}")
                continue
            archivos.append(ruta)
        else:
            avisos.append(f"no existe: {ruta}")
    unicos: dict[Path, Path] = {}
    for archivo in archivos:
        unicos.setdefault(archivo.resolve(), archivo)
    finales = []
    for archivo in unicos.values():
        try:
            if archivo.stat().st_size > MAX_BYTES:
                avisos.append(f"supera los 200 MB que acepta NotebookLM por fuente: {archivo.name}")
                continue
        except OSError:
            pass
        finales.append(archivo)
    return finales, avisos


def titulo_fuente_texto(texto: str, titulo: str | None) -> str:
    return (titulo or "").strip() or formato.recortar(texto.strip().splitlines()[0], 80) or "Texto"


@herramienta("Agregar fuentes a un cuaderno (sube documentos a Google)", lectura=False)
async def agregar_fuentes(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno de destino.")],
    archivos: Annotated[
        list[str] | None,
        Field(description="Rutas absolutas de archivos o carpetas de ESTE computador (PDF, Word .docx, "
              "texto, PowerPoint, Excel, audio, imágenes). Una carpeta se sube completa."),
    ] = None,
    urls: Annotated[
        list[str] | None, Field(description="Páginas web o videos de YouTube a agregar como fuente.")
    ] = None,
    texto: Annotated[
        str | None,
        Field(description="Texto a agregar como fuente (p. ej. una ley o un fallo traído de otra herramienta)."),
    ] = None,
    titulo_texto: Annotated[str | None, Field(description="Título para la fuente de `texto`.")] = None,
    repetir: Annotated[
        bool, Field(description="Subir aunque ya haya una fuente con el mismo nombre en el cuaderno.")
    ] = False,
) -> str:
    """Agrega fuentes a un cuaderno de NotebookLM: archivos locales, carpetas, URLs o texto.

    Los documentos se suben a la cuenta de Google del usuario. No sube dos veces un archivo
    que ya está en el cuaderno. Si la subida es larga, sigue en segundo plano (devuelve un
    trabajo_id para `ver_trabajo`).
    """
    lista_archivos, avisos = expandir_rutas(archivos or [])
    if len(lista_archivos) > MAX_ARCHIVOS:
        raise ToolError(
            f"Son {len(lista_archivos)} archivos; el máximo por llamada es {MAX_ARCHIVOS}. "
            "Confirma con el usuario la carpeta correcta o súbelos por partes."
        )
    if not (lista_archivos or urls or texto):
        detalle = ("\n" + "\n".join(avisos)) if avisos else ""
        raise ToolError("No hay nada que agregar." + detalle)

    cliente = await conexion.cliente()
    ya_estan: list[str] = []
    if not repetir:
        existentes = {t.casefold() for t in (await titulos_fuentes(cliente, cuaderno_id, refrescar=True)).values()}
        ya_estan = [a.name for a in lista_archivos if a.name.casefold() in existentes]
        ya_estan += [u for u in urls or [] if u.casefold() in existentes]
        lista_archivos = [a for a in lista_archivos if a.name.casefold() not in existentes]
        urls = [u for u in urls or [] if u.casefold() not in existentes]
        if texto and titulo_fuente_texto(texto, titulo_texto).casefold() in existentes:
            ya_estan.append(titulo_fuente_texto(texto, titulo_texto))
            texto = None
    if not (lista_archivos or urls or texto):
        return "Todo ya estaba en el cuaderno: " + ", ".join(ya_estan) + ". (Usa repetir=True para subirlo de nuevo.)"

    total = len(lista_archivos) + len(urls or []) + (1 if texto else 0)
    operacion = _agregar(cliente, cuaderno_id, lista_archivos, urls or [], texto, titulo_texto, avisos, ya_estan)
    return await trabajos.correr(f"Subida de {total} fuente(s)", operacion)


async def _agregar(
    cliente: Any, cuaderno_id: str, lista_archivos: list[Path], urls: list[str],
    texto: str | None, titulo_texto: str | None, avisos: list[str], ya_estan: list[str],
) -> str:
    inicio = time.monotonic()
    semaforo = asyncio.Semaphore(3)

    async def subir(etiqueta: str, accion) -> tuple[str, Any]:
        async with semaforo:
            try:
                return etiqueta, await accion()
            except Exception as error:
                return etiqueta, error

    tareas = [
        subir(a.name, functools.partial(cliente.sources.add_file, cuaderno_id, a, wait=False))
        for a in lista_archivos
    ]
    tareas += [subir(u, functools.partial(cliente.sources.add_url, cuaderno_id, u, wait=False)) for u in urls]
    if texto:
        titulo = titulo_fuente_texto(texto, titulo_texto)
        tareas.append(subir(titulo, functools.partial(cliente.sources.add_text, cuaderno_id, titulo, texto, wait=False)))
    resultados = await asyncio.gather(*tareas)

    agregadas = [(etiqueta, r) for etiqueta, r in resultados if not isinstance(r, Exception)]
    fallidas = [(etiqueta, r) for etiqueta, r in resultados if isinstance(r, Exception)]
    if fallidas and not agregadas:
        # Si todo falló por lo mismo (sesión vencida, cuota), basta con decirlo una vez.
        mensajes = {explicar(error)[0] for _, error in fallidas}
        if len(mensajes) == 1:
            raise ToolError(f"No se agregó ninguna fuente: {mensajes.pop()}")

    estados: dict[str, str] = {}
    if agregadas:
        # Si la subida fue rápida se espera el procesamiento aquí mismo, sin pasar el
        # límite de la app de escritorio; si fue lenta, se responde ya y se revisa después.
        restante = max(3.0, ESPERA - 5 - (time.monotonic() - inicio))
        ids = [fuente.id for _, fuente in agregadas]
        try:
            finales = await cliente.sources.wait_all_until_ready(cuaderno_id, ids, timeout=restante)
            for fuente_id, final in zip(ids, finales):
                if isinstance(final, Exception):
                    estados[fuente_id] = "procesando" if isinstance(final, TimeoutError) else f"con error ({final})"
                else:
                    estados[fuente_id] = "lista"
        except Exception:
            log.debug("espera de fuentes", exc_info=True)
    olvidar_cuaderno(cuaderno_id)

    lineas = [f"Agregadas {len(agregadas)} fuente(s) al cuaderno:"]
    for etiqueta, fuente in agregadas:
        lineas.append(f"  - «{fuente.title or etiqueta}» · {estados.get(fuente.id, 'procesando')} · id: {fuente.id}")
    if ya_estan:
        lineas.append(f"Ya estaban en el cuaderno (no se subieron de nuevo): {', '.join(ya_estan)}")
    if fallidas:
        lineas.append(f"No se pudieron agregar {len(fallidas)}:")
        lineas += [f"  - {etiqueta}: {explicar(error)[0]}" for etiqueta, error in fallidas]
    if avisos:
        lineas.append("Avisos:")
        lineas += [f"  - {a}" for a in avisos]
    if any(e == "procesando" for e in estados.values()) or len(estados) < len(agregadas):
        lineas.append("Las que siguen «procesando» estarán listas en unos minutos; revísalas con ver_cuaderno.")
    return "\n".join(lineas)


@herramienta("Quitar fuentes de un cuaderno", lectura=False, destructiva=True)
async def quitar_fuentes(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno.")],
    fuente_ids: Annotated[list[str], Field(description="Ids de las fuentes a quitar (de ver_cuaderno).")],
) -> str:
    """Elimina fuentes de un cuaderno de NotebookLM (por ejemplo, subidas por error o duplicadas).

    Es irreversible: confirma con el usuario cuáles antes de usarla.
    """
    cliente = await conexion.cliente()
    titulos = await titulos_fuentes(cliente, cuaderno_id, refrescar=True)
    desconocidas = [f for f in fuente_ids if f not in titulos]
    quitadas = []
    for fuente_id in fuente_ids:
        if fuente_id in titulos:
            await cliente.sources.delete(cuaderno_id, fuente_id)
            quitadas.append(f"«{titulos[fuente_id]}»")
    olvidar_cuaderno(cuaderno_id)
    lineas = [f"Quitadas {len(quitadas)} fuente(s): {', '.join(quitadas)}" if quitadas else "No se quitó nada."]
    if desconocidas:
        lineas.append("Estos ids no están en el cuaderno: " + ", ".join(desconocidas))
    return "\n".join(lineas)


# ──────────────────────────────────────────────── preguntar y verificar


@herramienta("Preguntar a NotebookLM sobre las fuentes", lectura=True)
async def preguntar(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno.")],
    pregunta: Annotated[str, Field(description="Pregunta concreta. Mejor varias específicas que una general.")],
    fuente_ids: Annotated[
        list[str] | None, Field(description="Limitar la respuesta a estas fuentes (opcional).")
    ] = None,
    conversacion_id: Annotated[
        str | None, Field(description="Para repreguntar en el mismo hilo: el id que devolvió la respuesta anterior.")
    ] = None,
) -> str:
    """Pregunta a NotebookLM (Gemini) y devuelve su respuesta anclada en las fuentes del cuaderno.

    Cada [n] de la respuesta viene resuelto con el título de la fuente y el pasaje textual
    que lo respalda. Úsala para que NotebookLM lea por ti un corpus grande; tú contrastas,
    razonas y redactas.
    """
    cliente = await conexion.cliente()

    async def operar() -> str:
        resultado = await cliente.chat.ask(
            cuaderno_id, pregunta, source_ids=fuente_ids, conversation_id=conversacion_id
        )
        titulos = await titulos_fuentes(cliente, cuaderno_id)
        if any(r.source_id not in titulos for r in resultado.references or []):
            titulos = await titulos_fuentes(cliente, cuaderno_id, refrescar=True)
        return formato.respuesta(resultado, titulos, await nombre_cuaderno(cliente, cuaderno_id))

    return await trabajos.correr("Pregunta a NotebookLM", operar())


@herramienta("Buscar pasajes textuales en las fuentes", lectura=True)
async def buscar_pasajes(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno.")],
    consulta: Annotated[str, Field(description="Lo que se busca: un hecho, una cláusula, un nombre, una fecha.")],
    fuente_ids: Annotated[list[str] | None, Field(description="Buscar sólo en estas fuentes (opcional).")] = None,
    limite: Annotated[int, Field(ge=1, le=20, description="Cuántos pasajes devolver.")] = 8,
) -> str:
    """Busca en las fuentes y devuelve los pasajes textuales más pertinentes, sin que NotebookLM los resuma.

    Sirve para verificar una afirmación o encontrar dónde se dice algo: lo que vuelve es
    texto original de los documentos.
    """
    cliente = await conexion.cliente()
    trozos = await cliente.sources.search(cuaderno_id, consulta, source_ids=fuente_ids, limit=limite)
    titulos = await titulos_fuentes(cliente, cuaderno_id)
    return formato.pasajes(trozos, titulos, consulta)


@herramienta("Leer el texto completo de una fuente", lectura=True)
async def leer_fuente(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno.")],
    fuente_id: Annotated[str, Field(description="Id de la fuente (de ver_cuaderno o de una cita).")],
    desde: Annotated[int, Field(ge=0, description="Carácter desde el que leer (para documentos largos).")] = 0,
    largo: Annotated[int, Field(ge=1000, le=60000, description="Cuántos caracteres devolver.")] = 20000,
) -> str:
    """Devuelve el texto de una fuente tal como NotebookLM lo leyó, por tramos.

    Úsala para leer el original detrás de una cita, o cuando necesites el texto exacto.
    """
    cliente = await conexion.cliente()

    async def operar() -> str:
        fuente = await texto_fuente(cliente, cuaderno_id, fuente_id)
        texto = fuente.texto
        total = len(texto)
        tramo = texto[desde : desde + largo]
        cabecera = f"«{fuente.titulo}» (fuente_id: {fuente_id}) · caracteres {desde}–{desde + len(tramo)} de {total}"
        if not tramo:
            return cabecera + "\n(no hay texto en ese tramo)"
        pie = ""
        if desde + len(tramo) < total:
            pie = f"\n\n[… sigue. Para continuar: leer_fuente(desde={desde + len(tramo)})]"
        if total < 200 and desde == 0:
            pie += "\n\n⚠ La fuente casi no tiene texto: puede ser un escaneo sin reconocimiento de texto (OCR)."
        return f"{cabecera}\n\n{tramo}{pie}"

    return await trabajos.correr("Lectura de una fuente", operar())


@herramienta("Verificar que las citas textuales estén literales en las fuentes", lectura=True)
async def verificar_citas(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno con los documentos originales.")],
    citas: Annotated[
        list[str],
        Field(description="Las frases que van entre comillas en el escrito, una por elemento. "
              "Las omisiones se marcan con […] o (...)."),
    ],
    fuente_ids: Annotated[
        list[str] | None, Field(description="Buscar sólo en estas fuentes, si se sabe de dónde vienen (más rápido).")
    ] = None,
) -> str:
    """Comprueba, letra por letra, si cada cita está tal cual en el texto de las fuentes.

    No es otra IA opinando: compara contra el texto de los documentos. Dice si cada cita
    está LITERAL, CON DIFERENCIAS (mostrando el texto real y qué cambia) o NO ENCONTRADA.
    Úsala antes de entregar cualquier escrito o informe con citas entre comillas.
    """
    import notebooklm as nlm

    if not citas:
        raise ToolError("No hay citas que verificar.")
    if len(citas) > 60:
        raise ToolError("Son más de 60 citas: verifícalas por partes.")
    cliente = await conexion.cliente()

    async def operar() -> str:
        lista = await cliente.sources.list(cuaderno_id)
        elegidas = [
            s for s in lista
            if (not fuente_ids or s.id in fuente_ids) and formato.nombre(s.status) != "ERROR"
        ]
        if not elegidas:
            raise ToolError("No hay fuentes legibles que revisar en ese cuaderno.")
        semaforo = asyncio.Semaphore(4)

        async def cargar(s):
            async with semaforo:
                try:
                    return await texto_fuente(cliente, cuaderno_id, s.id, s.title)
                except nlm.NotebookLMError:
                    return None

        fuentes = [f for f in await asyncio.gather(*(cargar(s) for s in elegidas)) if f is not None]
        resultados = await asyncio.to_thread(lambda: [verificacion.verificar(c, fuentes) for c in citas])
        texto = verificacion.informe(resultados)
        procesando = [s.title for s in elegidas if formato.nombre(s.status) != "READY"]
        if procesando:
            texto += "\n\n⚠ Fuentes aún en proceso (pueden faltar en la revisión): " + ", ".join(procesando)
        return texto

    return await trabajos.correr(f"Verificación de {len(citas)} cita(s)", operar())


@herramienta("Guardar una nota en el cuaderno", lectura=False)
async def guardar_nota(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno.")],
    titulo: Annotated[str, Field(description="Título de la nota, idealmente con autor y fecha.")],
    contenido: Annotated[str, Field(description="Texto de la nota (puede ser largo).")],
) -> str:
    """Guarda una nota en el cuaderno de NotebookLM (por ejemplo, tu análisis o tu minuta).

    Así el trabajo queda junto a los documentos del caso y el equipo lo ve en NotebookLM.
    """
    cliente = await conexion.cliente()
    nota = await cliente.notes.create(cuaderno_id, titulo, contenido)
    return f"Nota guardada en el cuaderno: «{nota.title or titulo}» · id: {nota.id}"


@herramienta("Buscar fuentes en la web con NotebookLM", lectura=True)
async def buscar_en_web(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno donde se haría la búsqueda.")],
    tema: Annotated[str, Field(description="Qué buscar.")],
) -> str:
    """Pide a NotebookLM que busque en la web fuentes sobre un tema y devuelve los resultados.

    No agrega nada al cuaderno: tú eliges cuáles valen (prefiere fuentes oficiales y
    académicas) y las incorporas con `agregar_fuentes(urls=[...])` si el usuario está de acuerdo.
    """
    cliente = await conexion.cliente()

    async def operar() -> str:
        tarea = await cliente.research.discover(cuaderno_id, tema)
        if not tarea.sources:
            return f"NotebookLM no encontró resultados web para «{tema}»."
        lineas = [f"Resultados web para «{tema}» ({len(tarea.sources)}):"]
        if tarea.summary:
            lineas += ["", "Panorama según NotebookLM: " + formato.recortar(tarea.summary, 1500), ""]
        for i, s in enumerate(tarea.sources, 1):
            lineas.append(f"  {i}. {s.title or 'sin título'} — {s.url}")
        lineas.append("\nPara incorporar alguno: agregar_fuentes(cuaderno_id, urls=[...]).")
        return "\n".join(lineas)

    return await trabajos.correr("Búsqueda web", operar())


# ──────────────────────────────────────────────────────── contenido generado

TipoContenido = Literal[
    "informe", "resumen_audio", "mapa_mental", "tabla_datos", "presentacion",
    "cuestionario", "tarjetas", "infografia", "video",
]
NOMBRES_TIPO = {
    "informe": "informe", "resumen_audio": "resumen en audio", "mapa_mental": "mapa mental",
    "tabla_datos": "tabla de datos", "presentacion": "presentación", "cuestionario": "cuestionario",
    "tarjetas": "tarjetas de estudio", "infografia": "infografía", "video": "video",
}
# Los que suelen estar en menos de un minuto: se esperan y se entregan de una vez.
RAPIDOS = {"informe", "tabla_datos", "cuestionario", "tarjetas"}


@herramienta("Generar contenido con NotebookLM (informe, audio, mapa, tabla…)", lectura=False)
async def generar(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno.")],
    tipo: Annotated[
        TipoContenido,
        Field(description="informe (texto), resumen_audio (podcast), mapa_mental, tabla_datos (comparativa "
              "en CSV), presentacion (PowerPoint), cuestionario, tarjetas, infografia, video."),
    ],
    instrucciones: Annotated[
        str | None,
        Field(description="Qué enfatizar o cómo hacerlo. En tabla_datos, qué columnas y filas. En informe "
              "'personalizado', es el encargo completo."),
    ] = None,
    fuente_ids: Annotated[list[str] | None, Field(description="Usar sólo estas fuentes (opcional).")] = None,
    idioma: Annotated[str, Field(description="Idioma de salida (es_419 = español latinoamericano).")] = "es_419",
    formato_informe: Annotated[
        Literal["resumen_ejecutivo", "guia_estudio", "explicacion", "personalizado"],
        Field(description="Sólo para tipo=informe."),
    ] = "resumen_ejecutivo",
    formato_audio: Annotated[
        Literal["conversacion", "breve", "critica", "debate"],
        Field(description="Sólo para resumen_audio. 'debate' enfrenta dos posturas: útil para preparar alegatos."),
    ] = "conversacion",
    duracion_audio: Annotated[Literal["corta", "normal", "larga"], Field(description="Sólo para resumen_audio.")] = "normal",
) -> str:
    """Encarga a NotebookLM un contenido basado en las fuentes del cuaderno.

    Informe, tabla de datos, cuestionario y tarjetas suelen estar en menos de un minuto y se
    devuelven aquí mismo. Audio, video, presentación e infografía tardan varios minutos: se
    devuelve un id y se recogen después con `obtener_contenido`.
    """
    import notebooklm as nlm

    if tipo == "informe" and formato_informe == "personalizado" and not instrucciones:
        raise ToolError("Un informe 'personalizado' necesita el encargo en `instrucciones`.")
    cliente = await conexion.cliente()
    art = cliente.artifacts

    if tipo == "mapa_mental":
        async def mapa() -> str:
            resultado = await cliente.mind_maps.generate(
                cuaderno_id, fuente_ids, kind=nlm.MindMapKind.NOTE_BACKED, language=idioma,
                instructions=instrucciones, wait=True,
            )
            arbol = resultado.tree or await cliente.mind_maps.get_tree(cuaderno_id, resultado.id)
            destino = libre(await carpeta_cuaderno(cliente, cuaderno_id) / f"{formato.nombre_archivo(resultado.title or 'mapa-mental')}.json")
            destino.write_text(json.dumps(arbol, ensure_ascii=False, indent=2), encoding="utf-8")
            return f"Mapa mental «{resultado.title}» (guardado en {destino}):\n\n{formato.arbol(arbol)}"

        return await trabajos.correr("Mapa mental", mapa())

    async def encargar() -> Any:
        if tipo == "informe":
            formatos = {
                "resumen_ejecutivo": nlm.ReportFormat.BRIEFING_DOC,
                "guia_estudio": nlm.ReportFormat.STUDY_GUIDE,
                "explicacion": nlm.ReportFormat.CONCEPT_EXPLANATION,
                "personalizado": nlm.ReportFormat.CUSTOM,
            }
            personalizado = formato_informe == "personalizado"
            return await art.generate_report(
                cuaderno_id, report_format=formatos[formato_informe], source_ids=fuente_ids, language=idioma,
                custom_prompt=instrucciones if personalizado else None,
                extra_instructions=None if personalizado else instrucciones,
            )
        if tipo == "resumen_audio":
            formatos_audio = {
                "conversacion": nlm.AudioFormat.DEEP_DIVE, "breve": nlm.AudioFormat.BRIEF,
                "critica": nlm.AudioFormat.CRITIQUE, "debate": nlm.AudioFormat.DEBATE,
            }
            duraciones = {"corta": nlm.AudioLength.SHORT, "normal": nlm.AudioLength.DEFAULT, "larga": nlm.AudioLength.LONG}
            return await art.generate_audio(
                cuaderno_id, source_ids=fuente_ids, language=idioma, instructions=instrucciones,
                audio_format=formatos_audio[formato_audio], audio_length=duraciones[duracion_audio],
            )
        if tipo == "tabla_datos":
            return await art.generate_data_table(cuaderno_id, source_ids=fuente_ids, language=idioma, instructions=instrucciones)
        if tipo == "presentacion":
            return await art.generate_slide_deck(cuaderno_id, source_ids=fuente_ids, language=idioma, instructions=instrucciones)
        if tipo == "cuestionario":
            return await art.generate_quiz(cuaderno_id, source_ids=fuente_ids, instructions=instrucciones)
        if tipo == "tarjetas":
            return await art.generate_flashcards(cuaderno_id, source_ids=fuente_ids, instructions=instrucciones)
        if tipo == "infografia":
            return await art.generate_infographic(cuaderno_id, source_ids=fuente_ids, language=idioma, instructions=instrucciones)
        return await art.generate_video(cuaderno_id, source_ids=fuente_ids, language=idioma, instructions=instrucciones)

    async def operar() -> str:
        inicio = time.monotonic()
        estado = await encargar()
        if estado.is_failed:
            raise ToolError(f"NotebookLM no aceptó el encargo: {estado.error or 'sin detalle'}. "
                            "Si habla de límites o cuota, hay que esperar.")
        contenido_id = estado.task_id
        if tipo in RAPIDOS:
            limite = inicio + ESPERA - 8
            while time.monotonic() < limite:
                await dormir(4)
                estado = await art.poll_status(cuaderno_id, contenido_id)
                if estado.is_complete:
                    return await entregar(cliente, cuaderno_id, await art.get(cuaderno_id, contenido_id))
                if estado.is_failed:
                    raise ToolError(f"NotebookLM no pudo generar el {NOMBRES_TIPO[tipo]}: {estado.error or 'sin detalle'}")
        espera = "unos minutos" if tipo in RAPIDOS else "varios minutos (audio y video pueden tardar 5 a 15)"
        return (
            f"Encargado: {NOMBRES_TIPO[tipo]} · contenido_id: {contenido_id}\n"
            f"Estará en {espera}. Recógelo con obtener_contenido(cuaderno_id, contenido_id=\"{contenido_id}\"). "
            "También aparece en el panel Studio del cuaderno en NotebookLM."
        )

    return await trabajos.correr(f"Encargo de {NOMBRES_TIPO[tipo]}", operar())


@herramienta("Ver o descargar contenido generado por NotebookLM", lectura=False)
async def obtener_contenido(
    cuaderno_id: Annotated[str, Field(description="Id del cuaderno.")],
    contenido_id: Annotated[
        str | None, Field(description="Id del contenido. Sin id, lista todo lo generado en el cuaderno.")
    ] = None,
    formato_presentacion: Annotated[
        Literal["pptx", "pdf"], Field(description="Sólo para presentaciones.")
    ] = "pptx",
) -> str:
    """Lista el contenido generado de un cuaderno o, con un id, lo descarga a este computador.

    Informes, tablas, cuestionarios, tarjetas y mapas mentales además se devuelven como
    texto para que puedas trabajarlos. Los archivos quedan en Documentos/notcd.
    """
    cliente = await conexion.cliente()
    if not contenido_id:
        return formato.contenidos(await cliente.artifacts.list(cuaderno_id))
    artefacto = await cliente.artifacts.get(cuaderno_id, contenido_id)
    if artefacto.is_failed:
        return "Ese contenido falló en NotebookLM. Se puede volver a encargar con `generar`."
    if not artefacto.is_completed:
        return "Todavía está en preparación. Vuelve a consultar en unos minutos."
    return await trabajos.correr(
        "Descarga de contenido", entregar(cliente, cuaderno_id, artefacto, formato_presentacion=formato_presentacion)
    )


async def carpeta_cuaderno(cliente: Any, cuaderno_id: str) -> Path:
    carpeta = rutas.carpeta_descargas() / formato.nombre_archivo(await nombre_cuaderno(cliente, cuaderno_id))
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def libre(ruta: Path) -> Path:
    """La misma ruta, o con -2, -3… si ya existe un archivo con ese nombre."""
    if not ruta.exists():
        return ruta
    n = 2
    while (candidata := ruta.with_name(f"{ruta.stem}-{n}{ruta.suffix}")).exists():
        n += 1
    return candidata


async def entregar(cliente: Any, cuaderno_id: str, artefacto: Any, *, formato_presentacion: str = "pptx") -> str:
    """Descarga un contenido listo y, si es texto, lo devuelve también en la respuesta."""
    art = cliente.artifacts
    tipo = formato.nombre(artefacto.kind)
    titulo = artefacto.title or formato.TIPOS_CONTENIDO.get(tipo, "contenido")
    base = await carpeta_cuaderno(cliente, cuaderno_id) / formato.nombre_archivo(titulo)
    i = artefacto.id

    if tipo == "REPORT":
        ruta = await art.download_report(cuaderno_id, str(libre(base.with_suffix(".md"))), i)
    elif tipo == "DATA_TABLE":
        ruta = await art.download_data_table(cuaderno_id, str(libre(base.with_suffix(".csv"))), i)
    elif tipo == "QUIZ":
        ruta = await art.download_quiz(cuaderno_id, str(libre(base.with_suffix(".md"))), i, output_format="markdown")
    elif tipo == "FLASHCARDS":
        ruta = await art.download_flashcards(cuaderno_id, str(libre(base.with_suffix(".md"))), i, output_format="markdown")
    elif tipo == "MIND_MAP":
        ruta = await art.download_mind_map(cuaderno_id, str(libre(base.with_suffix(".json"))), i)
        arbol = json.loads(Path(ruta).read_text(encoding="utf-8"))
        return f"Mapa mental «{titulo}» (guardado en {ruta}):\n\n{formato.arbol(arbol)}"
    elif tipo == "AUDIO":
        ruta = await art.download_audio(cuaderno_id, str(libre(base.with_suffix(".m4a"))), i)
    elif tipo == "VIDEO":
        ruta = await art.download_video(cuaderno_id, str(libre(base.with_suffix(".mp4"))), i)
    elif tipo == "INFOGRAPHIC":
        ruta = await art.download_infographic(cuaderno_id, str(libre(base.with_suffix(".png"))), i)
    elif tipo == "SLIDE_DECK":
        sufijo = "." + formato_presentacion
        ruta = await art.download_slide_deck(
            cuaderno_id, str(libre(base.with_suffix(sufijo))), i, output_format=formato_presentacion
        )
    else:
        return f"«{titulo}» está listo, pero este tipo ({tipo}) no se puede descargar desde notcd. Ábrelo en NotebookLM."

    if tipo in {"REPORT", "DATA_TABLE", "QUIZ", "FLASHCARDS"}:
        contenido = Path(ruta).read_text(encoding="utf-8-sig", errors="replace")
        return (
            f"{formato.TIPOS_CONTENIDO.get(tipo, tipo)} «{titulo}» generado por NotebookLM "
            f"(guardado en {ruta}):\n\n{formato.recortar(contenido, 40000)}"
        )
    return f"{formato.TIPOS_CONTENIDO.get(tipo, tipo).capitalize()} «{titulo}» descargado en: {ruta}"


# ──────────────────────────────────────────────────────── trabajos y método


@herramienta("Ver el resultado de un trabajo en segundo plano", lectura=True)
async def ver_trabajo(
    trabajo_id: Annotated[
        str | None, Field(description="El trabajo_id que devolvió otra herramienta. Sin id, lista los trabajos.")
    ] = None,
) -> str:
    """Devuelve el resultado de una operación que siguió en segundo plano (o dice que aún sigue)."""
    return await trabajos.ver(trabajo_id, explicacion)


MODOS_GUIA = Literal["general", "expediente", "contratos", "audiencia", "escritos", "investigacion", "equipo"]


@herramienta("Guía de método para trabajar con NotebookLM", lectura=True)
async def guia_de_metodo(
    modo: Annotated[
        MODOS_GUIA,
        Field(description="general (reglas y herramientas), expediente, contratos, audiencia, escritos "
              "(redactar o revisar con citas verificadas), investigacion, equipo (compartir, notas, confidencialidad)."),
    ] = "general",
) -> str:
    """Devuelve la guía de trabajo de notcd para un tipo de tarea: pasos, preguntas que rinden y verificación.

    Léela antes de un trabajo de varios pasos, salvo que la skill notcd ya esté cargada.
    """
    carpeta = rutas.skill_empaquetada()
    archivo = carpeta / "SKILL.md" if modo == "general" else carpeta / "referencias" / f"{modo}.md"
    try:
        texto = archivo.read_text(encoding="utf-8")
    except OSError:
        raise ToolError(f"No encontré la guía «{modo}» en {carpeta}. Reinstala notcd.")
    if texto.startswith("---"):
        texto = texto.split("---", 2)[2].lstrip()  # sin el encabezado de la skill
    return texto


@herramienta("Actualizar la conexión con NotebookLM", lectura=False)
async def actualizar_conexion() -> str:
    """Instala la última corrección de la conexión con NotebookLM (notebooklm-py).

    Úsala cuando `estado_conexion` avise que hay una corrección, o cuando operaciones que
    antes funcionaban fallan con errores raros (Google cambió algo). Después hay que
    reiniciar la app.
    """
    _, mensaje = await actualizacion.aplicar()
    return mensaje


# ───────────────────────────────────────────────────────────────── plantillas


@mcp.prompt(
    name="analizar_expediente",
    title="Analizar un expediente con NotebookLM",
    description="Sube un expediente o ebook a NotebookLM, lo lee con preguntas en serie y entrega un análisis con citas verificadas.",
)
def plantilla_expediente(carpeta: str, causa: str = "") -> str:
    return (
        "Analiza un expediente usando notcd, con NotebookLM como lector. Primero lee la guía con "
        "guia_de_metodo(modo=\"expediente\") y síguela.\n\n"
        f"Archivo o carpeta del expediente en este computador: {carpeta}\n"
        f"Causa: {causa or '(identifícala desde los documentos)'}\n\n"
        "Si ya existe un cuaderno para esta causa, úsalo en vez de crear otro. Entrega: identificación, "
        "cronología con fojas, lo que pide cada parte, prueba, plazos que corren (con la norma traída de "
        "fuente oficial), puntos débiles de cada lado y próximos pasos. Cada hecho con su cita y las citas "
        "textuales verificadas con verificar_citas. Ofrece guardar la minuta en el cuaderno."
    )


@mcp.prompt(
    name="revisar_contratos",
    title="Revisar o comparar contratos con NotebookLM",
    description="Sube contratos a NotebookLM, arma una tabla comparativa y entrega riesgos y desviaciones con respaldo.",
)
def plantilla_contratos(carpeta: str, que_revisar: str = "") -> str:
    return (
        "Revisa contratos usando notcd. Primero lee la guía con guia_de_metodo(modo=\"contratos\") y síguela.\n\n"
        f"Archivo o carpeta con los contratos en este computador: {carpeta}\n"
        f"Qué revisar o comparar: {que_revisar or 'cláusulas esenciales, riesgos y desviaciones del estándar'}\n\n"
        "Arma la tabla comparativa, verifica las celdas que importan con buscar_pasajes, y entrega riesgos "
        "priorizados y cambios propuestos. Ofrece la tabla en CSV y guardar el informe en el cuaderno."
    )


@mcp.prompt(
    name="preparar_audiencia",
    title="Preparar una audiencia o un alegato",
    description="Con el cuaderno de la causa: argumentos de cada lado, preguntas difíciles, minuta y audio de repaso.",
)
def plantilla_audiencia(cuaderno: str, audiencia: str) -> str:
    return (
        "Prepara una audiencia usando notcd. Primero lee la guía con guia_de_metodo(modo=\"audiencia\") y síguela.\n\n"
        f"Cuaderno de la causa (nombre o id): {cuaderno}\n"
        f"Audiencia o alegato a preparar: {audiencia}\n\n"
        "Entrega la minuta con argumentos, respaldo verificado y respuestas a las objeciones previsibles. "
        "Ofrece encargar un resumen en audio tipo debate para repasar."
    )


@mcp.prompt(
    name="verificar_escrito",
    title="Verificar las citas y hechos de un escrito",
    description="Revisa un borrador contra el expediente: citas literales, hechos que constan y flancos abiertos.",
)
def plantilla_escrito(cuaderno: str, escrito: str) -> str:
    return (
        "Revisa este escrito contra los documentos del cuaderno usando notcd. Primero lee la guía con "
        "guia_de_metodo(modo=\"escritos\") y síguela.\n\n"
        f"Cuaderno con los documentos (nombre o id): {cuaderno}\n\n"
        f"Escrito a revisar:\n{escrito}\n\n"
        "Verifica todas las citas textuales con verificar_citas y los hechos con buscar_pasajes. Entrega: citas a "
        "corregir con el texto real, hechos que no constan o constan distinto, y los flancos que deja abiertos."
    )


def main() -> None:
    rutas.migrar_version_anterior()
    registro.configurar()
    log.info("servidor iniciado (notcd %s)", __version__)
    mcp.run("stdio")
