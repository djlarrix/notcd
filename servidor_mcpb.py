"""Punto de entrada de la extensión de la app de escritorio (.mcpb).

La app de escritorio instala las dependencias de pyproject.toml con su propio uv y
ejecuta este archivo con `uv run`. Fuera de la extensión no se usa.
"""

from notcd.server import main

main()
