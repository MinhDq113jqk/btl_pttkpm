from uuid import UUID
from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str


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


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user: UserInfo


class SwitchSiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: UUID
