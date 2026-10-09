"""Inicio de sesión con el Chrome o el Edge instalados, sin Playwright.

En Windows con el Control inteligente de aplicaciones, Playwright no sirve: carga
greenlet (compilado, sin firma digital) y descarga un Chromium sin firma, y Windows
bloquea ambos. Chrome y Edge sí están firmados. notcd abre uno de ellos con un
perfil propio y el puerto de depuración local, espera a que la persona entre en
Google y lee las cookies por ese puerto (protocolo DevTools). Todo con la biblioteca
estándar: no hay nada compilado que Windows pueda bloquear.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from notcd import INICIO, rutas

FORMULARIO = "https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fnotebooklm.google.com%2F&hl=es-419"
HOSTS_NOTEBOOKLM = {"notebooklm.google.com", "notebook.google.com"}
NOMBRES = {"chrome": "Google Chrome", "edge": "Microsoft Edge"}


class SinNavegador(Exception):
    """No se pudo abrir el navegador pedido."""


def perfil() -> Path:
    """Perfil de navegador sólo de notcd: no toca el Chrome ni el Edge de la persona."""
    return INICIO / "navegador"


def ejecutables() -> dict[str, list[Path]]:
    if sys.platform == "win32":
        bases = [os.environ.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        return {
            "chrome": [Path(b, "Google", "Chrome", "Application", "chrome.exe") for b in bases if b],
            "edge": [Path(b, "Microsoft", "Edge", "Application", "msedge.exe") for b in bases if b],
        }
    if sys.platform == "darwin":
        apps = [Path("/Applications"), Path.home() / "Applications"]
        return {
            "chrome": [a / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome" for a in apps],
            "edge": [a / "Microsoft Edge.app" / "Contents" / "MacOS" / "Microsoft Edge" for a in apps],
        }
    encontrados = {n: shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium", "microsoft-edge")}
    return {
        "chrome": [Path(r) for n, r in encontrados.items() if r and "edge" not in n],
        "edge": [Path(encontrados["microsoft-edge"])] if encontrados["microsoft-edge"] else [],
    }


def disponibles(pedido: str | None = None) -> list[tuple[str, Path]]:
    """Los navegadores instalados, en orden de preferencia (Chrome primero)."""
    todos = ejecutables()
    orden = [pedido] if pedido else ["chrome", "edge"]
    resultado = []
    for nombre in orden:
        ruta = next((r for r in todos.get(nombre, []) if r.is_file()), None)
        if ruta:
            resultado.append((nombre, ruta))
    return resultado


# ───────────────────────────────────────────── canal DevTools (WebSocket mínimo)


class Canal:
    """Cliente WebSocket mínimo para el puerto de depuración local del navegador."""

    def __init__(self, puerto: int, ruta: str, espera: float = 10) -> None:
        self.sock = socket.create_connection(("127.0.0.1", puerto), timeout=espera)
        self._resto = b""
        self._id = 0
        clave = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET {ruta} HTTP/1.1\r\nHost: 127.0.0.1:{puerto}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {clave}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        while b"\r\n\r\n" not in self._resto:
            self._recibir_mas()
        cabecera, self._resto = self._resto.split(b"\r\n\r\n", 1)
        if b" 101 " not in cabecera.split(b"\r\n", 1)[0]:
            self.sock.close()
            raise ConnectionError("el navegador rechazó la conexión de depuración")

    def _recibir_mas(self) -> None:
        datos = self.sock.recv(65536)
        if not datos:
            raise ConnectionError("el navegador se cerró")
        self._resto += datos

    def _leer(self, n: int) -> bytes:
        while len(self._resto) < n:
            self._recibir_mas()
        datos, self._resto = self._resto[:n], self._resto[n:]
        return datos

    def _enviar_marco(self, opcode: int, datos: bytes) -> None:
        largo = len(datos)
        if largo < 126:
            cabecera = struct.pack("!BB", 0x80 | opcode, 0x80 | largo)
        elif largo < 65536:
            cabecera = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, largo)
        else:
            cabecera = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, largo)
        mascara = os.urandom(4)
        enmascarado = bytes(b ^ mascara[i % 4] for i, b in enumerate(datos))
        self.sock.sendall(cabecera + mascara + enmascarado)

    def _recibir_mensaje(self) -> str:
        partes = []
        while True:
            b0, b1 = self._leer(2)
            opcode, largo = b0 & 0x0F, b1 & 0x7F
            if largo == 126:
                (largo,) = struct.unpack("!H", self._leer(2))
            elif largo == 127:
                (largo,) = struct.unpack("!Q", self._leer(8))
            mascara = self._leer(4) if b1 & 0x80 else None
            datos = self._leer(largo)
            if mascara:
                datos = bytes(b ^ mascara[i % 4] for i, b in enumerate(datos))
            if opcode == 0x8:
                raise ConnectionError("el navegador cerró la conexión")
            if opcode == 0x9:
                self._enviar_marco(0xA, datos)
                continue
            if opcode == 0xA:
                continue
            partes.append(datos)
            if b0 & 0x80:
                return b"".join(partes).decode("utf-8")

    def llamar(self, metodo: str, params: dict | None = None) -> dict:
        self._id += 1
        mensaje = {"id": self._id, "method": metodo, "params": params or {}}
        self._enviar_marco(0x1, json.dumps(mensaje).encode("utf-8"))
        while True:
            respuesta = json.loads(self._recibir_mensaje())
            if respuesta.get("id") == self._id:
                if "error" in respuesta:
                    raise RuntimeError(f"{metodo}: {respuesta['error'].get('message')}")
                return respuesta.get("result", {})

    def cerrar(self) -> None:
        try:
            self._enviar_marco(0x8, b"")
        except OSError:
            pass
        self.sock.close()


# ──────────────────────────────────────────────────────────────── el navegador


def abrir(ejecutable: Path, *, oculto: bool = False, espera: float = 30) -> tuple[subprocess.Popen, int, str]:
    """Abre el navegador con el perfil de notcd y devuelve (proceso, puerto, ruta de depuración)."""
    carpeta = perfil()
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo_puerto = carpeta / "DevToolsActivePort"
    archivo_puerto.unlink(missing_ok=True)
    argumentos = [
        str(ejecutable), f"--user-data-dir={carpeta}", "--remote-debugging-port=0",
        "--no-first-run", "--no-default-browser-check", "--disable-sync", "--new-window",
    ]
    if oculto:
        argumentos.append("--headless=new")
    argumentos.append(FORMULARIO)
    try:
        proceso = subprocess.Popen(argumentos, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
    except OSError as error:
        raise SinNavegador(str(error)) from error
    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        try:
            lineas = archivo_puerto.read_text(encoding="utf-8").split()
            if len(lineas) >= 2:
                return proceso, int(lineas[0]), lineas[1]
        except (OSError, ValueError):
            pass
        if proceso.poll() not in (None, 0):
            raise SinNavegador(f"el navegador terminó con código {proceso.returncode}")
        time.sleep(0.3)
    cerrar_proceso(proceso)
    raise SinNavegador("el navegador no abrió su puerto de depuración a tiempo")


def cerrar_proceso(proceso: subprocess.Popen) -> None:
    if proceso.poll() is None:
        proceso.terminate()
        try:
            proceso.wait(10)
        except subprocess.TimeoutExpired:
            proceso.kill()


def hay_sesion(cookies: list[dict]) -> bool:
    nombres = {c.get("name") for c in cookies if str(c.get("domain", "")).endswith("google.com")}
    return {"SID", "__Secure-1PSIDTS"} <= nombres


def en_notebooklm(canal: Canal) -> bool:
    """Si alguna pestaña llegó a NotebookLM (no a su portada pública, que se ve sin sesión)."""
    for pagina in canal.llamar("Target.getTargets").get("targetInfos", []):
        url = urlparse(pagina.get("url", ""))
        if pagina.get("type") == "page" and url.hostname in HOSTS_NOTEBOOKLM and not url.path.startswith("/trynow"):
            return True
    return False


def formato_sesion(cookies: list[dict]) -> dict:
    """Las cookies del navegador en el formato que guarda Playwright (el que lee notebooklm-py)."""
    filas = []
    for c in cookies:
        if not c.get("name") or "value" not in c:
            continue
        filas.append({
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "expires": -1 if c.get("session") else c.get("expires", -1),
            "httpOnly": bool(c.get("httpOnly")),
            "secure": bool(c.get("secure")),
            "sameSite": c.get("sameSite") or "Lax",
        })
    return {"cookies": filas, "origins": []}


def sesion_aceptada(archivo: Path) -> bool:
    """Si NotebookLM acepta la sesión de ese archivo (abre la app y obtiene su token)."""

    async def probar() -> None:
        from notebooklm import NotebookLMClient

        async with NotebookLMClient.from_storage(str(archivo)):
            pass

    try:
        asyncio.run(probar())
        return True
    except Exception:
        return False


def guardar(cookies: list[dict]) -> bool:
    """Guarda la sesión si NotebookLM la acepta. Una sesión que no sirve no reemplaza a la anterior."""
    destino = rutas.sesion_google()
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".nuevo")
    temporal.write_text(json.dumps(formato_sesion(cookies), ensure_ascii=False, indent=2), encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(temporal, 0o600)
    if not sesion_aceptada(temporal):
        temporal.unlink(missing_ok=True)
        return False
    os.replace(temporal, destino)
    try:  # el correo de la cuenta, para mostrarlo en el estado (si falla, la sesión igual sirve)
        from notebooklm.auth import repair_account_metadata_from_playwright_storage

        asyncio.run(repair_account_metadata_from_playwright_storage(destino))
    except Exception:
        pass
    return True


def iniciar_sesion(ejecutable: Path, *, espera: float = 600, oculto: bool = False) -> bool:
    """Abre el formulario de Google y guarda la sesión cuando la persona llega a NotebookLM.

    Devuelve True si la sesión quedó guardada, False si se cerró la ventana o se acabó el tiempo.
    """
    proceso, puerto, ruta = abrir(ejecutable, oculto=oculto)
    canal = None
    try:
        canal = Canal(puerto, ruta)
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            try:
                cookies = canal.llamar("Storage.getCookies").get("cookies", [])
                if hay_sesion(cookies) and en_notebooklm(canal):
                    time.sleep(2)  # que Google termine de escribir las cookies
                    if guardar(canal.llamar("Storage.getCookies").get("cookies", [])):
                        return True
                    time.sleep(3)  # aún no sirve (p. ej., falta elegir la cuenta): se sigue esperando
            except (ConnectionError, OSError):
                return False  # la persona cerró la ventana
            time.sleep(1)
        return False
    finally:
        if canal is not None:
            try:
                canal.llamar("Browser.close")
            except Exception:
                pass
            canal.cerrar()
        cerrar_proceso(proceso)
