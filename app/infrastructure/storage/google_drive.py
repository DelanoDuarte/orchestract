from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.domain.storage.ports import ExternalFile, OAuthTokens

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


class GoogleDriveConnector:
    """Read-only Google Drive access via plain OAuth2 + Drive v3 REST calls
    (no `google-api-python-client`/`google-auth-oauthlib` -- the flow is one
    redirect URL and one token POST, not worth the heavier dependency).

    Note: only downloads real file bytes (`alt=media`); Google-native
    documents (Docs/Sheets/Slides, `application/vnd.google-apps.*`) would
    need a separate export endpoint and aren't supported in this pass.
    """

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def get_authorization_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": _SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self._redirect_uri,
                },
            )
            response.raise_for_status()
            return _tokens_from_response(response.json())

    async def _refresh(self, tokens: OAuthTokens) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": tokens.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            refreshed = _tokens_from_response(response.json())
            return OAuthTokens(
                access_token=refreshed.access_token,
                refresh_token=tokens.refresh_token,
                expires_at=refreshed.expires_at,
            )

    async def _valid_access_token(self, tokens: OAuthTokens) -> str:
        if tokens.expires_at and tokens.expires_at <= datetime.now(UTC) and tokens.refresh_token:
            tokens = await self._refresh(tokens)
        return tokens.access_token

    async def list_files(self, tokens: OAuthTokens, folder_id: str | None = None) -> list[ExternalFile]:
        access_token = await self._valid_access_token(tokens)
        query = f"'{folder_id}' in parents" if folder_id else None
        params = {
            "pageSize": 50,
            "fields": "files(id,name,mimeType,size,modifiedTime)",
            "orderBy": "modifiedTime desc",
        }
        if query:
            params["q"] = query
        async with httpx.AsyncClient() as client:
            response = await client.get(
                _FILES_URL, params=params, headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            return [
                ExternalFile(
                    id=f["id"],
                    name=f["name"],
                    mime_type=f["mimeType"],
                    size=int(f["size"]) if "size" in f else None,
                    modified_at=datetime.fromisoformat(f["modifiedTime"]) if "modifiedTime" in f else None,
                )
                for f in response.json().get("files", [])
            ]

    async def download_file(self, tokens: OAuthTokens, file_id: str) -> tuple[bytes, str, str]:
        access_token = await self._valid_access_token(tokens)
        async with httpx.AsyncClient() as client:
            meta_response = await client.get(
                f"{_FILES_URL}/{file_id}",
                params={"fields": "name,mimeType"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            meta_response.raise_for_status()
            meta = meta_response.json()

            content_response = await client.get(
                f"{_FILES_URL}/{file_id}",
                params={"alt": "media"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            content_response.raise_for_status()
            return content_response.content, meta["name"], meta["mimeType"]


def _tokens_from_response(payload: dict) -> OAuthTokens:
    expires_in = payload.get("expires_in")
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in) if expires_in is not None else None
    return OAuthTokens(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=expires_at,
    )
