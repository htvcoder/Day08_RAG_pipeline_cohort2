# Lab 9 Solutions - Multi-Agent Orchestration

## 1. Tổng quan bài Lab 9

Lab 9 refactor pipeline RAG từ Lab 8 sang kiến trúc nhiều thành phần hơn theo hướng:

```text
Supervisor -> Workers -> MCP Tools -> Synthesis -> Trace
```

Ở Lab 8, luồng xử lý retrieval, policy, generation và fallback chủ yếu nằm trong một số module tương đối tập trung. Sang Lab 9, hệ thống được tách thành các vai trò rõ ràng hơn để:

- dễ debug khi câu trả lời sai,
- dễ trace xem lỗi nằm ở routing, retrieval, policy hay synthesis,
- dễ mở rộng thêm tool hoặc worker mới,
- vẫn giữ được baseline Lab 8 trong `src/` để tái sử dụng.

## 2. Bối cảnh từ Lab 8

Project gốc là Lab 8 RAG Pipeline với các thành phần retrieval/generation nằm trong `src/`, đặc biệt là:

- `src/task5_semantic_search.py`
- `src/task6_lexical_search.py`
- `src/task7_reranking.py`
- `src/task9_retrieval_pipeline.py`
- `src/task10_generation.py`

Các module này cho thấy baseline Lab 8 đã có:

- semantic search trên ChromaDB,
- lexical search bằng BM25,
- reranking bằng MMR,
- retrieval pipeline có merge/fallback,
- generation có citation và fallback extractive.

Tuy nhiên, baseline này chưa có supervisor graph, chưa có worker tách vai, chưa có MCP mock riêng, và chưa có trace JSONL theo định dạng Lab 9.

## 3. Mục tiêu giải pháp Lab 9

Giải pháp đã triển khai có mục tiêu:

- xây dựng một lớp Lab 9 song song ở root project,
- giữ nguyên Lab 8 làm baseline, không xóa và không rename,
- chuyển domain sang **CS + IT Helpdesk** theo `README_lap9.md`,
- thêm supervisor để route task,
- thêm các worker độc lập để xử lý retrieval, policy/tool và synthesis,
- dùng MCP mock để mô phỏng external capability,
- lưu trace JSONL và có script evaluation cục bộ.

Domain thực tế đã triển khai trong code/data là:

- **CS + IT Helpdesk**

Bằng chứng:

- `data/docs/` có 5 file helpdesk/policy:
  - `policy_refund_v4.txt`
  - `sla_p1_2026.txt`
  - `access_control_sop.txt`
  - `it_helpdesk_faq.txt`
  - `hr_leave_policy.txt`
- `data/test_questions.json` gồm 15 câu hỏi xoay quanh P1, SLA, refund, admin access, contractor, FAQ và human review.

## 4. Kiến trúc tổng thể

Kiến trúc hiện tại gồm các thành phần chính:

- `graph.py`: supervisor orchestration
- `workers/retrieval.py`: retrieval worker
- `workers/policy_tool.py`: policy/tool worker
- `workers/synthesis.py`: synthesis worker
- `mcp_server.py`: MCP mock server
- `eval_trace.py`: evaluation + trace writer
- `contracts/worker_contracts.yaml`: mô tả contract input/output

Luồng tổng quát:

```text
User Query
   |
   v
Supervisor Node
   |
   +--> route_decision()
   |
   +--> Retrieval Worker hoặc Policy Tool Worker hoặc Human Review
   |
   v
Synthesis Worker
   |
   v
Final Answer + Citations + Sources + Confidence
   |
   v
Trace JSONL
```

## 5. Sprint 1 - Supervisor Graph

### 5.1. Đã làm gì

Đã tạo `graph.py` với các phần chính:

- `AgentState`
- `route_decision(task)`
- `supervisor_node(state)`
- `human_review_node(state)`
- `SupervisorGraph.invoke(state)`
- CLI demo bằng `python graph.py`

CLI hiện chạy 3 query demo:

1. `Ticket P1 lúc 2am - escalation xảy ra thế nào và ai nhận thông báo?`
2. `Contractor cần Admin Access để sửa P1 khẩn cấp - quy trình tạm thời là gì?`
3. `Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi - policy nào áp dụng?`

### 5.2. Cách hoạt động

`AgentState` được khai báo bằng `TypedDict` và hiện có các field chính:

- `task`
- `route_reason`
- `history`
- `risk_high`
- `supervisor_route`
- `workers_called`
- `worker_io_log`
- `mcp_tools_used`
- `mcp_results`
- `retrieved_chunks`
- `policy_result`
- `answer`
- `sources`
- `confidence`
- `hitl_triggered`

