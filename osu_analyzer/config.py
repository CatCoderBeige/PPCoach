"""Konfigurationsverwaltung: App-Zugangsdaten und gespeicherte Nutzereinstellungen.

Die osu! Client-ID/Secret gehoeren zur App (von dir als Entwickler registriert bei
https://osu.ppy.sh/home/account/edit#new-oauth-application), nicht zum einzelnen
Kunden. Kunden geben nur ihren osu! Nutzernamen ein - sonst nichts.

Damit die Zugangsdaten trotzdem nie im (oeffentlichen) Quellcode landen, liegen sie
in genau einer Datei: `_app_credentials.py` (siehe `_app_credentials.py.example` als
Vorlage). Diese Datei ist gitignored, wird aber als normales Python-Modul von
PyInstaller automatisch mit in die gebaute .exe eingepackt - der Kunde bekommt sie
eingebacken, ohne sie je zu sehen oder selbst konfigurieren zu muessen.
"""

import json
import os
from pathlib import Path

APP_NAME = "PPCoach"
VERSION = "1.0.5"

# --- Selbst-Update ---------------------------------------------------------
# Die App liest ihr Update direkt aus der GitHub-Releases-API des Repos:
# das jeweils NEUESTE Release liefert tag_name (= Version), body (= Changelog)
# und das .exe-Asset (= Download). Anders als eine statische latest.json wird die
# API nicht aggressiv vom CDN gecacht - so wird ein neues Release zuverlaessig und
# sofort erkannt (kein "immer keins verfuegbar" mehr).
#
# Beim Start (und bei jedem manuellen Klick) wird geprueft; ist eine neuere Version
# da, kann die App sich selbst herunterladen, austauschen und neu starten (updater.py).
#
# Solange dies leer ("") ist, bleibt die Update-Pruefung still deaktiviert.
UPDATE_API_URL = "https://api.github.com/repos/CatCoderBeige/PPCoach/releases/latest"

# Speicherort fuer persistierte Nutzereinstellungen (z.B. zuletzt genutzter Username)
SETTINGS_DIR = Path(os.getenv("APPDATA", Path.home())) / APP_NAME
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


class ConfigError(Exception):
    """Wird geworfen, wenn App-Zugangsdaten fehlen oder ungueltig sind."""


def get_app_credentials() -> tuple[str, str]:
    """Liefert (client_id, client_secret) fuer die osu! API aus _app_credentials.py.

    Wirft ConfigError mit einer verstaendlichen Meldung, falls die Datei fehlt.
    """
    try:
        from . import _app_credentials  # gitignored, siehe _app_credentials.py.example
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
