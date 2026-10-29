from uuid import UUID
from datetime import date
from sqlalchemy import BigInteger, Date, ForeignKey, JSON, String, UniqueConstraint, CheckConstraint, Uuid, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, IdentityTimestampMixin
from app.models.resident_portal import PortalScope, portal_scope


class CommercialLedger(IdentityTimestampMixin, PortalScope, Base):
    __tablename__='commercial_ledgers'
    __table_args__=portal_scope(__tablename__)+(UniqueConstraint('contract_id','kind','starts_on',name='uq_commercial_period'),
        CheckConstraint('amount_vnd > 0 AND received_vnd >= 0 AND received_vnd <= amount_vnd AND released_vnd >= 0 AND deducted_vnd >= 0 AND released_vnd + deducted_vnd <= received_vnd',name='commercial_money'),
        CheckConstraint("kind IN ('RENT','SERVICE','DEPOSIT') AND ends_on > starts_on", name='commercial_kind_period'),)
    contract_id:Mapped[UUID]=mapped_column(ForeignKey('greencity.operations_records.id'))
    source_record_id:Mapped[UUID]=mapped_column(ForeignKey('greencity.operations_records.id'))
    kind:Mapped[str]=mapped_column(String(20))
    starts_on:Mapped[date]=mapped_column(Date)
    ends_on:Mapped[date]=mapped_column(Date)
    due_on:Mapped[date]=mapped_column(Date)
    amount_vnd:Mapped[int]=mapped_column(BigInteger)
    received_vnd:Mapped[int]=mapped_column(BigInteger,default=0)
    released_vnd:Mapped[int]=mapped_column(BigInteger,default=0)
    deducted_vnd:Mapped[int]=mapped_column(BigInteger,default=0)
    status:Mapped[str]=mapped_column(String(20),default='OPEN')
    snapshot:Mapped[dict]=mapped_column(JSON)


class ExchangeState(IdentityTimestampMixin, PortalScope, Base):
    __tablename__='exchange_object_states'
    __table_args__=portal_scope(__tablename__)+(UniqueConstraint('endpoint_id','source_type','source_id',name='uq_exchange_object'),)
    endpoint_id:Mapped[UUID]=mapped_column(ForeignKey('greencity.integration_endpoints.id'))
    source_type:Mapped[str]=mapped_column(String(40))
    source_id:Mapped[UUID]=mapped_column(Uuid)
    source_version:Mapped[int]=mapped_column(Integer)
    payload:Mapped[dict]=mapped_column(JSON)
    external_reference:Mapped[str]=mapped_column(String(150))


class ExchangeReceipt(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'exchange_receipts'
    __table_args__ = portal_scope(__tablename__) + (UniqueConstraint('endpoint_id', 'external_id', name='uq_exchange_receipt'),)
    endpoint_id: Mapped[UUID] = mapped_column(ForeignKey('greencity.integration_endpoints.id'))
    external_id: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default='RECEIVED')


class AssistantConversation(IdentityTimestampMixin, PortalScope, Base):
    __tablename__ = 'assistant_conversations'
    __table_args__ = portal_scope(__tablename__)
    title: Mapped[str] = mapped_column(String(200))
    messages: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    request_id: Mapped[UUID | None] = mapped_column(ForeignKey('greencity.service_requests.id'), nullable=True)
