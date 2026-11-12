"""Índice persistente de Chroma con invalidación por contenido y embeddings."""

import hashlib
import json
import math
from pathlib import Path
import sqlite3
from typing import Callable
import uuid

from asistente.config import Settings
from asistente.documents import (
    EXTRACTION_VERSION, chunk_documents, discover_pdfs, extract_document, file_hash, make_ocr,
)
from asistente.ollama_client import OllamaClient, OllamaError, normalized_name

INDEX_VERSION = 1


class IndexErrorLocal(RuntimeError):
    pass


def read_manifest(settings: Settings) -> dict | None:
    path = settings.index_dir / "manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise IndexErrorLocal("No pude leer el índice. Vuelve a construirlo desde la barra lateral.") from exc


def corpus_signature(settings: Settings) -> str:
    files = []
    for path in discover_pdfs(settings.root):
        sha = file_hash(path)
        prepared = settings.prepared_dir / f"{sha}.json"
        files.append({
            "source": path.relative_to(settings.root).as_posix(),
            "sha256": sha,
            "prepared_sha256": file_hash(prepared) if prepared.exists() else None,
        })
    payload = {
        "version": INDEX_VERSION,
        "extraction_version": EXTRACTION_VERSION,
        "embedding_model": normalized_name(settings.embedding_model),
        "chunk_chars": settings.chunk_chars,
        "chunk_overlap": settings.chunk_overlap,
        "files": files,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def index_status(settings: Settings) -> tuple[bool, str, dict | None]:
    manifest = read_manifest(settings)
    if not manifest:
        return False, "Todavía no hay índice. Pulsa «Preparar documentos».", None
    if manifest.get("signature") != corpus_signature(settings):
        return False, "Cambió el material, los fragmentos o el modelo de embeddings. Reconstruye el índice.", manifest
    return True, "Índice listo", manifest


def chroma_client(settings: Settings):
    # Importación diferida: diagnóstico y extracción no necesitan cargar Chroma.
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    settings.index_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(settings.index_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def embedding_input(text: str, model: str, query: bool, title: str = "none") -> str:
    lower = model.lower()
    if "embeddinggemma" in lower:
        return f"task: search result | query: {text}" if query else f"title: {title} | text: {text}"
    if "e5" in lower:
        return f"query: {text}" if query else f"passage: {text}"
    if "nomic-embed-text" in lower:
        return f"search_query: {text}" if query else f"search_document: {text}"
    return text


def prepare_documents(settings: Settings, use_ocr: bool = False, progress: Callable | None = None) -> list[dict]:
    paths = discover_pdfs(settings.root)
    if not paths:
        raise IndexErrorLocal("No hay PDF. Agrega archivos en documents/ o en la raíz del proyecto.")
    ocr = make_ocr() if use_ocr else None
    documents = []
    for number, path in enumerate(paths):
        if progress:
            progress(number / len(paths), f"Leyendo {path.name}")
        documents.append(extract_document(path, settings.root, settings.prepared_dir, ocr=ocr))
    return documents


def build_index(settings: Settings, client: OllamaClient, use_ocr: bool = False, progress: Callable | None = None) -> dict:
    model = client.require_model(settings.embedding_model)
    documents = prepare_documents(settings, use_ocr, progress)
    build_signature = corpus_signature(settings)
    chunks = chunk_documents(documents, settings.chunk_chars, settings.chunk_overlap)
    if not chunks:
        raise IndexErrorLocal("No se extrajo texto suficiente. Prueba OCR; los PDF pueden ser imágenes.")
    database = chroma_client(settings)
    # No reemplaza el índice activo hasta que todo el nuevo índice esté completo.
    name = "course_" + uuid.uuid4().hex
    collection = database.create_collection(
        name=name, metadata={"hnsw:space": "cosine"}, embedding_function=None,
    )
    cache = sqlite3.connect(settings.index_dir / "embedding-cache.sqlite3")
    cache.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, vector TEXT NOT NULL)")
    try:
        # Una entrada por petición: menor pico de RAM y evita fallos de batching
        # observados con EmbeddingGemma en el runner de Ollama para Windows.
        batch_size = 1
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            if progress:
                progress(start / len(chunks), f"Generando embeddings {start + 1}–{start + len(batch)} de {len(chunks)}")
            inputs = [
                embedding_input(item["text"], settings.embedding_model, False, Path(item["source"]).stem)
                for item in batch
            ]
            cache_key = hashlib.sha256(json.dumps([
                normalized_name(settings.embedding_model), model.get("digest", ""), inputs,
            ], ensure_ascii=False).encode()).hexdigest()
            saved = cache.execute("SELECT vector FROM vectors WHERE key = ?", (cache_key,)).fetchone()
            if saved:
                vectors = json.loads(saved[0])
            else:
                vectors = client.embed(inputs, keep_alive="5m")
                cache.execute("INSERT OR REPLACE INTO vectors VALUES (?, ?)", (cache_key, json.dumps(vectors)))
                cache.commit()
            collection.add(
                ids=[item["id"] for item in batch],
                documents=[item["text"] for item in batch],
                embeddings=vectors,
                metadatas=[{key: item[key] for key in ("source", "page", "method", "part")} for item in batch],
            )
        if corpus_signature(settings) != build_signature:
            raise IndexErrorLocal("El material cambió mientras se construía el índice. Vuelve a preparar documentos.")
        manifest = {
            "version": INDEX_VERSION,
            "signature": build_signature,
            "collection": name,
            "embedding_model": normalized_name(settings.embedding_model),
            "embedding_digest": model.get("digest", ""),
            "chunks": len(chunks),
            "documents": [{
                "source": doc["source"],
                "sha256": doc["sha256"],
                "pages": len(doc["pages"]),
                "ocr_pages": sum(page["method"] == "ocr" for page in doc["pages"]),
                "missing_pages": doc["missing_pages"],
            } for doc in documents],
        }
        target = settings.index_dir / "manifest.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
    except Exception:
        # Sólo se borra la colección temporal que creó esta ejecución.
        database.delete_collection(name)
        raise
    finally:
        cache.close()
        if settings.keep_alive == "0":
            try:
                client.unload(settings.embedding_model)
            except OllamaError:
                # No ocultar un fallo de construcción por un fallo al liberar RAM.
                pass
    if progress:
        progress(1.0, "Índice listo")
    return manifest


def retrieve(settings: Settings, client: OllamaClient, question: str) -> list[dict]:
    ready, reason, manifest = index_status(settings)
    if not ready:
        raise IndexErrorLocal(reason)
    model = client.require_model(settings.embedding_model)
    if model.get("digest", "") != manifest.get("embedding_digest", ""):
        raise IndexErrorLocal("El modelo de embeddings cambió de versión. Reconstruye el índice.")
    try:
        collection = chroma_client(settings).get_collection(
            name=manifest["collection"], embedding_function=None,
        )
    except Exception as exc:
        raise IndexErrorLocal("La base vectorial no está disponible. Reconstruye el índice.") from exc
    vector = client.embed([embedding_input(question, settings.embedding_model, True)])[0]
    results = collection.query(
        query_embeddings=[vector], n_results=min(collection.count(), settings.top_k * 3),
        include=["documents", "metadatas", "distances"],
    )
    candidates = list(zip(results["documents"][0], results["metadatas"][0], results["distances"][0]))
    # Una página correcta no basta si la respuesta está en el fragmento siguiente.
    # Completa la continuidad del mejor resultado sin volver a generar embeddings.
    if candidates and not candidates[0][0].rstrip().endswith((".", "!", "?")):
        best = candidates[0][1]
        neighbor = collection.get(where={"$and": [
            {"source": {"$eq": best["source"]}},
            {"page": {"$eq": best["page"]}},
            {"part": {"$eq": best["part"] + 1}},
        ]}, include=["documents", "metadatas", "embeddings"])
        if neighbor["documents"]:
            neighbor_vector = neighbor["embeddings"][0]
            denominator = math.sqrt(sum(x * x for x in vector) * sum(x * x for x in neighbor_vector))
            similarity = float(sum(a * b for a, b in zip(vector, neighbor_vector)) / denominator) if denominator else 0.0
            neighbor_text = neighbor["documents"][0]
            neighbor_meta = {**neighbor["metadatas"][0], "neighbor": True}
            candidates = [candidates[0], (neighbor_text, neighbor_meta, 1 - similarity)] + [
                item for item in candidates[1:] if item[0] != neighbor_text
            ]
    hits = []
    seen = set()
    used_chars = 0
    for text, meta, distance in candidates:
        if text in seen:
            continue
        remaining = settings.max_context_chars - used_chars
        if remaining < 100:
            break
        text = text[:remaining]
        hits.append({**meta, "text": text, "similarity": round(1 - distance, 4), "id": len(hits) + 1})
        used_chars += len(text)
        seen.add(text)
        if len(hits) >= settings.top_k:
            break
    return hits
