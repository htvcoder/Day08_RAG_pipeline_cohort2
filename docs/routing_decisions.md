# Routing Decisions

## Decision 1
Query: `Ticket P1 lúc 2am - escalation xảy ra thế nào và ai nhận thông báo?`

Route: `retrieval_worker`

Reason: The task contains `P1`, `ticket`, and `escalation`, so the supervisor prioritizes retrieval of SLA evidence.

## Decision 2
Query: `Contractor cần Admin Access để sửa P1 khẩn cấp - quy trình tạm thời là gì?`

Route: `policy_tool_worker`

Reason: The task contains `contractor`, `admin access`, and `P1`, so policy handling is prioritized over pure retrieval and MCP tools are used to combine SOP plus ticket context.

## Decision 3
Query: `Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi - policy nào áp dụng?`

Route: `policy_tool_worker`

Reason: The task contains `Flash Sale`, `hoàn tiền`, and `policy`, so the refund policy path is the correct route and exception handling is required.
