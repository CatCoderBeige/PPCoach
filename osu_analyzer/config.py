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
VERSION = "1.0.0"

# --- Selbst-Update ---------------------------------------------------------
# URL zu einer kleinen JSON-Datei, in der die neueste Version + Download-Link steht.
# Die App fragt sie beim Start ab; ist eine neuere Version verfuegbar, kann sie sich
# selbst herunterladen, austauschen und neu starten (siehe updater.py).
#
# Erwartetes JSON-Format:
#   {
#     "version": "1.1.0",
#     "url": "https://.../PPCoach.exe",
#     "notes": "Was ist neu ..."   (optional)
#   }
#
# Hosting-Beispiele fuer diese Datei + die .exe:
#   - GitHub Releases / raw:  https://github.com/<user>/<repo>/releases/latest/download/latest.json
#   - eigener Webserver:      https://deine-seite.de/ppcoach/latest.json
#   - Cloud-Speicher mit Direktlink
#
# Solange dies leer ("") ist, bleibt die Update-Pruefung still deaktiviert.
# Zeigt auf die latest.json des jeweils neuesten GitHub-Releases (immer aktuell).
UPDATE_MANIFEST_URL = (
    "https://github.com/CatCoderBeige/PPCoach/releases/latest/download/latest.json"
)

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
            "Keine osu! API-Zugangsdaten gefunden. Bitte osu_analyzer/_app_credentials.py "
            "anlegen (Vorlage: osu_analyzer/_app_credentials.py.example kopieren und "
            "ausfuellen)."
        ) from exc

    client_id = getattr(_app_credentials, "CLIENT_ID", None)
    client_secret = getattr(_app_credentials, "CLIENT_SECRET", None)

    if not client_id or not client_secret:
        raise ConfigError(
            "osu_analyzer/_app_credentials.py existiert, aber CLIENT_ID/CLIENT_SECRET "
            "sind leer. Bitte mit echten Werten befuellen."
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
