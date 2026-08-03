"""Google OpenID Connect for *login* (distinct from the Drive import OAuth in
app/infrastructure/storage/google_drive.py, which requests drive scopes and
stores tokens). Same dependency-free httpx style: one redirect to Google's
consent screen, one code->token exchange, then a userinfo lookup to learn who
signed in. We read identity from the userinfo endpoint rather than parsing the
id_token JWT so we need no crypto dependency -- it comes straight from Google
over TLS in response to our confidential-client exchange, so it's trustworthy.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import get_settings

_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
_SCOPE = "openid email profile"


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str
    given_name: str | None


class GoogleOAuthClient:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    def authorization_url(self, state: str) -> str:
        params = {
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": _SCOPE,
            # Login only needs an id/userinfo now, no long-lived refresh token.
            "access_type": "online",
            # Always let the user pick which Google account to use.
            "prompt": "select_account",
            "state": state,
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> GoogleIdentity:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self._redirect_uri,
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]

            userinfo_response = await client.get(
                _USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            userinfo_response.raise_for_status()
            data = userinfo_response.json()

        return GoogleIdentity(
            sub=data["sub"],
            email=(data.get("email") or "").strip().lower(),
            email_verified=bool(data.get("email_verified", False)),
            name=(data.get("name") or data.get("email") or "").strip(),
            given_name=data.get("given_name"),
        )


def google_login_enabled() -> bool:
    settings = get_settings()
    return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)


def build_google_oauth_client() -> GoogleOAuthClient:
    settings = get_settings()
    return GoogleOAuthClient(
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        redirect_uri=f"{settings.oauth_redirect_base}/auth/google/callback",
    )
