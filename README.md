# PPCoach

An unofficial desktop tool that analyzes your osu! profile stats and top scores
and gives you concrete, rule-based improvement tips - weaknesses in accuracy, mod
usage, consistency, and PP-farming strategy.

**This tool is not affiliated with osu! or ppy.**

## Installation

Download `PPCoach.exe` and run it. No Python, no extra software, no API keys of
your own required.

## Usage

1. Start the app
2. Enter your osu! username
3. Click "Analyze"
4. Read the report - weaknesses and next steps are shown right away

That's all it takes - the app credentials for the osu! API are already baked into
the .exe (see the "For developers" section below).

Your most recently used username is stored locally so you don't have to type it in
every time.

## What the analysis covers

- Accuracy relative to star rating
- Untapped PP potential from mods (HD/HR/DT)
- How wide the difficulty band you play is
- Consistency (rank distribution of your top scores)
- Miss patterns by star rating
- Efficiency of playtime versus PP progress
- Concrete next steps based on your current PP level

There is **no live AI analysis** - all hints are based on fixed, transparent rules
over your actual play data. An AI-powered premium analysis is planned as a future
upgrade (see the "AI Coach" tile in the app).

## Automatic updates (self-update)

The app can update itself - the user never has to download a new file manually. On
startup (and on every manual click on the version hint at the bottom) it queries
the **latest GitHub release**. If a newer version is available, a green
"⬆ Update" button appears; a click downloads the new `.exe`, replaces the running
file via a small helper, and restarts the app.

The version info comes straight from the GitHub Releases API (`tag_name` = version,
`body` = changelog, `.exe` asset = download) - no separate `latest.json` needed, and
no CDN caching that "swallows" a new release.

The self-replacement only works in the built `.exe` (not when started via
`python main.py`) and is Windows-specific.

### Publishing a new update

The app updates live as **GitHub Releases** in the repo
`https://github.com/CatCoderBeige/PPCoach`. `UPDATE_API_URL` in `config.py` already
points to this repo's Releases API.

Publishing a new update is therefore a single step:

1. Bump `VERSION` in `osu_analyzer/config.py` (e.g. `1.0.0` -> `1.0.1`).
2. `python release.py --notes "What's new ..."`

The script builds the `.exe` and uploads it as release `vX.Y.Z` (the `--notes`
become the changelog). Existing users are offered the update automatically on their
next start. (Prerequisite: `gh` installed and `gh auth login` done.)

## Branding

The name and icon are currently a placeholder (`PPCoach`, generated gradient logo
in `assets/logo.png` / `assets/icon.ico`, created by `assets/generate_icon.py`).
To use your own logo:

- Replace `assets/icon.ico` with your own icon (same filename, several sizes
  16-256px embedded)
- Replace `assets/logo.png` for the marketing/Gumroad page
- Adjust the app name in `osu_analyzer/config.py` (`APP_NAME`) as well as `name=`
  in `PPCoach.spec` (rename the file if needed)

## For developers

```
pip install -r requirements.txt
python main.py
```

Accessing the osu! API requires app credentials (register once at
https://osu.ppy.sh/home/account/edit#new-oauth-application - a "Client Credentials"
app, no user login needed). Copy `osu_analyzer/_app_credentials.py.example` to
`osu_analyzer/_app_credentials.py` and fill in your own client ID/secret there. This
file is gitignored, but is bundled into the built .exe automatically as a normal
Python module - customers never see or need it, they only enter their osu! username.

**Known limitation:** The secret is embedded in the compiled `.exe` binary and can be
extracted with tools like `pyinstxtractor`. An accepted risk for the MVP, since the
client-credentials grant only has access to public osu! data (scope `public`) - no
user login, no private data involved. Worst case: third parties share your app's rate
limit, or osu! blocks the app on abuse. If that happens: register new app credentials
at https://osu.ppy.sh/home/account/edit#new-oauth-application, put them in
`_app_credentials.py`, and rebuild. A cleaner (but more involved) fix would be a tiny
token-proxy server that keeps the secret server-side.

### Building the .exe

```
pyinstaller PPCoach.spec
```

The finished `PPCoach.exe` will then be in `dist/`.
