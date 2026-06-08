from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def setup_page() -> None:
    st.set_page_config(
        page_title="RAG Chatbot — Pháp luật ma túy & tin tức liên quan",
        page_icon="📚",
        layout="wide",
    )
    st.title("RAG Chatbot — Pháp luật ma túy & tin tức liên quan")
    st.caption(
        "Chatbot trả lời dựa trên tài liệu pháp luật và tin tức đã thu thập. "
        "Câu trả lời có citation theo source documents."
    )


def init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "turns" not in st.session_state:
        st.session_state.turns = 0


def clear_chat_history() -> None:
    st.session_state.messages = []
    st.session_state.turns = 0


def build_contextual_query(user_query: str, messages: list[dict], max_turns: int = 4) -> str:
    relevant_messages = messages[-max_turns * 2 :]
    if not relevant_messages:
        return user_query

    history_lines = ["Conversation history:"]
    for message in relevant_messages:
        role = "User" if message.get("role") == "user" else "Assistant"
        history_lines.append(f"{role}: {message.get('content', '')}")

    history_lines.append("")
    history_lines.append("Current question:")
    history_lines.append(user_query)
    return "\n".join(history_lines)


def load_rag_modules() -> dict[str, Any]:
    try:
        from task9_retrieval_pipeline import retrieve
        from task10_generation import format_context, generate_with_citation, reorder_for_llm
    except Exception as exc:
        raise RuntimeError(f"Không import được các module RAG cần thiết: {exc}") from exc

    return {
        "retrieve": retrieve,
        "generate_with_citation": generate_with_citation,
        "reorder_for_llm": reorder_for_llm,
        "format_context": format_context,
    }


def format_source_label(source: dict[str, Any]) -> str:
    source_id = source.get("source_id", "")
    title = source.get("title", "")
    return f"[{source_id}] {title}".strip()


def render_sources(sources: list[dict[str, Any]]) -> None:
    if not sources:
        return

    with st.expander("Nguồn tài liệu đã sử dụng", expanded=False):
        for source in sources:
            metadata = source.get("metadata", {}) or {}
            preview = str(metadata.get("content_preview", "")) or ""
            st.markdown(format_source_label(source))
            st.markdown(f"- Source file: `{source.get('source_file', '')}`")
            st.markdown(f"- Source type: `{source.get('source_type', '')}`")
            st.markdown(f"- Chunk index: `{source.get('chunk_index', '')}`")
            st.markdown(f"- Score: `{float(source.get('score', 0.0)):.4f}`")
            st.markdown(f"- Pipeline method: `{metadata.get('pipeline_method', '')}`")
            if preview:
                st.markdown(f"- Preview: {preview}")


def render_debug_info(debug: dict[str, Any] | None) -> None:
    if not debug:
        return

    with st.expander("Debug pipeline", expanded=False):
        st.markdown(f"- Query gốc: `{debug.get('user_query', '')}`")
        st.markdown(f"- Contextual query: `{debug.get('contextual_query', '')}`")
        st.markdown(f"- top_k: `{debug.get('top_k', 0)}`")
        st.markdown(f"- context_k: `{debug.get('context_k', 0)}`")
        st.markdown(f"- score_threshold: `{debug.get('score_threshold', 0.0)}`")
        st.markdown(f"- Retrieved chunks: `{debug.get('retrieved_chunks', 0)}`")
        st.markdown(f"- Reordered chunks: `{debug.get('reordered_chunks', 0)}`")
        pipeline_methods = debug.get("pipeline_methods", [])
        st.markdown(f"- Pipeline methods: `{pipeline_methods}`")


def render_sidebar() -> dict[str, Any]:
    with st.sidebar:
        st.header("Cấu hình")
        top_k = st.slider("top_k", min_value=3, max_value=10, value=5)
        context_k = st.slider("context_k", min_value=5, max_value=15, value=8)
        score_threshold = st.slider("score_threshold", min_value=0.0, max_value=1.0, value=0.3, step=0.05)
        show_sources = st.checkbox("Hiển thị source documents", value=True)
        show_debug = st.checkbox("Hiển thị debug pipeline", value=False)

        if st.button("Xóa lịch sử chat", use_container_width=True):
            clear_chat_history()
            st.rerun()

        st.markdown("### Gợi ý câu hỏi")
        st.markdown(
            "- Hình phạt đối với tội phạm ma túy là gì?\n"
            "- Những nghệ sĩ Việt Nam nào từng vướng tin tức liên quan ma túy?\n"
            "- Luật phòng chống ma túy quy định gì về người sử dụng trái phép chất ma túy?"
        )

    return {
        "top_k": top_k,
        "context_k": context_k,
        "score_threshold": score_threshold,
        "show_sources": show_sources,
        "show_debug": show_debug,
    }


