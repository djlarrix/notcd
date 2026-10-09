import asyncio
from pathlib import Path
from types import SimpleNamespace

import notebooklm as nlm
import pytest

from notcd import nombres, rutas, server
from notcd.protocolo import ErrorHerramienta as ToolError
from notcd.conexion import SESION_INCOMPLETA, SESION_VENCIDA, SIN_SESION, explicar


async def llamar(nombre: str, **argumentos) -> str:
    resultado = await server.mcp.call_tool(nombre, argumentos)
    return "\n".join(c.text for c in resultado.content)


HERRAMIENTAS = {
    "estado_conexion", "iniciar_sesion", "listar_cuadernos", "ver_cuaderno", "crear_cuaderno",
    "configurar_lector", "compartir_cuaderno", "agregar_fuentes", "quitar_fuentes", "preguntar",
    "buscar_pasajes", "leer_fuente", "verificar_citas", "guardar_nota", "buscar_en_web", "generar",
    "obtener_contenido", "ver_trabajo", "guia_de_metodo", "actualizar_conexion",
}


async def test_publica_las_herramientas_esperadas():
    assert {t.name for t in await server.mcp.list_tools()} == HERRAMIENTAS


async def test_marca_lectura_y_destructivas():
    h = {t.name: t for t in await server.mcp.list_tools()}
    assert h["preguntar"].annotations.read_only_hint is True
    assert h["verificar_citas"].annotations.read_only_hint is True
    assert h["agregar_fuentes"].annotations.read_only_hint is False
    assert h["quitar_fuentes"].annotations.destructive_hint is True
    assert h["agregar_fuentes"].annotations.destructive_hint is False


async def test_publica_las_plantillas():
    nombres = {p.name for p in await server.mcp.list_prompts()}
    assert nombres == {"analizar_expediente", "revisar_contratos", "preparar_audiencia", "verificar_escrito"}


# ──────────────────────────────────────────────────────────────── sesión


async def test_sin_sesion_pide_iniciar_sesion():
    assert not rutas.sesion_google().exists()
    assert SIN_SESION in await llamar("estado_conexion")
    with pytest.raises(ToolError, match="iniciar_sesion"):
        await llamar("listar_cuadernos")


async def test_sesion_vencida_se_traduce_y_descarta_el_cliente(monkeypatch):
    descartado = []

    async def falla():
        raise nlm.AuthError("401")

    async def cerrar():
        descartado.append(True)

    monkeypatch.setattr(server.conexion, "cliente", falla)
    monkeypatch.setattr(server.conexion, "cerrar", cerrar)
    with pytest.raises(ToolError) as error:
        await llamar("listar_cuadernos")
    assert SESION_VENCIDA in str(error.value)
    assert descartado


def test_sesion_incompleta_se_explica():
    from notebooklm._auth.cookie_policy import RequiredCookieValidationError

    mensaje, descartar = explicar(RequiredCookieValidationError("Missing required cookies: SID"))
    assert mensaje == SESION_INCOMPLETA and descartar


def test_sesion_completa_exige_las_cookies_de_google():
    sesion = rutas.sesion_google()
    sesion.parent.mkdir(parents=True, exist_ok=True)
    try:
        sesion.write_text('{"cookies": [{"name": "NID"}]}')
        assert not rutas.sesion_completa()
        sesion.write_text('{"cookies": [{"name": "SID"}, {"name": "__Secure-1PSIDTS"}]}')
        assert rutas.sesion_completa()
    finally:
        sesion.unlink()


# ───────────────────────────────────────────────────────────── cuadernos


async def test_crear_cuaderno_lo_configura_como_lector_juridico(falso):
    _, llamadas = falso
    texto = await llamar("crear_cuaderno", titulo="Pérez con Banco · C-1-2025")
    assert "id: nb2" in texto and "lector jurídico" in texto
    _, args, kwargs = next(c for c in llamadas if c[0] == "chat.configure")
    assert args == ("nb2",)
    assert kwargs["goal"] == nlm.ChatGoal.CUSTOM
    assert "no consta en las fuentes" in kwargs["custom_prompt"]


