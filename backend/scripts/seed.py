import sys
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Database
from app.core.security import hash_password
from app.models.account import Account, AccountRole
from app.models.building import Building
from app.models.enums import RelationshipTypeEnum, RoleEnum, UnitStatusEnum
from app.models.person import Person, UnitPersonRelationship
from app.models.site import Site
from app.models.tenant import Tenant
from app.models.unit import Unit


def seed_database(session: Session) -> None:
    # 1. Tenant
    tenant = session.execute(
        select(Tenant).where(Tenant.name == "GreenCity Corporation")
    ).scalar_one_or_none()
    if not tenant:
        tenant = Tenant(name="GreenCity Corporation")
        session.add(tenant)
        session.flush()

    # 2. Two Sites: West (Demo) & East (Isolation Test)
    site_west = session.execute(
        select(Site).where(Site.tenant_id == tenant.id, Site.code == "GC-WEST")
    ).scalar_one_or_none()
    if not site_west:
        site_west = Site(
            tenant_id=tenant.id,
            code="GC-WEST",
            name="GreenCity West Đô Thị Mẫu",
            address="Đại lộ Ánh Sao, Khu đô thị Tây GreenCity, Hà Nội",
        )
        session.add(site_west)
        session.flush()

    site_east = session.execute(
        select(Site).where(Site.tenant_id == tenant.id, Site.code == "GC-EAST")
    ).scalar_one_or_none()
    if not site_east:
        site_east = Site(
            tenant_id=tenant.id,
            code="GC-EAST",
            name="GreenCity East Kiểm Thử Cô Lập",
            address="Đường Hoa Ban, Khu đô thị Đông GreenCity, Hà Nội",
        )
        session.add(site_east)
        session.flush()

    # 3. Buildings
    building_w1 = session.execute(
        select(Building).where(Building.site_id == site_west.id, Building.code == "W1")
    ).scalar_one_or_none()
    if not building_w1:
        building_w1 = Building(
            site_id=site_west.id,
            code="W1",
            name="Tòa Tháp Ruby W1",
            floors_count=25,
        )
        session.add(building_w1)
        session.flush()

    building_e1 = session.execute(
        select(Building).where(Building.site_id == site_east.id, Building.code == "E1")
    ).scalar_one_or_none()
    if not building_e1:
        building_e1 = Building(
            site_id=site_east.id,
            code="E1",
            name="Tòa Tháp Diamond E1",
            floors_count=20,
        )
        session.add(building_e1)
        session.flush()

    # 4. Units
    unit_w101 = session.execute(
        select(Unit).where(Unit.building_id == building_w1.id, Unit.unit_number == "W1-0101")
    ).scalar_one_or_none()
    if not unit_w101:
        unit_w101 = Unit(
            building_id=building_w1.id,
            unit_number="W1-0101",
            floor=1,
            area_m2=78.5,
            status=UnitStatusEnum.OCCUPIED,
            version=1,
        )
        session.add(unit_w101)
        session.flush()

    unit_e101 = session.execute(
        select(Unit).where(Unit.building_id == building_e1.id, Unit.unit_number == "E1-0201")
    ).scalar_one_or_none()
    if not unit_e101:
        unit_e101 = Unit(
            building_id=building_e1.id,
            unit_number="E1-0201",
            floor=2,
            area_m2=92.0,
            status=UnitStatusEnum.OCCUPIED,
            version=1,
        )
        session.add(unit_e101)
        session.flush()

    # 5. Persons & Unit Relationships (No real PII)
    person_an = session.execute(
        select(Person).where(Person.tenant_id == tenant.id, Person.phone_masked == "090***0001")
    ).scalar_one_or_none()
    if not person_an:
        person_an = Person(
            tenant_id=tenant.id,
            full_name="Nguyễn Văn An",
            phone_masked="090***0001",
            email_masked="an.nv***@greencity.vn",
        )
        session.add(person_an)
        session.flush()

    rel_w101 = session.execute(
        select(UnitPersonRelationship).where(
            UnitPersonRelationship.unit_id == unit_w101.id,
            UnitPersonRelationship.person_id == person_an.id,
        )
    ).scalar_one_or_none()
    if not rel_w101:
        rel_w101 = UnitPersonRelationship(
            unit_id=unit_w101.id,
            person_id=person_an.id,
            relationship_type=RelationshipTypeEnum.OWNER,
            is_active=True,
        )
        session.add(rel_w101)

    person_binh = session.execute(
        select(Person).where(Person.tenant_id == tenant.id, Person.phone_masked == "090***0002")
    ).scalar_one_or_none()
    if not person_binh:
        person_binh = Person(
            tenant_id=tenant.id,
            full_name="Trần Thị Bình",
            phone_masked="090***0002",
            email_masked="binh.tt***@greencity.vn",
        )
        session.add(person_binh)
        session.flush()

    rel_e101 = session.execute(
        select(UnitPersonRelationship).where(
            UnitPersonRelationship.unit_id == unit_e101.id,
            UnitPersonRelationship.person_id == person_binh.id,
        )
    ).scalar_one_or_none()
    if not rel_e101:
        rel_e101 = UnitPersonRelationship(
            unit_id=unit_e101.id,
            person_id=person_binh.id,
            relationship_type=RelationshipTypeEnum.OWNER,
            is_active=True,
        )
        session.add(rel_e101)

    # 6. Accounts and Roles (8 Roles)
    default_hashed_pwd = hash_password("Password@123")

    accounts_data = [
        ("admin_demo", "Quản Trị Viên Demo", [RoleEnum.ADMIN], None),
        ("director_west", "Giám Đốc BQL West", [RoleEnum.DIRECTOR], site_west.id),
        ("cskh_west", "Lễ Tân CSKH West", [RoleEnum.CSKH], site_west.id),
        ("cskh_east", "Lễ Tân CSKH East", [RoleEnum.CSKH], site_east.id),
        ("accountant_west", "Kế Toán Viên West", [RoleEnum.ACCOUNTANT], site_west.id),
        ("techlead_west", "Trưởng Kỹ Thuật West", [RoleEnum.TECHNICAL_LEAD], site_west.id),
        ("technician_west", "Kỹ Thuật Viên West", [RoleEnum.TECHNICIAN], site_west.id),
        ("cleaning_west", "Nhân Viên Vệ Sinh West", [RoleEnum.CLEANING], site_west.id),
        ("security_west", "Nhân Viên An Ninh West", [RoleEnum.SECURITY], site_west.id),
    ]

    for username, full_name, roles, site_id in accounts_data:
        account = session.execute(
            select(Account).where(Account.tenant_id == tenant.id, Account.username == username)
        ).scalar_one_or_none()
        if not account:
            account = Account(
                tenant_id=tenant.id,
                username=username,
                hashed_password=default_hashed_pwd,
                full_name=full_name,
                is_active=True,
            )
            session.add(account)
            session.flush()

        # Provision only these named demo accounts; never infer scope for arbitrary
        # existing users. Legacy site-only grants for building roles remain inert.
        for role in roles:
            building_id = None
            if role in {RoleEnum.CSKH, RoleEnum.TECHNICAL_LEAD, RoleEnum.SECURITY}:
                building_id = building_w1.id if site_id == site_west.id else building_e1.id
            existing_grant = session.execute(select(AccountRole).where(
                AccountRole.account_id == account.id, AccountRole.role == role,
                AccountRole.site_id == site_id, AccountRole.building_id == building_id,
            )).scalar_one_or_none()
            if existing_grant is None:
                acc_role = AccountRole(
                    account_id=account.id,
                    role=role,
                    site_id=site_id,
                    building_id=building_id,
                )
                session.add(acc_role)

    session.commit()
    print("Idempotent seed completed successfully!")


if __name__ == "__main__":
    db = Database(Settings())
    try:
        with db.get_session() as s:
            seed_database(s)
    finally:
        db.close()