def render_chat_history(show_sources: bool, show_debug: bool) -> None:
    for message in st.session_state.messages:
        with st.chat_message(message.get("role", "assistant")):
            st.markdown(message.get("content", ""))
            if message.get("role") == "assistant" and show_sources:
                render_sources(message.get("sources", []))
            if message.get("role") == "assistant" and show_debug:
                render_debug_info(message.get("debug"))


def preflight_checks() -> str | None:
    chroma_dir = PROJECT_ROOT / "data" / "index" / "chroma"
    if not chroma_dir.exists():
        return (
            "Thiếu index tại `data/index/chroma/`.\n\n"
            "Hãy chạy trước:\n"
            "`python src/task4_chunking_indexing.py`\n"
            "`python src/task5_semantic_search.py`\n"
            "`python src/task6_lexical_search.py`\n"
            "`python src/task7_reranking.py`\n"
            "`python src/task9_retrieval_pipeline.py`"
        )
    return None


def run_rag_chat(
    user_query: str,
    config: dict[str, Any],
    modules: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    contextual_query = build_contextual_query(user_query, st.session_state.messages)

    retrieve = modules["retrieve"]
    reorder_for_llm = modules["reorder_for_llm"]
    format_context = modules["format_context"]
    generate_with_citation = modules["generate_with_citation"]

    context_chunks = retrieve(
        contextual_query,
        top_k=config["context_k"],
        score_threshold=config["score_threshold"],
    )

    if not context_chunks:
        return "I cannot verify this information", [], {
            "user_query": user_query,
            "contextual_query": contextual_query,
            "top_k": config["top_k"],
            "context_k": config["context_k"],
            "score_threshold": config["score_threshold"],
            "retrieved_chunks": 0,
            "reordered_chunks": 0,
            "pipeline_methods": [],
        }

    selected_chunks = context_chunks[: config["context_k"]]
    reordered_chunks = reorder_for_llm(selected_chunks)
    _, sources = format_context(reordered_chunks)

    for source, chunk in zip(sources, reordered_chunks):
        content = str(chunk.get("content", ""))
        source["metadata"]["content_preview"] = " ".join(content.split())[:420]

    answer_text = generate_with_citation(contextual_query, reordered_chunks)
    debug_info = {
        "user_query": user_query,
        "contextual_query": contextual_query,
        "top_k": config["top_k"],
        "context_k": config["context_k"],
        "score_threshold": config["score_threshold"],
        "retrieved_chunks": len(context_chunks),
        "reordered_chunks": len(reordered_chunks),
        "pipeline_methods": [
            (chunk.get("metadata") or {}).get("pipeline_method", "") for chunk in reordered_chunks
        ],
    }
    return answer_text, sources, debug_info


def main() -> None:
    setup_page()
    init_session_state()

    config = render_sidebar()
    preflight_error = preflight_checks()
    if preflight_error:
        st.error(preflight_error)
        return

    try:
        modules = load_rag_modules()
    except Exception as exc:
        st.error(str(exc))
        return

    render_chat_history(config["show_sources"], config["show_debug"])

    user_prompt = st.chat_input("Nhập câu hỏi của bạn...")
    if not user_prompt:
        return

    st.session_state.messages.append({"role": "user", "content": user_prompt, "sources": [], "debug": {}})
    st.session_state.turns += 1

    with st.chat_message("user"):
        st.markdown(user_prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Đang truy xuất tài liệu và tạo câu trả lời..."):
                answer_text, sources, debug_info = run_rag_chat(user_prompt, config, modules)
            st.markdown(answer_text)
            if config["show_sources"]:
                render_sources(sources)
            if config["show_debug"]:
                render_debug_info(debug_info)
        except Exception as exc:
            answer_text = (
                "Xin lỗi, hệ thống chưa tạo được câu trả lời. "
                "Vui lòng kiểm tra index, API key hoặc chạy lại các task trước."
            )
            sources = []
            debug_info = {"error": str(exc)}
            st.error(answer_text)
            if config["show_debug"]:
                render_debug_info(debug_info)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer_text,
            "sources": sources,
            "debug": debug_info,
        }
    )


if __name__ == "__main__":
    main()
