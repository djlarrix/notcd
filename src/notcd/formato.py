"""Cómo se le presenta al asistente lo que devuelve NotebookLM.

Todo es texto plano en español. Las funciones son puras (no llaman a la red)
para poder probarlas sin una cuenta de Google.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Iterable

TIPOS_FUENTE = {
    "PDF": "PDF",
    "DOCX": "Word",
    "POWERPOINT": "PowerPoint",
    "EXCEL": "Excel",
    "CSV": "CSV",
    "EPUB": "EPUB",
    "MARKDOWN": "Markdown",
    "PASTED_TEXT": "texto pegado",
    "WEB_PAGE": "página web",
    "YOUTUBE": "YouTube",
    "GOOGLE_DOCS": "Google Docs",
    "GOOGLE_SLIDES": "Google Slides",
    "GOOGLE_SPREADSHEET": "Google Sheets",
    "GOOGLE_DRIVE": "Google Drive",
    "GOOGLE_DRIVE_AUDIO": "audio de Drive",
    "GOOGLE_DRIVE_VIDEO": "video de Drive",
    "IMAGE": "imagen",
    "MEDIA": "audio/video",
    "GMAIL": "Gmail",
}

ESTADOS_FUENTE = {
    "READY": "lista",
    "PROCESSING": "procesando",
    "PREPARING": "procesando",
    "ERROR": "con error",
}

TIPOS_CONTENIDO = {
    "AUDIO": "resumen en audio",
    "VIDEO": "video",
    "REPORT": "informe",
    "QUIZ": "cuestionario",
    "FLASHCARDS": "tarjetas de estudio",
    "MIND_MAP": "mapa mental",
    "INFOGRAPHIC": "infografía",
    "SLIDE_DECK": "presentación",
    "DATA_TABLE": "tabla de datos",
}

MAX_CITA = 700


def nombre(enum_o_texto: Any) -> str:
    """El nombre de un enum ('PDF') o el texto tal cual."""
    return getattr(enum_o_texto, "name", None) or str(enum_o_texto or "")


def fecha(valor: datetime | None) -> str:
    return valor.strftime("%d-%m-%Y") if valor else "—"


def recortar(texto: str, maximo: int) -> str:
    texto = texto.strip()
    if len(texto) <= maximo:
        return texto
    return texto[:maximo].rstrip() + " […]"


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def nombre_archivo(titulo: str, maximo: int = 60) -> str:
    """Un nombre de archivo legible y seguro en Mac y Windows."""
    limpio = re.sub(r"[^\w\s-]", "", sin_tildes(titulo or "sin-titulo"))
    limpio = re.sub(r"[\s_]+", "-", limpio).strip("-")
    return (limpio[:maximo].rstrip("-") or "sin-titulo")


# ───────────────────────────────────────────────────────────── cuadernos


def cuadernos(lista: Iterable[Any], filtro: str | None = None) -> str:
    lista = list(lista)
    if filtro:
        buscado = sin_tildes(filtro)
        lista = [nb for nb in lista if buscado in sin_tildes(nb.title or "")]
    if not lista:
        return "No hay cuadernos" + (f" cuyo título contenga «{filtro}»." if filtro else " en esta cuenta.")
    lineas = [f"{len(lista)} cuaderno(s) en NotebookLM:"]
    for nb in lista:
        rol = nombre(getattr(nb, "role", None)).lower()
        rol = {"owner": "", "editor": " · compartido (editor)", "viewer": " · compartido (lectura)"}.get(rol, "")
        visto = getattr(nb, "last_viewed_at", None)
        lineas.append(
            f"- «{nb.title or 'sin título'}» — {nb.sources_count} fuente(s){rol}"
            f" · visto {fecha(visto)} · id: {nb.id}"
        )
    return "\n".join(lineas)


def fuentes(lista: Iterable[Any]) -> str:
    lista = list(lista)
    if not lista:
        return "  (sin fuentes todavía)"
    lineas = []
    for i, s in enumerate(lista, 1):
        tipo = TIPOS_FUENTE.get(nombre(s.kind), nombre(s.kind).lower())
        estado = ESTADOS_FUENTE.get(nombre(s.status), nombre(s.status).lower())
        palabras = f" · {s.word_count:,} palabras".replace(",", ".") if getattr(s, "word_count", None) else ""
        aviso = "" if estado == "lista" else f" · {estado.upper()}"
        lineas.append(f"  {i}. «{s.title or 'sin título'}» ({tipo}{palabras}){aviso} · id: {s.id}")
    return "\n".join(lineas)


# ────────────────────────────────────────────────────────────── preguntas


def pasaje_relevante(citado: str, respuesta_texto: str, numero: int, maximo: int = MAX_CITA) -> str:
    """De un fragmento citado largo, el tramo que la respuesta cita junto a [numero].

    NotebookLM a veces marca como «cita» un bloque entero (con fuentes de texto
    pegado, el documento completo). Si la frase de la respuesta trae una cita
    entre comillas, se busca en el bloque y se muestra el tramo alrededor; si no,
    el comienzo del bloque.
    """
    plano = " ".join(citado.split())
    if len(plano) <= maximo:
        return plano
    marcador = re.compile(r"\[(?:\d+\s*,\s*)*%d(?:\s*,\s*\d+)*\]" % numero)
    for m in marcador.finditer(respuesta_texto):
        inicio_linea = respuesta_texto.rfind("\n", 0, m.start()) + 1
        tramo = respuesta_texto[max(inicio_linea, m.start() - 600) : m.start()]
        for entre_comillas in re.findall(r"[«\"“]([^»\"”]{12,})[»\"”]", tramo):
            buscado = " ".join(entre_comillas.split()).strip(" .,;:")
            i = plano.lower().find(buscado.lower())
            if i >= 0:
                margen = min(200, max(0, (maximo - len(buscado)) // 2))
                desde, hasta = max(0, i - margen), min(len(plano), i + len(buscado) + margen)
                return ("[…] " if desde else "") + plano[desde:hasta] + (" […]" if hasta < len(plano) else "")
    return recortar(plano, maximo)


def respuesta(resultado: Any, titulos: dict[str, str], cuaderno: str) -> str:
    """La respuesta de NotebookLM con cada [n] resuelto a su pasaje textual."""
    partes = [
        f"RESPUESTA DE NOTEBOOKLM (Gemini) sobre las fuentes de «{cuaderno}».",
        "Los [n] remiten a las citas de abajo. Es una lectura de las fuentes, no un análisis jurídico.",
        "",
        resultado.answer.strip() or "(NotebookLM no devolvió texto)",
        "",
    ]
    referencias = sorted(resultado.references or [], key=lambda r: r.citation_number or 0)
    if referencias:
        partes.append("CITAS (pasaje textual de la fuente que respalda cada [n]):")
        for ref in referencias:
            titulo = titulos.get(ref.source_id, "fuente sin título")
            texto = (ref.cited_text or "").strip()
            if texto:
                pasaje = f'\n      "{pasaje_relevante(texto, resultado.answer, ref.citation_number or 0)}"'
            else:
                pasaje = "\n      (la cita no trae texto: verifícala con leer_fuente)"
            partes.append(f"  [{ref.citation_number}] «{titulo}» (fuente_id: {ref.source_id}){pasaje}")
    elif "no consta" in sin_tildes(resultado.answer):
        partes.append(
            "Sin citas: NotebookLM dice que no consta, y eso no trae pasaje que citar. "
            "Que no aparezca no prueba que no exista: si importa, confírmalo con buscar_pasajes."
        )
    else:
        partes.append(
            "⚠ SIN CITAS: NotebookLM respondió sin anclar la respuesta en ninguna fuente. "
            "Trátala como no verificada."
        )
    partes.append("")
    partes.append(f"conversacion_id: {resultado.conversation_id} (pásalo para repreguntar en el mismo hilo)")
    sugeridas = [s.question for s in (getattr(resultado, "next_steps", None) or []) if s.question]
    if sugeridas:
        partes.append("Repreguntas que sugiere NotebookLM: " + " | ".join(sugeridas[:4]))
    return "\n".join(partes)


def pasajes(trozos: Iterable[Any], titulos: dict[str, str], consulta: str) -> str:
    trozos = list(trozos)
    if not trozos:
        return f"No encontré pasajes para «{consulta}» en las fuentes del cuaderno."
    lineas = [f"{len(trozos)} pasaje(s) textuales para «{consulta}», del más al menos pertinente:"]
    for i, t in enumerate(trozos, 1):
        titulo = titulos.get(t.source_id, "fuente sin título")
        lineas.append(f"\n{i}. «{titulo}» (fuente_id: {t.source_id})\n   \"{recortar(t.text, 1200)}\"")
    return "\n".join(lineas)


# ──────────────────────────────────────────────────────── contenido generado


def contenidos(lista: Iterable[Any]) -> str:
    lista = list(lista)
    if not lista:
        return "Este cuaderno no tiene contenido generado (informes, audios, mapas, etc.)."
    lineas = [f"{len(lista)} contenido(s) generado(s):"]
    for a in lista:
        tipo = TIPOS_CONTENIDO.get(nombre(a.kind), nombre(a.kind).lower())
        estado = estado_contenido(a)
        lineas.append(f"- {tipo}: «{a.title or 'sin título'}» · {estado} · {fecha(a.created_at)} · id: {a.id}")
    return "\n".join(lineas)


def estado_contenido(artefacto: Any) -> str:
    if artefacto.is_completed:
        return "listo"
    if artefacto.is_failed:
        return "falló"
    return "en preparación"


def arbol(nodo: dict[str, Any] | None, nivel: int = 0) -> str:
    """Un mapa mental {'name', 'children'} como esquema con sangría."""
    if not nodo:
        return ""
    lineas = ["  " * nivel + "- " + str(nodo.get("name", "")).strip()]
    for hijo in nodo.get("children") or []:
        lineas.append(arbol(hijo, nivel + 1))
    return "\n".join(l for l in lineas if l)
