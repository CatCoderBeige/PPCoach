"""Selbst-Update-Mechanismus (Launcher-artig) fuer PPCoach.

Idee: Der Nutzer muss nie manuell eine neue Datei herunterladen. Die App fragt
beim Start eine kleine JSON-Manifest-Datei ab (``UPDATE_MANIFEST_URL`` in config.py),
vergleicht die dort genannte Version mit der eigenen und kann - auf Knopfdruck -
die neue ``.exe`` herunterladen, die laufende Datei ersetzen und sich neu starten.

Der eigentliche Austausch funktioniert nur in der gebauten ``.exe`` (``sys.frozen``).
Im Python-Dev-Modus gibt es keine Ziel-.exe; dann wird der Austausch uebersprungen.

Windows-Besonderheit: Eine laufende ``.exe`` kann sich nicht selbst ueberschreiben.
Deshalb schreibt ``apply_update_and_restart`` ein winziges Batch-Skript, das wartet,
bis dieser Prozess beendet ist, die Datei ersetzt, die App neu startet und sich
anschliessend selbst loescht.
"""

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

import requests

from .config import UPDATE_MANIFEST_URL, VERSION

# Windows-Prozess-Flags, damit der Update-Helfer unser Beenden ueberlebt.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200

_UPDATE_EXE_NAME = "PPCoach_update.exe"
_UPDATE_BAT_NAME = "ppcoach_update.bat"


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
    """Fragt das Manifest ab und liefert UpdateInfo, falls eine neuere Version existiert.

    Ist ``UPDATE_MANIFEST_URL`` leer, wird still None zurueckgegeben (Feature deaktiviert).
    Wirft bei Netzwerk-/Formatfehlern eine Exception - der Aufrufer soll das tolerant
    behandeln (ein nicht erreichbarer Update-Server darf die App nie stoeren).
    """
    if not UPDATE_MANIFEST_URL:
        return None

    resp = requests.get(UPDATE_MANIFEST_URL, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    version = str(data["version"])
    url = str(data["url"])
    notes = str(data.get("notes", ""))

    if is_newer(version):
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
    return dest


def apply_update_and_restart(new_exe: str) -> None:
    """Ersetzt die laufende .exe durch ``new_exe`` und startet neu (Windows).

    Beendet danach sofort den aktuellen Prozess (``os._exit``), damit der Helfer die
    Datei ersetzen kann. Kehrt im Erfolgsfall NICHT zurueck.
    """
    if not is_frozen():
        raise RuntimeError(
            "Selbst-Update ist nur in der gebauten .exe moeglich, nicht im "
            "Python-Entwicklermodus."
        )

    current = sys.executable
    pid = os.getpid()
    bat_path = os.path.join(tempfile.gettempdir(), _UPDATE_BAT_NAME)

    # Warten bis dieser Prozess weg ist, dann Datei tauschen, neu starten, Skript loeschen.
    # ping statt timeout: robust auch ohne Konsolen-Stdin.
    script = (
        "@echo off\r\n"
        ":waitloop\r\n"
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        "    ping -n 2 127.0.0.1 >nul\r\n"
        "    goto waitloop\r\n"
        ")\r\n"
        f'move /Y "{new_exe}" "{current}" >nul\r\n'
        f'start "" "{current}"\r\n'
        'del "%~f0"\r\n'
    )
    with open(bat_path, "w", encoding="ascii") as fh:
        fh.write(script)

    subprocess.Popen(
        ["cmd", "/c", bat_path],
        creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    os._exit(0)
