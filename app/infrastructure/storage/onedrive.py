from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.domain.storage.ports import ExternalFile, OAuthTokens

_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SCOPE = "offline_access Files.Read"


class OneDriveConnector:
    """Read-only OneDrive access via plain OAuth2 + Microsoft Graph REST calls
    (no `msal` -- same reasoning as GoogleDriveConnector: the flow is one
    redirect URL and one token POST).
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
            "response_mode": "query",
            "scope": _SCOPE,
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
                    "scope": _SCOPE,
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
                    "scope": _SCOPE,
                },
            )
            response.raise_for_status()
            return _tokens_from_response(response.json())

    async def _valid_access_token(self, tokens: OAuthTokens) -> str:
        if tokens.expires_at and tokens.expires_at <= datetime.now(UTC) and tokens.refresh_token:
            tokens = await self._refresh(tokens)
        return tokens.access_token

    async def list_files(self, tokens: OAuthTokens, folder_id: str | None = None) -> list[ExternalFile]:
        access_token = await self._valid_access_token(tokens)
        path = f"/me/drive/items/{folder_id}/children" if folder_id else "/me/drive/root/children"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_GRAPH_BASE}{path}",
                params={"$top": 50, "$orderby": "lastModifiedDateTime desc"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return [
                ExternalFile(
                    id=item["id"],
                    name=item["name"],
                    mime_type=item.get("file", {}).get("mimeType", "application/octet-stream"),
                    size=item.get("size"),
                    modified_at=(
                        datetime.fromisoformat(item["lastModifiedDateTime"].replace("Z", "+00:00"))
                        if "lastModifiedDateTime" in item
                        else None
                    ),
                )
                for item in response.json().get("value", [])
                if "folder" not in item
            ]

    async def download_file(self, tokens: OAuthTokens, file_id: str) -> tuple[bytes, str, str]:
        access_token = await self._valid_access_token(tokens)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            meta_response = await client.get(
                f"{_GRAPH_BASE}/me/drive/items/{file_id}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            meta_response.raise_for_status()
            meta = meta_response.json()

            content_response = await client.get(
                f"{_GRAPH_BASE}/me/drive/items/{file_id}/content",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            content_response.raise_for_status()
            mime_type = meta.get("file", {}).get("mimeType", "application/octet-stream")
            return content_response.content, meta["name"], mime_type


def _tokens_from_response(payload: dict) -> OAuthTokens:
    expires_in = payload.get("expires_in")
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in) if expires_in is not None else None
    return OAuthTokens(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token"),
        expires_at=expires_at,
    )