async def test_configurar_lector_puede_quitarse(falso):
    _, llamadas = falso
    await llamar("configurar_lector", cuaderno_id="nb1", quitar=True)
    _, _, kwargs = next(c for c in llamadas if c[0] == "chat.configure")
    assert kwargs["goal"] == nlm.ChatGoal.DEFAULT and kwargs["custom_prompt"] is None


async def test_ver_cuaderno_marca_las_fuentes_en_proceso(falso):
    texto = await llamar("ver_cuaderno", cuaderno_id="nb1")
    assert "«Demanda.pdf» (PDF · 1.200 palabras) · id: f1" in texto
    assert "PROCESANDO" in texto
    assert "Juicio ordinario de cobro." in texto


async def test_compartir_valida_correos(falso):
    _, llamadas = falso
    texto = await llamar(
        "compartir_cuaderno", cuaderno_id="nb1", correos=["ana@estudio.cl", "no-es-correo"], rol="editor"
    )
    _, args, kwargs = next(c for c in llamadas if c[0] == "sharing.add_user")
    assert args == ("nb1", "ana@estudio.cl", nlm.SharePermission.EDITOR)
    assert "Compartido como editor con: ana@estudio.cl" in texto
    assert "no válidos, omitidos: no-es-correo" in texto


# ─────────────────────────────────────────────────────────────── fuentes


async def test_agregar_fuentes_sube_una_carpeta_y_reporta_estados(falso, tmp_path):
    _, llamadas = falso
    (tmp_path / "escritos").mkdir()
    (tmp_path / "escritos" / "replica.pdf").write_bytes(b"%PDF")
    (tmp_path / "escritos" / "notas.txt").write_text("x")
    (tmp_path / "escritos" / "~$borrador.docx").write_text("x")
    (tmp_path / "escritos" / "foto.heic").write_text("x")
    (tmp_path / "viejo.doc").write_text("x")

    texto = await llamar(
        "agregar_fuentes", cuaderno_id="nb1",
        archivos=[str(tmp_path / "escritos"), f'"{tmp_path / "viejo.doc"}"'],
        urls=["https://www.bcn.cl/leychile"],
    )
    subidos = sorted(Path(args[1]).name for nombre, args, _ in llamadas if nombre == "sources.add_file")
    assert subidos == ["notas.txt", "replica.pdf"]
    assert "Agregadas 3 fuente(s)" in texto
    assert "«replica.pdf» · lista" in texto
    assert "«https://www.bcn.cl/leychile» · procesando" in texto
    assert ".doc) no se acepta" in texto


async def test_agregar_fuentes_no_duplica(falso, tmp_path):
    _, llamadas = falso
    (tmp_path / "Demanda.pdf").write_bytes(b"%PDF")
    texto = await llamar("agregar_fuentes", cuaderno_id="nb1", archivos=[str(tmp_path / "Demanda.pdf")])
    assert "ya estaba en el cuaderno" in texto.lower()
    assert not any(c[0] == "sources.add_file" for c in llamadas)


async def test_agregar_fuentes_no_sube_credenciales(falso):
    sesion = rutas.sesion_google()
    sesion.parent.mkdir(parents=True, exist_ok=True)
    sesion.write_text("{}")
    try:
        with pytest.raises(ToolError, match="credenciales"):
            await llamar("agregar_fuentes", cuaderno_id="nb1", archivos=[str(sesion)])
    finally:
        sesion.unlink()


async def test_agregar_fuentes_pone_tope_por_llamada(falso, tmp_path):
    for i in range(server.MAX_ARCHIVOS + 1):
        (tmp_path / f"{i}.pdf").write_bytes(b"%PDF")
    with pytest.raises(ToolError, match="máximo"):
        await llamar("agregar_fuentes", cuaderno_id="nb1", archivos=[str(tmp_path)])


