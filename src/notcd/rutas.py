"""Dónde vive cada cosa en el computador."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from notcd import INICIO, nombres


def sesion_google() -> Path:
    """El archivo con la sesión de Google que guarda `notcd login`."""
    from notebooklm.paths import get_storage_path

    return Path(get_storage_path())


def cuenta_conectada() -> str | None:
    """Correo de la cuenta de Google conectada, si quedó registrado al iniciar sesión."""
    try:
        datos = json.loads(sesion_google().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cuenta = (datos.get("notebooklm") or {}).get("account") or {}
    return cuenta.get("email")


def sesion_completa() -> bool:
    """Si la sesión guardada tiene las cookies sin las que Google rechaza todo."""
    try:
        datos = json.loads(sesion_google().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    nombres = {c.get("name") for c in datos.get("cookies", []) if isinstance(c, dict)}
    return {"SID", "__Secure-1PSIDTS"} <= nombres


def carpeta_descargas() -> Path:
    """Donde quedan los audios, informes y tablas que genera NotebookLM."""
    otra = os.environ.get("NOTCD_DESCARGAS", "").strip()
    if otra and "${" not in otra:  # en la extensión, un ajuste vacío puede llegar sin reemplazar
        return Path(otra).expanduser()
    return documentos() / "notcd"


def documentos() -> Path:
    """La carpeta Documentos de verdad.

    En Windows suele estar redirigida a OneDrive (C:\\Users\\x\\OneDrive\\Documentos), así
    que se le pregunta a Windows dónde está en vez de suponer C:\\Users\\x\\Documents.
    """
    if sys.platform == "win32":
        if (ruta := documentos_windows()) and ruta.is_dir():
            return ruta
    candidata = Path.home() / "Documents"
    return candidata if candidata.is_dir() else Path.home()


def documentos_windows() -> Path | None:
    import ctypes
    import uuid

    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

    folderid_documents = uuid.UUID("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")
    guid = GUID.from_buffer_copy(folderid_documents.bytes_le)
    ruta = ctypes.c_wchar_p()
    try:
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ruta)) != 0:
            return None
        return Path(ruta.value)
    except (AttributeError, OSError):
        return None
    finally:
        if ruta.value is not None:
            ctypes.windll.ole32.CoTaskMemFree(ruta)


def registro_login() -> Path:
    return INICIO / "login.log"


def config_app_escritorio() -> Path:
    """El archivo de configuración de la app de escritorio, según el sistema.

    En Windows la versión de la Microsoft Store guarda la configuración dentro de
    su paquete y no en %APPDATA%; si existe esa carpeta, es la que manda.
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / nombres.CARPETA_ESCRITORIO / nombres.CONFIG_ESCRITORIO
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        for paquete in sorted((local / "Packages").glob(nombres.PAQUETES_TIENDA)):
            ruta = paquete / "LocalCache" / "Roaming" / nombres.CARPETA_ESCRITORIO
            if ruta.is_dir():
                return ruta / nombres.CONFIG_ESCRITORIO
        roaming = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return roaming / nombres.CARPETA_ESCRITORIO / nombres.CONFIG_ESCRITORIO
    return Path.home() / ".config" / nombres.CARPETA_ESCRITORIO / nombres.CONFIG_ESCRITORIO


def extensiones_app_escritorio() -> list[Path]:
    carpeta = config_app_escritorio().parent / nombres.CARPETA_EXTENSIONES
    try:
        return [c for c in carpeta.iterdir() if c.is_dir()]
    except OSError:
        return []


def extension_desktop_instalada() -> Path | None:
    """La carpeta de la extensión notcd (.mcpb) si está instalada en la app de escritorio."""
    return next((c for c in extensiones_app_escritorio() if c.name.endswith(".notcd")), None)


def extension_anterior_instalada() -> Path | None:
    """La extensión de una versión anterior de este proyecto, si sigue instalada."""
    return next((c for c in extensiones_app_escritorio() if c.name.endswith("." + nombres.ANTERIOR)), None)


def config_app_codigo() -> Path:
    return Path.home() / nombres.CONFIG_CODIGO


def skills_app_codigo() -> Path:
    return Path.home() / nombres.CARPETA_CODIGO / "skills"


# La skill no puede contener la marca de la app en ninguna parte (se rechaza al subirla).
# Se llama «notcd» y la carpeta raíz del ZIP se llama igual.
NOMBRE_SKILL = "notcd"
# El archivo para subir a la app lleva el nombre de la skill, distinto de los de versiones
# anteriores, para que no se confundan.
ZIP_SKILL = f"{NOMBRE_SKILL}.zip"
DESCARGA_SKILL = f"https://github.com/djlarrix/notcd/releases/latest/download/{ZIP_SKILL}"


def skill_empaquetada() -> Path:
    """La carpeta de la skill: dentro del paquete instalado o, en desarrollo, la raíz del repo."""
    dentro = Path(__file__).parent / "skill"
    if (dentro / "SKILL.md").is_file():
        return dentro
    return Path(__file__).resolve().parents[2]


# Rutas que nunca se suben a Google aunque alguien las pida: credenciales.
def es_ruta_prohibida(ruta: Path) -> bool:
    ruta = ruta.resolve()
    casa = Path.home().resolve()
    prohibidas = [INICIO.resolve(), casa / ".ssh", casa / ".gnupg", casa / ".aws", casa / ".notebooklm"]
    if any(ruta == p or p in ruta.parents for p in prohibidas):
        return True
    return ruta.name in {"storage_state.json", "master_token.json", ".env", nombres.CONFIG_ESCRITORIO, nombres.CONFIG_CODIGO}


def archivos_skill() -> list[Path]:
    """Lo que forma la skill: SKILL.md y la carpeta referencias (nada más del repositorio)."""
    carpeta = skill_empaquetada()
    return [carpeta / "SKILL.md", *sorted((carpeta / "referencias").glob("*.md"))]


def migrar_version_anterior() -> None:
    """Pasa a notcd lo que dejó la versión anterior de este proyecto, sin perder nada.

    La sesión de Google se mueve a la carpeta nueva (así no hay que volver a iniciar sesión),
    el resto de la carpeta anterior queda como respaldo dentro de la nueva, y la carpeta de
    descargas (audios, informes, tablas) cambia de nombre si la nueva todavía no existe.
    """
    if os.environ.get("NOTCD_HOME"):
        return  # carpeta personalizada (pruebas): no se toca nada del usuario
    import shutil

    try:
        vieja = Path.home() / f".{nombres.ANTERIOR}"
        if vieja.is_dir():
            INICIO.mkdir(parents=True, exist_ok=True)
            if (vieja / "google").is_dir() and not (INICIO / "google").exists():
                shutil.move(str(vieja / "google"), str(INICIO / "google"))
            if not (INICIO / "version-anterior").exists():
                shutil.move(str(vieja), str(INICIO / "version-anterior"))
        descargas_viejas = documentos() / nombres.ANTERIOR
        if descargas_viejas.is_dir() and not carpeta_descargas().exists():
            shutil.move(str(descargas_viejas), str(carpeta_descargas()))
    except OSError:
        pass
