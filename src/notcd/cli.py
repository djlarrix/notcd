"""El comando `notcd`: iniciar sesión, registrar en las apps del asistente, actualizar y desinstalar."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from notcd import INICIO, __version__, entorno_login, nombres, rutas

NOMBRE = "notcd"
RESPALDO = ".bak-notcd"

VERDE, AMARILLO, ROJO, TENUE, FUERTE, FIN = (
    ("\033[32m", "\033[33m", "\033[31m", "\033[90m", "\033[1m", "\033[0m")
    if sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    else ("",) * 6
)


def ok(texto: str) -> None:
    print(f"  {VERDE}✓{FIN} {texto}")


def aviso(texto: str) -> None:
    print(f"  {AMARILLO}!{FIN} {texto}")


def mal(texto: str) -> None:
    print(f"  {ROJO}✗{FIN} {texto}")


def nota(texto: str) -> None:
    print(f"    {TENUE}{texto}{FIN}")


# ────────────────────────────────────────────────────────────────── servidor


def servidor(_: argparse.Namespace) -> int:
    from notcd.server import main

    main()
    return 0


# ─────────────────────────────────────────────────────────────────── sesión


def login(args: argparse.Namespace) -> int:
    print(f"\n{FUERTE}Inicio de sesión en Google para NotebookLM{FIN}", flush=True)
    if args.cookies:
        nota(f"Leyendo la sesión de Google que ya tienes abierta en {args.cookies}.")
        if sys.platform == "darwin":
            nota("macOS puede pedir tu contraseña para el «llavero»: es normal (elige «Permitir siempre»).")
        if not capturar(["--browser-cookies", args.cookies]):
            return 1
        return estado(args)

    from notcd.conexion import hay_playwright

    if not hay_playwright():
        return login_navegador_instalado(args)

    from notcd import acceso

    if args.chrome:
        navegadores = ["chrome"]
    elif args.edge:
        navegadores = ["edge"]
    else:
        # El Chromium que trae Playwright falla en algunos macOS recientes; el Chrome
        # instalado sirve de respaldo.
        navegadores = ["chromium", "chrome"] if chrome_instalado() else ["chromium"]

    for i, navegador in enumerate(navegadores):
        if i:
            aviso(f"Reintentando con {NOMBRES_NAVEGADOR[navegador]}…")
        nota(f"Se abre una ventana de {NOMBRES_NAVEGADOR[navegador]}. Entra con la cuenta de Google que usas en NotebookLM.")
        nota("Cuando veas NotebookLM, la ventana se cierra sola. Tienes hasta 10 minutos.")
        try:
            listo = acceso.asegurar_sesion(navegador, espera=args.espera)
        except acceso.SinNavegador as error:
            aviso(f"No se pudo abrir {NOMBRES_NAVEGADOR[navegador]}: {error}")
            continue
        if not listo:
            mal("No se completó el inicio de sesión (se cerró la ventana o se acabó el tiempo).")
            nota("Vuelve a intentarlo con:  notcd login")
            return 1
        canal = [] if navegador == "chromium" else ["--browser", acceso.CANALES[navegador]]
        if capturar(canal):
            return estado(args)
    mal("No se pudo guardar la sesión de Google.")
    nota("Prueba con la sesión que ya tienes abierta en Chrome:  notcd login --cookies chrome")
    return 1


NOMBRES_NAVEGADOR = {"chromium": "navegador", "chrome": "Google Chrome", "edge": "Microsoft Edge"}


def login_navegador_instalado(args: argparse.Namespace) -> int:
    """Windows: inicio de sesión con el Chrome o el Edge instalados (firmados), sin Playwright."""
    from notcd import navegador

    pedido = "chrome" if args.chrome else "edge" if args.edge else None
    candidatos = navegador.disponibles(pedido)
    if not candidatos:
        mal(f"No encontré {NOMBRES_NAVEGADOR[pedido]}." if pedido else "No encontré Google Chrome ni Microsoft Edge.")
        nota("Instala Google Chrome (google.com/chrome) y vuelve a intentarlo con:  notcd login")
        return 1
    for i, (nombre, ejecutable) in enumerate(candidatos):
        if i:
            aviso(f"Reintentando con {NOMBRES_NAVEGADOR[nombre]}…")
        nota(f"Se abre una ventana de {NOMBRES_NAVEGADOR[nombre]}. Entra con la cuenta de Google que usas en NotebookLM.")
        nota("Cuando veas NotebookLM, la ventana se cierra sola. Tienes hasta 10 minutos.")
        try:
            listo = navegador.iniciar_sesion(ejecutable, espera=args.espera)
        except navegador.SinNavegador as error:
            aviso(f"No se pudo abrir {NOMBRES_NAVEGADOR[nombre]}: {error}")
            continue
        if not listo:
            mal("No se completó el inicio de sesión (se cerró la ventana o se acabó el tiempo).")
            nota("Vuelve a intentarlo con:  notcd login")
            return 1
        ok("Sesión de Google guardada")
        return estado(args)
    mal("No se pudo abrir el navegador para iniciar sesión.")
    nota("Si hay una ventana de inicio de sesión de notcd abierta, ciérrala y vuelve a intentarlo con:  notcd login")
    return 1


def capturar(opciones: list[str]) -> bool:
    """Guarda la sesión con notebooklm-py. Su salida (en inglés y técnica) sólo se muestra si falla."""
    resultado = subprocess.run(
        [sys.executable, "-m", "notebooklm", "login", *opciones],
        env=entorno_login(), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if resultado.returncode == 0 and rutas.sesion_completa():
        ok("Sesión de Google guardada")
        return True
    mal("La sesión no quedó completa.")
    for linea in (resultado.stdout + resultado.stderr).strip().splitlines()[-12:]:
        nota(linea)
    return False


def chrome_instalado() -> bool:
    if sys.platform == "darwin":
        return Path("/Applications/Google Chrome.app").exists() or (
            Path.home() / "Applications" / "Google Chrome.app"
        ).exists()
    if sys.platform == "win32":
        bases = [os.environ.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        return any(Path(b, "Google", "Chrome", "Application", "chrome.exe").exists() for b in bases if b)
    return shutil.which("google-chrome") is not None


def estado(_: argparse.Namespace) -> int:
    from notcd.conexion import explicar
    from notcd.server import conexion, estado_conexion

    async def revisar() -> str:
        try:
            return await estado_conexion()
        finally:
            await conexion.cerrar()

    try:
        texto = asyncio.run(revisar())
    except Exception as error:
        mal(explicar(error)[0])
        return 1
    conectado = texto.startswith("Conectado")
    (ok if conectado else aviso)(texto.splitlines()[0])
    for linea in texto.splitlines()[1:]:
        nota(linea)
    return 0 if conectado else 1


# ──────────────────────────────────────────────── registro en las apps


def entrada_servidor() -> dict:
    # El python del entorno de notcd, con ruta absoluta: la app de escritorio no hereda
    # el PATH de la terminal, así que un comando suelto no lo encontraría.
    return {"command": sys.executable, "args": ["-m", NOMBRE, "servidor"], "env": {}}


# Cada proceso con el ejecutable de la app en la sesión de Windows de este usuario, con su
# línea de comandos. Otros usuarios del mismo PC (Escritorio remoto, cambio rápido de
# usuario) no cuentan.
PS_PROCESOS = (
    "$s = (Get-Process -Id $PID).SessionId; "
    f"Get-CimInstance Win32_Process | Where-Object {{ $_.Name -eq '{nombres.EJECUTABLE_WINDOWS}' -and $_.SessionId -eq $s }} | "
    "ForEach-Object { [string]$_.ExecutablePath + [char]9 + [string]$_.CommandLine }"
)


def es_app_codigo(ruta: str) -> bool:
    """La app de código (versión de terminal) usa el mismo nombre de ejecutable en Windows, y no
    reescribe la configuración de la app de escritorio: no hay que esperarla."""
    r = ruta.lower().replace("/", "\\")
    return any(m in r for m in nombres.RUTAS_APP_CODIGO)


def que_es(ruta: str, comando: str) -> str:
    """Clasifica un proceso de la app. Sólo «principal» es la app de escritorio abierta de verdad.

    La app de escritorio (Electron) lanza ayudantes con su mismo ejecutable, que se
    distinguen por «--type=…» en la línea de comandos. Uno de ellos, el que reporta fallas
    (--type=crashpad-handler), sigue vivo después de cerrar la app: contarlo hacía creer que
    seguía abierta. Tampoco cuentan el puente de la extensión de Chrome ni las
    instalaciones y actualizaciones (--squirrel-…).
    """
    c = (comando or "").lower()
    if es_app_codigo(ruta):
        return "app de código"
    if "--type=" in c:
        return "ayudante de la app de escritorio (" + c.split("--type=", 1)[1].split()[0] + ")"
    if "chrome-extension://" in c or "native-host" in c or "--parent-window" in c:
        return "puente de la extensión de Chrome"
    if "--squirrel" in c:
        return "instalador o actualizador de la app"
    if not ruta and not c:
        return "sin información (de otro usuario o con permisos de administrador)"
    return "principal"


def procesos_app_windows() -> list[tuple[str, str]]:
    """(ruta, línea de comandos) de cada proceso de la app en esta sesión de Windows."""
    import base64

    # -EncodedCommand evita cualquier problema de comillas al pasarle el script a PowerShell.
    codificado = base64.b64encode(PS_PROCESOS.encode("utf-16-le")).decode("ascii")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", codificado],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    procesos = []
    for linea in r.stdout.splitlines():
        if linea.strip():
            ruta, _, comando = linea.partition("\t")
            procesos.append((ruta.strip(), comando.strip()))
    return procesos


def procesos_app_escritorio() -> list[str]:
    """La app de escritorio abierta por este usuario: sólo su proceso principal (la ruta, para mostrarla)."""
    try:
        if sys.platform == "win32":
            principales = {ruta or nombres.EJECUTABLE_WINDOWS for ruta, comando in procesos_app_windows() if que_es(ruta, comando) == "principal"}
            return sorted(principales)
        if sys.platform == "darwin":
            # En Mac sólo el proceso principal lleva el nombre exacto; sus ayudantes, «… Helper».
            r = subprocess.run(["pgrep", "-x", nombres.PROCESO_MAC], capture_output=True)
            return ["app de escritorio"] if r.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        pass
    return []


def app_escritorio_abierta() -> bool:
    if os.environ.get("NOTCD_IGNORAR_APP_ABIERTA") == "1":
        return False
    return bool(procesos_app_escritorio())


def como_cerrar_app() -> str:
    if sys.platform == "darwin":
        return "Command + Q (cerrar la ventana no basta)"
    return ("en la barra de tareas, junto al reloj, abre la flechita ^, clic derecho en el ícono de "
            "la app → Salir (cerrar la ventana no basta: la app sigue corriendo ahí)")


def revelar(ruta: Path) -> None:
    """Muestra el archivo en Finder o en el Explorador, para subirlo sin buscarlo."""
    if os.environ.get("CI"):
        return
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(ruta)], capture_output=True, timeout=10)
        elif sys.platform == "win32":
            subprocess.run(["explorer", f"/select,{ruta}"], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def escribir_registro(ruta: Path, etiqueta: str, *, quitar: bool = False, crear: bool = False) -> bool:
    """Agrega (o quita) notcd de un archivo de configuración de las apps sin tocar lo demás."""
    if not ruta.exists():
        if quitar:
            return True
        if not crear:
            aviso(f"{etiqueta}: no está instalado (no existe {ruta})")
            return True
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("{}", encoding="utf-8")
    crudo = ruta.read_text(encoding="utf-8")
    try:
        config = json.loads(crudo or "{}")
    except ValueError:
        mal(f"{etiqueta}: su configuración no es JSON válido; no la toco ({ruta})")
        return False
    servidores = config.setdefault("mcpServers", {})
    anterior = servidores.pop(nombres.ANTERIOR, None) is not None  # registro de la versión anterior
    if quitar:
        if NOMBRE not in servidores and not anterior:
            return True
        servidores.pop(NOMBRE, None)
    else:
        servidores[NOMBRE] = entrada_servidor()
    shutil.copyfile(ruta, ruta.with_name(ruta.name + RESPALDO))
    temporal = ruta.with_name(ruta.name + ".tmp-notcd")
    temporal.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, ruta)

    despues = json.loads(ruta.read_text(encoding="utf-8"))
    perdidas = [k for k in json.loads(crudo or "{}") if k not in despues]
    if perdidas:
        mal(f"{etiqueta}: se perdieron claves {perdidas}. Restaura {ruta.name}{RESPALDO}")
        return False
    ok(f"{etiqueta}: {'quitado' if quitar else 'registrado'} (respaldo en {ruta.name}{RESPALDO})")
    return True


def instalar_skill() -> Path | None:
    archivos = rutas.archivos_skill()
    origen = rutas.skill_empaquetada()
    if not archivos[0].is_file():
        mal(f"No encontré la skill en {origen}")
        return None
    destino = rutas.skills_app_codigo() / rutas.NOMBRE_SKILL
    for vieja in (destino, *(rutas.skills_app_codigo() / n for n in nombres.SKILLS_ANTERIORES)):
        if vieja.exists():
            shutil.rmtree(vieja)
    for archivo in archivos:
        copia = destino / archivo.relative_to(origen)
        copia.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archivo, copia)
    ok(f"Skill instalada para la app de código en {destino}")

    # La app de escritorio no lee esa carpeta: la skill se sube como ZIP desde Configuración.
    zip_ruta = rutas.carpeta_descargas() / rutas.ZIP_SKILL
    zip_ruta.parent.mkdir(parents=True, exist_ok=True)
    # Los ZIP de versiones anteriores se rechazan al subirlos: se quitan para que nadie los
    # suba por error (sólo los que generó este programa).
    carpetas = {rutas.carpeta_descargas(), rutas.documentos() / nombres.ANTERIOR, Path.home() / nombres.ANTERIOR}
    for carpeta in carpetas:
        for nombre in nombres.ZIPS_SKILL_ANTERIORES:
            viejo = carpeta / nombre
            if viejo.is_file():
                viejo.unlink()
                ok(f"Quitado un archivo de una versión anterior: {viejo.name}")
    with zipfile.ZipFile(zip_ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for archivo in archivos:
            z.write(archivo, Path(rutas.NOMBRE_SKILL) / archivo.relative_to(origen))
    ok(f"Skill para la app de escritorio lista para subir: {zip_ruta}")
    return zip_ruta


ESPERA_CIERRE = 600  # segundos que se espera a que la persona cierre la app de escritorio


def configurar(args: argparse.Namespace) -> int:
    print(f"\n{FUERTE}Registrando notcd en la app de escritorio y en la app de código{FIN}")
    errores = 0
    usa_desktop = not args.sin_desktop
    if rutas.extension_anterior_instalada():
        aviso("La app de escritorio tiene instalada la extensión de una versión anterior.")
        nota("Desinstálala en Configuración → Extensiones (la que no se llama notcd), o se verán herramientas repetidas.")
    if usa_desktop and rutas.extension_desktop_instalada():
        ok("La app de escritorio ya tiene la extensión notcd: no se registra otra vez (quedaría duplicada)")
        args.sin_desktop = True
    if not args.sin_desktop:
        abiertos = procesos_app_escritorio() if os.environ.get("NOTCD_IGNORAR_APP_ABIERTA") != "1" else []
        if abiertos:
            aviso("La app de escritorio está abierta: al cerrarse reescribe su configuración y borraría el registro.")
            for ruta in abiertos[:2]:
                nota(f"(detectado: {ruta})")
            if args.esperar:
                print(f"    {FUERTE}Ciérrala por completo ahora{FIN}: {como_cerrar_app()}. Esperando…", flush=True)
                limite = time.monotonic() + ESPERA_CIERRE
                try:
                    while app_escritorio_abierta() and time.monotonic() < limite:
                        time.sleep(3)
                except KeyboardInterrupt:
                    print()
                    return 1
            if app_escritorio_abierta():
                mal("La app de escritorio sigue abierta: no se registró en ella.")
                nota(f"Ciérrala ({como_cerrar_app()}) y ejecuta:  notcd configurar")
                if sys.platform == "win32":
                    nota("Si estás seguro de que está cerrada, en PowerShell:")
                    nota("  $env:NOTCD_IGNORAR_APP_ABIERTA='1'; notcd configurar")
                errores += 1
            else:
                ok("App de escritorio cerrada")
        if not app_escritorio_abierta():
            errores += not escribir_registro(rutas.config_app_escritorio(), "App de escritorio")
    if not args.sin_code:
        errores += not escribir_registro(rutas.config_app_codigo(), "App de código", crear=True)
    zip_ruta = instalar_skill()
    errores += zip_ruta is None

    print(f"\n{FUERTE}Siguientes pasos{FIN}")
    nota("1. Abre la app de escritorio (o una sesión nueva de la app de código).")
    if zip_ruta:
        nota("2. Opcional, en la app de escritorio: Configuración → Capacidades → Skills → Subir skill →")
        nota(f"   elige  {zip_ruta}")
        nota(f"   (ese archivo, {rutas.ZIP_SKILL}; no el ZIP del repositorio ni uno antiguo)")
        nota(f"   También se descarga de: {rutas.DESCARGA_SKILL}")
        if usa_desktop:
            revelar(zip_ruta)
    nota("3. Pregúntale: «¿Qué cuadernos tengo en NotebookLM?»")
    return 1 if errores else 0


def desinstalar(_: argparse.Namespace) -> int:
    print(f"\n{FUERTE}Quitando notcd de las apps{FIN}")
    if app_escritorio_abierta():
        aviso("La app de escritorio está abierta; ciérrala del todo y repite para quitarlo también de ahí.")
    else:
        escribir_registro(rutas.config_app_escritorio(), "App de escritorio", quitar=True)
    escribir_registro(rutas.config_app_codigo(), "App de código", quitar=True)
    for nombre in (rutas.NOMBRE_SKILL, *nombres.SKILLS_ANTERIORES):
        skill = rutas.skills_app_codigo() / nombre
        if skill.exists():
            shutil.rmtree(skill)
            ok("Skill de la app de código eliminada")
    print()
    nota("Para borrar también el programa:   uv tool uninstall notcd")
    nota(f"Para borrar la sesión de Google:   elimina la carpeta {INICIO}")
    nota("En la app de escritorio, la skill subida se borra desde Configuración → Capacidades.")
    return 0


# ─────────────────────────────────────────────────────────────── actualizar


def actualizar(_: argparse.Namespace) -> int:
    from notcd import actualizacion

    print(f"\n{FUERTE}Actualizando la conexión con NotebookLM{FIN}", flush=True)
    nota("Google cambia NotebookLM sin aviso; las correcciones llegan como versiones nuevas de notebooklm-py.")
    bien, mensaje = actualizacion.aplicar_sincrono()
    (ok if bien else mal)(mensaje)
    return 0 if bien else 1


def control_apps_windows() -> str:
    """Estado del Control inteligente de aplicaciones (bloquea programas sin firma digital)."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CI\Policy") as clave:
            valor, _ = winreg.QueryValueEx(clave, "VerifiedAndReputablePolicyState")
    except OSError:
        return "desactivado o no disponible"
    return {0: "desactivado", 1: "activado", 2: "en evaluación"}.get(valor, f"desconocido ({valor})")


