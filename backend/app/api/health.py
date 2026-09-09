import logging
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppError

router = APIRouter(tags=["Health"])
logger = logging.getLogger("greencity")


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["connected"]


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    try:
        request.app.state.database.ping()
    except SQLAlchemyError:
        logger.warning("database_unavailable correlation_id=%s", request.state.correlation_id)
        raise AppError("ERR-DATABASE-UNAVAILABLE", "Cơ sở dữ liệu tạm thời không khả dụng.", 503) from None
    return HealthResponse(status="ok", database="connected")
