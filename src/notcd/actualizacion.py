"""Mantener al día la conexión con NotebookLM.

Google cambia NotebookLM sin aviso y notebooklm-py publica la corrección como
versión de parche. Esto revisa (una vez al día) si hay una más nueva y la
aplica según cómo se instaló notcd:

- extensión de la app de escritorio (.mcpb): actualiza el entorno de la extensión con
  el mismo uv con que la app la ejecuta;
- instalador (uv tool): `uv tool upgrade notcd`;
- desarrollo: no se toca nada.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from notcd import INICIO

CACHE = INICIO / "versiones.json"
PYPI = "https://pypi.org/pypi/notebooklm-py/json"
UN_DIA = 24 * 3600


def numeros(version: str) -> tuple[int, ...] | None:
    partes = version.split(".")
    if not all(p.isdigit() for p in partes):
        return None  # prelanzamientos (a1, rc1…) no cuentan
    return tuple(int(p) for p in partes)


def instalada() -> str:
    import notebooklm

    return notebooklm.__version__


def mas_nueva_compatible(versiones: list[str]) -> str | None:
    """La versión estable más alta bajo 1.0 (el límite que acepta notcd)."""
    validas = [(n, v) for v in versiones if (n := numeros(v)) and n < (1,)]
    return max(validas)[1] if validas else None


async def ultima_disponible() -> str | None:
    """La versión más nueva publicada, consultando PyPI como mucho una vez al día."""
    try:
        guardado = json.loads(CACHE.read_text(encoding="utf-8"))
        if time.time() - guardado.get("consultado", 0) < UN_DIA:
            return guardado.get("ultima")
    except (OSError, ValueError):
        pass
    try:
        import httpx

        async with httpx.AsyncClient(timeout=4) as http:
            respuesta = await http.get(PYPI)
            respuesta.raise_for_status()
            ultima = mas_nueva_compatible(list(respuesta.json().get("releases", {})))
    except Exception:
        return None
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({"consultado": time.time(), "ultima": ultima}), encoding="utf-8")
    except OSError:
        pass
    return ultima


async def aviso() -> str | None:
    """Una línea para el usuario si hay corrección disponible, o None."""
    ultima = await ultima_disponible()
    actual = instalada()
    if ultima and numeros(actual) and numeros(ultima) and numeros(ultima) > numeros(actual):
        return (
            f"Hay una corrección de la conexión con NotebookLM (notebooklm-py {ultima}; instalada {actual}). "
            "Aplícala con `actualizar_conexion` (o `notcd actualizar` en la terminal) y reinicia la app."
        )
    return None


# ───────────────────────────────────────────────────────────────── aplicar


def raiz_proyecto() -> Path:
    return Path(__file__).resolve().parents[2]


def modo() -> str:
    raiz = raiz_proyecto()
    if (raiz / "manifest.json").is_file() and (raiz / "pyproject.toml").is_file():
        return "extension"
    try:
        if Path(sys.prefix).resolve() == (INICIO / "entorno").resolve():
            return "entorno"  # Windows: entorno del Python oficial firmado
    except OSError:
        pass
    if "uv/tools/notcd" in sys.prefix.replace("\\", "/") or "uv\\tools\\notcd" in sys.prefix:
        return "uv-tool"
    return "desarrollo"


def buscar_uv() -> str | None:
    if (uv := os.environ.get("UV")) and Path(uv).is_file():
        return uv  # `uv run` deja aquí el uv con que se lanzó el proceso
    candidatos = [shutil.which("uv")]
    casa = Path.home()
    candidatos += [str(casa / ".local" / "bin" / "uv"), str(casa / ".cargo" / "bin" / "uv")]
    if sys.platform == "win32":
        candidatos.append(str(casa / ".local" / "bin" / "uv.exe"))
    return next((c for c in candidatos if c and Path(c).is_file()), None)


def _correr(comando: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    # Certificados del sistema (redes de oficina que revisan las conexiones seguras) y copia
    # de archivos en vez de enlaces (menos choques con el antivirus en Windows).
    entorno = {**os.environ, "UV_SYSTEM_CERTS": "1", "UV_LINK_MODE": "copy"}
    return subprocess.run(
        comando, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        stdin=subprocess.DEVNULL, env=entorno,
    )


def aplicar_sincrono() -> tuple[bool, str]:
    """Actualiza notebooklm-py. Devuelve (salió bien, mensaje)."""
    forma = modo()
    if forma == "desarrollo":
        return False, "notcd corre desde el código fuente (desarrollo): actualiza con uv a mano."
    uv = buscar_uv()
    if not uv:
        return False, "No encontré uv para actualizar. Reinstala notcd con el instalador o la extensión nueva."
    antes = instalada()
    if forma == "extension":
        raiz = raiz_proyecto()
        pasos = [[uv, "lock", "--upgrade-package", "notebooklm-py"], [uv, "sync", "--quiet"]]
        for paso in pasos:
            r = _correr(paso, cwd=raiz)
            if r.returncode != 0:
                return False, "No se pudo actualizar la extensión: " + (r.stderr or r.stdout).strip()[-600:]
    elif forma == "entorno":
        try:
            fuente = descargar_ultima_version(INICIO / "fuente")
        except Exception as error:
            return False, f"No se pudo descargar la versión nueva: {error}"
        r = _correr([uv, "pip", "install", "--python", sys.executable, "--upgrade", "--reinstall-package", "notcd", str(fuente)])
        if r.returncode != 0:
            detalle = (r.stderr or r.stdout).strip()[-600:]
            return False, (
                "No se pudo actualizar (en Windows, si la app está abierta usa los archivos). Cierra la app "
                "por completo y vuelve a pegar el comando de instalación.\n" + detalle
            )
    else:
        try:
            fuente = descargar_ultima_version(INICIO / "fuente")
            r = _correr([uv, "tool", "install", "--force", "--upgrade", "--reinstall-package", "notcd",
                         "--python", "3.12", str(fuente)])
        except Exception as error:  # sin internet o GitHub caído: al menos las dependencias
            r = _correr([uv, "tool", "upgrade", "notcd"])
            if r.returncode == 0:
                return True, f"Dependencias al día, pero no se pudo descargar notcd nuevo ({error})."
        if r.returncode != 0:
            detalle = (r.stderr or r.stdout).strip()[-600:]
            if sys.platform == "win32":
                detalle += (
                    "\nEn Windows, cierra la app por completo y ejecuta en PowerShell: notcd actualizar"
                )
            return False, "No se pudo actualizar: " + detalle
    despues = _version_en_disco()
    notcd = _version_en_disco("notcd")
    sufijo = f" (notcd {notcd})" if notcd and forma == "uv-tool" else ""
    if despues and despues != antes:
        return True, f"Actualizado: notebooklm-py {antes} → {despues}{sufijo}. Reinicia la app para usarlo."
    return True, f"Al día: notebooklm-py {antes}{sufijo}. Reinicia la app si se instaló algo nuevo."


REPOSITORIO = "djlarrix/notcd"


def descargar_ultima_version(descargas: Path) -> Path:
    """Descarga la última versión (rama main) a una carpeta nueva y devuelve su ruta.

    Siempre una carpeta nueva: en Windows no se pueden mover ni borrar archivos que otro
    programa (el antivirus, por ejemplo) tenga abiertos. Las descargas anteriores se
    borran si se puede; si no, quedan para la próxima vez.
    """
    import io
    import zipfile

    import httpx

    respuesta = httpx.get(f"https://github.com/{REPOSITORIO}/archive/main.zip", follow_redirects=True, timeout=60)
    respuesta.raise_for_status()
    destino = descargas / time.strftime("%Y%m%d-%H%M%S")
    destino.mkdir(parents=True, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(respuesta.content)).extractall(destino)
    if descargas.is_dir():
        for vieja in descargas.iterdir():
            if vieja != destino and vieja.is_dir():
                shutil.rmtree(vieja, ignore_errors=True)
    return next(destino.glob("notcd-*"))


def _version_en_disco(paquete: str = "notebooklm") -> str | None:
    """La versión instalada ahora en disco (la del proceso actual puede ser la anterior)."""
    r = _correr([sys.executable, "-c", f"import {paquete}; print({paquete}.__version__)"])
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


async def aplicar() -> tuple[bool, str]:
    return await asyncio.to_thread(aplicar_sincrono)
