from enum import StrEnum


class RoleEnum(StrEnum):
    ADMIN = "admin"
    DIRECTOR = "director"
    CSKH = "cskh"
    ACCOUNTANT = "accountant"
    TECHNICAL_LEAD = "technical_lead"
    TECHNICIAN = "technician"
    CLEANING = "cleaning"
    SECURITY = "security"


class UnitStatusEnum(StrEnum):
    OCCUPIED = "occupied"
    VACANT = "vacant"
    RESERVED = "reserved"


class RelationshipTypeEnum(StrEnum):
    OWNER = "owner"
    TENANT = "tenant"
    FAMILY_MEMBER = "family_member"


class CleaningTaskStatusEnum(StrEnum):
    PLANNED = "PLANNED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    MISSED = "MISSED"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    CANCELLED = "CANCELLED"


class PatrolWindowStatusEnum(StrEnum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"


class SecurityIncidentStatusEnum(StrEnum):
    NEW = "NEW"
    TRIAGED = "TRIAGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SecurityIncidentSeverityEnum(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BillingAccountStatusEnum(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class AccountingPeriodStatusEnum(StrEnum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    LOCKED = "LOCKED"


class BillingRunStatusEnum(StrEnum):
    DRAFT = "DRAFT"
    CALCULATING = "CALCULATING"
    REVIEW = "REVIEW"
    POSTED = "POSTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BillingInvoiceStatusEnum(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    VOID = "VOID"


class PaymentStatusEnum(StrEnum):
    RECEIVED = "RECEIVED"
    ALLOCATING = "ALLOCATING"
    PARTIALLY_ALLOCATED = "PARTIALLY_ALLOCATED"
    ALLOCATED = "ALLOCATED"
    UNMATCHED = "UNMATCHED"
    OVERPAID = "OVERPAID"
    REVERSED = "REVERSED"


class OverpaymentCreditStatusEnum(StrEnum):
    OPEN = "OPEN"
    EXHAUSTED = "EXHAUSTED"
    VOID = "VOID"


class ArLedgerEntryTypeEnum(StrEnum):
    INVOICE_ISSUED = "INVOICE_ISSUED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    CREDIT_ISSUED = "CREDIT_ISSUED"
    CREDIT_APPLIED = "CREDIT_APPLIED"
    REVERSAL = "REVERSAL"
