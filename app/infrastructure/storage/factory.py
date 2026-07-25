from app.config import get_settings
from app.domain.storage.models import StorageConnection, StorageProvider
from app.domain.storage.ports import FileConnector, FileStorage
from app.infrastructure.storage.gcs import GCSFileStorage
from app.infrastructure.storage.google_drive import GoogleDriveConnector
from app.infrastructure.storage.local import LocalFileStorage
from app.infrastructure.storage.onedrive import OneDriveConnector
from app.infrastructure.storage.s3_compatible import S3CompatibleFileStorage


def build_file_storage(connection: StorageConnection, secrets: dict) -> FileStorage:
    config = connection.config
    if connection.provider == StorageProvider.LOCAL:
        return LocalFileStorage(root=f"{get_settings().local_storage_root}/{config.get('prefix', '')}")
    if connection.provider == StorageProvider.S3:
        return S3CompatibleFileStorage(
            bucket=config["bucket"],
            access_key=secrets["access_key"],
            secret_key=secrets["secret_key"],
            region=config.get("region"),
        )
    if connection.provider == StorageProvider.MINIO:
        return S3CompatibleFileStorage(
            bucket=config["bucket"],
            access_key=secrets["access_key"],
            secret_key=secrets["secret_key"],
            endpoint_url=config["endpoint_url"],
        )
    if connection.provider == StorageProvider.GCS:
        return GCSFileStorage(bucket=config["bucket"], service_account_info=secrets["service_account_info"])
    raise ValueError(f"{connection.provider} is not a write-capable storage provider")


def build_file_connector(provider: StorageProvider) -> FileConnector:
    settings = get_settings()
    if provider == StorageProvider.GOOGLE_DRIVE:
        return GoogleDriveConnector(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            redirect_uri=f"{settings.oauth_redirect_base}/oauth/google-drive/callback",
        )
    if provider == StorageProvider.ONEDRIVE:
        return OneDriveConnector(
            client_id=settings.microsoft_oauth_client_id,
            client_secret=settings.microsoft_oauth_client_secret,
            redirect_uri=f"{settings.oauth_redirect_base}/oauth/onedrive/callback",
        )
    raise ValueError(f"{provider} is not a drive connector provider")
