"""Operaciones largas que siguen en segundo plano.

La app de escritorio corta cualquier llamada a una herramienta a los ~60 segundos, y
los avisos de progreso no lo evitan. Subir un expediente grande, una pregunta
difícil sobre un cuaderno enorme o un mapa mental pueden tardar más. Cada una
de esas operaciones se lanza como tarea: si termina a tiempo, se responde
normal; si no, se devuelve un id y la tarea sigue corriendo dentro del servidor
hasta que el asistente pida el resultado con `ver_trabajo`.
"""

from __future__ import annotations

import asyncio
import functools
import os
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

# Margen bajo los ~60 s de la app de escritorio, contando la red y lo que tarda el asistente.
ESPERA = float(os.environ.get("NOTCD_ESPERA", "40"))
# Cuánto se guardan los resultados que nadie vino a buscar.
VIGENCIA = 6 * 3600


@dataclass
class Trabajo:
    id: str
    descripcion: str
    tarea: asyncio.Task
    inicio: float = field(default_factory=time.monotonic)
    fin: float | None = None


def _terminado(trabajo: Trabajo, tarea: asyncio.Task) -> None:
    trabajo.fin = time.monotonic()
    if not tarea.cancelled():
        tarea.exception()  # marca el error como visto: se informa cuando lo pidan


class Trabajos:
    def __init__(self) -> None:
        self._trabajos: dict[str, Trabajo] = {}

    async def correr(self, descripcion: str, operacion: Awaitable[str], espera: float | None = None) -> str:
        """Espera la operación hasta `espera` segundos; si no alcanza, la deja corriendo.

        Los errores que ocurren dentro del plazo se propagan tal cual, para que
        quien llama los traduzca como cualquier otro.
        """
        tarea = asyncio.ensure_future(operacion)
        try:
            return await asyncio.wait_for(asyncio.shield(tarea), timeout=ESPERA if espera is None else espera)
        except asyncio.TimeoutError:
            pass
        self._limpiar()
        trabajo = Trabajo(id=secrets.token_hex(3), descripcion=descripcion, tarea=tarea)
        tarea.add_done_callback(functools.partial(_terminado, trabajo))
        self._trabajos[trabajo.id] = trabajo
        return (
            f"⏳ {descripcion}: sigue en curso en segundo plano (NotebookLM está tardando). "
            f"No lo repitas. Pide el resultado con ver_trabajo(trabajo_id=\"{trabajo.id}\") "
            "en unos 30 segundos; mientras, puedes seguir con otra cosa."
        )

    async def ver(self, trabajo_id: str | None, explicar: Callable[[BaseException], Awaitable[str]]) -> str:
        if not trabajo_id:
            return self._listado()
        trabajo = self._trabajos.get(trabajo_id.strip())
        if trabajo is None:
            return f"No hay un trabajo con id «{trabajo_id}» (pudo haberse reiniciado la app). Usa ver_trabajo sin id para listarlos."
        if not trabajo.tarea.done():
            transcurrido = int(time.monotonic() - trabajo.inicio)
            return (
                f"⏳ {trabajo.descripcion}: sigue en curso ({transcurrido} s). "
                "Vuelve a consultar en unos 30 segundos."
            )
        self._trabajos.pop(trabajo.id, None)
        if trabajo.tarea.cancelled():
            return f"{trabajo.descripcion}: se canceló."
        error = trabajo.tarea.exception()
        if error is not None:
            return f"{trabajo.descripcion}: falló. {await explicar(error)}"
        return trabajo.tarea.result()

    def _listado(self) -> str:
        if not self._trabajos:
            return "No hay trabajos en segundo plano."
        lineas = ["Trabajos en segundo plano:"]
        for t in self._trabajos.values():
            estado = "terminado: pide el resultado" if t.tarea.done() else f"en curso ({int(time.monotonic() - t.inicio)} s)"
            lineas.append(f"- {t.descripcion} · {estado} · trabajo_id: {t.id}")
        return "\n".join(lineas)

    def _limpiar(self) -> None:
        ahora = time.monotonic()
        for id_, t in list(self._trabajos.items()):
            if t.fin is not None and ahora - t.fin > VIGENCIA:
                self._trabajos.pop(id_, None)
