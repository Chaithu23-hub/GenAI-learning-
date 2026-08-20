import io
from pathlib import Path

import streamlit as st

from legal_assistant.pipeline import answer_question, inspect_question
from legal_assistant.vector_store import ingest_documents

_CONFIDENCE_DOT = {"high": "🟢", "medium": "🟡", "low": "🔴"}

st.set_page_config(page_title="Legal Document Assistant", page_icon="⚖️", layout="centered")
st.title("⚖️ Legal Document Assistant")
st.caption(
    "Ask questions about the contracts and amendments in the knowledge base. "
    "Every answer is grounded in retrieved document chunks."
)

with st.sidebar:
    st.header("Settings")
    backend = st.selectbox(
        "Generation backend",
        ["auto", "extractive", "llm"],
        help="auto = use the LLM if an OpenAI-compatible endpoint is reachable, "
             "otherwise the offline extractive generator.",
    )
    doc_filter = st.selectbox(
        "Search only",
        [None, "contract", "amendment"],
        format_func=lambda v: "All documents" if v is None else v.capitalize() + "s",
    )
    st.divider()
    st.subheader("Upload PDFs")
    uploaded_pdfs = st.file_uploader(
        "Upload PDF files",
        type=["pdf"],
        accept_multiple_files=True,
    )
    ingest_after = st.checkbox("Ingest after upload", value=True)
    if st.button("Convert & Save PDFs"):
        if not uploaded_pdfs:
            st.warning("Select at least one PDF file before converting.")
        else:
            out_dir = Path("data/legal")
            out_dir.mkdir(parents=True, exist_ok=True)
            written = 0
            try:
                from pypdf import PdfReader
            except ImportError:
                st.error("Required package 'pypdf' is not installed. Run: pip install pypdf")
                written = 0
            else:
                for uploaded in uploaded_pdfs:
                    data = uploaded.read()
                    reader = PdfReader(io.BytesIO(data))
                    pages = [page.extract_text() or "" for page in reader.pages]
                    text = "\n\n".join(pages).strip()
                    md = f"# {Path(uploaded.name).stem}\n\n{text}\n"
                    target = out_dir / f"{Path(uploaded.name).stem}.md"
                    target.write_text(md, encoding="utf-8")
                    written += 1
                st.success(f"Wrote {written} markdown file(s) to {out_dir}")
                if ingest_after and written:
                    with st.spinner("Ingesting…"):
                        count = ingest_documents()
                    st.success(f"Ingested {count} chunks.")
    if st.button("Re-ingest documents", help="Re-chunk and re-embed everything in data/legal/"):
        with st.spinner("Ingesting…"):
            count = ingest_documents()
        st.success(f"Ingested {count} chunks.")

if "history" not in st.session_state:
    st.session_state.history = []

question = st.text_input(
    "Question",
    placeholder="e.g. What is the late payment interest rate under the MSA?",
)
if st.button("Ask", type="primary", disabled=not question.strip()):
    with st.spinner("Searching the knowledge base…"):
        inspection = inspect_question(
            question.strip(), document_type=doc_filter, backend=backend,
        )
    st.session_state.history.append((question.strip(), inspection))

for asked, inspection in reversed(st.session_state.history):
    payload = inspection["answer"]
    confidence = payload["confidence"]
    st.markdown(
        f"**Q: {asked}**  {_CONFIDENCE_DOT.get(confidence, '⚪')} {confidence} confidence"
    )
    if payload["out_of_scope"]:
        st.warning(payload["answer"], icon="🚫")
    else:
        st.markdown(payload["answer"])
    if payload.get("reasoning"):
        with st.expander("Reasoning"):
            st.markdown(payload["reasoning"])
    if payload.get("sources"):
        with st.expander(f"Sources ({len(payload['sources'])})"):
            for source in payload["sources"]:
                st.markdown(f"**{source['document']}** — `{source['chunk_id']}`")
                st.markdown(f"> {source['excerpt']}")
    with st.expander("Retrieval inspection"):
        st.caption("Top hybrid results passed to the answer generator")
        for rank, chunk in enumerate(inspection["retrieved"], start=1):
            st.markdown(
                f"**{rank}. {chunk.document}** — `{chunk.chunk_id}` — "
                f"{chunk.heading} — rerank {chunk.score:.2f}"
            )
            st.markdown(f"> {chunk.text[:500]}")
    st.divider()
