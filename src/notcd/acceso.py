"""Deja iniciada la sesión de Google en el perfil de navegador de notcd.

notebooklm-py 0.8.4 abre NotebookLM y, si cree ver una sesión iniciada, captura
las cookies. Desde el cambio de marca, sin sesión Google muestra una portada
pública en vez del formulario, y la librería la toma por una sesión iniciada:
cierra la ventana a los pocos segundos y guarda cookies inútiles
(teng-lin/notebooklm-py#2467). Por eso notcd abre primero el formulario de
Google en ese mismo perfil y espera a que la persona entre; después la librería
encuentra la sesión de verdad y la captura bien. Cuando ya hay sesión, esto no
muestra nada y termina al instante.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

FORMULARIO = "https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fnotebooklm.google.com%2F&hl=es-419"
HOSTS_NOTEBOOKLM = {"notebooklm.google.com", "notebook.google.com"}
CANALES = {"chrome": "chrome", "edge": "msedge"}

# Los mismos ajustes con que notebooklm-py abre su navegador: que Google no lo
# trate como automatizado y que el perfil sea legible sin el llavero de macOS.
ARGUMENTOS = ["--disable-blink-features=AutomationControlled", "--password-store=basic"]


class SinNavegador(Exception):
    """No se pudo abrir el navegador pedido."""


def perfil_navegador() -> Path:
    from notebooklm.paths import get_browser_profile_dir

    return Path(get_browser_profile_dir())


def hay_sesion(contexto) -> bool:
    nombres = {c["name"] for c in contexto.cookies("https://accounts.google.com")}
    return {"SID", "__Secure-1PSIDTS"} <= nombres


def en_notebooklm(contexto) -> bool:
    return any(urlparse(p.url).hostname in HOSTS_NOTEBOOKLM for p in contexto.pages)


def instalar_chromium() -> None:
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


def abrir(p, navegador: str):
    perfil = perfil_navegador()
    perfil.mkdir(parents=True, exist_ok=True)
    opciones = {
        "user_data_dir": str(perfil),
        "headless": False,
        "args": ARGUMENTOS,
        "ignore_default_args": ["--enable-automation"],
        "no_viewport": True,
    }
    if navegador in CANALES:
        opciones["channel"] = CANALES[navegador]
    try:
        return p.chromium.launch_persistent_context(**opciones)
    except Exception as error:
        if navegador == "chromium" and "Executable doesn't exist" in str(error):
            print("    Descargando el navegador para iniciar sesión (sólo la primera vez)…", flush=True)
            try:
                instalar_chromium()
                return p.chromium.launch_persistent_context(**opciones)
            except Exception as descarga:
                # Redes de oficina que bloquean la descarga: se sigue con Chrome si está instalado.
                raise SinNavegador(f"no se pudo descargar el navegador ({descarga})") from descarga
        raise SinNavegador(str(error).splitlines()[0]) from error


def asegurar_sesion(navegador: str = "chromium", espera: float = 600) -> bool:
    """Abre el formulario de Google si hace falta y espera a que la persona entre.

    Devuelve True cuando el perfil queda con sesión, False si se cerró la ventana
    o se acabó el tiempo.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        contexto = abrir(p, navegador)
        try:
            if hay_sesion(contexto):
                return True
            pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
            pagina.goto(FORMULARIO, wait_until="commit", timeout=60000)
            limite = time.monotonic() + espera
            while time.monotonic() < limite:
                if not contexto.pages:
                    return False  # la persona cerró la ventana
                if hay_sesion(contexto) and en_notebooklm(contexto):
                    time.sleep(2)  # que Google termine de escribir las cookies
                    return True
                time.sleep(1)
            return False
        finally:
            try:
                contexto.close()
            except Exception:
                pass
