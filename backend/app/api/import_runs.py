"""HTTP routes for the durable Unit CSV import flow."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse, Response

from app.core.database import Database
from app.core.exceptions import AppError
from app.core.policy import UserContext, get_current_user_context
from app.schemas.import_run import (
    ImportRunApplyRequest,
    ImportRunPreviewRequest,
    ImportRunRowsResponse,
    ImportRunRowView,
    ImportRunView,
    SignedImportErrorLink,
)
from app.services.import_runs import (
    IMPORT_RUN_ROLES,
    MAX_IMPORT_CSV_BYTES,
    apply_import_run,
    assert_error_file_token,
    create_error_file_signed_link,
    create_import_run,
    error_file_path,
    get_import_run,
    list_import_rows,
    preview_import_run,
    record_error_file_download,
    remove_private_file,
    resolve_import_building,
)


router = APIRouter(prefix="/import-runs", tags=["import-runs"])

CSV_TEMPLATE = (
    "unit_number,floor,area_m2,status\r\n"
    "W1-0101,1,78.50,occupied\r\n"
).encode("utf-8")


async def _read_csv_body(request: Request) -> bytes:
    buffered = bytearray()
    async for chunk in request.stream():
        if len(buffered) + len(chunk) > MAX_IMPORT_CSV_BYTES:
            raise AppError("ERR-FILE-REJECTED", "Tệp CSV rỗng hoặc vượt giới hạn kích thước.", 422)
        buffered.extend(chunk)
    return bytes(buffered)


def _execution_view(execution) -> ImportRunView:
    """Use the persisted receipt for retries, not mutable current run state."""
    return ImportRunView.model_validate(
        execution.replay_body if execution.replayed else execution.run,
    )


@router.get("/template")
def get_unit_csv_template(
    request: Request,
    current_user: UserContext = Depends(get_current_user_context),
):
    current_user.assert_role(*IMPORT_RUN_ROLES)
    current_user.assert_active_site()
    return Response(
        CSV_TEMPLATE,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="unit-import-template.csv"'},
    )


@router.post("", response_model=ImportRunView, status_code=201)
async def upload_import_csv(
    request: Request,
    building_code: str = Query(..., min_length=1, max_length=50),
    mode: Literal["PARTIAL", "ALL_OR_NOTHING"] = Query(...),
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    file_name: str | None = Header(None, alias="X-File-Name"),
):
    database: Database = request.app.state.database
    # Authorize the target before reading untrusted bytes into memory.
    with database.get_session() as session:
        resolve_import_building(session, current_user, building_code)
    content = await _read_csv_body(request)
    with database.get_session() as session:
        execution = create_import_run(
            session,
            current_user,
            request,
            building_code=building_code,
            mode=mode,
            file_name=file_name,
            claimed_mime_type=request.headers.get("content-type"),
            content=content,
            idempotency_key=idempotency_key,
            storage_root=request.app.state.settings.private_storage_path,
        )
        try:
            session.commit()
        except Exception:
            if not execution.replayed:
                remove_private_file(request.app.state.settings.private_storage_path, execution.run.source_storage_key)
            raise
        if execution.run.source_is_quarantined:
            raise AppError("ERR-FILE-QUARANTINED", "Tệp không an toàn và đã bị chặn.", 422)
        return _execution_view(execution)


@router.post("/{run_id}/preview", response_model=ImportRunView)
def preview_uploaded_import(
    request: Request,
    run_id: UUID,
    body: ImportRunPreviewRequest,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    database: Database = request.app.state.database
    with database.get_session() as session:
        execution = preview_import_run(
            session,
            current_user,
            request,
            run_id=run_id,
            body=body,
            idempotency_key=idempotency_key,
            storage_root=request.app.state.settings.private_storage_path,
        )
        try:
            session.commit()
        except Exception:
            if not execution.replayed:
                remove_private_file(request.app.state.settings.private_storage_path, execution.new_error_key)
            raise
        if not execution.replayed:
            remove_private_file(request.app.state.settings.private_storage_path, execution.cleanup_error_key)
        return _execution_view(execution)


@router.post("/{run_id}/apply", response_model=ImportRunView)
def apply_previewed_import(
    request: Request,
    run_id: UUID,
    body: ImportRunApplyRequest,
    current_user: UserContext = Depends(get_current_user_context),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    database: Database = request.app.state.database
    with database.get_session() as session:
        execution = apply_import_run(
            session,
            current_user,
            request,
            run_id=run_id,
            body=body,
            idempotency_key=idempotency_key,
            storage_root=request.app.state.settings.private_storage_path,
        )
        try:
            session.commit()
        except Exception:
            if not execution.replayed:
                remove_private_file(request.app.state.settings.private_storage_path, execution.new_error_key)
            raise
        if not execution.replayed:
            remove_private_file(request.app.state.settings.private_storage_path, execution.cleanup_error_key)
        return _execution_view(execution)


@router.get("/{run_id}", response_model=ImportRunView)
def get_import_run_detail(
    request: Request,
    run_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        return ImportRunView.model_validate(get_import_run(session, current_user, run_id))


@router.get("/{run_id}/rows", response_model=ImportRunRowsResponse)
def get_import_run_rows(
    request: Request,
    run_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        _, rows, total = list_import_rows(
            session, current_user, run_id=run_id, page=page, page_size=page_size,
        )
        return ImportRunRowsResponse(
            items=[ImportRunRowView.model_validate(row) for row in rows],
            page=page,
            page_size=page_size,
            total=total,
        )


@router.get("/{run_id}/error-file/signed-link", response_model=SignedImportErrorLink)
def create_import_error_file_link(
    request: Request,
    run_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        run, token, expires_at = create_error_file_signed_link(
            session,
            current_user,
            request,
            run_id=run_id,
            link_ttl_seconds=request.app.state.settings.attachment_link_ttl_seconds,
        )
        session.commit()
        return SignedImportErrorLink(
            url=f"/api/v1/import-runs/{run.id}/error-file?signed_token={token}",
            expires_at=expires_at,
        )


@router.get("/{run_id}/error-file")
def download_import_error_file(
    request: Request,
    run_id: UUID,
    signed_token: str = Query(..., min_length=1, max_length=16384),
    current_user: UserContext = Depends(get_current_user_context),
):
    with request.app.state.database.get_session() as session:
        run = get_import_run(session, current_user, run_id)
        assert_error_file_token(request, current_user, run, signed_token)
        target = error_file_path(request.app.state.settings.private_storage_path, run)
        record_error_file_download(session, current_user, request, run)
        session.commit()
        return FileResponse(
            target,
            media_type="text/csv; charset=utf-8",
            filename=run.error_filename or "import-errors.csv",
            headers={"Cache-Control": "private, no-store"},
        )
