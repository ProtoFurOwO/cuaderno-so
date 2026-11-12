"""Herramientas de preparación, diagnóstico y evaluación reproducible."""

import argparse
from dataclasses import replace
import json
import platform
import sys

from asistente.config import load_settings
from asistente.index import build_index, index_status, prepare_documents, retrieve
from asistente.ollama_client import OllamaClient
from asistente.pipeline import answer_question


def evaluate(settings, client, limit: int, retrieval_only: bool) -> dict:
    cases = json.loads((settings.root / "evaluation" / "questions.json").read_text(encoding="utf-8"))
    rows = []
    for case in cases[:limit or len(cases)]:
        print(f'Probando: {case["question"]}', flush=True)
        try:
            if retrieval_only:
                hits = retrieve(settings, client, case["question"])
                result = {"retrieved": hits}
            else:
                result = answer_question(settings, case["question"], client)
            expected = case.get("expected_pages", [])
            match = any(
                hit["page"] in expected and case.get("source_contains", "") in hit["source"]
                for hit in result["retrieved"]
            ) if expected else None
            row = {"case": case, "retrieval_hit": match, "result": result}
            if not retrieval_only:
                row["abstention_correct"] = result["insufficient"] == (not case["answerable"])
            rows.append(row)
        except Exception as exc:
            rows.append({"case": case, "error": str(exc)})
    positives = [row for row in rows if row["case"]["answerable"]]
    negatives = [row for row in rows if not row["case"]["answerable"]]
    return {
        "generation_model": settings.generation_model,
        "embedding_model": settings.embedding_model,
        "retrieval_only": retrieval_only,
        "summary": {
            "cases": len(rows),
            "errors": sum("error" in row for row in rows),
            "retrieval_hit_rate_at_k": sum(row.get("retrieval_hit") is True for row in positives) / len(positives) if positives else None,
            "out_of_scope_abstention_rate": sum(row.get("result", {}).get("insufficient") is True for row in negatives) / len(negatives) if negatives and not retrieval_only else None,
        },
        "note": "Retrieval hit rate cuenta coincidencias con páginas esperadas; no mide fidelidad ni exactitud de la respuesta. Revisión humana necesaria.",
        "rows": rows,
    }


def main() -> int:
    # PowerShell puede abrir stdout en cp1252; las respuestas pueden incluir
    # símbolos Unicode que no existen en esa codificación.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Asistente RAG local del curso")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Verificar Python, Ollama, modelos e índice")
    for name in ("prepare", "build"):
        command = sub.add_parser(name, help="Extraer texto" if name == "prepare" else "Construir índice vectorial")
        command.add_argument("--ocr", action="store_true")
    ask = sub.add_parser("ask", help="Consultar desde terminal")
    ask.add_argument("question")
    ask.add_argument("--model", help="Cambiar sólo el generador para esta consulta")
    evaluation = sub.add_parser("evaluate", help="Evaluar preguntas del material")
    evaluation.add_argument("--limit", type=int, default=0)
    evaluation.add_argument("--retrieval-only", action="store_true")
    args = parser.parse_args()
    try:
        settings = load_settings()
        if getattr(args, "model", None):
            settings = replace(settings, generation_model=args.model).validate()
        client = OllamaClient(settings)
        if args.command == "doctor":
            print(f"Python: {platform.python_version()} | {platform.platform()}")
            print(f"Ollama: {settings.base_url}")
            models = client.models()
            print("Modelos instalados: " + ", ".join(item["name"] for item in models))
            client.require_model(settings.embedding_model)
            client.require_model(settings.generation_model)
            ready, reason, manifest = index_status(settings)
            print(reason)
            if manifest:
                print(f'{manifest["chunks"]} fragmentos; embeddings: {manifest["embedding_model"]}')
            print("Configuración y modelos: OK. " + ("Listo para preguntar." if ready else "Falta preparar índice."))
        elif args.command == "prepare":
            docs = prepare_documents(settings, args.ocr, lambda value, text: print(text, flush=True))
            for doc in docs:
                print(f'{doc["source"]}: {len(doc["pages"])} páginas; pendientes: {doc["missing_pages"]}')
        elif args.command == "build":
            manifest = build_index(settings, client, args.ocr, lambda value, text: print(text, flush=True))
            print(f'Listo: {manifest["chunks"]} fragmentos.')
            for doc in manifest["documents"]:
                if doc["missing_pages"]:
                    print(f'AVISO {doc["source"]}: páginas pendientes de OCR {doc["missing_pages"]}')
        elif args.command == "ask":
            print(json.dumps(answer_question(settings, args.question, client), ensure_ascii=False, indent=2))
        elif args.command == "evaluate":
            if args.limit < 0:
                raise ValueError("--limit no puede ser negativo.")
            report = evaluate(settings, client, args.limit, args.retrieval_only)
            target = settings.root / "data" / ("evaluation-results-retrieval.json" if args.retrieval_only else "evaluation-results.json")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
            print(f"Resultados: {target}")
            if report["summary"]["errors"]:
                return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
