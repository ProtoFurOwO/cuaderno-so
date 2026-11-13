"""App de prueba visual: modelos falsos, misma interfaz y componentes reales."""

import os
from importlib import reload
from pathlib import Path
import runpy

import asistente.config as configuration
import asistente.pipeline as pipeline
from asistente.config import Settings
from asistente.ollama_client import OllamaClient
from tests.test_core import FakeClient

ROOT = Path(__file__).resolve().parents[1]
settings = Settings(root=Path(os.environ["CUADERNO_BROWSER_ROOT"]))
configuration.load_settings = lambda: settings
OllamaClient.models = lambda self: []
original_answer = reload(pipeline).answer_question
pipeline.answer_question = lambda config, question: original_answer(config, question, FakeClient())
runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
