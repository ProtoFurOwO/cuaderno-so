from asistente.config import Settings
from asistente.index import build_index, index_status
from tests.test_core import FakeClient, pdf_bytes


def test_rebuild_reuses_vectors_but_switching_embedder_does_not(tmp_path):
    (tmp_path / "curso.pdf").write_bytes(pdf_bytes())
    settings = Settings(root=tmp_path)
    first = build_index(settings, FakeClient())
    # Si se intentara pedir otro embedding, este cliente fallaría.
    second = build_index(settings, FakeClient(fail=True))
    assert first["collection"] != second["collection"]
    assert first["chunks"] == second["chunks"]
    assert index_status(settings)[0]
