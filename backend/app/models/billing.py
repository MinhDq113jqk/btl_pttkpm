from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityTimestampMixin


def scope_args(table_name: str):
    return (
        ForeignKeyConstraint(
            ["site_id", "tenant_id"],
            ["greencity.sites.id", "greencity.sites.tenant_id"],
            name=f"fk_{table_name}_site_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["building_id", "site_id"],
            ["greencity.buildings.id", "greencity.buildings.site_id"],
            name=f"fk_{table_name}_building_site",
            ondelete="CASCADE",
        ),
    )


ACCOUNTING_PERIOD_TRANSITIONS = {
    "OPEN": frozenset({"CLOSING"}),
    "CLOSING": frozenset({"OPEN", "CLOSED"}),
    # CLOSED may reopen only through a future maker-checker command; it is not
    # exposed by the foundation API and can never reopen once LOCKED.
    "CLOSED": frozenset({"CLOSING", "LOCKED"}),
    "LOCKED": frozenset(),
}

BILLING_RUN_TRANSITIONS = {
    "DRAFT": frozenset({"CALCULATING", "CANCELLED"}),
    "CALCULATING": frozenset({"REVIEW", "FAILED", "CANCELLED"}),
    "REVIEW": frozenset({"CALCULATING", "POSTED", "CANCELLED"}),
    "FAILED": frozenset({"CALCULATING", "CANCELLED"}),
    "POSTED": frozenset(),
    "CANCELLED": frozenset(),
}

BILLING_INVOICE_TRANSITIONS = {
    "DRAFT": frozenset({"ISSUED", "VOID"}),
    "ISSUED": frozenset({"PARTIALLY_PAID", "PAID", "VOID"}),
    "PARTIALLY_PAID": frozenset({"PAID"}),
    "PAID": frozenset(),
    "VOID": frozenset(),
}

PAYMENT_TRANSITIONS = {
    "RECEIVED": frozenset({"ALLOCATING", "UNMATCHED", "OVERPAID", "REVERSED"}),
    "ALLOCATING": frozenset({"PARTIALLY_ALLOCATED", "ALLOCATED", "UNMATCHED", "OVERPAID", "REVERSED"}),
    "PARTIALLY_ALLOCATED": frozenset({"ALLOCATING", "ALLOCATED", "OVERPAID", "REVERSED"}),
    "ALLOCATED": frozenset({"REVERSED"}),
    "UNMATCHED": frozenset({"RECEIVED", "ALLOCATING", "OVERPAID", "REVERSED"}),
    "OVERPAID": frozenset({"ALLOCATING", "REVERSED"}),
    "REVERSED": frozenset(),
}


