import logging
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppError

router = APIRouter(tags=["Health"])
legacy_router = APIRouter(tags=["Health"])
logger = logging.getLogger("greencity")


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["connected"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["connected"]
    schema_revision: str


EXPECTED_SCHEMA_REVISION = "0004"


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    try:
        request.app.state.database.ping()
    except SQLAlchemyError:
        logger.warning("database_unavailable correlation_id=%s", request.state.correlation_id)
        raise AppError("ERR-DATABASE-UNAVAILABLE", "Cơ sở dữ liệu tạm thời không khả dụng.", 503) from None
    return HealthResponse(status="ok", database="connected")


@router.get("/readiness", response_model=ReadinessResponse)
def readiness(request: Request):
    try:
        revision = request.app.state.database.current_revision()
    except SQLAlchemyError:
        logger.warning("database_not_ready correlation_id=%s", request.state.correlation_id)
        raise AppError("ERR-DATABASE-UNAVAILABLE", "Cơ sở dữ liệu tạm thời không khả dụng.", 503) from None
    if revision != EXPECTED_SCHEMA_REVISION:
        logger.warning("schema_not_ready correlation_id=%s", request.state.correlation_id)
        raise AppError("ERR-DATABASE-NOT-READY", "Cơ sở dữ liệu chưa đúng phiên bản yêu cầu.", 503)
    return ReadinessResponse(status="ready", database="connected", schema_revision=revision)


# Backward-compatible liveness alias only; readiness remains versioned.
legacy_router.add_api_route("/health", health, methods=["GET"],
                            response_model=HealthResponse, include_in_schema=False)
