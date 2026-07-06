"""Release helper for PPCoach.

Builds the .exe and uploads it as a GitHub release - in one step. The auto-updater
reads the version (tag_name), changelog (body) and the .exe straight from the
GitHub Releases API; a separate latest.json is not needed.

Steps for a new update:
  1. Bump VERSION in osu_analyzer/config.py (e.g. "1.0.0" -> "1.1.0").
  2. python release.py --notes "What's new ..."

Prerequisites: pyinstaller installed, gh (GitHub CLI) installed and logged in via
`gh auth login`.
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
    """Reads VERSION from config.py without having to import the package."""
    ns: dict = {}
    config_text = (ROOT / "osu_analyzer" / "config.py").read_text(encoding="utf-8")
    for line in config_text.splitlines():
        if line.strip().startswith("VERSION"):
            exec(line, ns)  # noqa: S102 - controlled, our own file
            break
    version = ns.get("VERSION")
    if not version:
        sys.exit("Could not read VERSION from config.py.")
    return version


def _find_gh() -> str:
    gh = shutil.which("gh")
    if gh:
        return gh
    default = r"C:\Program Files\GitHub CLI\gh.exe"
    if os.path.exists(default):
        return default
    sys.exit("gh (GitHub CLI) not found. Please install it: winget install GitHub.cli")


def build_exe() -> Path:
    print(">> Building .exe with PyInstaller ...")
    subprocess.run([sys.executable, "-m", "PyInstaller", "PPCoach.spec", "--noconfirm"],
                   cwd=ROOT, check=True)
    exe = ROOT / "dist" / EXE_NAME
    if not exe.exists():
        sys.exit(f"Build failed: {exe} does not exist.")
    return exe


def create_release(gh: str, version: str, notes: str, exe: Path):
    tag = f"v{version}"
    print(f">> Creating GitHub release {tag} ...")
    subprocess.run(
        [gh, "release", "create", tag, str(exe),
         "--repo", REPO, "--title", f"PPCoach {tag}", "--notes", notes],
        cwd=ROOT, check=True,
    )
    print(f">> Done! Release {tag} is online. Users get the update automatically.")


def main():
    parser = argparse.ArgumentParser(description="Create a PPCoach release")
    parser.add_argument("--notes", default="", help="Changelog / what's new")
    parser.add_argument("--skip-build", action="store_true",
                        help="Reuse the existing dist/PPCoach.exe")
    args = parser.parse_args()

    version = _read_version()
    notes = args.notes or f"PPCoach {version}"
    gh = _find_gh()

    print(f"== Release for version {version} ==")
    exe = (ROOT / "dist" / EXE_NAME) if args.skip_build else build_exe()
    if args.skip_build and not exe.exists():
        sys.exit("--skip-build set, but dist/PPCoach.exe is missing.")
    create_release(gh, version, notes, exe)


if __name__ == "__main__":
    main()
