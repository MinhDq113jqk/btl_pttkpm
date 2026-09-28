from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("username")
    @classmethod
    def reject_nul_username(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("username contains an unsupported character")
        return value


class SiteSummary(BaseModel):
    id: UUID
    code: str
    name: str


class UserInfo(BaseModel):
    account_id: UUID
    tenant_id: UUID
    username: str
    full_name: str
    roles: list[str]
    active_site_id: UUID | None
    allowed_sites: list[SiteSummary]
    resident_person_id: UUID | None = None
    # Unit IDs are server-derived effective grants for the active site.  They
    # allow a resident UI to choose a unit without supplying a Person identity.
    resident_unit_ids: list[UUID] = Field(default_factory=list)
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user: UserInfo


class SwitchSiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: UUID
