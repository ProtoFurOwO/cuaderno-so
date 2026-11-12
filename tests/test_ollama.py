import pytest

from asistente.config import Settings
from asistente.ollama_client import OllamaClient, OllamaError


def test_embedding_payload_and_cpu(monkeypatch):
    client = OllamaClient(Settings())
    calls = []

    def request(method, endpoint, **kwargs):
        calls.append((endpoint, kwargs["json"]))
        return {"embeddings": [[0.1, 0.2]]}

    monkeypatch.setattr(client, "_request", request)
    assert client.embed(["texto"], keep_alive="5m") == [[0.1, 0.2]]
    assert calls[0][1]["keep_alive"] == "5m"
    assert calls[0][1]["options"]["num_gpu"] == 0
    assert calls[0][1]["truncate"] is False


@pytest.mark.parametrize("endpoint_error", ["/tokenize", "/health"])
def test_tokenizer_recovery_is_bounded(monkeypatch, endpoint_error):
    client = OllamaClient(Settings())
    calls = []

    def request(method, endpoint, **kwargs):
        calls.append(endpoint)
        if endpoint == "/api/generate":
            return {}
        raise OllamaError(f"Ollama HTTP 400: {endpoint_error}: connection reset")

    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(OllamaError):
        client.embed(["texto"])
    assert calls == ["/api/embed", "/api/generate", "/api/embed"]


def test_no_retry_on_configuration_error(monkeypatch):
    client = OllamaClient(Settings())
    calls = []

    def request(method, endpoint, **kwargs):
        calls.append(endpoint)
        raise OllamaError("model not found")

    monkeypatch.setattr(client, "_request", request)
    with pytest.raises(OllamaError):
        client.embed(["texto"])
    assert calls == ["/api/embed"]


@pytest.mark.parametrize("embeddings", [[], [[]], [[float("nan")]], [[0.1], [0.2]]])
def test_invalid_embedding_response(monkeypatch, embeddings):
    client = OllamaClient(Settings())
    monkeypatch.setattr(client, "_request", lambda *args, **kwargs: {"embeddings": embeddings})
    with pytest.raises(OllamaError):
        client.embed(["texto"])
