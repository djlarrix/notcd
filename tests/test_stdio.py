"""El servidor real, lanzado como lo lanza la app: un proceso hablando MCP por stdio."""

import os
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def test_la_app_puede_conectarse_y_listar_herramientas(tmp_path):
    entorno = {k: v for k, v in os.environ.items() if k != "NOTEBOOKLM_HOME"}
    entorno["NOTCD_HOME"] = str(tmp_path / ".notcd")
    parametros = StdioServerParameters(command=sys.executable, args=["-m", "notcd", "servidor"], env=entorno)
    async with stdio_client(parametros) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            inicio = await sesion.initialize()
            assert inicio.server_info.name == "notcd"
            assert "NotebookLM LEE" in inicio.instructions
            herramientas = await sesion.list_tools()
            assert len(herramientas.tools) == 20
            plantillas = await sesion.list_prompts()
            assert len(plantillas.prompts) == 4
            estado = await sesion.call_tool("estado_conexion", {})
            assert "iniciar_sesion" in estado.content[0].text
            sin_sesion = await sesion.call_tool("listar_cuadernos", {})
            assert sin_sesion.is_error
