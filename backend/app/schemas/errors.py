from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    correlation_id: UUID


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


# Register centrally so FastAPI's default validation schema cannot diverge from
# the runtime handler when a new route introduces a request DTO.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {
        "model": ErrorEnvelope,
        "description": description,
        "headers": {"X-Correlation-ID": {
            "description": "Mã truy vết yêu cầu, trùng correlation_id trong lỗi.",
            "schema": {"type": "string", "format": "uuid"},
        }},
    }
    for status, description in {
        401: "Chưa xác thực.",
        403: "Không có quyền thực hiện.",
        404: "Không tìm thấy dữ liệu.",
        405: "Phương thức không được hỗ trợ.",
        409: "Xung đột dữ liệu.",
        422: "Dữ liệu yêu cầu không hợp lệ.",
        500: "Lỗi hệ thống.",
        503: "Dịch vụ tạm thời không khả dụng.",
    }.items()
}