`supervisor_node()` sẽ:

- đọc `state["task"]`,
- gọi `route_decision()`,
- ghi `supervisor_route`,
- ghi `route_reason`,
- set `risk_high`,
- append vào `history`.

`SupervisorGraph.invoke()` chạy theo flow:

1. `supervisor_node`
2. nếu route là `human_review` thì gọi `human_review_node`
3. nếu route là `policy_tool_worker` thì gọi `workers.policy_tool.run`
4. ngược lại gọi `workers.retrieval.run`
5. sau đó luôn gọi `workers.synthesis.run`

### 5.3. Routing logic

Routing logic hiện tại trong code:

| Nhóm từ khóa | Route | Lý do |
|---|---|---|
| `hoàn tiền`, `refund`, `policy`, `flash sale`, `digital product` | `policy_tool_worker` | Cần kiểm tra policy và exception |
| `cấp quyền`, `access`, `admin`, `contractor`, `emergency` | `policy_tool_worker` | Cần kiểm tra quyền truy cập và phê duyệt |
| `mã lỗi không rõ`, `unknown error`, `unclear` | `human_review` | Tín hiệu không rõ, cần con người xem xét |
| `p1`, `escalation`, `ticket`, `sla` | `retrieval_worker` | Cần tìm bằng chứng/tài liệu vận hành |
| các trường hợp còn lại | `retrieval_worker` | Route mặc định sang retrieval |

`risk_high` được set theo nhóm từ khóa rủi ro cao:

- `p1`
- `emergency`
- `admin access`
- `contractor`
- `refund dispute`
- `flash sale`

`route_reason` luôn được ghi thành chuỗi mô tả lý do route.

### 5.4. File liên quan

- `graph.py`
- `README_lap9.md`
- `docs/routing_decisions.md`

## 6. Sprint 2 - Workers

### 6.1. Retrieval Worker

`workers/retrieval.py` implement hàm:

```python
def run(state: dict) -> dict:
    ...
```

Input chính:

- `state["task"]`
- `state.get("top_k", 5)`

Retrieval worker hiện tìm tài liệu trong domain helpdesk từ:

- `data/docs/*.txt`

Chiến lược retrieval:

1. Thử `chroma_search()` trên:
   - `data/index/day09_chroma`
   - collection `day09_docs`
2. Nếu Chroma không có, thiếu dependency, hoặc lỗi:
   - fallback sang `keyword_search()`

Điểm đáng chú ý:

- worker **không crash** nếu thiếu `chromadb`,
- retrieval fallback là keyword-based search trên các chunk tạo trực tiếp từ file text,
- chunking được làm cục bộ qua `chunk_text()`.

Format `retrieved_chunks` hiện tại:

```python
{
  "content": "...",
  "score": 11.0,
  "metadata": {
    "source_file": "data/docs/sla_p1_2026.txt",
    "source_type": "helpdesk_policy",
    "title": "SLA P1 2026",
    "chunk_index": 0
  }
}
```

`worker_io_log` của retrieval worker ghi:

- timestamp
- worker name
- input task
- retrieval method (`chroma` hoặc `keyword_fallback`)
- số lượng kết quả
- danh sách source files

### 6.2. Policy Tool Worker

`workers/policy_tool.py` implement hàm:

```python
def run(state: dict) -> dict:
    ...
```

Worker này:

- gọi MCP client từ `mcp_server.py`,
- dùng `search_kb()` để lấy chunk liên quan,
- nếu phát hiện ticket P1 thì gọi thêm `get_ticket_info()`,
- build `policy_result` từ nội dung query + chunk + ticket info.

Các case policy hiện có trong code:

- Flash Sale refund
- Digital Product refund
- Contractor / Admin Access
- Emergency P1 access
- P1 / ticket / escalation
- HR / leave policy như một case ngoài core helpdesk

`policy_result` hiện có các field:

```python
{
  "decision": "...",
  "applicable_policy": "...",
  "exceptions": [...],
  "requires_approval": True,
  "risk_level": "high",
  "evidence_sources": [...]
}
```

Worker cũng ghi:

- `retrieved_chunks`
- `mcp_tools_used`
- `mcp_results`
- `worker_io_log`
- `workers_called`

`mcp_tools_used` hiện lưu tool call log từ MCP, còn `mcp_results` lưu preview kết quả của từng tool.

### 6.3. Synthesis Worker

`workers/synthesis.py` implement hàm:

```python
def run(state: dict) -> dict:
    ...
```

