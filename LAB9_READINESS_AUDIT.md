# Lab 9 Readiness Audit

## 1. README_lap9.md Summary

[README_lap9.md](D:/VinUni/labs/Day08_RAG_pipeline_cohort2/README_lap9.md:1) yêu cầu refactor Day 08 RAG thành hệ `Supervisor + Workers + MCP + Trace`, và domain gốc của Lab 9 là **CS + IT Helpdesk**, không phải pháp luật ma túy/news. Bốn sprint bắt buộc là:
1. `graph.py` với `AgentState`, `supervisor_node()`, `route_decision()`, `route_reason`.
2. `workers/` gồm `retrieval.py`, `policy_tool.py`, `synthesis.py`, có `run(state)` và `worker_io_log`.
3. `mcp_server.py` với tối thiểu `search_kb()` và `get_ticket_info()`.
4. `eval_trace.py`, trace JSONL, contracts, docs, reports, test/grading questions.

## 2. Current Project Structure

Hiện có: `src/`, `data/landing/`, `data/standardized/`, `data/index/chroma/`, `group_project/`, `tests/`, `README.md`, `README_lap9.md`, `requirements.txt`, `.env.example`, `app.py`.

Chưa thấy artifact quan trọng cho Lab 9: `graph.py`, `workers/`, `mcp_server.py`, `eval_trace.py`, `contracts/`, `artifacts/traces/`, `docs/`, `reports/`, `data/docs/`, `data/test_questions.json`, `data/grading_questions.json`.

## 3. Lab 8 Completion Status

| Module | File | Status | Main functions | Reusable for Lab 9? | Notes/Risks |
|---|---|---|---|---|---|
| Task 4 | `src/task4_chunking_indexing.py` | Implemented | `get_markdown_files`, `load_documents`, `chunk_documents`, `index_chunks`, `main` | Yes, partial | Local Chroma + local SBERT, reusable ingestion/indexing; currently hard-wired to `data/standardized/` and old domain. |
| Task 5 | `src/task5_semantic_search.py` | Implemented | `load_collection`, `encode_query`, `semantic_search`, `main` | Yes | Good retrieval core; depends on Task 4 index + `chromadb`. |
| Task 6 | `src/task6_lexical_search.py` | Implemented | `tokenize`, `load_chunks_from_chroma`, `lexical_search`, `main` | Yes | Reusable BM25; also coupled to Chroma-stored chunks. |
| Task 7 | `src/task7_reranking.py` | Implemented | `deduplicate_candidates`, `mmr_select`, `rerank`, `main` | Yes | Nice local reranker path; can become retrieval worker post-processing. |
| Task 8 | `src/task8_pageindex_vectorless.py` | Implemented | `upload_documents`, `run_pageindex_search`, `pageindex_search`, fallback helpers | Maybe | Useful only if you keep PageIndex; not required by Lab 9 and introduces API dependency. |
| Task 9 | `src/task9_retrieval_pipeline.py` | Implemented | `retrieve`, RRF merge, fallback logic, CLI | Yes, strongest reuse | Best candidate for `retrieval` worker internals, but still monolithic and old-domain oriented. |
| Task 10 | `src/task10_generation.py` | Implemented | `reorder_for_llm`, `format_context`, `generate_with_citation`, `answer`, CLI | Yes | Strong base for `synthesis` worker; still tied to direct retrieval call and provider envs. |
| App | `app.py` | Implemented | Streamlit chat, contextual query, `run_rag_chat` | Low | UI is Day 08 chatbot for drug-law/news, not Lab 9 orchestrator. |

## 4. Data / Domain Assessment

Current `data/` is clearly Day 08 domain: legal docs + news about ma túy/nghệ sĩ. `group_project/evaluation/golden_dataset.json` is also Day 08 domain. Lab 9 spec expects **helpdesk/internal policy docs** like `policy_refund_v4.txt`, `sla_p1_2026.txt`, `access_control_sop.txt`, `it_helpdesk_faq.txt`, `hr_leave_policy.txt`.