async def test_quitar_fuentes(falso):
    _, llamadas = falso
    texto = await llamar("quitar_fuentes", cuaderno_id="nb1", fuente_ids=["f2", "zzz"])
    assert [c[1] for c in llamadas if c[0] == "sources.delete"] == [("nb1", "f2")]
    assert "«Contestación.pdf»" in texto and "zzz" in texto


# ───────────────────────────────────────────────────── preguntar y verificar


async def test_preguntar_resuelve_cada_cita_con_su_pasaje(falso):
    texto = await llamar("preguntar", cuaderno_id="nb1", pregunta="¿Cuándo se notificó?")
    assert "La demanda se notificó el 3 de marzo [1]." in texto
    assert "[1] «Demanda.pdf» (fuente_id: f1)" in texto
    assert '"notificada con fecha 3 de marzo de 2025"' in texto
    assert "conversacion_id: conv-1" in texto


async def test_respuesta_sin_citas_se_advierte(falso):
    cliente, _ = falso

    async def sin_citas(*_, **__):
        return SimpleNamespace(answer="Creo que sí.", conversation_id="c", references=[], next_steps=[])

    cliente.chat.ask = sin_citas
    assert "SIN CITAS" in await llamar("preguntar", cuaderno_id="nb1", pregunta="¿?")


async def test_pregunta_lenta_sigue_en_segundo_plano(falso, monkeypatch):
    cliente, _ = falso
    liberar = asyncio.Event()
    original = cliente.chat.ask

    async def lenta(*args, **kwargs):
        await liberar.wait()
        return await original(*args, **kwargs)

    cliente.chat.ask = lenta
    monkeypatch.setattr("notcd.trabajos.ESPERA", 0.05)
    texto = await llamar("preguntar", cuaderno_id="nb1", pregunta="¿?")
    assert "segundo plano" in texto
    trabajo_id = texto.split('trabajo_id="')[1].split('"')[0]
    assert "sigue en curso" in await llamar("ver_trabajo", trabajo_id=trabajo_id)
    liberar.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0.01)
    assert "[1] «Demanda.pdf»" in await llamar("ver_trabajo", trabajo_id=trabajo_id)
    assert "No hay un trabajo" in await llamar("ver_trabajo", trabajo_id=trabajo_id)


async def test_error_en_segundo_plano_se_explica(falso, monkeypatch):
    cliente, _ = falso

    async def falla(*_, **__):
        await asyncio.sleep(0.05)
        raise nlm.RateLimitError("429")

    cliente.chat.ask = falla
    monkeypatch.setattr("notcd.trabajos.ESPERA", 0.01)
    texto = await llamar("preguntar", cuaderno_id="nb1", pregunta="¿?")
    trabajo_id = texto.split('trabajo_id="')[1].split('"')[0]
    await asyncio.sleep(0.1)
    assert "limitando las solicitudes" in await llamar("ver_trabajo", trabajo_id=trabajo_id)


async def test_buscar_pasajes_devuelve_texto_original(falso):
    texto = await llamar("buscar_pasajes", cuaderno_id="nb1", consulta="notificación")
    assert '«Demanda.pdf» (fuente_id: f1)\n   "notificada con fecha 3 de marzo"' in texto


async def test_leer_fuente_por_tramos(falso):
    texto = await llamar("leer_fuente", cuaderno_id="nb1", fuente_id="f1", desde=0, largo=1000)
    assert texto.startswith("«Demanda.pdf» (fuente_id: f1) · caracteres 0–")
    assert "fojas 12" in texto and "sigue" not in texto


