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
