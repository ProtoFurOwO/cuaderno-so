"""Interfaz de consulta local. Ejecutar con: python -m streamlit run app.py."""

from dataclasses import replace
from html import escape
import json
from pathlib import Path

import pymupdf
import streamlit as st

from asistente.config import load_settings
from asistente.documents import discover_pdfs, save_upload
from asistente.index import IndexErrorLocal, build_index, index_status
from asistente.ollama_client import OllamaClient, OllamaError
from asistente.pipeline import answer_question

st.set_page_config(page_title="Cuaderno · Sistemas Operativos", page_icon="📖", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1140px; padding-top: 2.5rem; padding-bottom: 4rem;}
h1 {letter-spacing: -0.045em; font-weight: 750;}
h2, h3 {letter-spacing: -0.025em;}
[data-testid="stSidebar"] {border-right: 1px solid color-mix(in srgb, currentColor 18%, transparent);}
/* Streamlit elige superficie y texto juntos según el tema activo.
   Un fondo blanco fijo deja texto blanco invisible en el tema oscuro. */
[data-testid="stChatMessage"] {border: 1px solid color-mix(in srgb, currentColor 18%, transparent); border-radius: 12px;}
[data-testid="stChatMessage"] p {line-height: 1.7;}
[data-testid="stMetricValue"] {font-size: 1.7rem;}
.course-rule {height: 5px; background: #2457a7; width: 54px; margin-bottom: 18px;}
.answer-copy {color: inherit; background: transparent; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 1rem; line-height: 1.7; max-width: 74ch;}
@media (max-width: 640px) {.block-container {padding-top: 1.4rem;} h1 {font-size: 2rem !important;}}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=10, show_spinner=False)
def installed_models(settings):
    try:
        return OllamaClient(settings).models(), None
    except OllamaError as exc:
        return [], str(exc)


@st.cache_data(max_entries=8, show_spinner=False)
def page_preview(path: str, modified_ns: int, number: int) -> bytes:
    with pymupdf.open(path) as document:
        return document[number - 1].get_pixmap(matrix=pymupdf.Matrix(1.25, 1.25), alpha=False).tobytes("png")


def show_fragment(hit: dict, key: str, root: Path):
    label = f'[{hit["id"]}] {Path(hit["source"]).stem} · pág. {hit["page"]}'
    with st.expander(label):
        st.caption(f'Similitud coseno: {hit["similarity"]:.3f} | Extracción: {hit["method"]}. No es porcentaje de certeza.')
        if hit.get("neighbor"):
            st.caption("Fragmento contiguo agregado para no cortar una explicación o lista.")
        st.text(hit["text"])
        path = (root / hit["source"]).resolve()
        if path.is_relative_to(root.resolve()) and path in [p.resolve() for p in discover_pdfs(root)]:
            if st.checkbox("Ver página original", key=key):
                st.image(page_preview(str(path), path.stat().st_mtime_ns, hit["page"]), width="stretch")


def show_result(result: dict, number: int, root: Path):
    if result["insufficient"]:
        st.info(result["answer"])
    else:
        # Texto, no HTML ni imágenes remotas provenientes del modelo.
        st.markdown(f'<div class="answer-copy">{escape(result["answer"])}</div>', unsafe_allow_html=True)
    st.caption(f'{result["model"]} | {result["seconds"]:.1f} s | {len(result["sources"])} fuentes citadas')
    if result["sources"]:
        st.markdown("**Fuentes de la respuesta**")
        for hit in result["sources"]:
            show_fragment(hit, f'source_{number}_{hit["id"]}', root)
    with st.expander("Cómo se obtuvo esta respuesta"):
        st.write(result["reason"])
        st.caption(f'Búsqueda: {result["retrieval_seconds"]:.2f} s | Generación: {result["generation_seconds"]:.2f} s')
        st.caption("Estos son los candidatos recuperados; no todos necesariamente respaldan la respuesta.")
        for hit in result["retrieved"]:
            show_fragment(hit, f'retrieved_{number}_{hit["id"]}', root)