Synthesis worker tổng hợp từ:

- `retrieved_chunks`
- `policy_result`
- `hitl_triggered`

Chiến lược synthesis hiện tại:

- không gọi LLM bắt buộc,
- dùng extractive/template synthesis để chạy ổn định cục bộ,
- reuse `reorder_for_llm()` từ `src/task10_generation.py`.

Nếu có `policy_result`, câu trả lời sẽ ghép từ:

- `decision`
- `applicable_policy`
- `exceptions`
- yêu cầu approval nếu có

Citation đang dùng dạng:

- `[1]`
- `[2]`

Nguồn được build từ danh sách chunks sau reorder.

`confidence` hiện được gán theo rule đơn giản:

- `0.2` nếu `hitl_triggered=True`
- `0.9` nếu có cả `policy_result` và `chunks`
- `0.75` nếu chỉ có `chunks`
- `0.35` nếu gần như không có evidence

Nếu không đủ evidence:

- trả câu trả lời fallback rõ ràng,
- hoặc yêu cầu human review nếu đã đi vào nhánh `human_review`.

### 6.4. Worker I/O Log

Mỗi worker đều append vào `worker_io_log`.

Hiện log có tính mô tả, ví dụ:

- retrieval method
- input task
- output count
- mcp tools called
- output decision
- used chunks
- used policy result
- confidence

Điều này giúp debug theo từng bước thay vì chỉ nhìn final answer.

### 6.5. File liên quan

- `workers/retrieval.py`
- `workers/policy_tool.py`
- `workers/synthesis.py`
- `contracts/worker_contracts.yaml`
- `src/task10_generation.py`

## 7. Sprint 3 - MCP Mock Server

### 7.1. Lý do dùng MCP mock

Giải pháp hiện dùng **mock MCP** thay vì MCP server thật vì:

- đơn giản hơn để chạy local,
- không cần thêm hạ tầng ngoài,
- ít lỗi hơn trong môi trường lab,
- vẫn thể hiện đúng ý tưởng “tool worker gọi external capability qua interface riêng”.

Hiện tại đây **chưa phải MCP server thật** theo thư viện `mcp`; nó là lớp Python mock có interface rõ ràng.

### 7.2. Tool search_kb

`mcp_server.py` định nghĩa:

```python
class MockMCPServer:
    def search_kb(self, query: str, top_k: int = 3) -> dict:
        ...
```

`search_kb()`:

- đọc `data/docs/*.txt`,
- tách paragraph bằng `split_paragraphs()`,
- token hóa query và paragraph,
- chấm điểm keyword đơn giản,
- trả về top chunk phù hợp nhất.

Format trả về:

```python
{
  "chunks": [...],
  "sources": [...],
  "tool_call": {
    "tool": "search_kb",
    "input": {"query": query, "top_k": top_k},
    "output": {"num_chunks": n, "sources": [...]},
    "timestamp": "..."
  }
}
```

### 7.3. Tool get_ticket_info

Tool thứ hai là:

```python
def get_ticket_info(self, ticket_id: str) -> dict:
    ...
```

Hiện có mock data cho:

- `P1-2026-001`
- `P1-2026-002`

Nếu ticket không nằm trong danh sách này thì trả về một default P1 payload.

Kết quả gồm:

- `ticket_id`
- `severity`
- `created_at`
- `on_call`
- `notified`
- `escalation_steps`
- `tool_call`

### 7.4. Cách Policy Worker gọi MCP

`workers/policy_tool.py` dùng:

```python
client = get_mcp_client()
kb_result = client.search_kb(task, top_k=top_k)
```

Sau đó:

- update `retrieved_chunks` từ `kb_result["chunks"]`
- append `tool_call` của `search_kb`
- nếu phát hiện ticket P1 thì gọi thêm `get_ticket_info`
- append thêm `tool_call` của `get_ticket_info`

Như vậy Policy Tool Worker không truy cập Chroma trực tiếp mà lấy context qua MCP mock.

### 7.5. File liên quan

- `mcp_server.py`
- `workers/policy_tool.py`
- `contracts/worker_contracts.yaml`

## 8. Sprint 4 - Trace, Evaluation, Docs, Report

### 8.1. Trace format

`eval_trace.py` tạo trace JSONL với các field:

- `run_id`
- `task`
- `supervisor_route`
- `route_reason`
- `workers_called`
- `mcp_tools_used`
- `retrieved_sources`
- `final_answer`
- `confidence`
- `hitl_triggered`
- `latency_ms`
- `timestamp`

Trace được tạo qua hàm:

