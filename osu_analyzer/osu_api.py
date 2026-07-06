"""Client fuer die offizielle osu! API v2 mit Fehlerbehandlung."""

import requests

from .config import get_app_credentials

TOKEN_URL = "https://osu.ppy.sh/oauth/token"
API_BASE = "https://osu.ppy.sh/api/v2"
REQUEST_TIMEOUT = 10


class OsuApiError(Exception):
    """Verstaendliche Fehlermeldung fuer die GUI-Schicht."""


class UserNotFoundError(OsuApiError):
    pass


class RateLimitError(OsuApiError):
    pass


def _request(method: str, url: str, **kwargs) -> requests.Response:
    try:
        response = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.exceptions.Timeout as exc:
        raise OsuApiError("Connection to the osu! API timed out.") from exc
    except requests.exceptions.ConnectionError as exc:
        raise OsuApiError(
            "Could not connect to the osu! API. Please check your internet connection."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise OsuApiError(f"Unexpected network error: {exc}") from exc

    if response.status_code == 404:
        raise UserNotFoundError("This osu! username/ID was not found.")
    if response.status_code == 429:
        raise RateLimitError("osu! API rate limit reached. Please wait a moment and try again.")
    if response.status_code == 401:
        raise OsuApiError("Authentication with the osu! API failed (invalid app credentials).")
    if not response.ok:
        raise OsuApiError(f"osu! API error (status {response.status_code}).")

    return response


class OsuApiClient:
    def __init__(self):
        self._token: str | None = None

    def _get_token(self) -> str:
        if self._token:
            return self._token

        client_id, client_secret = get_app_credentials()
        response = _request(
            "POST",
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
                "scope": "public",
            },
        )

        try:
            token = response.json()["access_token"]
        except (ValueError, KeyError) as exc:
            raise OsuApiError("Unexpected response while logging in to the osu! API.") from exc

        self._token = token
        return token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def get_user_stats(self, username: str) -> dict:
        response = _request(
            "GET",
            f"{API_BASE}/users/{username}/osu",
            headers=self._auth_headers(),
            params={"key": "username"},
        )
        try:
            return response.json()
        except ValueError as exc:
            raise OsuApiError("Could not read the osu! API response.") from exc

    def get_top_scores(self, user_id: int, limit: int = 10) -> list[dict]:
        # /scores/best akzeptiert nur die numerische User-ID, keinen Nutzernamen
        # (anders als /users/{user}/osu) - daher hier immer id, nie key=username.
        response = _request(
            "GET",
            f"{API_BASE}/users/{user_id}/scores/best",
            headers=self._auth_headers(),
            params={"key": "id", "limit": limit},
        )
        try:
            return response.json()
        except ValueError as exc:
            raise OsuApiError("Could not read the osu! API response.") from exc