def diagnostico(_: argparse.Namespace) -> int:
    """Todo lo que hace falta para dar soporte, sin datos de clientes."""
    import platform

    import notebooklm

    from notcd import actualizacion, registro

    print(f"\n{FUERTE}Diagnóstico de notcd{FIN}")
    nota(f"notcd {__version__} · notebooklm-py {notebooklm.__version__} · Python {platform.python_version()}")
    nota(f"Sistema: {platform.platform()}")
    nota(f"Instalación: {actualizacion.modo()} ({sys.executable})")
    if sys.platform == "win32":
        nota(f"Control inteligente de aplicaciones de Windows: {control_apps_windows()}")
    nota(f"Carpeta de notcd: {INICIO}")
    nota(f"Descargas: {rutas.carpeta_descargas()}")

    print(f"\n{FUERTE}Sesión de Google{FIN}")
    if not rutas.sesion_google().is_file():
        aviso("Sin sesión: ejecuta  notcd login")
    elif not rutas.sesion_completa():
        aviso("Sesión incompleta: ejecuta  notcd login")
    else:
        ok(f"Sesión guardada ({rutas.cuenta_conectada() or 'cuenta sin correo registrado'})")

    print(f"\n{FUERTE}Registro en las apps{FIN}")
    for etiqueta, ruta in (("App de escritorio", rutas.config_app_escritorio()), ("App de código", rutas.config_app_codigo())):
        try:
            entrada = json.loads(ruta.read_text(encoding="utf-8")).get("mcpServers", {}).get(NOMBRE)
        except (OSError, ValueError):
            entrada = None
        if entrada:
            existe = Path(entrada.get("command", "")).exists()
            (ok if existe else mal)(f"{etiqueta}: registrado{'' if existe else ' pero el programa no existe: ' + entrada.get('command', '')}")
        else:
            nota(f"{etiqueta}: no registrado en {ruta.name} (normal si se instaló como extensión)")
    skill = rutas.skills_app_codigo() / rutas.NOMBRE_SKILL / "SKILL.md"
    nota(f"Skill de la app de código: {'instalada' if skill.is_file() else 'no instalada'}")
    if rutas.extension_anterior_instalada():
        aviso("Sigue instalada la extensión de una versión anterior: desinstálala en Configuración → Extensiones.")

    if sys.platform == "win32":
        print(f"\n{FUERTE}Procesos de la app en esta sesión ({nombres.EJECUTABLE_WINDOWS}){FIN}")
        try:
            procesos = procesos_app_windows()
        except (OSError, subprocess.SubprocessError) as error:
            procesos = []
            nota(f"no se pudieron listar: {error}")
        if not procesos:
            nota("ninguno")
        for ruta, comando in procesos:
            nota(f"{que_es(ruta, comando)}: {ruta or '?'}  {comando[:120]}")
        nota("Sólo «principal» cuenta como app de escritorio abierta.")

    print(f"\n{FUERTE}Conexión{FIN}", flush=True)
    resultado = estado(_)
    lineas = registro.ultimas_lineas(25)
    if lineas:
        print(f"\n{FUERTE}Últimas operaciones (sin contenido){FIN}")
        for linea in lineas:
            nota(linea)
    return resultado


