import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import legacy_router as legacy_health_router
from app.api.health import router as health_router
from app.api.assistant import router as assistant_router
from app.api.cleaning import router as cleaning_router
from app.api.billing import router as billing_router
from app.api.security import router as security_router
from app.api.maintenance import router as maintenance_router
from app.api.service_requests import router as service_requests_router
from app.api.resident_service_requests import router as resident_service_requests_router
from app.api.resident_billing import router as resident_billing_router
from app.api.resident_notifications import router as resident_notifications_router
from app.api.observability import router as observability_router
from app.api.portal import router as portal_router
from app.api.portal_registrations import router as portal_registrations_router
from app.api.portal_finance import router as portal_finance_router
from app.api.property import router as property_router
from app.api.financial_control import router as financial_control_router
from app.api.portal_documents import router as portal_documents_router
from app.api.portal_accounts import router as portal_accounts_router
from app.api.portal_adjustments import router as portal_adjustments_router
from app.api.portal_control import router as portal_control_router
from app.api.account_administration import router as account_administration_router
from app.api.operational_ledgers import router as operational_ledgers_router
from app.api.operations_records import router as operations_records_router
from app.api.sad_work import router as sad_work_router
from app.api.operational_reports import router as operational_reports_router
from app.api.notification_channels import router as notification_channels_router
from app.core.config import Settings
from app.core.database import Database
from app.core.exceptions import register_exception_handlers
from app.middleware.correlation_id import CorrelationMiddleware
from app.schemas.errors import ERROR_RESPONSES


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.auth_secret()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database = database if database is not None else Database(settings)
        try:
            yield
        finally:
            if database is None:
                app.state.database.close()



    logger = logging.getLogger("greencity")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(handler)
    app = FastAPI(title="GreenCity API", version="0.1.0", lifespan=lifespan,
                  responses=ERROR_RESPONSES)
    app.state.settings = settings
    register_exception_handlers(app)
    app.include_router(health_router, prefix="/api/v1")
    from app.api.auth import router as auth_router
    from app.api.import_runs import router as import_runs_router
    from app.api.persons import router as persons_router
    from app.api.units import router as units_router
    from app.api.parcels import router as parcels_router
    app.include_router(auth_router, prefix="/api/v1")
    from app.api.account_profile import router as account_profile_router
    from app.api.parking_reconciliation import router as parking_reconciliation_router
    app.include_router(account_profile_router, prefix="/api/v1")
    app.include_router(parking_reconciliation_router, prefix="/api/v1")
    from app.api.sad_completion import router as sad_completion_router
    app.include_router(sad_completion_router, prefix="/api/v1")
    app.include_router(assistant_router, prefix="/api/v1")
    app.include_router(import_runs_router, prefix="/api/v1")
    app.include_router(persons_router, prefix="/api/v1")
    app.include_router(units_router, prefix="/api/v1")
    app.include_router(parcels_router, prefix="/api/v1")
    app.include_router(service_requests_router, prefix="/api/v1")
    app.include_router(resident_service_requests_router, prefix="/api/v1")
    app.include_router(resident_billing_router, prefix="/api/v1")
    app.include_router(resident_notifications_router, prefix="/api/v1")
    app.include_router(maintenance_router, prefix="/api/v1")
    app.include_router(cleaning_router, prefix="/api/v1")
    app.include_router(security_router, prefix="/api/v1")
    app.include_router(billing_router, prefix="/api/v1")
    app.include_router(property_router, prefix="/api/v1")
    app.include_router(financial_control_router, prefix="/api/v1")
    app.include_router(observability_router, prefix="/api/v1")
    for router in (portal_router, portal_registrations_router, portal_finance_router,
                   portal_documents_router, portal_accounts_router, portal_adjustments_router,
                   portal_control_router, account_administration_router, operational_ledgers_router, operations_records_router, operational_reports_router, notification_channels_router, sad_work_router):
        app.include_router(router, prefix="/api/v1")
    from app.api.integration_exchange import router as integration_exchange_router
    app.include_router(integration_exchange_router, prefix='/api/v1')
    from app.api.grounded_assistant import router as grounded_assistant_router
    app.include_router(grounded_assistant_router, prefix='/api/v1')
    # Preserve existing monitoring clients without publishing a second API contract.
    app.include_router(legacy_health_router)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=False, allow_methods=["GET", "POST", "PATCH"],
                       allow_headers=["Authorization", "Content-Type", "Idempotency-Key",
                                      "X-Correlation-ID", "X-File-Name"],
                       expose_headers=["X-Correlation-ID", "Retry-After"])

    # Outer scoped middleware also sees the safe 500 response from the
    # correlation layer when an auth or assistant handler fails unexpectedly.
    @app.middleware("http")
    async def private_api_response_headers(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if (path == "/api/v1/auth" or path.startswith("/api/v1/auth/")
                or path == "/api/v1/assistant" or path.startswith("/api/v1/assistant/")
                or path == "/api/v1/portal" or path.startswith("/api/v1/portal/")):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    return app
