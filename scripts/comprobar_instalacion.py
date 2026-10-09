"""Comprueba una instalación hecha con el instalador: que la app de código pueda lanzar el
servidor registrado en su configuración y que publique todas sus herramientas.

    uv run --no-project --with "mcp>=2.3,<3" python scripts/comprobar_instalacion.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from notcd import nombres  # noqa: E402  (sólo nombres de archivos; no necesita dependencias)

ESPERADAS = 20


async def main() -> None:
    entrada = json.loads((Path.home() / nombres.CONFIG_CODIGO).read_text(encoding="utf-8"))["mcpServers"]["notcd"]
    print("Registrado:", entrada["command"], " ".join(entrada["args"]))
    entorno = {k: v for k, v in os.environ.items() if k in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "TEMP", "TMP")}
    parametros = StdioServerParameters(command=entrada["command"], args=entrada["args"], env=entorno)
    async with stdio_client(parametros) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            await sesion.initialize()
            herramientas = (await sesion.list_tools()).tools
            plantillas = (await sesion.list_prompts()).prompts
            estado = (await sesion.call_tool("estado_conexion", {})).content[0].text
    print(f"{len(herramientas)} herramientas, {len(plantillas)} plantillas")
    print("estado_conexion:", estado.splitlines()[0])
    skill = Path.home() / nombres.CARPETA_CODIGO / "skills" / "notcd" / "SKILL.md"
    assert len(herramientas) == ESPERADAS, f"se esperaban {ESPERADAS} herramientas"
    assert skill.is_file(), "falta la skill de la app de código"
    print("OK")


asyncio.run(main())
sys.exit(0)
