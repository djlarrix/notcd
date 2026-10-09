"""Servidor MCP mínimo por stdio, en Python puro.

notcd no usa la biblioteca oficial de MCP para servir: depende de pydantic-core y
cryptography, que traen archivos compilados sin firma digital, y en Windows el
Control inteligente de aplicaciones los bloquea («Una directiva de Control de
aplicaciones bloqueó este archivo»). Este módulo implementa, con la biblioteca
estándar, lo que notcd usa del protocolo: el saludo inicial, herramientas y
plantillas. Las pruebas lo comprueban con el cliente oficial.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sys
import threading
import types
import typing
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, Literal, get_args, get_origin

log = logging.getLogger("notcd")

# Versiones del protocolo con saludo inicial («initialize»), de la más antigua a la más nueva.
VERSIONES = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")

METODO_DESCONOCIDO = -32601
PARAMETROS_INVALIDOS = -32602
ERROR_INTERNO = -32603
JSON_INVALIDO = -32700


class ErrorHerramienta(Exception):
    """Falla de una herramienta, ya redactada para el asistente."""


class ErrorProtocolo(Exception):
    def __init__(self, codigo: int, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo = codigo


@dataclass(frozen=True)
class Campo:
    """Descripción y límites de un parámetro: `Annotated[int, Campo(description=..., ge=1)]`."""

    description: str = ""
    ge: float | None = None
    le: float | None = None


@dataclass(frozen=True)
class Anotaciones:
    title: str | None = None
    read_only_hint: bool | None = None
    destructive_hint: bool | None = None
    idempotent_hint: bool | None = None
    open_world_hint: bool | None = None

    def json(self) -> dict[str, Any]:
        claves = {
            "title": self.title, "readOnlyHint": self.read_only_hint, "destructiveHint": self.destructive_hint,
            "idempotentHint": self.idempotent_hint, "openWorldHint": self.open_world_hint,
        }
        return {k: v for k, v in claves.items() if v is not None}


@dataclass(frozen=True)
class Texto:
    text: str
    type: str = "text"


@dataclass(frozen=True)
class ResultadoHerramienta:
    content: list[Texto]
    is_error: bool = False


@dataclass(frozen=True)
class Mensaje:
    role: str
    content: Texto


@dataclass(frozen=True)
class ResultadoPlantilla:
    messages: list[Mensaje]
    description: str | None = None


@dataclass(frozen=True)
class Parametro:
    name: str
    tipo: Any
    requerido: bool
    defecto: Any = None
    campo: Campo | None = None

    @property
    def description(self) -> str | None:
        return self.campo.description if self.campo and self.campo.description else None


@dataclass
class Registrada:
    """Una herramienta o una plantilla, con sus parámetros leídos de la firma de la función."""

    name: str
    funcion: Callable[..., Any]
    parametros: list[Parametro]
    title: str | None = None
    description: str | None = None
    annotations: Anotaciones | None = None

    @property
    def arguments(self) -> list[Parametro]:  # para las plantillas, con el nombre del protocolo
        return self.parametros


def leer_parametros(funcion: Callable[..., Any]) -> list[Parametro]:
    original = inspect.unwrap(funcion)
    tipos = typing.get_type_hints(original, include_extras=True)
    parametros = []
    for nombre, p in inspect.signature(original).parameters.items():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        tipo = tipos.get(nombre, Any)
        campo = None
        if get_origin(tipo) is Annotated:
            campo = next((m for m in get_args(tipo)[1:] if isinstance(m, Campo)), None)
        requerido = p.default is inspect.Parameter.empty
        parametros.append(Parametro(nombre, tipo, requerido, None if requerido else p.default, campo))
    return parametros


# ─────────────────────────────────────────────────────── esquemas y validación


def _sin_anotar(tipo: Any) -> tuple[Any, Campo | None]:
    if get_origin(tipo) is Annotated:
        base, *extras = get_args(tipo)
        return base, next((m for m in extras if isinstance(m, Campo)), None)
    return tipo, None


def _opcional(tipo: Any) -> tuple[Any, bool]:
    if get_origin(tipo) in (typing.Union, types.UnionType):
        resto = [a for a in get_args(tipo) if a is not type(None)]
        if len(resto) < len(get_args(tipo)) and len(resto) == 1:
            return resto[0], True
    return tipo, False


def esquema(tipo: Any) -> dict[str, Any]:
    base, campo = _sin_anotar(tipo)
    base, opcional = _opcional(base)
    origen = get_origin(base)
    if origen is Literal:
        valores = list(get_args(base))
        s: dict[str, Any] = {"type": "string" if all(isinstance(v, str) for v in valores) else "integer", "enum": valores}
    elif base is str:
        s = {"type": "string"}
    elif base is bool:
        s = {"type": "boolean"}
    elif base is int:
        s = {"type": "integer"}
    elif base is float:
        s = {"type": "number"}
    elif origen is list or base is list:
        argumentos = get_args(base)
        s = {"type": "array", "items": esquema(argumentos[0]) if argumentos else {}}
    elif origen is dict or base is dict:
        s = {"type": "object"}
    else:
        s = {}
    if campo is not None:
        if campo.ge is not None:
            s["minimum"] = campo.ge
        if campo.le is not None:
            s["maximum"] = campo.le
    if opcional:
        s = {"anyOf": [s, {"type": "null"}]}
    if campo is not None and campo.description:
        s["description"] = campo.description
    return s


def esquema_entrada(parametros: list[Parametro]) -> dict[str, Any]:
    propiedades = {}
    for p in parametros:
        s = esquema(p.tipo)
        if not p.requerido and isinstance(p.defecto, (str, int, float, bool, type(None))):
            s["default"] = p.defecto
        propiedades[p.name] = s
    resultado: dict[str, Any] = {"type": "object", "properties": propiedades}
    requeridos = [p.name for p in parametros if p.requerido]
    if requeridos:
        resultado["required"] = requeridos
    return resultado


def convertir(valor: Any, tipo: Any, nombre: str) -> Any:
    """Valida un argumento contra su tipo, con las conversiones obvias («5» → 5)."""
    base, campo = _sin_anotar(tipo)
    base, opcional = _opcional(base)
    if valor is None:
        if opcional:
            return None
        raise ErrorHerramienta(f"Falta el valor de «{nombre}».")
    origen = get_origin(base)
    if origen is Literal:
        permitidos = get_args(base)
        if valor not in permitidos:
            raise ErrorHerramienta(f"«{nombre}» debe ser uno de: {', '.join(map(str, permitidos))}.")
        return valor
    if base is str:
        if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
            raise ErrorHerramienta(f"«{nombre}» debe ser un texto.")
        return str(valor)
    if base is bool:
        if isinstance(valor, str) and valor.strip().lower() in ("true", "false"):
            return valor.strip().lower() == "true"
        if not isinstance(valor, bool):
            raise ErrorHerramienta(f"«{nombre}» debe ser true o false.")
        return valor
    if base in (int, float):
        try:
            if isinstance(valor, bool):
                raise ValueError
            numero = float(valor) if base is float else (int(valor) if not isinstance(valor, float) else valor)
            if base is int and isinstance(numero, float):
                if not numero.is_integer():
                    raise ValueError
                numero = int(numero)
        except (TypeError, ValueError):
            raise ErrorHerramienta(f"«{nombre}» debe ser un número{' entero' if base is int else ''}.") from None
        if campo is not None and campo.ge is not None and numero < campo.ge:
            raise ErrorHerramienta(f"«{nombre}» debe ser al menos {campo.ge:g}.")
        if campo is not None and campo.le is not None and numero > campo.le:
            raise ErrorHerramienta(f"«{nombre}» debe ser como máximo {campo.le:g}.")
        return numero
    if origen is list or base is list:
        if isinstance(valor, str):
            texto = valor.strip()
            if texto.startswith("["):
                try:
                    valor = json.loads(texto)
                except ValueError:
                    raise ErrorHerramienta(f"«{nombre}» debe ser una lista.") from None
            else:
                valor = [valor]  # un solo elemento enviado sin la lista
        if not isinstance(valor, list):
            raise ErrorHerramienta(f"«{nombre}» debe ser una lista.")
        argumentos = get_args(base)
        return [convertir(v, argumentos[0], nombre) for v in valor] if argumentos else valor
    if origen is dict or base is dict:
        if not isinstance(valor, dict):
            raise ErrorHerramienta(f"«{nombre}» debe ser un objeto.")
        return valor
    return valor


def argumentos(parametros: list[Parametro], recibidos: dict[str, Any] | None) -> dict[str, Any]:
    recibidos = recibidos or {}
    if not isinstance(recibidos, dict):
        raise ErrorHerramienta("Los argumentos deben venir como un objeto.")
    resultado = {}
    for p in parametros:
        if p.name in recibidos:
            resultado[p.name] = convertir(recibidos[p.name], p.tipo, p.name)
        elif p.requerido:
            raise ErrorHerramienta(f"Falta el parámetro «{p.name}».")
    return resultado


# ─────────────────────────────────────────────────────────────────── servidor


@dataclass
class Servidor:
    name: str
    version: str
    title: str | None = None
    instructions: str | None = None
    herramientas: dict[str, Registrada] = field(default_factory=dict)
    plantillas: dict[str, Registrada] = field(default_factory=dict)

    # ── registro

    def tool(self, *, name: str | None = None, title: str | None = None, description: str | None = None,
             annotations: Anotaciones | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def registrar(funcion: Callable[..., Any]) -> Callable[..., Any]:
            nombre = name or funcion.__name__
            self.herramientas[nombre] = Registrada(
                nombre, funcion, leer_parametros(funcion), title,
                description or inspect.getdoc(inspect.unwrap(funcion)), annotations,
            )
            return funcion
        return registrar

    def prompt(self, *, name: str | None = None, title: str | None = None,
               description: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def registrar(funcion: Callable[..., Any]) -> Callable[..., Any]:
            nombre = name or funcion.__name__
            self.plantillas[nombre] = Registrada(
                nombre, funcion, leer_parametros(funcion), title, description or inspect.getdoc(funcion),
            )
            return funcion
        return registrar

    # ── uso directo (pruebas y empaquetado)

    async def list_tools(self) -> list[Registrada]:
        return list(self.herramientas.values())

    async def list_prompts(self) -> list[Registrada]:
        return list(self.plantillas.values())

    async def call_tool(self, nombre: str, recibidos: dict[str, Any] | None = None) -> ResultadoHerramienta:
        """Corre una herramienta. Si falla, levanta ErrorHerramienta con el mensaje para el asistente."""
        herramienta = self.herramientas.get(nombre)
        if herramienta is None:
            raise ErrorHerramienta(f"No existe la herramienta «{nombre}».")
        resultado = herramienta.funcion(**argumentos(herramienta.parametros, recibidos))
        if inspect.isawaitable(resultado):
            resultado = await resultado
        return ResultadoHerramienta([Texto(resultado if isinstance(resultado, str) else json.dumps(resultado, ensure_ascii=False))])

    async def get_prompt(self, nombre: str, recibidos: dict[str, Any] | None = None) -> ResultadoPlantilla:
        plantilla = self.plantillas.get(nombre)
        if plantilla is None:
            raise ErrorProtocolo(PARAMETROS_INVALIDOS, f"No existe la plantilla «{nombre}».")
        try:
            valores = argumentos(plantilla.parametros, recibidos)
        except ErrorHerramienta as error:
            raise ErrorProtocolo(PARAMETROS_INVALIDOS, str(error)) from None
        texto = plantilla.funcion(**valores)
        if inspect.isawaitable(texto):
            texto = await texto
        return ResultadoPlantilla([Mensaje("user", Texto(texto))], plantilla.description)

    # ── protocolo

    def _saludo(self, params: dict[str, Any]) -> dict[str, Any]:
        pedida = params.get("protocolVersion")
        informacion = {"name": self.name, "version": self.version}
        if self.title:
            informacion["title"] = self.title
        resultado = {
            "protocolVersion": pedida if pedida in VERSIONES else VERSIONES[-1],
            "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
            "serverInfo": informacion,
        }
        if self.instructions:
            resultado["instructions"] = self.instructions
        return resultado

    def _herramientas_json(self) -> list[dict[str, Any]]:
        lista = []
        for h in self.herramientas.values():
            d: dict[str, Any] = {"name": h.name}
            if h.title:
                d["title"] = h.title
            if h.description:
                d["description"] = h.description
            d["inputSchema"] = esquema_entrada(h.parametros)
            if h.annotations:
                d["annotations"] = h.annotations.json()
            lista.append(d)
        return lista

    def _plantillas_json(self) -> list[dict[str, Any]]:
        lista = []
        for p in self.plantillas.values():
            d: dict[str, Any] = {"name": p.name}
            if p.title:
                d["title"] = p.title
            if p.description:
                d["description"] = p.description
            d["arguments"] = [
                {"name": a.name, "required": a.requerido, **({"description": a.description} if a.description else {})}
                for a in p.parametros
            ]
            lista.append(d)
        return lista

    async def atender(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if metodo == "initialize":
            return self._saludo(params)
        if metodo in ("ping", "logging/setLevel"):
            return {}
        if metodo == "tools/list":
            return {"tools": self._herramientas_json()}
        if metodo == "tools/call":
            try:
                resultado = await self.call_tool(params.get("name", ""), params.get("arguments"))
            except ErrorHerramienta as error:
                return {"content": [{"type": "text", "text": str(error)}], "isError": True}
            return {"content": [{"type": "text", "text": t.text} for t in resultado.content], "isError": False}
        if metodo == "prompts/list":
            return {"prompts": self._plantillas_json()}
        if metodo == "prompts/get":
            r = await self.get_prompt(params.get("name", ""), params.get("arguments"))
            mensajes = [{"role": m.role, "content": {"type": "text", "text": m.content.text}} for m in r.messages]
            return {"messages": mensajes, **({"description": r.description} if r.description else {})}
        if metodo == "resources/list":
            return {"resources": []}
        if metodo == "resources/templates/list":
            return {"resourceTemplates": []}
        raise ErrorProtocolo(METODO_DESCONOCIDO, f"Method not found: {metodo}")

    async def _responder(self, salida: Callable[[dict[str, Any]], None], ident: Any, metodo: str,
                         params: dict[str, Any]) -> None:
        try:
            respuesta: dict[str, Any] = {"result": await self.atender(metodo, params)}
        except asyncio.CancelledError:
            return  # la app canceló la petición: no se responde
        except ErrorProtocolo as error:
            respuesta = {"error": {"code": error.codigo, "message": str(error)}}
        except Exception as error:
            log.exception("falla interna en %s", metodo)
            respuesta = {"error": {"code": ERROR_INTERNO, "message": f"Error interno: {error}"}}
        salida({"jsonrpc": "2.0", "id": ident, **respuesta})

    async def servir(self, entrada: typing.BinaryIO, escribir: Callable[[bytes], None]) -> None:
        """Atiende mensajes JSON-RPC, uno por línea, hasta que se cierre la entrada."""
        loop = asyncio.get_running_loop()
        cola: asyncio.Queue[bytes | None] = asyncio.Queue()

        def leer() -> None:
            try:
                for linea in entrada:
                    loop.call_soon_threadsafe(cola.put_nowait, linea)
            except (OSError, ValueError):
                pass
            finally:
                loop.call_soon_threadsafe(cola.put_nowait, None)

        threading.Thread(target=leer, name="entrada-mcp", daemon=True).start()

        def salida(mensaje: dict[str, Any]) -> None:
            escribir(json.dumps(mensaje, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")

        pendientes: dict[str, asyncio.Task[None]] = {}
        while (linea := await cola.get()) is not None:
            if not linea.strip():
                continue
            try:
                recibido = json.loads(linea)
            except ValueError:
                salida({"jsonrpc": "2.0", "id": None, "error": {"code": JSON_INVALIDO, "message": "Parse error"}})
                continue
            for mensaje in recibido if isinstance(recibido, list) else [recibido]:
                if not isinstance(mensaje, dict) or not isinstance(mensaje.get("method"), str):
                    continue  # respuestas de la app: este servidor no le hace peticiones
                params = mensaje.get("params") if isinstance(mensaje.get("params"), dict) else {}
                if "id" not in mensaje:
                    if mensaje["method"] == "notifications/cancelled":
                        tarea = pendientes.get(json.dumps(params.get("requestId")))
                        if tarea:
                            tarea.cancel()
                    continue
                clave = json.dumps(mensaje["id"])
                tarea = asyncio.create_task(self._responder(salida, mensaje["id"], mensaje["method"], params))
                pendientes[clave] = tarea
                tarea.add_done_callback(lambda _t, c=clave: pendientes.pop(c, None))
        # La app cerró la conexión: lo que está por terminar alcanza a responder; lo largo se cancela.
        if pendientes:
            await asyncio.wait(list(pendientes.values()), timeout=2)
        for tarea in list(pendientes.values()):
            tarea.cancel()
        await asyncio.gather(*pendientes.values(), return_exceptions=True)

    def run(self) -> None:
        """Atiende a la app por stdin/stdout hasta que cierre la conexión."""
        entrada = sys.stdin.buffer
        salida = sys.stdout.buffer
        # Lo que alguna biblioteca imprima no debe mezclarse con el canal MCP.
        sys.stdout = sys.stderr

        def escribir(datos: bytes) -> None:
            salida.write(datos)
            salida.flush()

        asyncio.run(self.servir(entrada, escribir))
