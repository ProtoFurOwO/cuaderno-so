"""Regresión de contraste WCAG en Chrome con temas claro y oscuro.

Opt-in: RUN_BROWSER_TESTS=1 python -m pytest tests/test_browser.py -q
No llama a Ollama ni descarga modelos.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

import pytest

from asistente.config import Settings
from asistente.index import build_index
from tests.test_core import FakeClient, pdf_bytes

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_TESTS") != "1",
    reason="Pruebas Chrome opcionales: establece RUN_BROWSER_TESTS=1.",
)
ROOT = Path(__file__).resolve().parents[1]

CONTRAST = """element => {
    const rgba = value => {
        const values = value.match(/[\\d.]+/g).map(Number);
        return [values[0], values[1], values[2], values.length > 3 ? values[3] : 1];
    };
    const over = (front, back) => front.slice(0, 3).map((v, i) => v * front[3] + back[i] * (1 - front[3]));
    const nodes = [];
    for (let node = element; node; node = node.parentElement) nodes.unshift(node);
    let background = [255, 255, 255];
    for (const node of nodes) background = over(rgba(getComputedStyle(node).backgroundColor), background);
    const foreground = over(rgba(getComputedStyle(element).color), background);
    const luminance = color => color.map(v => {
        v /= 255;
        return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    }).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
    const a = luminance(foreground), b = luminance(background);
    return {foreground, background, ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)};
}"""


@contextmanager
def server(root: Path, theme: str):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    palettes = {
        "light": ("#F7F9FC", "#EAF0F8", "#172B49"),
        "dark": ("#0E1117", "#262730", "#FAFAFA"),
    }
    background, secondary, text = palettes[theme]
    env = {**os.environ, "CUADERNO_BROWSER_ROOT": str(root), "PYTHONPATH": str(ROOT)}
    command = [
        sys.executable, "-m", "streamlit", "run", "tests/browser_app.py",
        "--server.headless=true", f"--server.port={port}", "--server.fileWatcherType=none",
        f"--theme.base={theme}", f"--theme.backgroundColor={background}",
        f"--theme.secondaryBackgroundColor={secondary}", f"--theme.textColor={text}",
    ]
    process = subprocess.Popen(
        command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    ready = threading.Event()
    output = []

    def collect_output():
        for line in process.stdout:
            output.append(line)
            if f"127.0.0.1:{port}" in line:
                ready.set()

    threading.Thread(target=collect_output, daemon=True).start()
    try:
        assert ready.wait(30), "Streamlit no inició: " + "".join(output)
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        process.wait(timeout=15)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_answer_user_and_sources_have_readable_contrast(tmp_path, theme):
    playwright = pytest.importorskip("playwright.sync_api")
    (tmp_path / "curso.pdf").write_bytes(pdf_bytes())
    build_index(Settings(root=tmp_path), FakeClient())
    with server(tmp_path, theme) as url, playwright.sync_playwright() as engine:
        browser = engine.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 1000})
            page.goto(url)
            question = "¿Qué administra el sistema operativo?"
            entry = page.get_by_placeholder("Escribe tu pregunta sobre el curso…")
            entry.fill(question)
            entry.press("Enter")
            answer = page.locator(".answer-copy")
            answer.wait_for(timeout=20000)
            source = page.locator('[data-testid="stExpander"]').filter(has_text="pág. 1").first
            source.locator("summary").click()
            targets = {
                "respuesta": answer,
                "pregunta": page.locator('[data-testid="stChatMessage"]').first.locator('[data-testid="stText"]'),
                "fuente": source.locator('[data-testid="stText"]'),
                "título de fuentes": page.get_by_text("Fuentes de la respuesta", exact=True),
            }
            measurements = {}
            for label, target in targets.items():
                target.wait_for(state="visible")
                colors = target.evaluate(CONTRAST)
                assert colors["ratio"] >= 4.5, f"{theme}: {label}: {colors}"
                measurements[label] = colors
            # Captura después de terminar la transición de apertura del acordeón.
            page.evaluate("""() => Promise.all(document.getAnimations()
                .filter(animation => animation.effect?.getComputedTiming().iterations !== Infinity)
                .map(animation => animation.finished.catch(() => {})))""")
            page.screenshot(path=str(tmp_path / f"contrast-{theme}.png"), full_page=True)
            (tmp_path / f"contrast-{theme}.json").write_text(json.dumps(measurements, indent=2), encoding="utf-8")
            if theme == "dark":
                # Control negativo: el fondo blanco anterior debe fallar la misma medición.
                old_style = page.add_style_tag(content='[data-testid="stChatMessage"] {background: white !important;}')
                assert answer.evaluate(CONTRAST)["ratio"] < 4.5
                old_style.evaluate("element => element.remove()")
        finally:
            browser.close()