# ───────────────────────────────────────────────────────────────────── main


def utf8() -> None:
    """Salida en UTF-8 aunque vaya a un archivo o a otro programa.

    En Windows, Python escribe con la codificación antigua del sistema cuando la
    salida no es la consola (el instalador, el registro del inicio de sesión), y
    un «✓» o una tilde hacen caer el programa. El servidor MCP no pasa por aquí:
    su salida es el canal con la app y la maneja el SDK.
    """
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure") and (flujo.encoding or "").lower().replace("-", "") != "utf8":
            flujo.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=NOMBRE,
        description="notcd: NotebookLM (Gemini Notebook) para el asistente de IA.",
    )
    parser.add_argument("--version", action="version", version=f"notcd {__version__}")
    sub = parser.add_subparsers(dest="comando", metavar="comando")

    p = sub.add_parser("login", help="iniciar sesión con la cuenta de Google de NotebookLM")
    grupo = p.add_mutually_exclusive_group()
    grupo.add_argument("--chrome", action="store_true", help="usar Google Chrome")
    grupo.add_argument("--edge", action="store_true", help="usar Microsoft Edge")
    grupo.add_argument("--cookies", metavar="NAVEGADOR", help="tomar la sesión ya abierta en chrome, edge, firefox…")
    p.add_argument("--espera", type=float, default=600, help=argparse.SUPPRESS)
    p.set_defaults(fn=login)

    sub.add_parser("estado", help="comprobar la conexión con NotebookLM").set_defaults(fn=estado)

    p = sub.add_parser("configurar", help="registrar notcd en la app de escritorio y la de código, e instalar la skill")
    p.add_argument("--sin-desktop", action="store_true", help="no tocar la app de escritorio")
    p.add_argument("--sin-code", action="store_true", help="no tocar la app de código")
    p.add_argument("--esperar", action="store_true", help="si la app de escritorio está abierta, esperar a que se cierre")
    p.set_defaults(fn=configurar)

    sub.add_parser("actualizar", help="traer la última versión compatible de la conexión con NotebookLM").set_defaults(
        fn=actualizar
    )
    sub.add_parser("diagnostico", help="información para soporte (sin datos de clientes)").set_defaults(fn=diagnostico)
    sub.add_parser("desinstalar", help="quitar notcd de las apps").set_defaults(fn=desinstalar)
    sub.add_parser("servidor", help="(lo usan las apps) iniciar el servidor MCP").set_defaults(fn=servidor)

    args = parser.parse_args(argv)
    if getattr(args, "fn", None) is not servidor:
        utf8()
    rutas.migrar_version_anterior()
    if not getattr(args, "fn", None):
        parser.print_help()
        return 0
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