class BillingAccount(IdentityTimestampMixin, Base):
    __tablename__ = "billing_accounts"
    __table_args__ = scope_args(__tablename__) + (
        ForeignKeyConstraint(
            ["unit_id", "building_id"],
            ["greencity.units.id", "greencity.units.building_id"],
            name="fk_billing_accounts_unit_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "building_id", name="uq_billing_accounts_id_building"),
        UniqueConstraint("building_id", "unit_id", name="uq_billing_accounts_building_unit"),
        UniqueConstraint("site_id", "account_number", name="uq_billing_accounts_site_number"),
        CheckConstraint("status IN ('ACTIVE','SUSPENDED','CLOSED')", name="billing_accounts_status"),
        Index("ix_billing_accounts_scope_status", "tenant_id", "site_id", "building_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    unit_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    account_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    opened_on: Mapped[date] = mapped_column(Date, nullable=False)
    closed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FeePolicy(IdentityTimestampMixin, Base):
    __tablename__ = "billing_fee_policies"
    __table_args__ = scope_args(__tablename__) + (
        UniqueConstraint("id", "building_id", name="uq_billing_fee_policies_id_building"),
        UniqueConstraint("building_id", "code", name="uq_billing_fee_policies_building_code"),
        Index("ix_billing_fee_policies_scope_active", "tenant_id", "site_id", "building_id", "is_active"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class FeePolicyVersion(IdentityTimestampMixin, Base):
    __tablename__ = "billing_fee_policy_versions"
    __table_args__ = scope_args(__tablename__) + (
        ForeignKeyConstraint(
            ["fee_policy_id", "building_id"],
            ["greencity.billing_fee_policies.id", "greencity.billing_fee_policies.building_id"],
            name="fk_billing_fee_policy_versions_policy_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "building_id", name="uq_billing_fee_policy_versions_id_building"),
        UniqueConstraint("fee_policy_id", "version_number", name="uq_billing_fee_policy_versions_policy_version"),
        UniqueConstraint("fee_policy_id", "effective_from", name="uq_billing_fee_policy_versions_policy_effective"),
        CheckConstraint("unit_rate_vnd >= 0", name="billing_fee_policy_versions_rate_nonnegative"),
        CheckConstraint("basis IN ('UNIT_AREA_M2')", name="billing_fee_policy_versions_basis"),
        CheckConstraint("rounding_unit_vnd > 0", name="billing_fee_policy_versions_rounding_unit"),
        CheckConstraint("version_number > 0", name="billing_fee_policy_versions_version_positive"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="billing_fee_policy_versions_dates"),
        Index("ix_billing_fee_policy_versions_scope_effective", "tenant_id", "site_id", "building_id", "effective_from"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    fee_policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    unit_rate_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    basis: Mapped[str] = mapped_column(String(30), nullable=False, default="UNIT_AREA_M2")
    rounding_unit_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AccountingPeriod(IdentityTimestampMixin, Base):
    __tablename__ = "accounting_periods"
    __table_args__ = scope_args(__tablename__) + (
        UniqueConstraint("id", "building_id", name="uq_accounting_periods_id_building"),
        UniqueConstraint("building_id", "period_key", name="uq_accounting_periods_building_key"),
        CheckConstraint("period_end >= period_start", name="accounting_periods_dates"),
        CheckConstraint("status IN ('OPEN','CLOSING','CLOSED','LOCKED')", name="accounting_periods_status"),
        Index("ix_accounting_periods_scope_status", "tenant_id", "site_id", "building_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    period_key: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BillingRun(IdentityTimestampMixin, Base):
    __tablename__ = "billing_runs"
    __table_args__ = scope_args(__tablename__) + (
        ForeignKeyConstraint(
            ["accounting_period_id", "building_id"],
            ["greencity.accounting_periods.id", "greencity.accounting_periods.building_id"],
            name="fk_billing_runs_period_building",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["fee_policy_version_id", "building_id"],
            ["greencity.billing_fee_policy_versions.id", "greencity.billing_fee_policy_versions.building_id"],
            name="fk_billing_runs_policy_version_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "building_id", name="uq_billing_runs_id_building"),
        UniqueConstraint("id", "accounting_period_id", "building_id", name="uq_billing_runs_id_period_building"),
        UniqueConstraint("site_id", "run_key", name="uq_billing_runs_site_key"),
        UniqueConstraint("building_id", "accounting_period_id", "fee_policy_version_id", name="uq_billing_runs_period_policy"),
        CheckConstraint("status IN ('DRAFT','CALCULATING','REVIEW','POSTED','FAILED','CANCELLED')", name="billing_runs_status"),
        Index("ix_billing_runs_scope_status", "tenant_id", "site_id", "building_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    accounting_period_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    fee_policy_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    run_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    initiated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BillingInvoice(IdentityTimestampMixin, Base):
    __tablename__ = "billing_invoices"
    __table_args__ = scope_args(__tablename__) + (
        ForeignKeyConstraint(
            ["billing_account_id", "building_id"],
            ["greencity.billing_accounts.id", "greencity.billing_accounts.building_id"],
            name="fk_billing_invoices_account_building",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["billing_run_id", "accounting_period_id", "building_id"],
            ["greencity.billing_runs.id", "greencity.billing_runs.accounting_period_id", "greencity.billing_runs.building_id"],
            name="fk_billing_invoices_run_period_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "building_id", name="uq_billing_invoices_id_building"),
        UniqueConstraint("site_id", "invoice_number", name="uq_billing_invoices_site_number"),
        UniqueConstraint("billing_account_id", "accounting_period_id", name="uq_billing_invoices_account_period"),
        CheckConstraint("status IN ('DRAFT','ISSUED','PARTIALLY_PAID','PAID','VOID')", name="billing_invoices_status"),
        CheckConstraint("total_vnd >= 0 AND outstanding_vnd >= 0 AND outstanding_vnd <= total_vnd", name="billing_invoices_amounts"),
        Index("ix_billing_invoices_scope_status", "tenant_id", "site_id", "building_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    billing_account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    billing_run_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    accounting_period_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False)
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    total_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    outstanding_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class BillingInvoiceItem(IdentityTimestampMixin, Base):
    __tablename__ = "billing_invoice_items"
    __table_args__ = scope_args(__tablename__) + (
        ForeignKeyConstraint(
            ["billing_invoice_id", "building_id"],
            ["greencity.billing_invoices.id", "greencity.billing_invoices.building_id"],
            name="fk_billing_invoice_items_invoice_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("source_pending_charge_id", name="uq_billing_invoice_items_source_charge"),
        ForeignKeyConstraint(
            ["fee_policy_version_id", "building_id"],
            ["greencity.billing_fee_policy_versions.id", "greencity.billing_fee_policy_versions.building_id"],
            name="fk_billing_invoice_items_policy_version_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("billing_invoice_id", "line_number", name="uq_billing_invoice_items_invoice_line"),
        CheckConstraint("line_number > 0", name="billing_invoice_items_line_positive"),
        CheckConstraint("amount_vnd >= 0", name="billing_invoice_items_amount_nonnegative"),
        Index("ix_billing_invoice_items_invoice", "billing_invoice_id", "line_number"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    billing_invoice_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    fee_policy_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_pending_charge_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("greencity.pending_charges.id", name="fk_billing_items_pending_charge", ondelete="RESTRICT"), nullable=True,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    basis: Mapped[str] = mapped_column(String(30), nullable=False, default="UNIT_AREA_M2")
    basis_quantity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    unit_rate_vnd_snapshot: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rounding_unit_vnd_snapshot: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)


class Payment(IdentityTimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = scope_args(__tablename__) + (
        ForeignKeyConstraint(
            ["billing_account_id", "building_id"],
            ["greencity.billing_accounts.id", "greencity.billing_accounts.building_id"],
            name="fk_payments_account_building",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["accounting_period_id", "building_id"],
            ["greencity.accounting_periods.id", "greencity.accounting_periods.building_id"],
            name="fk_payments_period_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "building_id", name="uq_payments_id_building"),
        UniqueConstraint("tenant_id", "site_id", "payment_source", "source_reference", name="uq_payments_source_reference"),
        UniqueConstraint("tenant_id", "site_id", "receipt_number", name="uq_payments_receipt_number"),
        CheckConstraint("payment_source IN ('CASH','BANK_TRANSFER','GATEWAY')", name="payments_source"),
        CheckConstraint("status IN ('RECEIVED','ALLOCATING','PARTIALLY_ALLOCATED','ALLOCATED','UNMATCHED','OVERPAID','REVERSED')", name="payments_status"),
        CheckConstraint("amount_vnd > 0", name="payments_amount_positive"),
        Index("ix_payments_scope_received", "tenant_id", "site_id", "building_id", "received_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    billing_account_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    accounting_period_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    payment_source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    receipt_number: Mapped[str] = mapped_column(String(80), nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="RECEIVED")
    received_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class PaymentAllocation(IdentityTimestampMixin, Base):
    __tablename__ = "payment_allocations"
    __table_args__ = scope_args(__tablename__) + (
        ForeignKeyConstraint(
            ["payment_id", "building_id"],
            ["greencity.payments.id", "greencity.payments.building_id"],
            name="fk_payment_allocations_payment_building",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["billing_invoice_id", "building_id"],
            ["greencity.billing_invoices.id", "greencity.billing_invoices.building_id"],
            name="fk_payment_allocations_invoice_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("payment_id", "billing_invoice_id", name="uq_payment_allocations_payment_invoice"),
        CheckConstraint("amount_vnd > 0", name="payment_allocations_amount_positive"),
        Index("ix_payment_allocations_invoice", "billing_invoice_id"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    payment_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    billing_invoice_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    allocated_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)


class UnmatchedPayment(IdentityTimestampMixin, Base):
    __tablename__ = "unmatched_payments"
    __table_args__ = scope_args(__tablename__) + (
        ForeignKeyConstraint(
            ["payment_id", "building_id"],
            ["greencity.payments.id", "greencity.payments.building_id"],
            name="fk_unmatched_payments_payment_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("payment_id", name="uq_unmatched_payments_payment"),
        CheckConstraint("amount_vnd > 0", name="unmatched_payments_amount_positive"),
        CheckConstraint("status IN ('OPEN','RESOLVED','REFUNDED')", name="unmatched_payments_status"),
        Index("ix_unmatched_payments_scope_status", "tenant_id", "site_id", "building_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    payment_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class OverpaymentCredit(IdentityTimestampMixin, Base):
    __tablename__ = "overpayment_credits"
    __table_args__ = scope_args(__tablename__) + (
        ForeignKeyConstraint(
            ["billing_account_id", "building_id"],
            ["greencity.billing_accounts.id", "greencity.billing_accounts.building_id"],
            name="fk_overpayment_credits_account_building",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["payment_id", "building_id"],
            ["greencity.payments.id", "greencity.payments.building_id"],
            name="fk_overpayment_credits_payment_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("payment_id", name="uq_overpayment_credits_payment"),
        CheckConstraint("original_vnd > 0 AND remaining_vnd >= 0 AND remaining_vnd <= original_vnd", name="overpayment_credits_amounts"),
        CheckConstraint("status IN ('OPEN','EXHAUSTED','VOID')", name="overpayment_credits_status"),
        Index("ix_overpayment_credits_scope_status", "tenant_id", "site_id", "building_id", "status"),
    )

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    billing_account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    payment_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    original_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    remaining_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ArLedgerEntry(Base):
    __tablename__ = "ar_ledger_entries"
    __table_args__ = scope_args(__tablename__) + (
        ForeignKeyConstraint(
            ["billing_account_id", "building_id"],
            ["greencity.billing_accounts.id", "greencity.billing_accounts.building_id"],
            name="fk_ar_ledger_entries_account_building",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["accounting_period_id", "building_id"],
            ["greencity.accounting_periods.id", "greencity.accounting_periods.building_id"],
            name="fk_ar_ledger_entries_period_building",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("source_type", "source_id", "entry_type", name="uq_ar_ledger_entries_source_type"),
        CheckConstraint("entry_type IN ('INVOICE_ISSUED','PAYMENT_RECEIVED','CREDIT_ISSUED','CREDIT_APPLIED','REVERSAL')", name="ar_ledger_entries_type"),
        CheckConstraint("(debit_vnd > 0 AND credit_vnd = 0) OR (credit_vnd > 0 AND debit_vnd = 0)", name="ar_ledger_entries_one_sided"),
        Index("ix_ar_ledger_entries_account_effective", "billing_account_id", "effective_at", "id"),
        Index("ix_ar_ledger_entries_scope_period", "tenant_id", "site_id", "building_id", "accounting_period_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("greencity.tenants.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    building_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    billing_account_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    accounting_period_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    debit_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credit_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("greencity.accounts.id", ondelete="RESTRICT"), nullable=True)