- `trace_from_state()`
- `write_trace()`

### 8.2. Eval pipeline

`eval_trace.py` đọc câu hỏi từ:

- `data/test_questions.json`

Sau đó:

1. khởi tạo `SupervisorGraph`
2. lặp qua 15 câu hỏi
3. gọi `graph.invoke()`
4. đo latency
5. build trace entry
6. ghi ra file trong `artifacts/traces/`
7. copy trace mới nhất sang `artifacts/grading_run.jsonl`

### 8.3. Metrics đã tính

Các metric hiện có trong code:

- `total_questions`
- `route_distribution`
- `avg_confidence`
- `avg_latency_ms`
- `mcp_usage_count`
- `hitl_count`
- `answer_coverage_count`

Ngoài ra `compare_single_vs_multi()` còn tạo một so sánh mức cao giữa:

- `single_agent_baseline`
- `multi_agent_lab9`

với các chỉ số:

- `traceability_score`
- `modularity_score`
- `avg_worker_steps`

Lưu ý: hai score traceability/modularity ở đây là giá trị mô tả tĩnh trong code, không phải metric học máy hay metric semantic tự động.

### 8.4. Docs và reports đã tạo

Hiện repo đã có:

- `docs/system_architecture.md`
- `docs/routing_decisions.md`
- `docs/single_vs_multi_comparison.md`
- `reports/group_report.md`
- `reports/individual/template.md`

Vai trò hiện tại của các file này:

- `system_architecture.md`: mô tả baseline Day 8, layer Day 9, data flow và trace
- `routing_decisions.md`: ghi 3 quyết định route tiêu biểu
- `single_vs_multi_comparison.md`: mô tả tradeoff giữa baseline và multi-agent
- `group_report.md`: tóm tắt mục tiêu, kiến trúc, cách chạy, kết quả, hạn chế
- `template.md`: khung báo cáo cá nhân

### 8.5. File liên quan

- `eval_trace.py`
- `artifacts/traces/`
- `artifacts/grading_run.jsonl`
- `docs/system_architecture.md`
- `docs/routing_decisions.md`
- `docs/single_vs_multi_comparison.md`
- `reports/group_report.md`
- `reports/individual/template.md`

## 9. Luồng xử lý end-to-end

Luồng xử lý hiện tại của hệ thống:

```text
User Query
   |
   v
Supervisor Node
   |
   +--> route_decision()
   |
   +--> Retrieval Worker hoặc Policy Tool Worker hoặc Human Review
   |
   v
Synthesis Worker
   |
   v
Final Answer + Citations + Sources + Confidence
   |
   v
Trace JSONL
```

Mô tả cụ thể:

1. User query đi vào `build_initial_state()`.
2. `SupervisorGraph.invoke()` gọi `supervisor_node()`.
3. `route_decision()` quyết định route dựa trên keyword.
4. Nếu là `retrieval_worker`, hệ thống tìm evidence từ `data/docs`.
5. Nếu là `policy_tool_worker`, hệ thống gọi MCP mock để search knowledge base và lấy ticket info khi cần.
6. Nếu là `human_review`, state được gắn `hitl_triggered=True`.
7. `synthesis_worker` tạo final answer, sources và confidence.
8. `eval_trace.py` có thể chạy toàn bộ tập câu hỏi và ghi trace JSONL.

## 10. Các quyết định thiết kế quan trọng

Các quyết định chính trong solution hiện tại:

1. **Chuyển domain sang CS + IT Helpdesk**
   - bám đúng yêu cầu `README_lap9.md`
   - không reuse domain ma túy/news của Lab 8 cho Lab 9

2. **Giữ nguyên Lab 8 làm baseline**
   - các file trong `src/` không bị xóa và vẫn dùng được làm tham chiếu
   - solution Lab 9 được build song song ở root project

3. **Không phụ thuộc bắt buộc vào Chroma hay LLM**
   - retrieval có fallback keyword search
   - synthesis dùng template/extractive mặc định
   - phù hợp với môi trường local và lab

4. **Dùng MCP mock thay vì MCP thật**
   - dễ triển khai
   - ít lỗi setup
   - vẫn thể hiện rõ luồng tool calling

5. **Ưu tiên traceability hơn độ “thông minh”**
   - state, worker log, MCP log và trace JSONL được ưu tiên làm rõ
   - dễ phân tích vì sao hệ thống route hoặc trả lời như vậy

## 11. Cách chạy chương trình

### Cài dependency

```bash
python -m pip install -r requirements.txt
```

### Chạy demo graph

```bash
python graph.py
```

### Chạy evaluation và ghi trace

