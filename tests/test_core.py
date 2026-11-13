from dataclasses import replace
import json
from types import SimpleNamespace

import pymupdf
import pytest

from asistente.config import Settings, load_settings
from asistente.documents import chunk_documents, clean_text, discover_pdfs, extract_document, save_upload, split_text
from asistente.index import IndexErrorLocal, build_index, corpus_signature, embedding_input, index_status, read_manifest, retrieve
from asistente.ollama_client import OllamaError, normalized_name
from asistente.pipeline import NO_EVIDENCE, answer_question, validate_answer


def pdf_bytes(text="El sistema operativo administra los recursos del equipo. " * 8):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox((40, 40, 550, 700), text)
    content = doc.tobytes()
    doc.close()
    return content


@pytest.fixture
def settings(tmp_path):
    (tmp_path / "curso.pdf").write_bytes(pdf_bytes())
    return Settings(root=tmp_path)


class FakeClient:
    def __init__(self, fail=False, digest="test-digest"):
        self.fail = fail
        self.digest = digest

    def require_model(self, name):
        return {"name": name, "digest": self.digest}

    def unload(self, model):
        pass

    def embed(self, texts, keep_alive=None):
        if self.fail:
            raise OllamaError("fallo simulado")
        return [[1.0, 0.0, 0.0] for _ in texts]

    def generate(self, question, context):
        return json.dumps({"answer": "Según el material del curso, administra recursos. [1]", "source_ids": [1], "insufficient": False})


