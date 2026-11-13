"""Crea un ZIP portátil sin entornos, modelos, secretos ni base vectorial."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent


def main():
    files = [ROOT / name for name in (
        "app.py", "manage.py", "empaquetar.py", "config.toml", "README.md",
        "requirements.txt", "requirements-lock.txt", "requirements-dev.txt",
        "requirements-ocr.txt", "requirements-browser.txt", "pytest.ini", "instalar.bat", "iniciar.bat", ".gitignore",
        ".streamlit/config.toml",
    )]
    for folder in ("asistente", "tests", "docs", "evaluation", "documents", "data/prepared"):
        files.extend(path for path in (ROOT / folder).rglob("*") if path.is_file() and path.suffix.lower() in {".py", ".md", ".json", ".pdf"})
    files.extend(ROOT.glob("*.pdf"))
    files = sorted(set(path for path in files if path.exists()))
    output = ROOT / "dist" / "Cuaderno-SO.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, Path("Cuaderno-SO") / path.relative_to(ROOT))
    print(f"ZIP: {output} ({output.stat().st_size / 1024 / 1024:.1f} MB; {len(files)} archivos)")
    print("Incluye PDF y texto extraído del curso. Compartir sólo con permiso; no publicar sin autorización.")
    print("No incluye .venv, modelos de Ollama, índice ni config.local.toml.")


if __name__ == "__main__":
    main()