def main():
    try:
        base = load_settings()
    except (ValueError, TypeError) as exc:
        st.error(f"Configuración inválida: {exc}")
        st.stop()
    models, connection_error = installed_models(base)
    available = [item["name"] for item in models]
    generators = [name for name in available if not any(term in name.lower() for term in ("embed", "bge", "e5"))]
    options = list(dict.fromkeys([base.generation_model, *generators]))
    with st.sidebar:
        st.title("Cuaderno")
        st.caption("Tu material, con referencias.")
        st.divider()
        selected = st.selectbox("Modelo que responde", options, help="Cambia sólo la generación; no modifica el índice. La selección dura esta sesión.")
        save_ram = st.checkbox(
            "Ahorrar RAM entre preguntas", value=base.keep_alive == "0",
            help="Libera cada modelo al terminar. Actívalo si falta RAM; recargar modelos vuelve más lentas las consultas. Con 16 GB puedes dejarlo desactivado.",
        )
        keep_alive = "0" if save_ram else (base.keep_alive if base.keep_alive != "0" else "5m")
        settings = replace(base, generation_model=selected, keep_alive=keep_alive)
        st.caption(f"Búsqueda: {settings.embedding_model}")
        retention = "liberar al terminar" if save_ram else f"conservar modelos: {keep_alive}"
        device = "CPU" if settings.force_cpu else "Ollama automático"
        st.caption(f"{device} | {settings.num_threads} hilos | {retention}")
        if connection_error:
            st.error(connection_error)
        else:
            st.success("Ollama conectado")
        if st.button("Actualizar conexión y modelos", width="stretch"):
            installed_models.clear()
            st.rerun()
        with st.expander("Instalar otro LLM"):
            st.code("ollama pull qwen2.5:0.5b", language="powershell")
            st.caption("Después actualiza la lista y selecciónalo. Para conservarlo, cambia generation_model en config.local.toml.")
        st.divider()
        st.subheader("Documentos")
        use_ocr = st.checkbox("OCR para páginas escaneadas", value=False, help="Opcional. El texto ya preparado se reutiliza, sin necesitar OCR en otra laptop.")
        if st.button("Preparar documentos", type="primary", width="stretch", disabled=bool(connection_error)):
            bar = st.progress(0, text="Preparando índice…")
            try:
                build_index(settings, OllamaClient(settings), use_ocr, lambda value, text: bar.progress(value, text=text))
                st.session_state.messages = []
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo preparar: {exc}")
                st.caption("El índice anterior se conserva. Corrige el problema y vuelve a intentar.")
        with st.expander("Agregar PDF"):
            uploads = st.file_uploader("Archivos del curso", type=["pdf"], accept_multiple_files=True)
            if st.button("Guardar archivos", disabled=not uploads):
                try:
                    for upload in uploads:
                        save_upload(settings.root, upload.name, upload.getvalue())
                    st.success("Guardados. Pulsa «Preparar documentos» para incluirlos.")
                except Exception as exc:
                    st.error(str(exc))
        if st.button("Limpiar conversación", width="stretch"):
            st.session_state.messages = []
            st.rerun()
        st.caption("Cada pregunta se consulta por separado. No hay memoria conversacional.")

    try:
        ready, status, manifest = index_status(settings)
    except IndexErrorLocal as exc:
        ready, status, manifest = False, str(exc), None
    st.markdown('<div class="course-rule"></div>', unsafe_allow_html=True)
    st.title("Pregunta a tus apuntes.")
    st.write("Asistente de Sistemas Operativos. Busca en el material del curso y muestra de dónde sale cada respuesta.")
    chat_tab, material_tab = st.tabs(["Preguntar", "Material y método"])
    with material_tab:
        st.subheader("Biblioteca del curso")
        pdfs = discover_pdfs(settings.root)
        for path in pdfs:
            st.write(path.name)
            relative = path.relative_to(settings.root).as_posix()
            detail = next((doc for doc in (manifest or {}).get("documents", []) if doc["source"] == relative), None)
            if detail:
                st.caption(f'{detail["pages"]} páginas | {detail["ocr_pages"]} procesadas con OCR')
                if detail["missing_pages"]:
                    st.warning(f'Cobertura incompleta o pendiente de OCR: páginas {detail["missing_pages"]}. Puede faltar información.')
            st.download_button("Descargar PDF original", data=path.read_bytes(), file_name=path.name, mime="application/pdf", key=f"pdf_{relative}")
        if not pdfs:
            st.info("Agrega PDF desde la barra lateral.")
        st.divider()
        st.subheader("Qué hace la IA")
        st.code("PDF → texto por página → fragmentos → embeddings → Chroma\nPregunta → embeddings → búsqueda coseno → contexto → LLM → respuesta y fuentes", language=None)
        st.write("EmbeddingGemma encuentra texto parecido por significado. Qwen redacta usando los fragmentos recuperados. No entrenamos ni ajustamos los modelos.")
        st.write("El índice se guarda en disco. Sólo se reconstruye si cambia el material, la extracción, el tamaño de fragmentos o el modelo de embeddings.")
        st.warning("RAG reduce alucinaciones, no las elimina. Se validan los identificadores de las citas, no que cada afirmación sea verdadera. El material puede estar desactualizado y el OCR puede tener errores.")
        st.caption("Las páginas indicadas corresponden al contador del PDF, empezando en 1. Sólo se indexan PDF; el DOCX original no se incluye.")
    with chat_tab:
        if not ready:
            st.info(status)
        else:
            cols = st.columns(3)
            cols[0].metric("Documentos", len(manifest["documents"]))
            cols[1].metric("Páginas", sum(doc["pages"] for doc in manifest["documents"]))
            cols[2].metric("Fragmentos", manifest["chunks"])
            if any(doc["missing_pages"] for doc in manifest["documents"]):
                st.warning("Hay páginas pendientes de OCR. Consulta «Material y método» para ver la cobertura.")
        if "messages" not in st.session_state:
            st.session_state.messages = []
        if not st.session_state.messages:
            st.subheader("¿Qué quieres repasar?")
            st.caption("Prueba una pregunta concreta. Abre las fuentes para comprobar la respuesta.")
            for prompt in (
                "¿Qué diferencia hay entre tiempo real duro y suave?",
                "¿Para qué sirve el comando chmod?",
                "¿Qué diferencia hay entre un pipe y un FIFO?",
            ):
                if st.button(prompt, disabled=not ready or bool(connection_error), width="stretch"):
                    st.session_state.pending_question = prompt
        for number, message in enumerate(st.session_state.messages):
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    st.text(message["content"])
                elif "result" in message:
                    show_result(message["result"], number, settings.root)
                else:
                    st.error(message["content"])
        question = st.chat_input("Escribe tu pregunta sobre el curso…", disabled=not ready or bool(connection_error), max_chars=2000)
        question = question or st.session_state.pop("pending_question", None)
        if question and ready:
            st.session_state.messages.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.text(question)
            with st.chat_message("assistant"):
                try:
                    with st.spinner("Buscando evidencia y generando respuesta local…"):
                        result = answer_question(settings, question)
                    st.session_state.messages.append({"role": "assistant", "result": result})
                    st.rerun()
                except Exception as exc:
                    message = str(exc)
                    st.error(message)
                    st.session_state.messages.append({"role": "assistant", "content": message})
        if st.session_state.messages:
            st.download_button("Guardar conversación", json.dumps(st.session_state.messages, ensure_ascii=False, indent=2), file_name="consulta-curso.json", mime="application/json")
        st.caption("Procesamiento local con la URL predeterminada. No hay búsqueda en Internet. Verifica siempre las fuentes.")


main()
