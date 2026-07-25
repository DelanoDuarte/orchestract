import enum
from datetime import datetime

from sqlalchemy import JSON, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.shared.base import Base
from app.domain.shared.encrypted_json import EncryptedJSON
from app.domain.shared.types import utcnow
from app.domain.storage.exceptions import ReadOnlyProviderCannotBePrimaryError


class StorageProvider(str, enum.Enum):
    S3 = "s3"
    GCS = "gcs"
    MINIO = "minio"
    GOOGLE_DRIVE = "google_drive"
    ONEDRIVE = "onedrive"
    LOCAL = "local"


READ_ONLY_PROVIDERS = {StorageProvider.GOOGLE_DRIVE, StorageProvider.ONEDRIVE}


class ConnectionStatus(str, enum.Enum):
    PENDING = "pending"
    CONNECTED = "connected"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class StorageCredential(Base):
    """Secrets for a StorageConnection: bucket access keys or OAuth tokens.

    Kept in a separate table (not columns on StorageConnection) so it's easy
    to exclude from anything that serializes a connection, and so the
    sensitive blob has a single, obvious owner. `secrets` is encrypted at
    rest -- see EncryptedJSON.
    """

    __tablename__ = "storage_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    storage_connection_id: Mapped[int] = mapped_column(
        ForeignKey("storage_connections.id"), unique=True, index=True
    )
    secrets: Mapped[dict] = mapped_column(EncryptedJSON)

    connection: Mapped["StorageConnection"] = relationship(back_populates="credential")


class StorageConnection(Base):
    """A configured file-storage backend or read-only drive connection for one organization.

    Exactly one connection may be `is_primary` at a time (where new document
    version bytes are written) and only one connection may exist per
    (organization, provider) pair -- both are cross-aggregate-instance
    invariants enforced by the application layer (`StorageService`), since
    they depend on sibling rows rather than this aggregate's own state.
    """

    __tablename__ = "storage_connections"
    __table_args__ = (UniqueConstraint("organization_id", "provider", name="uq_conn_org_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    provider: Mapped[StorageProvider] = mapped_column(Enum(StorageProvider))
    status: Mapped[ConnectionStatus] = mapped_column(Enum(ConnectionStatus), default=ConnectionStatus.PENDING)
    is_primary: Mapped[bool] = mapped_column(default=False)
    display_name: Mapped[str] = mapped_column(String(200))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    credential: Mapped[StorageCredential | None] = relationship(
        back_populates="connection", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    @property
    def is_write_capable(self) -> bool:
        return self.provider not in READ_ONLY_PROVIDERS

    @classmethod
    def create(
        cls, organization_id: int, provider: StorageProvider, display_name: str, config: dict | None = None
    ) -> "StorageConnection":
        return cls(
            organization_id=organization_id,
            provider=provider,
            display_name=display_name,
            config=config or {},
            status=ConnectionStatus.PENDING,
            is_primary=False,
        )

    def set_credential(self, secrets: dict) -> StorageCredential:
        if self.credential is None:
            self.credential = StorageCredential(secrets=secrets)
        else:
            self.credential.secrets = secrets
        return self.credential

    def mark_connected(self) -> None:
        self.status = ConnectionStatus.CONNECTED

    def mark_error(self, message: str) -> None:
        self.status = ConnectionStatus.ERROR
        self.config = {**self.config, "last_error": message}

    def disconnect(self) -> None:
        self.status = ConnectionStatus.DISCONNECTED
        self.is_primary = False

    def mark_primary(self) -> None:
        if not self.is_write_capable:
            raise ReadOnlyProviderCannotBePrimaryError(self.provider.value)
        self.is_primary = True

    def unmark_primary(self) -> None:
        self.is_primary = False
