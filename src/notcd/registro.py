"""Registro de actividad para dar soporte, sin contenido de los documentos.

Se anota qué herramienta se usó, cuánto tardó y si falló (con el tipo de error),
nunca preguntas, respuestas, títulos ni rutas: el archivo se puede pedir a un
colega para diagnosticar sin exponer información de clientes.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from notcd import INICIO

ARCHIVO = INICIO / "notcd.log"


def configurar() -> None:
    raiz = logging.getLogger("notcd")
    if raiz.handlers:
        return
    raiz.setLevel(logging.INFO)
    raiz.propagate = False  # el SDK de MCP ya tiene su propio manejador en la raíz
    formato = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    consola = logging.StreamHandler(sys.stderr)  # la app lo guarda en sus propios registros MCP
    consola.setFormatter(formato)
    raiz.addHandler(consola)
    try:
        ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        archivo = RotatingFileHandler(ARCHIVO, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        archivo.setFormatter(formato)
        raiz.addHandler(archivo)
    except OSError:
        pass


def ultimas_lineas(n: int = 40) -> list[str]:
    try:
        return ARCHIVO.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []
