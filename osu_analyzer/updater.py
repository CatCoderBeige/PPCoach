"""Selbst-Update-Mechanismus (Launcher-artig) fuer PPCoach.

Idee: Der Nutzer muss nie manuell eine neue Datei herunterladen. Die App fragt
beim Start eine kleine JSON-Manifest-Datei ab (``UPDATE_MANIFEST_URL`` in config.py),
vergleicht die dort genannte Version mit der eigenen und kann - auf Knopfdruck -
die neue ``.exe`` herunterladen, die laufende Datei ersetzen und sich neu starten.

Der eigentliche Austausch funktioniert nur in der gebauten ``.exe`` (``sys.frozen``).
Im Python-Dev-Modus gibt es keine Ziel-.exe; dann wird der Austausch uebersprungen.

Windows-Besonderheit: Eine laufende ``.exe`` kann ihren INHALT nicht selbst
ueberschreiben - aber sie kann UMBENANNT werden, waehrend sie laeuft. Genau das
nutzt ``apply_update_and_restart``: die laufende Exe wird zur Seite umbenannt
(``.old``), die neue Exe an den Originalpfad geschrieben, die neue Version gestartet
und der Prozess beendet. Beim naechsten Start wird die ``.old`` aufgeraeumt. Diese
Technik ist deutlich robuster als der fruehere "warten + ueberschreiben"-Ansatz
(keine Race Condition, kein Batch, das die Datei sperren koennte).
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

import requests

from .config import UPDATE_API_URL, VERSION

# Windows-Prozess-Flags, damit der neu gestartete Prozess unser Beenden ueberlebt.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200

_UPDATE_EXE_NAME = "PPCoach_update.exe"
_LOG_NAME = "ppcoach_update.log"


def _log(msg: str) -> None:
    """Schreibt eine Diagnosezeile nach %TEMP%\\ppcoach_update.log (Fehler ignoriert)."""
    try:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n"
        with open(os.path.join(tempfile.gettempdir(), _LOG_NAME), "a",
                  encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def cleanup_old() -> None:
    """Loescht die beim letzten Update zur Seite gelegte ``PPCoach.exe.old``.

    Beim Start aufrufen. Falls die Datei noch gesperrt ist (Vorgaenger-Prozess noch
    nicht ganz beendet), wird sie beim naechsten Start erneut versucht.
    """
    if not is_frozen():
        return
    old = sys.executable + ".old"
    if os.path.exists(old):
        try:
            os.remove(old)
            _log(f"cleanup_old: removed {old}")
        except OSError:
            pass


@dataclass
class UpdateInfo:
    version: str
    url: str
    notes: str = ""


def is_frozen() -> bool:
    """True, wenn wir als gebaute .exe laufen (PyInstaller), nicht als python main.py."""
    return bool(getattr(sys, "frozen", False))


def _parse_version(value: str) -> tuple[int, ...]:
    """'1.2.0' / 'v1.2' -> (1, 2, 0). Nicht-numerische Teile werden zu 0."""
    parts = []
    for piece in str(value).strip().lstrip("vV").split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def is_newer(remote: str, local: str = VERSION) -> bool:
    """Vergleicht zwei Versions-Strings komponentenweise (auf gleiche Laenge aufgefuellt)."""
    a, b = _parse_version(remote), _parse_version(local)
    length = max(len(a), len(b))
    a += (0,) * (length - len(a))
    b += (0,) * (length - len(b))
    return a > b


def check_for_update(timeout: int = 8) -> UpdateInfo | None:
    """Fragt das neueste GitHub-Release ab und liefert UpdateInfo, falls neuer.

    Liest tag_name (Version), body (Changelog) und das .exe-Asset (Download) aus der
    GitHub-Releases-API. No-Cache-Header + eindeutiger Query-Parameter verhindern,
    dass ein veralteter (gecachter) Stand geliefert wird - so wird ein neues Release
    bei JEDER Pruefung zuverlaessig erkannt.

    Ist ``UPDATE_API_URL`` leer, wird still None zurueckgegeben. Wirft bei Netzwerk-/
    Formatfehlern eine Exception - der Aufrufer behandelt das tolerant.
    """
    if not UPDATE_API_URL:
        return None

    resp = requests.get(
        UPDATE_API_URL,
        timeout=timeout,
        headers={
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        params={"_": int(time.time())},  # Cache-Buster
    )
    resp.raise_for_status()
    data = resp.json()

    version = str(data.get("tag_name", "")).lstrip("vV")
    notes = str(data.get("body") or "").strip()

    # Download-Link: das erste .exe-Asset des Releases.
    url = ""
    for asset in data.get("assets", []):
        name = str(asset.get("name", ""))
        if name.lower().endswith(".exe"):
            url = str(asset.get("browser_download_url", ""))
            break

    if version and url and is_newer(version):
        return UpdateInfo(version=version, url=url, notes=notes)
    return None


def download_update(info: UpdateInfo, progress_cb=None, timeout: int = 60) -> str:
    """Laedt die neue .exe in den Temp-Ordner und liefert den Pfad zurueck.

    ``progress_cb(fraction: float)`` wird - falls uebergeben und die Groesse bekannt
    ist - mit dem Fortschritt (0.0..1.0) aufgerufen.
    """
    dest = os.path.join(tempfile.gettempdir(), _UPDATE_EXE_NAME)

    with requests.get(info.url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                fh.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(min(done / total, 1.0))

    if progress_cb:
        progress_cb(1.0)

    # Sanity-Check: eine echte Windows-.exe beginnt mit "MZ". Verhindert, dass eine
    # HTML-Fehlerseite o.ae. faelschlich als Programm eingespielt wird.
    with open(dest, "rb") as fh:
        magic = fh.read(2)
    if magic != b"MZ":
        raise RuntimeError("Downloaded file is not a valid .exe (bad magic bytes).")

    return dest


def replace_executable(current: str, new_exe: str) -> str:
    """Tauscht die Datei ``current`` gegen ``new_exe`` aus und liefert den Pfad der
    zur Seite gelegten alten Datei (``current + ".old"``).

    Technik: ``current`` wird umbenannt (``.old``) - das erlaubt Windows auch fuer
    eine gerade laufende Exe -, dann wird ``new_exe`` an den Originalpfad verschoben
    (mit Retries gegen kurzzeitige Virenscanner-Sperren). Schlaegt das Verschieben
    fehl, wird zurueckgerollt und eine Exception geworfen, damit nie eine kaputte/
    fehlende Exe zurueckbleibt. Separat gehalten, damit die Logik testbar ist.
    """
    old = current + ".old"

    if os.path.exists(old):
        try:
            os.remove(old)
        except OSError as exc:
            _log(f"replace: could not remove stale .old: {exc}")

    os.rename(current, old)  # laufende Exe zur Seite (waehrend sie laeuft erlaubt)
    _log("replace: renamed current -> .old")

    last_err = None
    for attempt in range(5):
        try:
            shutil.move(new_exe, current)
            _log(f"replace: moved new -> current (attempt {attempt + 1})")
            last_err = None
            break
        except OSError as exc:
            last_err = exc
            _log(f"replace: move attempt {attempt + 1} failed: {exc}")
            time.sleep(0.6)

    if last_err is not None:
        try:
            os.rename(old, current)  # Rollback -> App bleibt startbar
            _log("replace: rolled back .old -> current")
        except OSError as exc:
            _log(f"replace: ROLLBACK FAILED: {exc}")
        raise RuntimeError(f"Could not install the update: {last_err}")

    return old


def apply_update_and_restart(new_exe: str) -> None:
    """Ersetzt die laufende .exe durch ``new_exe`` und startet die neue Version neu.

    Beendet den aktuellen Prozess bei Erfolg (``os._exit``). Die zurueckgelassene
    ``.old`` raeumt der neu gestartete Prozess beim Start via ``cleanup_old()`` auf.
    """
    if not is_frozen():
        raise RuntimeError(
            "Self-update only works in the built .exe, not in Python dev mode."
        )

    current = sys.executable
    _log(f"apply: current={current}  new={new_exe}")
    replace_executable(current, new_exe)

    try:
        subprocess.Popen(
            [current],
            creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            cwd=os.path.dirname(current) or None,
        )
        _log("apply: relaunched new version, exiting")
    except OSError as exc:
        _log(f"apply: relaunch failed: {exc}")
    os._exit(0)