```bash
python eval_trace.py
```

### Test retrieval worker độc lập

```bash
python -c "from workers.retrieval import run; s={'task':'SLA ticket P1 là bao lâu?','history':[]}; print(run(s))"
```

### Test MCP ticket tool độc lập

```bash
python -c "from mcp_server import MockMCPServer; print(MockMCPServer().get_ticket_info('P1-2026-001'))"
```

## 12. Kết quả kiểm thử

Dựa trên artifact hiện có trong repo:

- `artifacts/traces/trace_20260609_180446.jsonl`
- `artifacts/traces/trace_20260609_180545.jsonl`
- `artifacts/traces/trace_20260609_180725.jsonl`
- `artifacts/grading_run.jsonl`

Trace mới nhất hiện phản ánh 15 câu hỏi trong `data/test_questions.json`.

### Tóm tắt kết quả

- Số câu hỏi đã chạy: `15`
- Các route đã xuất hiện:
  - `retrieval_worker`
  - `policy_tool_worker`
  - `human_review`
- Có dùng MCP: `Có`
- Có HITL: `Có`, xuất hiện ở query `Unknown error code xuất hiện nhưng mô tả không rõ - hệ thống nên route thế nào?`
- Confidence trung bình theo `eval_trace.py`: khoảng `0.803`

### Phân bố route

Theo run evaluation gần nhất:

- `retrieval_worker`: `5`
- `policy_tool_worker`: `9`
- `human_review`: `1`

### Ví dụ query -> route -> answer

1. Query:
   - `Ticket P1 lúc 2am - escalation xảy ra thế nào và ai nhận thông báo?`
   - Route: `retrieval_worker`
   - Answer: trả về tóm tắt dựa trên `SLA P1 2026` với citation `[1]`

2. Query:
   - `Contractor cần Admin Access để sửa P1 khẩn cấp - quy trình tạm thời là gì?`
   - Route: `policy_tool_worker`
   - MCP: `search_kb` + `get_ticket_info`
   - Answer: nêu temporary admin access, approval, audit logging, citation `[1][2]`

3. Query:
   - `Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi - policy nào áp dụng?`
   - Route: `policy_tool_worker`
   - MCP: `search_kb`
   - Answer: áp dụng `Refund Policy v4`, có Flash Sale exception và yêu cầu supervisor approval

4. Query:
   - `Unknown error code xuất hiện nhưng mô tả không rõ - hệ thống nên route thế nào?`
   - Route: `human_review`
   - HITL: `true`
   - Answer: yêu cầu human review trước khi hành động

## 13. Những giới hạn hiện tại

Các giới hạn hiện có đúng theo code hiện tại:

- MCP hiện là **mock**, chưa phải MCP server thật dùng thư viện `mcp`.
- Retrieval có thể dùng **keyword fallback** nếu ChromaDB cho domain Day 9 chưa sẵn sàng.
- Thư mục `data/index/day09_chroma` chưa được chứng minh là đã build index hoàn chỉnh trong solution hiện tại.
- Synthesis hiện là **template/extractive**, chưa tối ưu độ tự nhiên như LLM-based synthesis.
- Dataset helpdesk trong `data/docs/` là **mock/training data** được tạo để phục vụ bài lab.
- `compare_single_vs_multi()` dùng một phần score mô tả tĩnh, chưa phải hệ metric semantic correctness sâu.
- Một số câu trả lời retrieval hiện vẫn mang tính “trích dẫn đoạn liên quan nhất”, chưa phải answer synthesis giàu diễn đạt.

## 14. Kết luận

Giải pháp Lab 9 hiện tại đã triển khai được một lớp multi-agent orchestration chạy cục bộ cho domain **CS + IT Helpdesk** với các thành phần chính:

- supervisor graph,
- retrieval worker,
- policy tool worker,
- synthesis worker,
- MCP mock server,
- trace/evaluation pipeline,
- docs và reports hỗ trợ nộp bài.

Điểm mạnh của solution là:

- giữ nguyên baseline Lab 8 để tái sử dụng,
- tách vai trò rõ ràng,
- có trace và worker log để debug,
- không phụ thuộc bắt buộc vào API ngoài,
- có thể chạy local tương đối ổn định.

Hạn chế chính là MCP vẫn là mock, retrieval domain mới chưa có semantic index riêng hoàn chỉnh, và synthesis còn thiên về template/extractive. Tuy vậy, solution hiện đã thể hiện đúng tinh thần Lab 9: tách pipeline monolithic thành hệ thống dễ route, dễ trace và dễ mở rộng hơn.
