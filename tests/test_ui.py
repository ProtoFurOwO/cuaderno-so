from pathlib import Path

from streamlit.testing.v1 import AppTest

from asistente.config import Settings
from asistente.index import build_index, read_manifest
from asistente.pipeline import answer_question
from tests.test_core import FakeClient, pdf_bytes


def test_empty_app_and_no_ollama(tmp_path, monkeypatch):
    monkeypatch.setattr("asistente.config.load_settings", lambda: Settings(root=tmp_path))
    monkeypatch.setattr("asistente.ollama_client.OllamaClient.models", lambda self: [])
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    app.run(timeout=20)
    assert not app.exception
    assert any("Pregunta a tus apuntes" in item.value for item in app.title)
    assert app.chat_input[0].disabled


def test_chat_sources_preview_and_model_switch(tmp_path, monkeypatch):
    settings = Settings(root=tmp_path)
    (tmp_path / "curso.pdf").write_bytes(pdf_bytes())
    original = build_index(settings, FakeClient())
    monkeypatch.setattr("asistente.config.load_settings", lambda: settings)
    monkeypatch.setattr("asistente.ollama_client.OllamaClient.models", lambda self: [{"name": "qwen2.5:0.5b"}])
    monkeypatch.setattr("asistente.pipeline.answer_question", lambda config, question: answer_question(config, question, FakeClient()))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    app.run(timeout=20)
    assert not app.chat_input[0].disabled
    app.selectbox[0].select("qwen2.5:0.5b").run(timeout=20)
    app.chat_input[0].set_value("¿Qué administra el sistema operativo?").run(timeout=20)
    assert not app.exception
    assert len(app.session_state["messages"]) == 2
    app.run(timeout=20)
    assert len(app.chat_message) == 2
    assert any("qwen2.5:0.5b" in item.value for item in app.caption)
    previews = [item for item in app.checkbox if item.label == "Ver página original"]
    assert previews
    previews[0].check().run(timeout=20)
    assert not app.exception
    assert read_manifest(settings)["collection"] == original["collection"]
