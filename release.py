"""Release-Helfer fuer PPCoach.

Baut die .exe und laedt sie als GitHub-Release hoch - in einem Schritt. Der
Auto-Updater liest Version (tag_name), Changelog (body) und die .exe direkt aus
der GitHub-Releases-API; eine separate latest.json ist nicht noetig.

Ablauf fuer ein neues Update:
  1. In osu_analyzer/config.py die VERSION hochzaehlen (z.B. "1.0.0" -> "1.1.0").
  2. python release.py --notes "Was ist neu ..."

Voraussetzungen: pyinstaller installiert, gh (GitHub CLI) installiert und via
`gh auth login` angemeldet.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = "CatCoderBeige/PPCoach"
EXE_NAME = "PPCoach.exe"


def _read_version() -> str:
    """Liest VERSION aus config.py, ohne das Paket importieren zu muessen."""
    ns: dict = {}
    config_text = (ROOT / "osu_analyzer" / "config.py").read_text(encoding="utf-8")
    for line in config_text.splitlines():
        if line.strip().startswith("VERSION"):
            exec(line, ns)  # noqa: S102 - kontrollierte, eigene Datei
            break
    version = ns.get("VERSION")
    if not version:
        sys.exit("Konnte VERSION nicht aus config.py lesen.")
    return version


def _find_gh() -> str:
    gh = shutil.which("gh")
    if gh:
        return gh
    default = r"C:\Program Files\GitHub CLI\gh.exe"
    if os.path.exists(default):
        return default
    sys.exit("gh (GitHub CLI) nicht gefunden. Bitte installieren: winget install GitHub.cli")


def build_exe() -> Path:
    print(">> Baue .exe mit PyInstaller ...")
    subprocess.run([sys.executable, "-m", "PyInstaller", "PPCoach.spec", "--noconfirm"],
                   cwd=ROOT, check=True)
    exe = ROOT / "dist" / EXE_NAME
    if not exe.exists():
        sys.exit(f"Build fehlgeschlagen: {exe} existiert nicht.")
    return exe


def create_release(gh: str, version: str, notes: str, exe: Path):
    tag = f"v{version}"
    print(f">> Erstelle GitHub-Release {tag} ...")
    subprocess.run(
        [gh, "release", "create", tag, str(exe),
         "--repo", REPO, "--title", f"PPCoach {tag}", "--notes", notes],
        cwd=ROOT, check=True,
    )
    print(f">> Fertig! Release {tag} ist online. Nutzer bekommen das Update automatisch.")


def main():
    parser = argparse.ArgumentParser(description="PPCoach Release erstellen")
    parser.add_argument("--notes", default="", help="Changelog / Was ist neu")
    parser.add_argument("--skip-build", action="store_true",
                        help="Vorhandene dist/PPCoach.exe wiederverwenden")
    args = parser.parse_args()

    version = _read_version()
    notes = args.notes or f"PPCoach {version}"
    gh = _find_gh()

    print(f"== Release fuer Version {version} ==")
    exe = (ROOT / "dist" / EXE_NAME) if args.skip_build else build_exe()
    if args.skip_build and not exe.exists():
        sys.exit("--skip-build gesetzt, aber dist/PPCoach.exe fehlt.")
    create_release(gh, version, notes, exe)


if __name__ == "__main__":
    main()
