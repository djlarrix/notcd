"""Arma los entregables de una versión en dist/:

- notcd-<versión>.mcpb   extensión de la app de escritorio (doble clic para instalar)
- notcd.zip               la skill, para subirla en la app de escritorio

    uv run python scripts/empaquetar.py

La lista de herramientas y plantillas del manifiesto se saca del servidor mismo,
para que nunca quede desfasada.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARMADO = RAIZ / "build" / "mcpb"
DIST = RAIZ / "dist"

# Lo que viaja en la extensión. Nada de .venv, pruebas ni instaladores.
ARCHIVOS = ["pyproject.toml", "uv.lock", "README.md", ".python-version", "servidor_mcpb.py", "SKILL.md"]
CARPETAS = ["src/notcd", "referencias"]


def version() -> str:
    return tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


async def capacidades() -> tuple[list[dict], list[dict]]:
    sys.path.insert(0, str(RAIZ / "src"))
    from notcd.server import mcp

    herramientas = [
        {"name": t.name, "description": (t.description or "").strip().splitlines()[0]}
        for t in await mcp.list_tools()
    ]
    plantillas = []
    for p in await mcp.list_prompts():
        argumentos = [a.name for a in p.arguments or []]
        texto = (await mcp.get_prompt(p.name, {a: f"${{arguments.{a}}}" for a in argumentos})).messages[0].content.text
        plantillas.append({"name": p.name, "description": p.description, "arguments": argumentos, "text": texto})
    return herramientas, plantillas


def manifiesto(v: str) -> dict:
    herramientas, plantillas = asyncio.run(capacidades())
    plantilla = json.loads((RAIZ / "extension" / "manifest.json").read_text(encoding="utf-8"))
    plantilla["version"] = v
    plantilla["tools"] = herramientas
    plantilla["prompts"] = plantillas
    return plantilla


def copiar() -> None:
    if ARMADO.exists():
        shutil.rmtree(ARMADO)
    ARMADO.mkdir(parents=True)
    for archivo in ARCHIVOS:
        shutil.copy2(RAIZ / archivo, ARMADO / archivo)
    for carpeta in CARPETAS:
        shutil.copytree(
            RAIZ / carpeta, ARMADO / carpeta, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
        )
    shutil.copy2(RAIZ / "extension" / "icon.png", ARMADO / "icon.png")


def comprimir(origen: Path, destino: Path, prefijo: str = "") -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.unlink(missing_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for archivo in sorted(origen.rglob("*")):
            if archivo.is_file() and archivo.name != ".DS_Store":
                z.write(archivo, str(Path(prefijo) / archivo.relative_to(origen)) if prefijo else str(archivo.relative_to(origen)))


def validar(manifiesto_ruta: Path) -> None:
    npx = shutil.which("npx")
    if not npx:
        print("  (sin npx: se omite la validación oficial del manifiesto)")
        return
    r = subprocess.run([npx, "-y", "@anthropic-ai/mcpb", "validate", str(manifiesto_ruta)], capture_output=True, text=True)
    salida = (r.stdout + r.stderr).strip()
    print("  " + salida.replace("\n", "\n  "))
    if r.returncode != 0:
        sys.exit("El manifiesto no pasó la validación oficial.")


def main() -> None:
    if not (RAIZ / "uv.lock").exists():
        sys.exit("Falta uv.lock: ejecuta `uv lock` antes de empaquetar.")
    v = version()
    print(f"notcd {v}")
    copiar()
    (ARMADO / "manifest.json").write_text(json.dumps(manifiesto(v), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validar(ARMADO / "manifest.json")
    extension = DIST / f"notcd-{v}.mcpb"
    comprimir(ARMADO, extension)
    skill = DIST / "notcd.zip"
    sys.path.insert(0, str(RAIZ / "src"))
    from notcd import rutas

    skill.unlink(missing_ok=True)
    with zipfile.ZipFile(skill, "w", zipfile.ZIP_DEFLATED) as z:
        for archivo in rutas.archivos_skill():
            z.write(archivo, str(Path("notcd") / archivo.relative_to(RAIZ)))
    print(f"  {extension.relative_to(RAIZ)} ({extension.stat().st_size // 1024} KB)")
    print(f"  {skill.relative_to(RAIZ)} ({skill.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
