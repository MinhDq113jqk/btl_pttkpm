import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.schemas.errors import ErrorDetail, ErrorEnvelope

logger = logging.getLogger("greencity")


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code, self.message, self.status_code = code, message, status_code


def error_response(request: Request, status: int, code: str, message: str):
    correlation_id = getattr(request.state, "correlation_id", None) or str(uuid4())
    envelope = ErrorEnvelope(error=ErrorDetail(
        code=code, message=message, correlation_id=correlation_id,
    ))
    return JSONResponse(status_code=status, content=envelope.model_dump(mode="json"),
                        headers={"X-Correlation-ID": str(envelope.error.correlation_id)})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return error_response(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Never echo rejected bodies: future login payloads contain passwords.
        return error_response(request, 422, "ERR-VALIDATION", "Dữ liệu yêu cầu không hợp lệ.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        codes = {401: "ERR-UNAUTHORIZED", 403: "ERR-FORBIDDEN", 404: "ERR-NOTFOUND"}
        response = error_response(request, exc.status_code,
                                  codes.get(exc.status_code, "ERR-HTTP"),
                                  "Không thể xử lý yêu cầu.")
        if exc.headers:
            response.headers.update(exc.headers)
        return response
