import pytest
from pydantic import ValidationError
from sqlalchemy import BigInteger

from app.models import (
    ACCOUNTING_PERIOD_TRANSITIONS,
    BILLING_INVOICE_TRANSITIONS,
    BILLING_RUN_TRANSITIONS,
    PAYMENT_TRANSITIONS,
    AccountingPeriodStatusEnum,
    ArLedgerEntry,
    ArLedgerEntryTypeEnum,
    BillingAccount,
    BillingInvoice,
    BillingInvoiceItem,
    BillingInvoiceStatusEnum,
    BillingRun,
    BillingRunStatusEnum,
    FeePolicyVersion,
    Payment,
    PaymentStatusEnum,
)
from app.schemas.r4 import BillingPaymentCreate


def names(constraints):
    return {constraint.name for constraint in constraints}


def test_r4_state_enums_and_transitions_are_explicit_and_terminal_states_do_not_reopen():
    assert {state.value for state in AccountingPeriodStatusEnum} == {"OPEN", "CLOSING", "CLOSED", "LOCKED"}
    assert {state.value for state in BillingRunStatusEnum} == {"DRAFT", "CALCULATING", "REVIEW", "POSTED", "FAILED", "CANCELLED"}
    assert {state.value for state in BillingInvoiceStatusEnum} == {"DRAFT", "ISSUED", "PARTIALLY_PAID", "PAID", "VOID"}
    assert {state.value for state in PaymentStatusEnum} == {
        "RECEIVED", "ALLOCATING", "PARTIALLY_ALLOCATED", "ALLOCATED", "UNMATCHED", "OVERPAID", "REVERSED",
    }
    assert {state.value for state in ArLedgerEntryTypeEnum} == {
        "INVOICE_ISSUED", "PAYMENT_RECEIVED", "CREDIT_ISSUED", "CREDIT_APPLIED", "REVERSAL",
    }
    assert ACCOUNTING_PERIOD_TRANSITIONS["LOCKED"] == frozenset()
    assert BILLING_RUN_TRANSITIONS["POSTED"] == frozenset()
    assert BILLING_RUN_TRANSITIONS["FAILED"] == frozenset({"CALCULATING", "CANCELLED"})
    assert BILLING_INVOICE_TRANSITIONS["PAID"] == frozenset()
    assert PAYMENT_TRANSITIONS["REVERSED"] == frozenset()


def test_r4_constraints_keep_billing_runs_and_payments_idempotent_and_ledger_one_sided():
    assert {
        "uq_billing_runs_site_key",
        "uq_billing_runs_period_policy",
        "ck_billing_runs_billing_runs_status",
    }.issubset(names(BillingRun.__table__.constraints))
    assert {
        "uq_payments_source_reference",
        "uq_payments_receipt_number",
        "ck_payments_payments_amount_positive",
    }.issubset(names(Payment.__table__.constraints))
    assert {
        "uq_ar_ledger_entries_source_type",
        "ck_ar_ledger_entries_ar_ledger_entries_one_sided",
    }.issubset(names(ArLedgerEntry.__table__.constraints))


def test_r4_amounts_are_integer_vnd_and_billing_invoice_items_do_not_repurpose_r2_posting_anchor():
    for column in (
        FeePolicyVersion.__table__.c.unit_rate_vnd,
        BillingInvoice.__table__.c.total_vnd,
        BillingInvoice.__table__.c.outstanding_vnd,
        BillingInvoiceItem.__table__.c.amount_vnd,
        Payment.__table__.c.amount_vnd,
        ArLedgerEntry.__table__.c.debit_vnd,
        ArLedgerEntry.__table__.c.credit_vnd,
    ):
        assert isinstance(column.type, BigInteger)
    assert BillingInvoiceItem.__tablename__ == "billing_invoice_items"
    assert BillingInvoiceItem.__tablename__ != "invoice_items"
    assert "uq_billing_accounts_building_unit" in names(BillingAccount.__table__.constraints)


def test_r4_payment_contract_rejects_float_bool_and_naive_datetime_for_vnd_input():
    payload = {
        "billing_account_id": "0e7d0d36-178a-4e50-93d6-8a412d9b6902",
        "accounting_period_id": "eece1bfa-00d4-4e8d-8f9d-5e56a0f7b2a9",
        "payment_source": "BANK_TRANSFER",
        "source_reference": "bank-20260914-001",
        "receipt_number": "RCPT-20260914-001",
        "amount_vnd": 120000,
        "received_at": "2026-09-14T09:00:00+07:00",
    }
    assert BillingPaymentCreate.model_validate(payload).amount_vnd == 120000
    for invalid in (120000.0, True):
        with pytest.raises(ValidationError):
            BillingPaymentCreate.model_validate(payload | {"amount_vnd": invalid})
    with pytest.raises(ValidationError):
        BillingPaymentCreate.model_validate(payload | {"received_at": "2026-09-14T09:00:00"})