Option A: Làm Lab 9 đúng domain `README_lap9.md`
- Cần thêm `data/docs/` theo helpdesk domain.
- Cần build/index lại trên corpus mới.
- Phù hợp spec và an toàn hơn khi chấm bài.

Option B: Adapt Lab 9 trên domain Lab 8 hiện tại
- Về kỹ thuật làm được.
- Về yêu cầu chấm bài: rủi ro cao vì routing examples, policy worker, MCP mock, test questions đều đang xoay quanh helpdesk/refund/P1/access.
- Chỉ nên chọn nếu giảng viên cho phép đổi domain, hiện trong README không thấy cho phép.

## 5. Mapping Lab 8 to Lab 9

| Lab 9 component | Reuse from Lab 8 | Refactor needed |
|---|---|---|
| Retrieval Worker | `task5`, `task6`, `task7`, nhất là `task9.retrieve()` | Tách khỏi monolith, trả về `retrieved_chunks` + `worker_io_log` trong state |
| Policy Tool Worker | Một phần từ retrieval + metadata handling | Viết mới logic policy/exception; bỏ direct Chroma, gọi MCP client |
| Synthesis Worker | `task10.format_context`, `reorder_for_llm`, `generate_with_citation` | Đổi input sang state, grounded only from worker outputs |
| Supervisor graph | Hầu như chưa có | Viết mới hoàn toàn |
| MCP server | Chưa có | Viết mới hoàn toàn |
| Trace/eval | `group_project/evaluation/eval_pipeline.py` là template tham khảo | Viết mới `eval_trace.py` + trace schema + compare single vs multi |
| Docs/report | Có `group_project/README.md`, `results.md` template | Tạo bộ docs/reports đúng cấu trúc Lab 9 |

## 6. Gap Analysis Against README_lap9.md

| Requirement | Status | Evidence in code | What is needed |
|---|---|---|---|
| `graph.py`, `AgentState`, supervisor routing | Missing | Chỉ thấy trong `README_lap9.md`, không thấy code repo-wide | Tạo Sprint 1 orchestrator mới |
| `workers/retrieval.py` | Missing | Chưa có `workers/` | Tách logic từ `task9` |
| `workers/policy_tool.py` | Missing | Chưa có | Viết worker policy + exception cases |
| `workers/synthesis.py` | Missing | Chưa có | Tách từ `task10` |
| `worker_io_log` | Missing | Không thấy keyword ngoài README | Thêm vào state/trace |
| `mcp_server.py`, `search_kb`, `get_ticket_info` | Missing | Không thấy code repo-wide | Viết mock MCP |
| Policy worker gọi MCP thay vì direct Chroma | Missing | Hiện retrieval/search gọi direct Chroma | Refactor worker interface |
| Trace JSONL + required fields | Missing | Không có `artifacts/traces/`, `eval_trace.py` | Thêm trace writer + analyzer |
| `contracts/worker_contracts.yaml` | Missing | Không có `contracts/` | Viết contract I/O |
| Docs/report files | Missing | Không có `docs/`, `reports/` | Tạo theo spec |
| `data/docs`, `test_questions`, `grading_questions` | Missing | Không thấy trong `data/` | Thêm dataset đúng domain |

## 7. Current Run/Test Status

Command run:
- `python src/task9_retrieval_pipeline.py "hình phạt tội phạm ma túy" --top-k 5 --no-fallback`
- Kết quả: chạy được entrypoint nhưng `semantic` và `lexical` đều fail vì thiếu importable `chromadb`; final result rỗng.
- Ý nghĩa: code tồn tại, nhưng môi trường hiện tại chưa đủ dependency/runtime để xác nhận pipeline hoạt động thực tế.

