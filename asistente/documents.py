"""Extracción por página y OCR opcional; nunca cambia los PDF originales."""

import hashlib
import json
from pathlib import Path
import re
from typing import Callable

import pymupdf

EXTRACTION_VERSION = 2


def discover_pdfs(root: Path) -> list[Path]:
    paths = list(root.glob("*.pdf")) + list(root.glob("*.PDF"))
    folder = root / "documents"
    if folder.exists():
        paths.extend(p for p in folder.rglob("*") if p.suffix.lower() == ".pdf")
    return sorted(set(paths), key=lambda p: str(p).casefold())


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_upload(root: Path, name: str, content: bytes) -> Path:
    name = Path(name.replace("\\", "/")).name
    if not name or Path(name).suffix.lower() != ".pdf":
        raise ValueError("Sólo se aceptan archivos PDF.")
    if len(content) > 30 * 1024 * 1024:
        raise ValueError("El PDF supera el límite de 30 MB.")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass or not len(document):
                raise ValueError("El PDF está vacío o protegido con contraseña.")
    except pymupdf.FileDataError as exc:
        raise ValueError("El archivo no es un PDF válido.") from exc
    folder = root / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if path.exists():
        if path.read_bytes() == content:
            return path
        raise ValueError(f"Ya existe {name} con otro contenido. Renombra el nuevo PDF; no se sobrescribió nada.")
    with path.open("xb") as handle:
        handle.write(content)
    return path


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ").replace("\u00ad", "")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_ocr() -> Callable:
    try:
        from rapidocr_onnxruntime import RapidOCR
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "OCR no instalado. Ejecuta: python -m pip install -r requirements-ocr.txt"
        ) from exc
    # Evita que ONNX monopolice todos los núcleos de una laptop.
    engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)

    def recognize(page: pymupdf.Page) -> str:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        result, _ = engine(image)
        return "\n".join(line[1] for line in result) if result else ""

    return recognize


def extract_document(
    path: Path,
    root: Path,
    prepared_dir: Path,
    ocr: Callable | None = None,
    force: bool = False,
) -> dict:
    sha = file_hash(path)
    cache = prepared_dir / f"{sha}.json"
    if cache.exists() and not force:
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if saved.get("sha256") == sha and saved.get("version") == EXTRACTION_VERSION:
            # Con OCR habilitado reintenta páginas previamente no reconocidas.
            if not ocr or not saved.get("missing_pages"):
                saved["source"] = path.relative_to(root).as_posix()
                return saved
    pages = []
    missing = []
    with pymupdf.open(path) as document:
        if document.needs_pass:
            raise ValueError(f"PDF protegido con contraseña: {path.name}")
        for number, page in enumerate(document, 1):
            text = clean_text(page.get_text(sort=True))
            method = "text"
            # Detecta página escaneada completa o imagen grande con texto parcial.
            image_area = sum(
                abs(pymupdf.Rect(info["bbox"]).get_area())
                for info in page.get_image_info()
            )
            scanned = (
                len(text) < 100
                or (len(text) < 250 and image_area > 0)
                or image_area > page.rect.get_area() * 0.55
            )
            if scanned and ocr is not None:
                recognized = clean_text(ocr(page))
                if len(recognized) > len(text):
                    text, method = recognized, "ocr"
                if len(text) < 100:
                    missing.append(number)
            elif scanned:
                missing.append(number)
            pages.append({"page": number, "text": text, "method": method})
    result = {
        "version": EXTRACTION_VERSION,
        "source": path.relative_to(root).as_posix(),
        "sha256": sha,
        "pages": pages,
        "missing_pages": missing,
        "note": "OCR automático: puede contener errores. Verificar contra el PDF original.",
    }
    prepared_dir.mkdir(parents=True, exist_ok=True)
    temporary = cache.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(cache)
    return result


def split_text(text: str, size: int, overlap: int) -> list[str]:
    if size < 1 or not 0 <= overlap < size:
        raise ValueError("Tamaño o solapamiento inválido.")
    parts = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            # Prefiere párrafo, oración o palabra; evita cortar a mitad de palabra.
            candidates = [text.rfind(sep, start + size // 2, end) for sep in ("\n", ". ", " ")]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + 1
        part = text[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return parts


def chunk_documents(documents: list[dict], size: int, overlap: int) -> list[dict]:
    chunks = []
    for doc in documents:
        for page in doc["pages"]:
            if len(page["text"].strip()) < 40:
                continue
            for number, text in enumerate(split_text(page["text"], size, overlap)):
                identity = f'{doc["source"]}:{doc["sha256"]}:{page["page"]}:{number}'
                chunks.append({
                    "id": hashlib.sha256(identity.encode()).hexdigest(),
                    "text": text,
                    "source": doc["source"],
                    "page": page["page"],
                    "method": page["method"],
                    "part": number,
                })
    return chunks
