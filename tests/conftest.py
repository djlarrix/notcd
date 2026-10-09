"""Un NotebookLM falso para probar el servidor sin cuenta de Google ni red."""

import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

# Antes de importar notcd: nada de las pruebas debe tocar el ~/.notcd real.
_CASA = Path(tempfile.mkdtemp(prefix="notcd-pruebas-"))
os.environ["NOTCD_HOME"] = str(_CASA / ".notcd")
os.environ["NOTCD_DESCARGAS"] = str(_CASA / "descargas")
os.environ.pop("NOTEBOOKLM_HOME", None)

import notebooklm as nlm  # noqa: E402
import pytest  # noqa: E402

from notcd import server  # noqa: E402


TEXTOS = {
    "f1": SimpleNamespace(
        title="Demanda.pdf",
        rendered_content="En lo principal: demanda. La demanda fue notificada con fecha 3 de marzo de 2025 "
        "al demandado en su domicilio, según consta a fojas 12.",
        content="",
    ),
    "f2": SimpleNamespace(title="Contestación.pdf", rendered_content="El demandado niega los hechos.", content=""),
}


@dataclass
class Fuente:
    id: str
    title: str
    kind: object = nlm.SourceType.PDF
    status: object = nlm.SourceStatus.READY
    word_count: int | None = 1200


@dataclass
class Artefacto:
    id: str
    title: str
    kind: object
    estado: str = "completed"
    created_at: datetime | None = field(default_factory=lambda: datetime(2026, 10, 7, tzinfo=timezone.utc))

    @property
    def is_completed(self):
        return self.estado == "completed"

    @property
    def is_failed(self):
        return self.estado == "failed"


class Llamadas(list):
    def __call__(self, nombre, *args, **kwargs):
        self.append((nombre, args, kwargs))


def asincrona(llamadas, nombre, resultado):
    async def fn(*args, **kwargs):
        llamadas(nombre, *args, **kwargs)
        return resultado(*args, **kwargs) if callable(resultado) else resultado

    return fn


@pytest.fixture
def falso(monkeypatch):
    """Reemplaza la conexión por un cliente falso y devuelve (cliente, llamadas)."""
    llamadas = Llamadas()
    fuentes = [Fuente("f1", "Demanda.pdf"), Fuente("f2", "Contestación.pdf", status=nlm.SourceStatus.PROCESSING)]
    nb = SimpleNamespace(id="nb1", title="Pérez con Banco", sources_count=2, role=None, last_viewed_at=None)

    def respuesta(*_, **__):
        return SimpleNamespace(
            answer="La demanda se notificó el 3 de marzo [1].",
            conversation_id="conv-1",
            references=[SimpleNamespace(citation_number=1, source_id="f1", cited_text="notificada con fecha 3 de marzo de 2025")],
            next_steps=[SimpleNamespace(question="¿Y la contestación?")],
        )

    def descargar_texto(texto):
        def fn(_cuaderno, ruta, *_, **__):
            Path(ruta).write_text(texto, encoding="utf-8")
            return ruta

        return fn

    cliente = SimpleNamespace(
        notebooks=SimpleNamespace(
            list=asincrona(llamadas, "notebooks.list", [nb]),
            get=asincrona(llamadas, "notebooks.get", nb),
            create=asincrona(llamadas, "notebooks.create", lambda titulo: SimpleNamespace(id="nb2", title=titulo)),
            get_description=asincrona(
                llamadas, "notebooks.get_description",
                SimpleNamespace(summary="Juicio ordinario de cobro.", suggested_topics=[SimpleNamespace(question="¿Plazos?")]),
            ),
        ),
        sources=SimpleNamespace(
            list=asincrona(llamadas, "sources.list", fuentes),
            add_file=asincrona(llamadas, "sources.add_file", lambda nb_id, ruta, **_: Fuente("n-" + Path(ruta).stem, Path(ruta).name)),
            add_url=asincrona(llamadas, "sources.add_url", lambda nb_id, url, **_: Fuente("u1", url)),
            add_text=asincrona(llamadas, "sources.add_text", lambda nb_id, titulo, texto, **_: Fuente("t1", titulo)),
            wait_all_until_ready=asincrona(
                llamadas, "sources.wait_all_until_ready",
                lambda nb_id, ids, **_: [nlm.SourceTimeoutError(i, 45.0) if i == "u1" else Fuente(i, i) for i in ids],
            ),
            search=asincrona(llamadas, "sources.search", [SimpleNamespace(source_id="f1", text="notificada con fecha 3 de marzo", rank=1)]),
            get_fulltext=asincrona(llamadas, "sources.get_fulltext", lambda nb_id, sid, **_: TEXTOS[sid]),
            delete=asincrona(llamadas, "sources.delete", None),
        ),
        chat=SimpleNamespace(
            ask=asincrona(llamadas, "chat.ask", respuesta),
            configure=asincrona(llamadas, "chat.configure", None),
        ),
        sharing=SimpleNamespace(add_user=asincrona(llamadas, "sharing.add_user", None)),
        research=SimpleNamespace(
            discover=asincrona(
                llamadas, "research.discover",
                SimpleNamespace(
                    summary="Panorama.",
                    sources=[SimpleNamespace(title="Ley Chile", url="https://www.bcn.cl/leychile/x")],
                ),
            )
        ),
        notes=SimpleNamespace(
            list=asincrona(llamadas, "notes.list", []),
            create=asincrona(llamadas, "notes.create", lambda nb_id, titulo, contenido: SimpleNamespace(id="n1", title=titulo)),
        ),
        artifacts=SimpleNamespace(
            generate_report=asincrona(
                llamadas, "artifacts.generate_report", SimpleNamespace(task_id="a1", is_failed=False, error=None)
            ),
            generate_audio=asincrona(
                llamadas, "artifacts.generate_audio", SimpleNamespace(task_id="a2", is_failed=False, error=None)
            ),
            poll_status=asincrona(llamadas, "artifacts.poll_status", SimpleNamespace(is_complete=True, is_failed=False)),
            get=asincrona(
                llamadas, "artifacts.get",
                lambda nb_id, aid: Artefacto(aid, "Minuta", nlm.ArtifactType.REPORT if aid == "a1" else nlm.ArtifactType.AUDIO),
            ),
            list=asincrona(llamadas, "artifacts.list", [Artefacto("a1", "Minuta", nlm.ArtifactType.REPORT)]),
            download_report=asincrona(llamadas, "artifacts.download_report", descargar_texto("# Minuta\nHechos.")),
            download_audio=asincrona(llamadas, "artifacts.download_audio", descargar_texto("audio")),
        ),
    )

    async def obtener():
        return cliente

    monkeypatch.setattr(server.conexion, "cliente", obtener)
    monkeypatch.setattr(server, "dormir", _sin_espera)
    server._titulos.clear()
    server._nombres_cuaderno.clear()
    return cliente, llamadas


async def _sin_espera(_segundos):
    return None


@pytest.fixture
def casa_temporal(tmp_path, monkeypatch):
    """Un HOME falso para probar la escritura de configuraciones de las apps."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    if sys.platform == "win32":
        monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    return tmp_path