def test_config_overrides_and_environment(tmp_path, monkeypatch):
    for key in ("LLM_MODEL", "EMBEDDING_MODEL", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    (tmp_path / "config.toml").write_text('[ollama]\ngeneration_model="base"\n[rag]\ntop_k=2\n')
    (tmp_path / "config.local.toml").write_text('[ollama]\ngeneration_model="local"\n')
    assert load_settings(tmp_path).generation_model == "local"
    monkeypatch.setenv("LLM_MODEL", "environment")
    result = load_settings(tmp_path)
    assert result.generation_model == "environment"
    assert result.top_k == 2


@pytest.mark.parametrize("values", [
    {"chunk_chars": 100, "chunk_overlap": 100}, {"top_k": 0},
    {"min_similarity": 1.1}, {"base_url": "file:///test"}, {"generation_model": ""},
    {"num_threads": 0}, {"num_threads": 33}, {"num_threads": True},
])
def test_invalid_config(values):
    with pytest.raises(ValueError):
        replace(Settings(), **values).validate()


def test_split_limits_and_full_coverage():
    text = " ".join(f"palabra{number}" for number in range(150))
    parts = split_text(text, 150, 30)
    assert all(0 < len(part) <= 150 for part in parts)
    assert all(word in " ".join(parts) for word in text.split())
    assert parts[-1].endswith("palabra149")
    assert split_text("", 100, 10) == []
    with pytest.raises(ValueError):
        split_text("test", 100, 100)


def test_clean_text():
    assert clean_text("  alma-\ncenamiento\x00  de\t datos  ") == "almacenamiento de datos"


def test_extract_and_cache(settings):
    path = settings.root / "curso.pdf"
    first = extract_document(path, settings.root, settings.prepared_dir)
    second = extract_document(path, settings.root, settings.prepared_dir)
    assert first == second
    assert len(first["pages"]) == 1
    assert first["pages"][0]["page"] == 1
    assert "recursos" in first["pages"][0]["text"]
    chunks = chunk_documents([first], 150, 30)
    assert all(chunk["page"] == 1 for chunk in chunks)
    assert len({chunk["id"] for chunk in chunks}) == len(chunks)


def test_ocr_cache_portable_and_missing_coverage(tmp_path):
    document = pymupdf.open()
    document.new_page()
    path = tmp_path / "scan.pdf"
    document.save(path)
    document.close()
    prepared = tmp_path / "data" / "prepared"
    plain = extract_document(path, tmp_path, prepared)
    assert plain["missing_pages"] == [1]
    with_ocr = extract_document(path, tmp_path, prepared, ocr=lambda page: "Texto reconocido " * 20)
    assert with_ocr["missing_pages"] == []
    assert with_ocr["pages"][0]["method"] == "ocr"
    assert extract_document(path, tmp_path, prepared) == with_ocr


def test_upload_safe_and_no_overwrite(tmp_path):
    data = pdf_bytes()
    saved = save_upload(tmp_path, "../../archivo.pdf", data)
    assert saved == tmp_path / "documents" / "archivo.pdf"
    assert save_upload(tmp_path, "archivo.pdf", data) == saved
    with pytest.raises(ValueError, match="Ya existe"):
        save_upload(tmp_path, "archivo.pdf", pdf_bytes("otro contenido"))
    with pytest.raises(ValueError):
        save_upload(tmp_path, "no.pdf", b"no es pdf")
    with pytest.raises(ValueError):
        save_upload(tmp_path, "archivo.docx", data)
    assert discover_pdfs(tmp_path) == [saved]


def test_generator_change_preserves_index_signature(settings):
    assert corpus_signature(settings) == corpus_signature(replace(settings, generation_model="otro-modelo"))
    assert corpus_signature(settings) == corpus_signature(replace(settings, keep_alive="0", num_threads=2))
    assert corpus_signature(settings) != corpus_signature(replace(settings, embedding_model="otro-embedding"))
    assert corpus_signature(settings) != corpus_signature(replace(settings, chunk_chars=500))


def test_build_retrieve_and_staleness(settings):
    manifest = build_index(settings, FakeClient())
    assert manifest["chunks"] > 0
    assert index_status(settings)[0]
    hits = retrieve(settings, FakeClient(), "¿Qué hace el sistema operativo?")
    assert hits[0]["page"] == 1
    assert hits[0]["similarity"] == pytest.approx(1.0)
    assert index_status(replace(settings, generation_model="otro"))[0]
    with pytest.raises(IndexErrorLocal, match="versión"):
        retrieve(settings, FakeClient(digest="new-digest"), "pregunta")
    assert not index_status(replace(settings, embedding_model="otro"))[0]
    (settings.root / "nuevo.pdf").write_bytes(pdf_bytes())
    assert not index_status(settings)[0]


def test_failed_build_preserves_active_manifest(settings):
    previous = build_index(settings, FakeClient())
    with pytest.raises(OllamaError):
        build_index(settings, FakeClient(fail=True, digest="uncached-version"))
    assert read_manifest(settings) == previous
    assert index_status(settings)[0]


def test_material_change_during_build_does_not_publish(settings):
    class MutatingClient(FakeClient):
        def embed(self, texts, keep_alive=None):
            (settings.root / "nuevo.pdf").write_bytes(pdf_bytes())
            return super().embed(texts, keep_alive)

    with pytest.raises(IndexErrorLocal, match="cambió"):
        build_index(settings, MutatingClient())
    assert read_manifest(settings) is None


def test_retrieval_completes_a_cut_list_with_neighbor(settings, monkeypatch):
    build_index(settings, FakeClient())
    meta = {"source": "curso.pdf", "page": 1, "part": 0, "method": "text"}
    collection = SimpleNamespace(
        count=lambda: 2,
        query=lambda **kwargs: {
            "documents": [["Los servicios son:"]],
            "metadatas": [[meta]], "distances": [[0.1]],
        },
        get=lambda **kwargs: {
            "documents": ["Procesamiento por lotes, transacciones y tiempo compartido."],
            "metadatas": [{**meta, "part": 1}], "embeddings": [[1.0, 0.0, 0.0]],
        },
    )
    monkeypatch.setattr("asistente.index.chroma_client", lambda config: SimpleNamespace(get_collection=lambda **kwargs: collection))
    hits = retrieve(settings, FakeClient(), "¿Qué servicios ofrece?")
    assert hits[1]["neighbor"] is True
    assert hits[1]["similarity"] == 1.0
    assert "transacciones" in hits[1]["text"]


def test_pipeline_integration_with_fake_models(settings):
    build_index(settings, FakeClient())
    result = answer_question(settings, "¿Qué administra?", FakeClient())
    assert not result["insufficient"]
    assert result["sources"][0]["page"] == 1
    assert result["model"] == settings.generation_model


def test_pipeline_abstains_without_generation(settings, monkeypatch):
    monkeypatch.setattr("asistente.pipeline.retrieve", lambda *args: [{"id": 1, "similarity": 0.1}])
    result = answer_question(settings, "pastel", client=object())
    assert result["answer"] == NO_EVIDENCE
    assert result["generation_seconds"] == 0
    assert result["sources"] == []


@pytest.mark.parametrize("question", ["", " " * 4, "a" * 2001])
def test_question_validation(settings, question):
    with pytest.raises(ValueError):
        answer_question(settings, question)


@pytest.mark.parametrize("payload", [
    "no json", "[]", '{"insufficient":"false"}',
    '{"insufficient":false,"answer":"Inventado","source_ids":[]}',
    '{"insufficient":false,"answer":"Inventado","source_ids":[99]}',
    '{"insufficient":false,"answer":"Texto [2]","source_ids":[1]}',
    '{"insufficient":false,"answer":"Texto","source_ids":[true]}',
])
def test_reject_invalid_answers(payload):
    with pytest.raises(OllamaError):
        validate_answer(payload, {1})


def test_valid_answer_and_abstention():
    accepted = validate_answer('{"insufficient":false,"answer":"Texto [1]","source_ids":[1,1]}', {1})
    assert accepted["source_ids"] == [1]
    assert validate_answer('{"insufficient":true}', {1})["answer"] == NO_EVIDENCE


def test_embedding_prompts():
    assert embedding_input("hola", "embeddinggemma", True) == "task: search result | query: hola"
    assert embedding_input("hola", "embeddinggemma", False, "curso") == "title: curso | text: hola"
    assert normalized_name("embeddinggemma") == "embeddinggemma:latest"
    assert normalized_name("qwen2.5:1.5b") == "qwen2.5:1.5b"
