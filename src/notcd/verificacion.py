"""Verificación mecánica de citas textuales contra el texto de las fuentes.

Una cita entre comillas en un escrito tiene que estar, palabra por palabra, en
el documento. Esto no depende de ninguna IA: busca cada cita en el texto que
NotebookLM extrajo de las fuentes y dice si está tal cual, si está con
diferencias (y cuáles) o si no está.

Se toleran las diferencias que no son de contenido: tipos de comillas y
guiones, espacios y saltos de línea, y las omisiones marcadas con […] o (...).
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

EQUIVALENCIAS = {
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"', "‟": '"', "″": '"',
    "‘": "'", "’": "'", "‚": "'", "´": "'", "`": "'", "′": "'",
    "–": "-", "—": "-", "‐": "-", "‑": "-", "−": "-",
    "…": "...", "­": "", "​": "", "﻿": "",
}
OMISION = re.compile(r"\s*(?:\[\s*(?:\.\.\.|…)\s*\]|\(\s*(?:\.\.\.|…)\s*\)|\.\.\.|…)\s*")
COMILLAS_EXTERIORES = "\"'«»“”‘’ \n\t"
PALABRA = re.compile(r"\w+", re.UNICODE)
# Dentro de cuántos caracteres tienen que aparecer los tramos de una cita con omisiones.
DISTANCIA_OMISION = 4000
UMBRAL_APROXIMADA = 0.75
CONTEXTO = 140


# ─────────────────────────────────────────────────────────── normalización


def normalizar(texto: str) -> tuple[str, list[int]]:
    """Texto con comillas, guiones y espacios unificados, y la posición original de cada carácter."""
    salida: list[str] = []
    mapa: list[int] = []
    espacio = False
    for i, c in enumerate(texto):
        if c.isspace():
            if not espacio and salida:
                salida.append(" ")
                mapa.append(i)
            espacio = True
            continue
        espacio = False
        for r in EQUIVALENCIAS.get(c, c):
            salida.append(r)
            mapa.append(i)
    while salida and salida[-1] == " ":
        salida.pop()
        mapa.pop()
    return "".join(salida), mapa


def sin_tildes(palabra: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", palabra.lower()) if unicodedata.category(c) != "Mn")


def tramos(cita: str) -> list[str]:
    """La cita sin comillas exteriores, partida en las omisiones […]."""
    limpia, _ = normalizar(cita.strip().strip(COMILLAS_EXTERIORES))
    partes = [p.strip(COMILLAS_EXTERIORES) for p in OMISION.split(limpia)]
    return [p for p in partes if p]


# ───────────────────────────────────────────────────────────────── fuente


@dataclass
class Fuente:
    id: str
    titulo: str
    texto: str
    _norm: str | None = field(default=None, repr=False)
    _mapa: list[int] | None = field(default=None, repr=False)
    _minus: str | None = field(default=None, repr=False)
    _palabras: list[tuple[str, int, int]] | None = field(default=None, repr=False)
    _indice: dict[tuple[str, str, str], list[int]] | None = field(default=None, repr=False)

    @property
    def norm(self) -> str:
        if self._norm is None:
            self._norm, self._mapa = normalizar(self.texto)
        return self._norm

    @property
    def mapa(self) -> list[int]:
        self.norm
        return self._mapa  # type: ignore[return-value]

    @property
    def minus(self) -> str:
        if self._minus is None:
            self._minus = self.norm.lower()
        return self._minus

    @property
    def palabras(self) -> list[tuple[str, int, int]]:
        if self._palabras is None:
            self._palabras = [(sin_tildes(m.group()), m.start(), m.end()) for m in PALABRA.finditer(self.texto)]
        return self._palabras

    @property
    def indice(self) -> dict[tuple[str, str, str], list[int]]:
        if self._indice is None:
            indice: dict[tuple[str, str, str], list[int]] = {}
            p = [w for w, _, _ in self.palabras]
            for i in range(len(p) - 2):
                indice.setdefault((p[i], p[i + 1], p[i + 2]), []).append(i)
            self._indice = indice
        return self._indice

    def original(self, inicio_norm: int, fin_norm: int) -> tuple[int, int]:
        """Convierte un tramo del texto normalizado en posiciones del texto original."""
        return self.mapa[inicio_norm], self.mapa[fin_norm - 1] + 1


# ─────────────────────────────────────────────────────────────── resultado


@dataclass
class Resultado:
    cita: str
    tipo: str  # "exacta", "exacta_mayusculas", "aproximada", "no_encontrada", "vacia"
    fuente: Fuente | None = None
    inicio: int = 0
    fin: int = 0
    similitud: float = 1.0
    diferencias: list[str] = field(default_factory=list)
    omisiones: int = 0

    @property
    def texto_fuente(self) -> str:
        return self.fuente.texto[self.inicio : self.fin] if self.fuente else ""

    def contexto(self) -> str:
        if not self.fuente:
            return ""
        t = self.fuente.texto
        antes = t[max(0, self.inicio - CONTEXTO) : self.inicio]
        despues = t[self.fin : self.fin + CONTEXTO]
        unir = lambda s: " ".join(s.split())  # noqa: E731
        despues = unir(despues)
        separador = "" if despues[:1] in ",.;:)" else " "
        return f"…{unir(antes)} ⟦{unir(self.texto_fuente)}⟧{separador}{despues}…"


# ─────────────────────────────────────────────────────────────── búsqueda


def _buscar_tramos(texto: str, partes: list[str]) -> tuple[int, int] | None:
    """Busca los tramos en orden, cada uno cerca del anterior. Devuelve (inicio, fin) normalizados."""
    primero = partes[0]
    desde = 0
    while (inicio := texto.find(primero, desde)) != -1:
        fin = inicio + len(primero)
        for parte in partes[1:]:
            siguiente = texto.find(parte, fin, fin + DISTANCIA_OMISION + len(parte))
            if siguiente == -1:
                break
            fin = siguiente + len(parte)
        else:
            return inicio, fin
        desde = inicio + 1
    return None


def _exacta(partes: list[str], fuentes: list[Fuente]) -> Resultado | None:
    # Una cita que empieza a mitad de oración suele cambiar la mayúscula inicial:
    # eso no la hace menos literal.
    inicial = partes[0][:1].swapcase() + partes[0][1:]
    variantes = [(partes, False), ([inicial, *partes[1:]], False), ([p.lower() for p in partes], True)]
    for buscadas, minusculas in variantes:
        for f in fuentes:
            texto = f.minus if minusculas else f.norm
            if minusculas and len(texto) != len(f.norm):
                continue  # .lower() cambió largos: las posiciones ya no calzan
            hallado = _buscar_tramos(texto, buscadas)
            if hallado:
                inicio, fin = f.original(*hallado)
                return Resultado(
                    cita="", tipo="exacta_mayusculas" if minusculas else "exacta",
                    fuente=f, inicio=inicio, fin=fin, omisiones=len(partes) - 1,
                )
    return None


def _aproximada(partes: list[str], fuentes: list[Fuente]) -> Resultado | None:
    cita_palabras = [sin_tildes(m.group()) for p in partes for m in PALABRA.finditer(p)]
    n = len(cita_palabras)
    if n < 5:
        return None  # con tan pocas palabras, un parecido no significa nada
    mejor: Resultado | None = None
    for f in fuentes:
        votos: Counter[int] = Counter()
        for j in range(n - 2):
            for pos in f.indice.get((cita_palabras[j], cita_palabras[j + 1], cita_palabras[j + 2]), [])[:60]:
                votos[pos - j] += 1
        for inicio_cand, cuenta in votos.most_common(3):
            if cuenta < 2:
                break
            a = max(0, inicio_cand - 5)
            b = min(len(f.palabras), inicio_cand + n + 5)
            ventana = [w for w, _, _ in f.palabras[a:b]]
            comparador = difflib.SequenceMatcher(None, cita_palabras, ventana, autojunk=False)
            bloques = [bl for bl in comparador.get_matching_blocks() if bl.size]
            if not bloques:
                continue
            iguales = sum(bl.size for bl in bloques)
            primera = a + bloques[0].b
            ultima = a + bloques[-1].b + bloques[-1].size - 1
            largo_fuente = ultima - primera + 1
            similitud = 2 * iguales / (n + largo_fuente)
            if similitud >= UMBRAL_APROXIMADA and (mejor is None or similitud > mejor.similitud):
                inicio = f.palabras[primera][1]
                fin = f.palabras[ultima][2]
                mejor = Resultado(cita="", tipo="aproximada", fuente=f, inicio=inicio, fin=fin, similitud=similitud)
    if mejor:
        mejor.diferencias = diferencias(" ".join(partes), mejor.texto_fuente)
    return mejor


def diferencias(cita: str, real: str, maximo: int = 6) -> list[str]:
    """Las diferencias palabra a palabra, contadas para un abogado."""
    a = PALABRA.findall(cita)
    b = PALABRA.findall(real)
    comparador = difflib.SequenceMatcher(None, [sin_tildes(x) for x in a], [sin_tildes(x) for x in b], autojunk=False)
    salida = []
    for op, i1, i2, j1, j2 in comparador.get_opcodes():
        if op == "equal":
            # Iguales sin tildes pero distintas con tildes: también es una diferencia.
            for x, y in zip(a[i1:i2], b[j1:j2]):
                if x != y and x.lower() != y.lower():
                    salida.append(f"«{x}» en vez de «{y}»")
            continue
        tuyo, fuente = " ".join(a[i1:i2]), " ".join(b[j1:j2])
        if op == "replace":
            salida.append(f"tu cita dice «{tuyo}», la fuente dice «{fuente}»")
        elif op == "delete":
            salida.append(f"sobra «{tuyo}» (no está en la fuente)")
        else:
            salida.append(f"falta «{fuente}»")
    if len(salida) > maximo:
        salida = salida[:maximo] + [f"y {len(salida) - maximo} diferencia(s) más"]
    return salida


def verificar(cita: str, fuentes: list[Fuente]) -> Resultado:
    partes = tramos(cita)
    if not partes:
        return Resultado(cita=cita, tipo="vacia")
    resultado = _exacta(partes, fuentes) or _aproximada(partes, fuentes)
    if resultado is None:
        return Resultado(cita=cita, tipo="no_encontrada")
    resultado.cita = cita
    return resultado


# ──────────────────────────────────────────────────────────────── informe


def informe(resultados: list[Resultado]) -> str:
    conteo = Counter(r.tipo for r in resultados)
    exactas = conteo["exacta"] + conteo["exacta_mayusculas"]
    lineas = [
        f"VERIFICACIÓN DE {len(resultados)} CITA(S) contra el texto de las fuentes: "
        f"{exactas} literal(es), {conteo['aproximada']} con diferencias, {conteo['no_encontrada']} no encontrada(s).",
    ]
    for i, r in enumerate(resultados, 1):
        corta = " ".join(r.cita.strip().strip(COMILLAS_EXTERIORES).split())
        corta = corta if len(corta) <= 160 else corta[:157] + "…"
        lineas.append("")
        if r.tipo in ("exacta", "exacta_mayusculas"):
            matiz = " salvo mayúsculas" if r.tipo == "exacta_mayusculas" else ""
            omis = f" (con {r.omisiones} omisión(es) marcadas, en orden)" if r.omisiones else ""
            lineas.append(f"{i}. ✓ LITERAL{matiz}{omis} — «{r.fuente.titulo}» (fuente_id: {r.fuente.id})")
            lineas.append(f"   Cita: \"{corta}\"")
            lineas.append(f"   En la fuente: {r.contexto()}")
        elif r.tipo == "aproximada":
            lineas.append(
                f"{i}. ≈ CON DIFERENCIAS ({round(r.similitud * 100)} % igual) — «{r.fuente.titulo}» "
                f"(fuente_id: {r.fuente.id}). No la cites así entre comillas."
            )
            lineas.append(f"   Tu cita: \"{corta}\"")
            lineas.append(f"   La fuente dice: \"{' '.join(r.texto_fuente.split())}\"")
            if r.diferencias:
                lineas.append("   Diferencias: " + "; ".join(r.diferencias))
        elif r.tipo == "vacia":
            lineas.append(f"{i}. (cita vacía)")
        else:
            lineas.append(f"{i}. ✗ NO ENCONTRADA en las fuentes revisadas.")
            lineas.append(f"   Cita: \"{corta}\"")
            lineas.append(
                "   Puede ser una paráfrasis, estar en un documento que no está en el cuaderno, "
                "o venir de un escaneo sin texto reconocible. Búscala con buscar_pasajes; "
                "si no aparece, no la pongas entre comillas."
            )
    return "\n".join(lineas)