Command run:
- `python src/task10_generation.py "hình phạt tội phạm ma túy là gì?" --top-k 5 --context-k 8`
- Kết quả: retrieval fail vì thiếu `chromadb`; fallback PageIndex cũng không usable; trả `I cannot verify this information`.
- Ý nghĩa: generation path degrade an toàn, nhưng chưa chứng minh được answer quality.

## 8. Recommended Implementation Plan

Giai đoạn chuẩn bị:
- Chốt domain. Tôi khuyên chọn **Option A: đúng helpdesk domain Lab 9**.
- Thêm corpus `data/docs/` và bộ `test_questions`/`grading_questions`.
- Kiểm tra dependency thật sự đang cài trước khi code Sprint 1, vì hiện runtime thiếu `chromadb`.

Sprint 1:
- Tạo `graph.py`.
- Thêm `AgentState`, `supervisor_node()`, `route_decision()`, `route_reason`, route `retrieval/policy_tool/human_review/synthesis`.
- Test: `python graph.py`.

Sprint 2:
- Tạo `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py`, `contracts/worker_contracts.yaml`.
- Refactor reuse từ `task9` và `task10`; policy worker xử lý Flash Sale / Admin Access / P1 edge cases.
- Test từng worker độc lập bằng import + `run(state)`.

Sprint 3:
- Tạo `mcp_server.py`.
- Implement mock `search_kb(query, top_k)` và `get_ticket_info(ticket_id)`.
- Refactor policy worker sang MCP client path.
- Test: gọi tool trực tiếp + 1 query qua graph có log quyết định MCP.

Sprint 4:
- Tạo `eval_trace.py`, `artifacts/traces/`, `docs/*`, `reports/*`.
- Lưu trace JSONL, `analyze_trace()`, `compare_single_vs_multi()`, chạy 15 câu hỏi.
- Test: `python eval_trace.py`.

## 9. Proposed File/Folder Changes

- `graph.py`: create new.
- `workers/retrieval.py`: create, reuse logic từ `task9`.
- `workers/policy_tool.py`: create new, không overwrite gì hiện có.
- `workers/synthesis.py`: create, refactor từ `task10`.
- `mcp_server.py`: create new.
- `eval_trace.py`: create new.
- `contracts/worker_contracts.yaml`: create new.
- `docs/`, `reports/`, `artifacts/traces/`: create new.
- `data/docs/`, `data/test_questions.json`, `data/grading_questions.json`: create new if theo đúng domain Lab 9.
- `src/task9_retrieval_pipeline.py`, `src/task10_generation.py`: nên `reuse + refactor`, không rename, tránh overwrite behavior Day 08 nếu bạn vẫn muốn giữ baseline để so sánh.

## 10. Risks and Decisions Needed

- Quyết định lớn nhất là **domain**. Nếu không chuyển sang helpdesk, bài có thể lệch spec.
- Cần quyết định giữ Day 08 files làm baseline hay refactor trực tiếp. Tôi khuyên giữ nguyên làm baseline và build Lab 9 layer song song.
- Environment hiện thiếu runtime dependency thực tế cho Chroma; nếu chưa xử lý, Sprint 1 xong vẫn khó verify Sprint 2 trở đi.
- `group_project/evaluation/eval_pipeline.py` hiện chỉ là template, chưa thể dùng như trace/eval của Lab 9.

## 11. Next Prompt Recommendation

Dùng prompt này sau khi bạn chốt domain:

```text
Bắt đầu Sprint 1 cho Lab 9 trong project hiện tại. Domain đã chốt là [ghi rõ domain]. Hãy IMPLEMENT, không chỉ phân tích. Giữ nguyên code Lab 8 làm baseline, tạo mới graph.py cho supervisor orchestration với AgentState, supervisor_node(), route_decision(), route_reason, và route retrieval/policy_tool/human_review/synthesis theo README_lap9.md. Sau đó chạy test command an toàn để xác nhận python graph.py chạy được.
```
