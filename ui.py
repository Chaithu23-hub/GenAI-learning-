"""Streamlit UI for the legal document RAG assistant.

Run with:  .venv\\Scripts\\streamlit.exe run ui.py
"""

import streamlit as st

from legal_assistant.pipeline import answer_question
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
    if st.button("Re-ingest documents", help="Re-chunk and re-embed everything in data/legal/"):
        with st.spinner("Ingesting…"):
            count = ingest_documents()
        st.success(f"Ingested {count} chunks.")

if "history" not in st.session_state:
    st.session_state.history = []

question = st.text_input(
    "Question", placeholder="e.g. What is the late payment interest rate under the MSA?"
)
if st.button("Ask", type="primary", disabled=not question.strip()):
    with st.spinner("Searching the knowledge base…"):
        payload = answer_question(
            question.strip(), document_type=doc_filter, backend=backend
        )
    st.session_state.history.append((question.strip(), payload))

for asked, payload in reversed(st.session_state.history):
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
    if payload["sources"]:
        with st.expander(f"Sources ({len(payload['sources'])})"):
            for source in payload["sources"]:
                st.markdown(f"**{source['document']}** — `{source['chunk_id']}`")
                st.markdown(f"> {source['excerpt']}")
    st.divider()
