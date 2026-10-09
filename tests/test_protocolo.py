"""El servidor MCP propio (notcd/protocolo.py): esquemas, validación y el canal stdio."""

import asyncio
import io
import json
import subprocess
import sys
from typing import Annotated, Literal

import pytest

from notcd.protocolo import Anotaciones, Campo, ErrorHerramienta, Servidor, esquema


def servidor_de_prueba() -> Servidor:
    s = Servidor(name="prueba", version="1.0", title="Prueba", instructions="Instrucciones.")

    @s.tool(title="Sumar", annotations=Anotaciones(read_only_hint=True))
    async def sumar(
        a: Annotated[int, Campo(description="Primero.", ge=0, le=10)],
        b: int = 1,
        modo: Literal["normal", "doble"] = "normal",
        etiquetas: Annotated[list[str] | None, Campo(description="Opcional.")] = None,
    ) -> str:
        """Suma dos números.

        Sirve para probar.
        """
        total = (a + b) * (2 if modo == "doble" else 1)
        return f"{total} {etiquetas or []}"

    @s.tool()
    async def lenta() -> str:
        await asyncio.sleep(30)
        return "no debería llegar"

    @s.tool()
    async def falla() -> str:
        raise ErrorHerramienta("explicación para el asistente")

    @s.prompt(name="plantilla", title="Una plantilla", description="Describe.")
    def plantilla(carpeta: str, causa: str = "") -> str:
        return f"carpeta={carpeta} causa={causa}"

    return s


def test_esquema_de_tipos():
    assert esquema(Annotated[int, Campo(description="d", ge=1, le=5)]) == {
        "type": "integer", "minimum": 1, "maximum": 5, "description": "d",
    }
    assert esquema(Literal["a", "b"]) == {"type": "string", "enum": ["a", "b"]}
    assert esquema(list[str] | None) == {"anyOf": [{"type": "array", "items": {"type": "string"}}, {"type": "null"}]}
    assert esquema(bool) == {"type": "boolean"}


async def test_llamar_valida_y_convierte():
    s = servidor_de_prueba()
    r = await s.call_tool("sumar", {"a": "3", "modo": "doble", "etiquetas": "x"})
    assert r.content[0].text == "8 ['x']"
    with pytest.raises(ErrorHerramienta, match="Falta el parámetro «a»"):
        await s.call_tool("sumar", {})
    with pytest.raises(ErrorHerramienta, match="como máximo 10"):
        await s.call_tool("sumar", {"a": 11})
    with pytest.raises(ErrorHerramienta, match="uno de: normal, doble"):
        await s.call_tool("sumar", {"a": 1, "modo": "triple"})
    with pytest.raises(ErrorHerramienta, match="número entero"):
        await s.call_tool("sumar", {"a": 1.5})
    with pytest.raises(ErrorHerramienta, match="No existe"):
        await s.call_tool("otra", {})


async def conversar(s: Servidor, mensajes: list[dict], *, antes_de_cerrar: float = 0) -> list[dict]:
    """Manda los mensajes al servidor como lo haría la app y devuelve lo que respondió."""
    escritura = []
    lineas = b"".join(json.dumps(m).encode() + b"\n" for m in mensajes)

    class Entrada:
        def __iter__(self):
            yield from io.BytesIO(lineas)
            if antes_de_cerrar:
                import time
                time.sleep(antes_de_cerrar)

    await s.servir(Entrada(), escritura.append)
    return [json.loads(linea) for linea in escritura]


async def test_conversacion_completa_por_stdio():
    s = servidor_de_prueba()
    respuestas = await conversar(s, [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "sumar", "arguments": {"a": 2}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "falla", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 5, "method": "prompts/get", "params": {"name": "plantilla", "arguments": {"carpeta": "/x"}}},
        {"jsonrpc": "2.0", "id": 6, "method": "server/discover", "params": {}},
        {"jsonrpc": "2.0", "id": 7, "method": "prompts/get", "params": {"name": "plantilla", "arguments": {}}},
    ], antes_de_cerrar=0.3)
    por_id = {r["id"]: r for r in respuestas}
    inicio = por_id[1]["result"]
    assert inicio["protocolVersion"] == "2025-06-18"
    assert inicio["serverInfo"] == {"name": "prueba", "version": "1.0", "title": "Prueba"}
    assert inicio["instructions"] == "Instrucciones."
    sumar = next(t for t in por_id[2]["result"]["tools"] if t["name"] == "sumar")
    assert sumar["description"] == "Suma dos números.\n\nSirve para probar."
    assert sumar["annotations"] == {"readOnlyHint": True}
    assert sumar["inputSchema"]["required"] == ["a"]
    assert sumar["inputSchema"]["properties"]["modo"] == {"type": "string", "enum": ["normal", "doble"], "default": "normal"}
    assert por_id[3]["result"] == {"content": [{"type": "text", "text": "3 []"}], "isError": False}
    assert por_id[4]["result"]["isError"] is True and "explicación" in por_id[4]["result"]["content"][0]["text"]
    assert por_id[5]["result"]["messages"][0]["content"]["text"] == "carpeta=/x causa="
    assert por_id[6]["error"]["code"] == -32601  # la app vuelve al saludo clásico
    assert por_id[7]["error"]["code"] == -32602


async def test_version_desconocida_responde_la_mas_nueva():
    respuestas = await conversar(servidor_de_prueba(), [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2099-01-01"}},
    ])
    assert respuestas[0]["result"]["protocolVersion"] == "2025-11-25"


async def test_cancelar_una_peticion_no_deja_respuesta():
    respuestas = await conversar(servidor_de_prueba(), [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "lenta", "arguments": {}}},
        {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
    ], antes_de_cerrar=0.3)
    assert respuestas == [{"jsonrpc": "2.0", "id": 2, "result": {}}]


async def test_json_roto_no_corta_la_conexion():
    s = servidor_de_prueba()
    escritura = []

    class Entrada:
        def __iter__(self):
            yield b"{esto no es json\n"
            yield b'{"jsonrpc":"2.0","id":9,"method":"ping"}\n'

    await s.servir(Entrada(), escritura.append)
    respuestas = [json.loads(x) for x in escritura]
    assert respuestas[0]["error"]["code"] == -32700
    assert respuestas[1] == {"jsonrpc": "2.0", "id": 9, "result": {}}


def test_notcd_no_carga_nada_compilado():
    """En Windows, el Control inteligente de aplicaciones bloquea lo compilado sin firma."""
    codigo = (
        "import sys, notcd.server, notcd.cli, notcd.navegador, notcd.protocolo, notebooklm\n"
        "compilados = sorted(n for n, m in list(sys.modules.items())\n"
        "    if (getattr(m, '__file__', None) or '').endswith(('.so', '.pyd'))\n"
        "    and 'site-packages' in (m.__file__ or ''))\n"
        "print(compilados)"
    )
    salida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True).stdout
    assert salida.strip() == "[]"
