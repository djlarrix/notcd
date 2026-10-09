"""La conexión con NotebookLM y la traducción de sus errores a algo accionable."""

from __future__ import annotations

import asyncio
import logging
from contextlib import AbstractAsyncContextManager
from typing import Any

from notcd import rutas

log = logging.getLogger("notcd")

SIN_SESION = (
    "notcd todavía no tiene una sesión de Google. Llama a la herramienta "
    "`iniciar_sesion` (abre una ventana para entrar con la cuenta de Google que usa "
    "NotebookLM) o, desde la terminal, ejecuta: notcd login"
)

SESION_VENCIDA = (
    "La sesión de Google expiró o Google la rechazó. Llama a `iniciar_sesion` para "
    "volver a entrar (o ejecuta `notcd login` en la terminal) y repite la operación."
)


SESION_INCOMPLETA = (
    "La sesión de Google guardada está incompleta (el inicio de sesión no terminó bien). "
    "Llama a `iniciar_sesion` y pide al usuario que entre con su cuenta en la ventana que se abre, "
    "o ejecuta `notcd login` en la terminal."
)


class Conexion:
    """Un único cliente de NotebookLM, abierto al primer uso y reutilizado.

    Si Google rechaza la sesión, se descarta el cliente para que la siguiente
    llamada relea el archivo de sesión (por ejemplo, después de iniciar sesión de
    nuevo) sin tener que reiniciar la app.
    """

    def __init__(self) -> None:
        self._contexto: AbstractAsyncContextManager[Any] | None = None
        self._cliente: Any = None
        self._candado = asyncio.Lock()

    async def cliente(self) -> Any:
        async with self._candado:
            if self._cliente is None:
                if not rutas.sesion_google().is_file():
                    raise SinSesion(SIN_SESION)
                from notebooklm import NotebookLMClient

                # keepalive mantiene viva la cookie mientras la app está abierta;
                # allow_headless permite recuperar una sesión vencida usando el
                # perfil de navegador que quedó del inicio de sesión.
                contexto = NotebookLMClient.from_storage(keepalive=600, allow_headless=True)
                self._cliente = await contexto.__aenter__()
                self._contexto = contexto
            return self._cliente

    async def cerrar(self) -> None:
        async with self._candado:
            contexto, self._contexto, self._cliente = self._contexto, None, None
        if contexto is not None:
            try:
                await contexto.__aexit__(None, None, None)
            except Exception:  # cerrar nunca debe tapar el error original
                log.debug("error al cerrar el cliente", exc_info=True)


class SinSesion(Exception):
    """No hay archivo de sesión: nunca se inició sesión con Google."""


def explicar(error: BaseException) -> tuple[str, bool]:
    """Devuelve (mensaje para el asistente, si hay que descartar el cliente)."""
    import notebooklm as nlm

    if isinstance(error, SinSesion):
        return str(error), True
    if type(error).__name__ == "RequiredCookieValidationError":
        # La sesión guardada quedó incompleta (inicio de sesión interrumpido o mal detectado).
        return SESION_INCOMPLETA, True
    if isinstance(error, nlm.AuthError):
        return SESION_VENCIDA, True
    if isinstance(error, nlm.MissingDependencyError):
        return f"Falta un componente de notcd: {error}. Reinstala con el instalador.", False
    if isinstance(error, nlm.RateLimitError):
        return (
            "NotebookLM está limitando las solicitudes de esta cuenta (cuota de uso). "
            "Espera unos minutos antes de reintentar; no repitas la operación en bucle."
        ), False
    if isinstance(error, nlm.NotebookLimitError):
        return (
            "La cuenta llegó al máximo de cuadernos o de fuentes que permite su plan de "
            f"NotebookLM ({error}). Hay que borrar algo en notebooklm.google.com o usar otro cuaderno."
        ), False
    if isinstance(error, nlm.NotebookNotFoundError):
        return (
            "No existe ese cuaderno en esta cuenta (o pertenece a otra cuenta de Google). "
            "Usa `listar_cuadernos` para ver los ids correctos."
        ), False
    if isinstance(error, nlm.SourceNotFoundError):
        return "No existe esa fuente en el cuaderno. Usa `ver_cuaderno` para ver los ids de las fuentes.", False
    if isinstance(error, nlm.ArtifactNotFoundError):
        return "No existe ese contenido generado. Usa `obtener_contenido` sin id para listarlos.", False
    if isinstance(error, nlm.NotFoundError):
        return f"NotebookLM no encontró lo pedido: {error}", False
    if isinstance(error, nlm.WaitTimeoutError):
        return (
            "NotebookLM sigue procesando y se acabó el tiempo de espera. No es un error: "
            "consulta de nuevo en un rato (ver_cuaderno u obtener_contenido)."
        ), False
    if isinstance(error, nlm.SourceProcessingError):
        return f"NotebookLM no pudo procesar la fuente: {error}", False
    if isinstance(error, nlm.ValidationError):
        return f"Datos no válidos para NotebookLM: {error}", False
    if isinstance(error, nlm.NetworkError):
        return "No hay conexión con Google en este momento. Revisa internet y reintenta.", False
    if isinstance(error, nlm.NotebookLMError):
        return (
            f"NotebookLM respondió con un error: {error}. Si se repite con operaciones que "
            "antes funcionaban, probablemente Google cambió algo: actualiza con `notcd actualizar`."
        ), False
    if isinstance(error, FileNotFoundError):
        return f"No encontré el archivo: {error.filename or error}", False
    if isinstance(error, PermissionError):
        return f"Sin permiso para leer: {error.filename or error}", False
    return f"Error inesperado ({type(error).__name__}): {error}", False
