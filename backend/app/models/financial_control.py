"""Drafts and decisions are distinct from invoices, ledger entries and cash movements."""
from datetime import date, datetime
from uuid import UUID
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, IdentityTimestampMixin
from app.models.resident_portal import PortalScope, portal_scope


class BillingReview(IdentityTimestampMixin, PortalScope, Base):
    __tablename__='billing_reviews'
    __table_args__=portal_scope(__tablename__)+(
        CheckConstraint('(billing_run_id IS NULL) <> (fee_source_id IS NULL)',name='review_one_source'),
        UniqueConstraint('billing_run_id',name='uq_billing_review_run'),
        UniqueConstraint('fee_source_id','period_id',name='uq_billing_review_source_period'),
        CheckConstraint("status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','ISSUED','CANCELLED','WAITING_INFO')",name='billing_review_status'),
    )
    billing_run_id:Mapped[UUID|None]=mapped_column(ForeignKey('greencity.billing_runs.id'),nullable=True)
    fee_source_id:Mapped[UUID|None]=mapped_column(ForeignKey('greencity.portal_fee_sources.id'),nullable=True)
    period_id:Mapped[UUID]=mapped_column(ForeignKey('greencity.accounting_periods.id'),nullable=False)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='DRAFT')
    snapshot:Mapped[dict]=mapped_column(JSON,nullable=False)
    calculation_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    approved_by_id:Mapped[UUID|None]=mapped_column(ForeignKey('greencity.accounts.id'),nullable=True)
    issued_invoice_ids:Mapped[list]=mapped_column(JSON,nullable=False,default=list)


class FinanceCommand(IdentityTimestampMixin, PortalScope, Base):
    __tablename__='finance_commands'
    __table_args__=portal_scope(__tablename__)+(
        CheckConstraint("status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','EXECUTED','WAITING_INFO','CANCELLED','RECONCILIATION')",name='finance_command_status'),
        CheckConstraint('amount_vnd >= 0',name='finance_command_amount'),
        Index('ix_finance_commands_status','site_id','kind','status'),
    )
    kind:Mapped[str]=mapped_column(String(30),nullable=False)
    period_id:Mapped[UUID]=mapped_column(ForeignKey('greencity.accounting_periods.id'),nullable=False)
    target_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    amount_vnd:Mapped[int]=mapped_column(BigInteger,nullable=False,default=0)
    reason:Mapped[str]=mapped_column(String(4000),nullable=False)
    evidence_reference:Mapped[str]=mapped_column(String(300),nullable=False)
    data:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
    snapshot:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='DRAFT')
    approved_by_id:Mapped[UUID|None]=mapped_column(ForeignKey('greencity.accounts.id'),nullable=True)
    executed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)


class ArCase(IdentityTimestampMixin, PortalScope, Base):
    __tablename__='ar_cases'
    __table_args__=portal_scope(__tablename__)+(
        CheckConstraint("kind IN ('DISPUTE','REMINDER','PROMISE')",name='ar_case_kind'),
        CheckConstraint('amount_vnd > 0',name='ar_case_amount'),
    )
    invoice_id:Mapped[UUID]=mapped_column(ForeignKey('greencity.billing_invoices.id'),nullable=False)
    invoice_item_id:Mapped[UUID|None]=mapped_column(ForeignKey('greencity.billing_invoice_items.id'),nullable=True)
    kind:Mapped[str]=mapped_column(String(20),nullable=False)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='OPEN')
    amount_vnd:Mapped[int]=mapped_column(BigInteger,nullable=False)
    due_on:Mapped[date|None]=mapped_column(Date,nullable=True)
    reason:Mapped[str]=mapped_column(String(4000),nullable=False)
    data:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)


class ApprovalDelegation(IdentityTimestampMixin, PortalScope, Base):
    __tablename__='approval_delegations'
    __table_args__=portal_scope(__tablename__)+(CheckConstraint('valid_to > valid_from',name='approval_delegation_dates'),)
    delegate_account_id:Mapped[UUID]=mapped_column(ForeignKey('greencity.accounts.id'),nullable=False)
    purpose:Mapped[str]=mapped_column(String(40),nullable=False)
    valid_from:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    valid_to:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    revoked:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)


class FinancePolicy(IdentityTimestampMixin, PortalScope, Base):
    __tablename__='finance_policies'
    __table_args__=portal_scope(__tablename__)+(UniqueConstraint('site_id','code',name='uq_finance_policy_code'),)
    code:Mapped[str]=mapped_column(String(40),nullable=False)
    purpose:Mapped[str]=mapped_column(String(300),nullable=False)
    data:Mapped[dict]=mapped_column(JSON,nullable=False)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='ACTIVE')


class AllocationReversal(IdentityTimestampMixin, Base):
    __tablename__ = 'payment_allocation_reversals'
    __table_args__ = (CheckConstraint('(allocation_id IS NULL) <> (credit_allocation_id IS NULL)', name='reversal_one_allocation'),)
    allocation_id: Mapped[UUID | None] = mapped_column(ForeignKey('greencity.payment_allocations.id'), nullable=True, unique=True)
    credit_allocation_id: Mapped[UUID | None] = mapped_column(ForeignKey('greencity.credit_use_allocations.id'), nullable=True, unique=True)
    command_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.finance_commands.id'), nullable=False)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CreditUseAllocation(IdentityTimestampMixin, Base):
    __tablename__ = 'credit_use_allocations'
    __table_args__ = (CheckConstraint('amount_vnd > 0', name='credit_use_amount'),UniqueConstraint('command_id','invoice_id',name='uq_credit_use_command_invoice'))
    command_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.finance_commands.id'), nullable=False)
    credit_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.overpayment_credits.id'), nullable=False)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.billing_invoices.id'), nullable=False, index=True)
    amount_vnd: Mapped[int] = mapped_column(BigInteger, nullable=False)


class FinanceEvent(IdentityTimestampMixin, Base):
    __tablename__ = 'finance_events'
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.accounts.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(4000), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