async def test_verificar_citas_contra_el_texto(falso):
    texto = await llamar(
        "verificar_citas", cuaderno_id="nb1",
        citas=[
            "«notificada con fecha 3 de marzo de 2025 al demandado»",
            '"La demanda fue notificada con fecha 3 de abril de 2025 al demandado en su domicilio"',
            '"el demandado confesó la deuda"',
        ],
    )
    assert "1 literal(es), 1 con diferencias, 1 no encontrada(s)" in texto
    assert "tu cita dice «abril», la fuente dice «marzo»" in texto


async def test_buscar_en_web_no_agrega_nada(falso):
    _, llamadas = falso
    texto = await llamar("buscar_en_web", cuaderno_id="nb1", tema="nulidad del despido")
    assert "https://www.bcn.cl/leychile/x" in texto
    assert not any(c[0].startswith("sources.add") for c in llamadas)


# ──────────────────────────────────────────────────────── contenido generado


async def test_generar_informe_lo_espera_y_lo_entrega(falso):
    _, llamadas = falso
    texto = await llamar("generar", cuaderno_id="nb1", tipo="informe", instrucciones="Enfócate en plazos")
    _, _, kwargs = next(c for c in llamadas if c[0] == "artifacts.generate_report")
    assert kwargs["report_format"] == nlm.ReportFormat.BRIEFING_DOC
    assert kwargs["extra_instructions"] == "Enfócate en plazos"
    assert kwargs["language"] == "es_419"
    assert "# Minuta\nHechos." in texto
    assert (rutas.carpeta_descargas() / "perez-con-banco" / "minuta.md").exists()


async def test_informe_personalizado_exige_encargo(falso):
    with pytest.raises(ToolError, match="instrucciones"):
        await llamar("generar", cuaderno_id="nb1", tipo="informe", formato_informe="personalizado")


async def test_generar_audio_devuelve_id_sin_esperar(falso):
    _, llamadas = falso
    texto = await llamar("generar", cuaderno_id="nb1", tipo="resumen_audio", formato_audio="debate")
    _, _, kwargs = next(c for c in llamadas if c[0] == "artifacts.generate_audio")
    assert kwargs["audio_format"] == nlm.AudioFormat.DEBATE
    assert "contenido_id: a2" in texto
    assert not any(c[0] == "artifacts.poll_status" for c in llamadas)


async def test_obtener_contenido_lista_y_descarga(falso):
    assert "informe: «Minuta» · listo" in await llamar("obtener_contenido", cuaderno_id="nb1")
    texto = await llamar("obtener_contenido", cuaderno_id="nb1", contenido_id="a2")
    assert texto.startswith("Resumen en audio «Minuta» descargado en:")
    assert texto.endswith(".m4a")


# ─────────────────────────────────────────────────────────────────── guías


@pytest.mark.parametrize("modo", ["general", "expediente", "contratos", "audiencia", "escritos", "investigacion", "equipo"])
async def test_guias_disponibles(modo):
    texto = await llamar("guia_de_metodo", modo=modo)
    assert len(texto) > 500 and not texto.startswith("---")


async def test_las_guias_que_cita_la_skill_existen():
    skill = (rutas.skill_empaquetada() / "SKILL.md").read_text(encoding="utf-8")
    for nombre in ["expediente", "contratos", "audiencia", "escritos", "investigacion", "equipo"]:
        assert f"referencias/{nombre}.md" in skill
        assert (rutas.skill_empaquetada() / "referencias" / f"{nombre}.md").is_file()


async def test_las_herramientas_que_nombran_las_guias_existen():
    """Que la skill no mande al asistente a usar herramientas que no existen."""
    citadas = set()
    import re

    for archivo in rutas.archivos_skill():
        citadas |= set(re.findall(r"`([a-z_]+)(?:\(|`)", archivo.read_text(encoding="utf-8")))
    nombres_de_herramienta = {c for c in citadas if "_" in c and not c.startswith(("fuente_", "conversacion_", "titulo_", "formato_", "trabajo_", "lector_"))}
    assert nombres_de_herramienta - HERRAMIENTAS - {"tabla_datos", "resumen_audio", "mapa_mental", "fuente_ids"} == set()


