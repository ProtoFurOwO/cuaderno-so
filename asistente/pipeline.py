"""Recuperación, generación con evidencia y validación de referencias."""

import json
import re
import time

from asistente.config import Settings
from asistente.index import retrieve
from asistente.ollama_client import OllamaClient, OllamaError

NO_EVIDENCE = "No encontré información suficiente en los documentos."


def validate_answer(raw: str, available_ids: set[int]) -> dict:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise OllamaError("El LLM no devolvió JSON válido. Prueba otro modelo generador.") from exc
    if not isinstance(data, dict) or type(data.get("insufficient")) is not bool:
        raise OllamaError("La respuesta del LLM no cumple el formato esperado.")
    if data["insufficient"]:
        return {"answer": NO_EVIDENCE, "source_ids": [], "insufficient": True}
    answer, ids = data.get("answer"), data.get("source_ids")
    if not isinstance(answer, str) or not answer.strip() or not isinstance(ids, list) or not ids:
        raise OllamaError("El modelo respondió sin evidencia identificable. No mostraré esa respuesta.")
    if any(type(item) is not int or item not in available_ids for item in ids):
        raise OllamaError("El modelo inventó una referencia. No mostraré esa respuesta; revisa los fragmentos.")
    inline = {int(number) for number in re.findall(r"\[(\d+)\]", answer)}
    if not inline.issubset(set(ids)):
        raise OllamaError("El modelo incluyó citas que no coinciden con sus fuentes.")
    answer = answer.strip()
    if not answer.casefold().startswith("según el material del curso"):
        answer = "Según el material del curso:\n\n" + answer
    return {"answer": answer, "source_ids": list(dict.fromkeys(ids)), "insufficient": False}


def answer_question(settings: Settings, question: str, client: OllamaClient | None = None) -> dict:
    question = question.strip()
    if not question:
        raise ValueError("Escribe una pregunta.")
    if len(question) > 2000:
        raise ValueError("Limita la pregunta a 2000 caracteres.")
    start = time.perf_counter()
    client = client or OllamaClient(settings)
    retrieved = retrieve(settings, client, question)
    retrieval_seconds = time.perf_counter() - start
    evidence = [hit for hit in retrieved if hit["similarity"] >= settings.min_similarity]
    generation_seconds = 0.0
    if not evidence:
        validated = {"answer": NO_EVIDENCE, "source_ids": [], "insufficient": True}
        reason = "Los fragmentos no superaron el umbral de similitud. No se llamó al LLM."
    else:
        client.require_model(settings.generation_model)
        context = "\n\n".join(
            f'[{hit["id"]}] Archivo: {hit["source"]}; página PDF: {hit["page"]}\n{hit["text"]}'
            for hit in evidence
        )
        generation_start = time.perf_counter()
        validated = validate_answer(client.generate(question, context), {hit["id"] for hit in evidence})
        generation_seconds = time.perf_counter() - generation_start
        reason = "El LLM indicó evidencia insuficiente." if validated["insufficient"] else "Respuesta con referencias válidas; revisar fidelidad del contenido."
    return {
        **validated,
        "question": question,
        "sources": [hit for hit in evidence if hit["id"] in validated["source_ids"]],
        "retrieved": retrieved,
        "reason": reason,
        "model": settings.generation_model,
        "embedding_model": settings.embedding_model,
        "seconds": round(time.perf_counter() - start, 2),
        "retrieval_seconds": round(retrieval_seconds, 2),
        "generation_seconds": round(generation_seconds, 2),
    }
