"""Configuración portátil: TOML base, TOML local y variables de entorno."""

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    base_url: str = "http://127.0.0.1:11434"
    generation_model: str = "qwen2.5:1.5b"
    embedding_model: str = "embeddinggemma:latest"
    timeout_seconds: int = 240
    keep_alive: str = "5m"
    force_cpu: bool = True
    num_threads: int = 4
    chunk_chars: int = 1000
    chunk_overlap: int = 160
    top_k: int = 4
    min_similarity: float = 0.40
    max_context_chars: int = 4200
    context_tokens: int = 4096
    max_answer_tokens: int = 384

    @property
    def index_dir(self) -> Path:
        return self.root / "data" / "index"

    @property
    def prepared_dir(self) -> Path:
        return self.root / "data" / "prepared"

    def validate(self) -> "Settings":
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("La URL de Ollama debe comenzar con http:// o https://.")
        if not self.generation_model.strip() or not self.embedding_model.strip():
            raise ValueError("Los nombres de modelos no pueden estar vacíos.")
        if not 0 <= self.chunk_overlap < self.chunk_chars:
            raise ValueError("chunk_overlap debe ser menor que chunk_chars y no negativo.")
        if self.chunk_chars < 100 or self.top_k < 1 or self.max_context_chars < 100:
            raise ValueError("Tamaños de fragmentos, contexto y top_k inválidos.")
        if not 0 <= self.min_similarity <= 1:
            raise ValueError("min_similarity debe estar entre 0 y 1.")
        if min(self.timeout_seconds, self.context_tokens, self.max_answer_tokens) < 1:
            raise ValueError("Timeout y límites de tokens deben ser positivos.")
        if type(self.num_threads) is not int or not 1 <= self.num_threads <= 32:
            raise ValueError("num_threads debe ser un entero entre 1 y 32.")
        return self


def load_settings(root: Path = ROOT) -> Settings:
    values = {}
    for name in ("config.toml", "config.local.toml"):
        path = root / name
        if path.exists():
            with path.open("rb") as handle:
                content = tomllib.load(handle)
            for section in ("ollama", "rag"):
                values.update(content.get(section, {}))
    for env, field in {
        "OLLAMA_BASE_URL": "base_url",
        "LLM_MODEL": "generation_model",
        "EMBEDDING_MODEL": "embedding_model",
    }.items():
        if os.environ.get(env):
            values[field] = os.environ[env]
    return Settings(root=root, **values).validate()