async def test_plantilla_de_expediente_menciona_la_guia():
    resultado = await server.mcp.get_prompt("analizar_expediente", {"carpeta": "/tmp/causa"})
    texto = resultado.messages[0].content.text
    assert "guia_de_metodo(modo=\"expediente\")" in texto and "/tmp/causa" in texto


async def test_agregar_texto_no_duplica(falso):
    _, llamadas = falso
    texto = await llamar("agregar_fuentes", cuaderno_id="nb1", texto="cualquier cosa", titulo_texto="Demanda.pdf")
    assert "ya estaba" in texto.lower()
    assert not any(c[0] == "sources.add_text" for c in llamadas)


def test_cita_larga_muestra_el_tramo_que_respalda_la_frase():
    from notcd.formato import pasaje_relevante

    citado = "Encabezado. " * 100 + "La renta mensual será de 18 UF, pagadera por anticipado. " + "Otra cláusula. " * 100
    frase = "Consta que «La renta mensual será de 18 UF» [2]."
    tramo = pasaje_relevante(citado, frase, 2)
    assert "La renta mensual será de 18 UF" in tramo and tramo.startswith("[…]")
    assert pasaje_relevante(citado, frase, 3).startswith("Encabezado.")


async def test_no_consta_sin_citas_no_se_trata_como_error(falso):
    cliente, _ = falso

    async def no_consta(*_, **__):
        return SimpleNamespace(answer="Respecto de mascotas, **no consta en las fuentes**.", conversation_id="c", references=[], next_steps=[])

    cliente.chat.ask = no_consta
    texto = await llamar("preguntar", cuaderno_id="nb1", pregunta="¿Mascotas?")
    assert "SIN CITAS" not in texto and "confírmalo con buscar_pasajes" in texto


RESERVADAS = (nombres.marca, "anthropic")


def test_el_encabezado_de_la_skill_no_tiene_palabras_reservadas():
    """La app rechaza la subida si el nombre o la descripción contienen su marca."""
    import yaml

    texto = (rutas.skill_empaquetada() / "SKILL.md").read_text(encoding="utf-8")
    encabezado = yaml.safe_load(texto.split("---")[1])
    assert set(encabezado) == {"name", "description"}
    assert encabezado["name"] == rutas.NOMBRE_SKILL == "notcd"
    for campo in ("name", "description"):
        for reservada in RESERVADAS:
            assert reservada not in encabezado[campo].lower(), (campo, reservada)
    assert len(encabezado["description"]) <= 1024
    assert "<" not in encabezado["description"] and ">" not in encabezado["description"]


def test_la_skill_no_contiene_palabras_reservadas_en_ningun_archivo():
    for archivo in rutas.archivos_skill():
        texto = archivo.read_text(encoding="utf-8").lower()
        for reservada in RESERVADAS:
            assert reservada not in texto and reservada not in archivo.name.lower(), (archivo.name, reservada)


def test_el_repositorio_entero_no_contiene_la_marca():
    """Requisito del proyecto: la marca de la app no aparece escrita en ningún archivo ni nombre.

    Los nombres técnicos que la necesitan se arman por partes en notcd/nombres.py.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    ignorar = {".git", ".venv", "build", "dist", "__pycache__", ".pytest_cache", ".ruff_cache"}
    hallazgos = []
    for archivo in raiz.rglob("*"):
        relativo = archivo.relative_to(raiz)
        if any(parte in ignorar for parte in relativo.parts):
            continue
        if nombres.marca in str(relativo).lower():
            hallazgos.append(str(relativo))
        if archivo.is_file():
            try:
                texto = archivo.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue  # binarios (el ícono)
            if nombres.marca in texto.lower():
                hallazgos.append(f"{relativo} (contenido)")
    assert hallazgos == []
