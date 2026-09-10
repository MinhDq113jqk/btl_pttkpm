"""r1_foundation

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    schema = 'greencity'

    op.create_table(
        'sites',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('address', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['greencity.tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_sites_tenant_id_code'),
        schema=schema
    )
    op.create_index(op.f('ix_greencity_sites_tenant_id'), 'sites', ['tenant_id'], unique=False, schema=schema)

    op.create_table(
        'buildings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('site_id', sa.Uuid(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('floors_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['site_id'], ['greencity.sites.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_id', 'code', name='uq_buildings_site_id_code'),
        schema=schema
    )
    op.create_index(op.f('ix_greencity_buildings_site_id'), 'buildings', ['site_id'], unique=False, schema=schema)

    op.create_table(
        'units',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('building_id', sa.Uuid(), nullable=False),
        sa.Column('unit_number', sa.String(length=50), nullable=False),
        sa.Column('floor', sa.Integer(), nullable=False),
        sa.Column('area_m2', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='occupied'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['building_id'], ['greencity.buildings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('building_id', 'unit_number', name='uq_units_building_id_unit_number'),
        schema=schema
    )
    op.create_index(op.f('ix_greencity_units_building_id'), 'units', ['building_id'], unique=False, schema=schema)

    op.create_table(
        'persons',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('full_name', sa.String(length=200), nullable=False),
        sa.Column('phone_masked', sa.String(length=50), nullable=False),
        sa.Column('email_masked', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['greencity.tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema=schema
    )
    op.create_index(op.f('ix_greencity_persons_tenant_id'), 'persons', ['tenant_id'], unique=False, schema=schema)

    op.create_table(
        'unit_person_relationships',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('unit_id', sa.Uuid(), nullable=False),
        sa.Column('person_id', sa.Uuid(), nullable=False),
        sa.Column('relationship_type', sa.String(length=50), nullable=False, server_default='owner'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['unit_id'], ['greencity.units.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['person_id'], ['greencity.persons.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema=schema
    )
    op.create_index(op.f('ix_greencity_unit_person_relationships_unit_id'), 'unit_person_relationships', ['unit_id'], unique=False, schema=schema)
    op.create_index(op.f('ix_greencity_unit_person_relationships_person_id'), 'unit_person_relationships', ['person_id'], unique=False, schema=schema)

    op.create_table(
        'accounts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=200), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['greencity.tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'username', name='uq_accounts_tenant_id_username'),
        schema=schema
    )
    op.create_index(op.f('ix_greencity_accounts_tenant_id'), 'accounts', ['tenant_id'], unique=False, schema=schema)

    op.create_table(
        'account_roles',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('account_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('site_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['greencity.accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['site_id'], ['greencity.sites.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema=schema
    )
    op.create_index(op.f('ix_greencity_account_roles_account_id'), 'account_roles', ['account_id'], unique=False, schema=schema)
    op.create_index(op.f('ix_greencity_account_roles_site_id'), 'account_roles', ['site_id'], unique=False, schema=schema)


def downgrade() -> None:
    schema = 'greencity'
    op.drop_table('account_roles', schema=schema)
    op.drop_table('accounts', schema=schema)
    op.drop_table('unit_person_relationships', schema=schema)
    op.drop_table('persons', schema=schema)
    op.drop_table('units', schema=schema)
    op.drop_table('buildings', schema=schema)
    op.drop_table('sites', schema=schema)
