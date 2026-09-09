import logging
from time import perf_counter
from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import error_response

logger = logging.getLogger("greencity")


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            correlation_id = str(UUID(request.headers.get("X-Correlation-ID", "")))
        except ValueError:
            correlation_id = str(uuid4())
        request.state.correlation_id = correlation_id
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # No exception text/traceback: drivers can contain connection secrets.
            logger.error("unhandled_error correlation_id=%s", correlation_id)
            response = error_response(request, 500, "ERR-INTERNAL", "Lỗi hệ thống.")
        response.headers["X-Correlation-ID"] = correlation_id
        # Log route templates only, never query strings or arbitrary path values.
        route = request.scope.get("route")
        path = getattr(route, "path", "<unmatched>")
        logger.info("method=%s path=%s status_code=%s processing_time_ms=%.2f correlation_id=%s user_id=%s",
                    request.method, path, response.status_code,
                    (perf_counter() - started) * 1000, correlation_id,
                    getattr(request.state, "user_id", None))
        return response
