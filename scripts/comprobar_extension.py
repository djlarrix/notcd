"""Hace con la extensión lo mismo que la app de escritorio: la descomprime, instala sus
dependencias con uv y la ejecuta con `uv run`; luego se conecta como cliente MCP.

    uv run python scripts/comprobar_extension.py dist/notcd-<versión>.mcpb
"""

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def conectar(uv: str, carpeta: Path, casa: Path) -> None:
    entorno = {k: v for k, v in os.environ.items() if k in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "TEMP", "TMP", "PATH")}
    entorno["NOTCD_HOME"] = str(casa)
    entorno["NOTCD_DESCARGAS"] = "${user_config.carpeta_descargas}"  # ajuste vacío, sin reemplazar
    parametros = StdioServerParameters(command=uv, args=["run", "--directory", str(carpeta), "servidor_mcpb.py"], env=entorno)
    async with stdio_client(parametros) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            info = await sesion.initialize()
            herramientas = (await sesion.list_tools()).tools
            plantillas = (await sesion.list_prompts()).prompts
            guia = (await sesion.call_tool("guia_de_metodo", {"modo": "escritos"})).content[0].text
            estado = (await sesion.call_tool("estado_conexion", {})).content[0].text
    print(f"{info.server_info.name} {info.server_info.version}: {len(herramientas)} herramientas, {len(plantillas)} plantillas")
    print("estado_conexion:", estado.splitlines()[0])
    assert len(herramientas) == 20 and len(plantillas) == 4
    assert guia.startswith("# Redactar o revisar")


def main() -> None:
    mcpb = Path(sys.argv[1]).resolve()
    uv = shutil.which("uv") or sys.exit("falta uv")
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp) / "extension"
        zipfile.ZipFile(mcpb).extractall(carpeta)
        subprocess.run([uv, "sync", "--quiet"], cwd=carpeta, check=True)
        modo = subprocess.run(
            [uv, "run", "--directory", str(carpeta), "python", "-c",
             "from notcd import actualizacion; print(actualizacion.modo())"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        print("modo de instalación:", modo)
        assert modo == "extension"
        asyncio.run(conectar(uv, carpeta, Path(tmp) / "casa"))
    print("OK")


if __name__ == "__main__":
    main()
