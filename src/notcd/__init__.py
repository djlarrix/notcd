"""notcd: NotebookLM (Gemini Notebook) y el asistente de IA trabajando juntos."""

import os
from pathlib import Path

__version__ = "0.3.0"

# Todo lo de notcd vive en ~/.notcd, aparte de cualquier otra
# instalación de notebooklm-py que la persona tenga. Tiene que fijarse antes de
# importar notebooklm, que lee NOTEBOOKLM_HOME al resolver rutas.
INICIO = Path(os.environ.get("NOTCD_HOME") or Path.home() / ".notcd")
os.environ.setdefault("NOTEBOOKLM_HOME", str(INICIO / "google"))


def entorno_login() -> dict[str, str]:
    """Entorno para el proceso de inicio de sesión (notebooklm-py o el propio notcd).

    PYTHONUTF8 evita que su salida se rompa en Windows cuando va a un archivo. El
    problema de fondo del inicio de sesión (la ventana que se cerraba sola) se
    resuelve en notcd.acceso.
    """
    entorno = os.environ.copy()
    entorno.setdefault("PYTHONUTF8", "1")
    return entorno
