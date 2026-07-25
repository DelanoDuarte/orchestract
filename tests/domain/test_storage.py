import pytest

from app.domain.storage.exceptions import ReadOnlyProviderCannotBePrimaryError
from app.domain.storage.models import ConnectionStatus, StorageConnection, StorageProvider

ORG = 1


def test_create_starts_pending_and_not_primary():
    connection = StorageConnection.create(ORG, StorageProvider.S3, "Prod bucket", {"bucket": "acme"})
    assert connection.status == ConnectionStatus.PENDING
    assert connection.is_primary is False
    assert connection.config == {"bucket": "acme"}


@pytest.mark.parametrize("provider", [StorageProvider.S3, StorageProvider.GCS, StorageProvider.MINIO, StorageProvider.LOCAL])
def test_write_capable_providers_can_become_primary(provider):
    connection = StorageConnection.create(ORG, provider, "Backend")
    connection.mark_primary()
    assert connection.is_primary is True


@pytest.mark.parametrize("provider", [StorageProvider.GOOGLE_DRIVE, StorageProvider.ONEDRIVE])
def test_read_only_providers_cannot_become_primary(provider):
    connection = StorageConnection.create(ORG, provider, "Drive")
    assert connection.is_write_capable is False
    with pytest.raises(ReadOnlyProviderCannotBePrimaryError):
        connection.mark_primary()
    assert connection.is_primary is False


def test_unmark_primary():
    connection = StorageConnection.create(ORG, StorageProvider.S3, "Backend")
    connection.mark_primary()
    connection.unmark_primary()
    assert connection.is_primary is False


def test_lifecycle_transitions():
    connection = StorageConnection.create(ORG, StorageProvider.GCS, "Backend")
    connection.mark_connected()
    assert connection.status == ConnectionStatus.CONNECTED

    connection.mark_error("bucket not found")
    assert connection.status == ConnectionStatus.ERROR
    assert connection.config["last_error"] == "bucket not found"

    connection.mark_primary()
    connection.disconnect()
    assert connection.status == ConnectionStatus.DISCONNECTED
    assert connection.is_primary is False


def test_set_credential_creates_then_updates():
    connection = StorageConnection.create(ORG, StorageProvider.S3, "Backend")
    assert connection.credential is None

    connection.set_credential({"access_key": "a", "secret_key": "b"})
    assert connection.credential.secrets == {"access_key": "a", "secret_key": "b"}

    connection.set_credential({"access_key": "a", "secret_key": "rotated"})
    assert connection.credential.secrets["secret_key"] == "rotated"
