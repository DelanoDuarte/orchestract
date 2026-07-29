import enum
import secrets
from datetime import datetime, timedelta

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.shared.base import Base
from app.domain.shared.password import hash_password, verify_password
from app.domain.shared.types import slugify, utcnow
from app.domain.users.exceptions import EmptyRoleNameError, EmptyUserEmailError, EmptyUserNameError

_SESSION_TTL = timedelta(days=14)
EMAIL_VERIFICATION_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(hours=1)


class Role(Base):
    """A dynamically created role within an organization.

    `agent_id` is the optional link described by the feature: when set, only
    users holding this (or another) role linked to that same agent may act
    on workflow steps the agent owns. Left null, the role carries no special
    editing power and steps owned by an unlinked agent stay open to anyone.
    """

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_role_org_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id"), default=None, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @classmethod
    def create(
        cls, organization_id: int, name: str, description: str | None = None, agent_id: int | None = None
    ) -> "Role":
        name = name.strip()
        if not name:
            raise EmptyRoleNameError()
        return cls(
            organization_id=organization_id,
            name=name,
            slug=slugify(name),
            description=description,
            agent_id=agent_id,
        )

    def rename(self, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name:
            raise EmptyRoleNameError()
        self.name = new_name
        self.slug = slugify(new_name)

    def set_description(self, description: str | None) -> None:
        self.description = description

    def set_agent(self, agent_id: int | None) -> None:
        self.agent_id = agent_id


class User(Base):
    """A person who can log in to one organization.

    Every user carries exactly one `role_id` -- roles are the unit that
    workflow-step permissions are checked against (see
    `app.domain.users.permissions.can_edit_step`).
    """

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(300))
    password_hash: Mapped[str] = mapped_column(String(300))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @classmethod
    def create(
        cls, organization_id: int, name: str, email: str, raw_password: str, role_id: int
    ) -> "User":
        name = name.strip()
        if not name:
            raise EmptyUserNameError()
        email = email.strip().lower()
        if not email:
            raise EmptyUserEmailError()
        return cls(
            organization_id=organization_id,
            name=name,
            email=email,
            password_hash=hash_password(raw_password),
            role_id=role_id,
            is_active=True,
        )

    def verify_password(self, raw_password: str) -> bool:
        return verify_password(raw_password, self.password_hash)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = hash_password(raw_password)

    def rename(self, new_name: str) -> None:
        new_name = new_name.strip()
        if not new_name:
            raise EmptyUserNameError()
        self.name = new_name

    def set_role(self, role_id: int) -> None:
        self.role_id = role_id

    def deactivate(self) -> None:
        self.is_active = False

    def activate(self) -> None:
        self.is_active = True

    def mark_email_verified(self) -> None:
        self.email_verified_at = utcnow()

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None


class UserSession(Base):
    """An opaque, DB-backed login session. The cookie only ever holds
    `token` -- validity/expiry/revocation are all checked server-side
    against this table, so a session can be invalidated by deleting the row.
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()

    @classmethod
    def issue(cls, user_id: int, ttl: timedelta = _SESSION_TTL) -> "UserSession":
        return cls(user_id=user_id, token=secrets.token_urlsafe(32), expires_at=utcnow() + ttl)

    def is_valid(self) -> bool:
        return utcnow() < self.expires_at


class UserTokenPurpose(str, enum.Enum):
    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"


class UserToken(Base):
    """A single-use, DB-backed token for out-of-band flows (email
    verification, password reset) -- mirrors `UserSession`'s shape, but
    scoped to a `purpose` and always deleted after use rather than left to
    expire naturally.
    """

    __tablename__ = "user_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[UserTokenPurpose] = mapped_column(Enum(UserTokenPurpose))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()

    @classmethod
    def issue(cls, user_id: int, purpose: UserTokenPurpose) -> "UserToken":
        ttl = EMAIL_VERIFICATION_TTL if purpose is UserTokenPurpose.EMAIL_VERIFICATION else PASSWORD_RESET_TTL
        return cls(
            user_id=user_id,
            purpose=purpose,
            token=secrets.token_urlsafe(32),
            expires_at=utcnow() + ttl,
        )

    def is_valid(self) -> bool:
        return utcnow() < self.expires_at
