"""Genera extension/icon.png: dos círculos que se cruzan (el asistente y NotebookLM).

Sin dependencias: escribe el PNG a mano. Se corre una vez; el ícono va al repo.
"""

import math
import struct
import zlib
from pathlib import Path

LADO = 512
FONDO = (31, 36, 48)
ASISTENTE = (217, 119, 87)
GOOGLE = (66, 133, 244)
RADIO_ESQUINA = 110
R = 130
C1 = (LADO / 2 - 72, LADO / 2)
C2 = (LADO / 2 + 72, LADO / 2)


def dentro_esquinas(x: float, y: float) -> float:
    """Cobertura (0-1) del cuadrado de esquinas redondeadas, con antialias."""
    cx = min(max(x, RADIO_ESQUINA), LADO - RADIO_ESQUINA)
    cy = min(max(y, RADIO_ESQUINA), LADO - RADIO_ESQUINA)
    d = math.hypot(x - cx, y - cy)
    return max(0.0, min(1.0, RADIO_ESQUINA - d + 0.5))


def circulo(x: float, y: float, c: tuple[float, float]) -> float:
    return max(0.0, min(1.0, R - math.hypot(x - c[0], y - c[1]) + 0.5))


def mezclar(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


filas = []
for y in range(LADO):
    fila = bytearray([0])
    for x in range(LADO):
        px, py = x + 0.5, y + 0.5
        color = FONDO
        a1, a2 = circulo(px, py, C1), circulo(px, py, C2)
        color = mezclar(color, ASISTENTE, a1 * 0.95)
        color = mezclar(color, GOOGLE, a2 * 0.80)
        if a1 and a2:  # la intersección: lo que hacen juntas, en blanco
            color = mezclar(color, (250, 250, 250), min(a1, a2) * 0.92)
        alfa = dentro_esquinas(px, py)
        fila += bytes([round(color[0]), round(color[1]), round(color[2]), round(alfa * 255)])
    filas.append(bytes(fila))


def trozo(tipo: bytes, datos: bytes) -> bytes:
    return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)


png = b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", LADO, LADO, 8, 6, 0, 0, 0))
png += trozo(b"IDAT", zlib.compress(b"".join(filas), 9)) + trozo(b"IEND", b"")
destino = Path(__file__).resolve().parents[1] / "extension" / "icon.png"
destino.write_bytes(png)
print(f"{destino} ({len(png)} bytes)")
