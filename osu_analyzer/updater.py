"""Self-update mechanism (launcher-style) for PPCoach.

Idea: the user never has to download a new file manually. On startup the app
queries the GitHub Releases API (``UPDATE_API_URL`` in config.py), compares the
release version with its own, and can - at the click of a button - download the new
``.exe``, replace the running file and restart itself.

The actual replacement only works in the built ``.exe`` (``sys.frozen``). In Python
dev mode there is no target .exe, so the replacement is skipped.

Windows quirk: a running ``.exe`` cannot overwrite its own CONTENT - but it can be
RENAMED while running. That's exactly what ``apply_update_and_restart`` uses: the
running exe is renamed aside (``.old``), the new exe is written to the original path,
the new version is started and the process exits. On the next start the ``.old`` is
cleaned up. This technique is far more robust than the earlier "wait + overwrite"
approach (no race condition, no batch file that could lock the file).
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

# Windows process flags so the newly started process survives our own exit.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200

_UPDATE_EXE_NAME = "PPCoach_update.exe"
_LOG_NAME = "ppcoach_update.log"

# Guard against applying twice in the same process (e.g. a fast double-click):
# once an update is running, further calls are ignored.
_apply_started = False


def _log(msg: str) -> None:
    """Writes a diagnostic line to %TEMP%\\ppcoach_update.log (errors ignored)."""
    try:
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n"
        with open(os.path.join(tempfile.gettempdir(), _LOG_NAME), "a",
                  encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def cleanup_old() -> None:
    """Deletes the ``PPCoach.exe.old`` left aside by the last update, as well as
    leftovers from older update approaches (temp exe, stale batch file).

    Call on startup. If a file is still locked (previous process not fully exited
    yet), it is retried on the next start.
    """
    if not is_frozen():
        return
    leftovers = [
        sys.executable + ".old",
        os.path.join(tempfile.gettempdir(), _UPDATE_EXE_NAME),
        os.path.join(tempfile.gettempdir(), "ppcoach_update.bat"),  # old approach
    ]
    for path in leftovers:
        if os.path.exists(path):
            try:
                os.remove(path)
                _log(f"cleanup_old: removed {path}")
            except OSError:
                pass


def _strip_mark_of_the_web(path: str) -> None:
    """Removes the 'Mark of the Web' (NTFS stream ``:Zone.Identifier``) from
    ``path``. Without this marker Windows does not treat the freshly installed exe
    as 'from the internet' - so no SmartScreen/security warning appears on the
    automatic restart. Errors (not NTFS, not present) don't matter.
    """
    try:
        os.remove(path + ":Zone.Identifier")
        _log("strip_motw: removed Zone.Identifier")
    except OSError:
        pass


@dataclass
class UpdateInfo:
    version: str
    url: str
    notes: str = ""


def is_frozen() -> bool:
    """True if we run as a built .exe (PyInstaller), not as python main.py."""
    return bool(getattr(sys, "frozen", False))


def _parse_version(value: str) -> tuple[int, ...]:
    """'1.2.0' / 'v1.2' -> (1, 2, 0). Non-numeric parts become 0."""
    parts = []
    for piece in str(value).strip().lstrip("vV").split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts) or (0,)


def is_newer(remote: str, local: str = VERSION) -> bool:
    """Compares two version strings component-wise (padded to equal length)."""
    a, b = _parse_version(remote), _parse_version(local)
    length = max(len(a), len(b))
    a += (0,) * (length - len(a))
    b += (0,) * (length - len(b))
    return a > b


def check_for_update(timeout: int = 8) -> UpdateInfo | None:
    """Queries the latest GitHub release and returns UpdateInfo if it is newer.

    Reads tag_name (version), body (changelog) and the .exe asset (download) from the
    GitHub Releases API. No-cache headers + a unique query parameter prevent a stale
    (cached) state from being served - so a new release is detected reliably on EVERY
    check.

    If ``UPDATE_API_URL`` is empty, None is returned silently. Raises an exception on
    network/format errors - the caller handles that tolerantly.
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
        params={"_": int(time.time())},  # cache buster
    )
    resp.raise_for_status()
    data = resp.json()

    version = str(data.get("tag_name", "")).lstrip("vV")
    notes = str(data.get("body") or "").strip()

    # Download link: the first .exe asset of the release.
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
    """Downloads the new .exe into the temp folder and returns the path.

    ``progress_cb(fraction: float)`` is called with the progress (0.0..1.0) - if
    provided and the size is known.
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

    # Sanity check: a real Windows .exe starts with "MZ". Prevents an HTML error
    # page or similar from being installed as the program by mistake.
    with open(dest, "rb") as fh:
        magic = fh.read(2)
    if magic != b"MZ":
        raise RuntimeError("Downloaded file is not a valid .exe (bad magic bytes).")

    return dest


def replace_executable(current: str, new_exe: str) -> str:
    """Swaps the file ``current`` for ``new_exe`` and returns the path of the old
    file set aside (``current + ".old"``).

    Technique: ``current`` is renamed (``.old``) - Windows allows this even for a
    currently running exe -, then ``new_exe`` is moved to the original path (with
    retries against short-lived antivirus locks). If the move fails, it is rolled
    back and an exception is raised, so a broken/missing exe is never left behind.
    Kept separate so the logic is testable.
    """
    old = current + ".old"

    # Idempotent: if the source file is missing, the new exe was already installed
    # (e.g. by a second instance or a double click). Then there is nothing left to
    # do - no rollback, no error message, the app just restarts normally.
    if not os.path.exists(new_exe):
        _log("replace: new_exe missing -> already applied, nothing to do")
        return old

    if os.path.exists(old):
        try:
            os.remove(old)
        except OSError as exc:
            _log(f"replace: could not remove stale .old: {exc}")

    os.rename(current, old)  # running exe set aside (allowed while it runs)
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
            os.rename(old, current)  # rollback -> app stays launchable
            _log("replace: rolled back .old -> current")
        except OSError as exc:
            _log(f"replace: ROLLBACK FAILED: {exc}")
        raise RuntimeError(f"Could not install the update: {last_err}")

    return old


def apply_update_and_restart(new_exe: str) -> None:
    """Replaces the running .exe with ``new_exe`` and restarts the new version.

    Terminates the current process on success (``os._exit``). The leftover ``.old``
    is cleaned up by the newly started process on startup via ``cleanup_old()``.
    """
    global _apply_started
    if _apply_started:
        _log("apply: already in progress in this process, ignoring second call")
        return
    _apply_started = True

    if not is_frozen():
        raise RuntimeError(
            "Self-update only works in the built .exe, not in Python dev mode."
        )

    current = sys.executable
    _log(f"apply: current={current}  new={new_exe}")
    replace_executable(current, new_exe)
    # Don't leave the freshly installed exe marked as 'from the internet' -> otherwise
    # Windows could show a SmartScreen warning on the restart.
    _strip_mark_of_the_web(current)

    # Fresh environment for the relaunch. A PyInstaller onefile process carries
    # internal variables (_PYI_APPLICATION_HOME_DIR / _PYI_PARENT_PROCESS_LEVEL /
    # _MEIPASS2) that tell a spawned copy of itself to REUSE the current unpack dir
    # instead of extracting again. After an update that is exactly wrong: the new exe
    # would run the OLD extracted code and then crash with a FileNotFoundError once
    # the old process's temp dir is cleaned up. Stripping them forces a clean, full
    # extraction of the new exe.
    env = os.environ.copy()
    for key in [k for k in env if k.startswith("_PYI") or k.startswith("_MEIPASS")]:
        del env[key]

    try:
        subprocess.Popen(
            [current], env=env,
            creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
            cwd=os.path.dirname(current) or None,
        )
        _log("apply: relaunched new version (fresh env), exiting")
    except OSError as exc:
        _log(f"apply: relaunch failed: {exc}")
    os._exit(0)
