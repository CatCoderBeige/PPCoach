"""Configuration management: app credentials and stored user settings.

The osu! client ID/secret belong to the app (registered by you as the developer at
https://osu.ppy.sh/home/account/edit#new-oauth-application), not to the individual
customer. Customers only enter their osu! username - nothing else.

To make sure the credentials still never end up in the (public) source code, they
live in exactly one file: `_app_credentials.py` (see `_app_credentials.py.example`
as a template). This file is gitignored, but is bundled into the built .exe
automatically by PyInstaller as a normal Python module - the customer gets it baked
in without ever seeing or having to configure it.
"""

import json
import os
from pathlib import Path

APP_NAME = "PPCoach"
VERSION = "1.0.8"

# --- Self-update -----------------------------------------------------------
# The app reads its update straight from the repo's GitHub Releases API:
# the LATEST release provides tag_name (= version), body (= changelog) and the
# .exe asset (= download). Unlike a static latest.json, the API isn't aggressively
# cached by the CDN - so a new release is detected reliably and immediately
# (no more "always nothing available").
#
# It's checked on startup (and on every manual click); if a newer version is
# available, the app can download, replace and restart itself (updater.py).
#
# As long as this is empty (""), the update check stays silently disabled.
UPDATE_API_URL = "https://api.github.com/repos/CatCoderBeige/PPCoach/releases/latest"

# Location for persisted user settings (e.g. most recently used username)
SETTINGS_DIR = Path(os.getenv("APPDATA", Path.home())) / APP_NAME
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


class ConfigError(Exception):
    """Raised when app credentials are missing or invalid."""


def get_app_credentials() -> tuple[str, str]:
    """Returns (client_id, client_secret) for the osu! API from _app_credentials.py.

    Raises ConfigError with a clear message if the file is missing.
    """
    try:
        from . import _app_credentials  # gitignored, see _app_credentials.py.example
    except ImportError as exc:
        raise ConfigError(
            "No osu! API credentials found. Please create osu_analyzer/_app_credentials.py "
            "(template: copy osu_analyzer/_app_credentials.py.example and fill it in)."
        ) from exc

    client_id = getattr(_app_credentials, "CLIENT_ID", None)
    client_secret = getattr(_app_credentials, "CLIENT_SECRET", None)

    if not client_id or not client_secret:
        raise ConfigError(
            "osu_analyzer/_app_credentials.py exists, but CLIENT_ID/CLIENT_SECRET are "
            "empty. Please fill them with real values."
        )

    return client_id, client_secret


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_settings(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def get_last_username() -> str | None:
    return load_settings().get("last_username")


def set_last_username(username: str) -> None:
    settings = load_settings()
    settings["last_username"] = username
    save_settings(settings)
