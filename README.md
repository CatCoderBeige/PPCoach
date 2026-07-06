# PPCoach

Ein inoffizielles Desktop-Tool, das deine osu! Profil-Stats und Top-Scores analysiert
und dir konkrete, regelbasierte Verbesserungstipps gibt - Schwachstellen in Genauigkeit,
Mod-Nutzung, Konsistenz und PP-Farming-Strategie.

**Dieses Tool ist nicht von osu! oder ppy affiliiert.**

## Installation

Lade `PPCoach.exe` herunter und starte sie. Kein Python, keine Zusatzsoftware,
keine eigenen API-Keys noetig.

## Nutzung

1. App starten
2. Deinen osu! Nutzernamen eingeben
3. "Analysieren" klicken
4. Report lesen - Schwachstellen und naechste Schritte werden direkt angezeigt

Mehr braucht es nicht - die App-Zugangsdaten fuer die osu! API stecken bereits fest
in der .exe (siehe Abschnitt "Fuer Entwickler" unten).

Dein zuletzt genutzter Nutzername wird lokal gespeichert, damit du ihn nicht jedes Mal
neu eingeben musst.

## Was die Analyse abdeckt

- Genauigkeit im Verhaeltnis zur Sternebewertung
- Ungenutztes PP-Potenzial durch Mods (HD/HR/DT)
- Wie breit dein gespieltes Schwierigkeitsband ist
- Konsistenz (Rank-Verteilung deiner Top-Scores)
- Miss-Muster nach Sternebewertung
- Effizienz von Spielzeit zu PP-Fortschritt
- Konkrete naechste Schritte je nach aktuellem PP-Level

Es findet **keine Live-KI-Analyse** statt - alle Hinweise basieren auf festen,
nachvollziehbaren Regeln ueber deine tatsaechlichen Spieldaten. Eine KI-gestuetzte
Premium-Analyse ist als zukuenftiges Upgrade in Planung (siehe "AI Coach"-Kachel in der App).

## Automatische Updates (Selbst-Update)

Die App kann sich selbst aktualisieren - der Nutzer muss nie manuell eine neue Datei
herunterladen. Beim Start (und bei jedem manuellen Klick auf den Versions-Hinweis
unten) fragt sie das **neueste GitHub-Release** ab. Ist eine neuere Version verfuegbar,
erscheint ein gruener "⬆ Update"-Button; ein Klick laedt die neue `.exe`, ersetzt die
laufende Datei ueber einen kleinen Helfer und startet die App neu.

Die Versions-Info kommt direkt aus der GitHub-Releases-API (`tag_name` = Version,
`body` = Changelog, `.exe`-Asset = Download) - keine separate `latest.json` noetig, und
kein CDN-Caching, das ein neues Release "verschluckt".

Der Selbstaustausch funktioniert nur in der gebauten `.exe` (nicht beim Start ueber
`python main.py`) und ist Windows-spezifisch.

### Neues Update veroeffentlichen

Die App-Updates liegen als **GitHub Releases** im Repo
`https://github.com/CatCoderBeige/PPCoach`. `UPDATE_API_URL` in `config.py` zeigt bereits
auf die Releases-API dieses Repos.

Ein neues Update ist damit ein Schritt:

1. In `osu_analyzer/config.py` die `VERSION` hochzaehlen (z.B. `1.0.0` -> `1.0.1`).
2. `python release.py --notes "Was ist neu ..."`

Das Skript baut die `.exe` und laedt sie als Release `vX.Y.Z` hoch (die `--notes`
werden zum Changelog). Bestehende Nutzer bekommen das Update beim naechsten Start
automatisch angeboten. (Voraussetzung: `gh` installiert und `gh auth login` erledigt.)

## Branding

Name und Icon sind aktuell ein Platzhalter (`PPCoach`, generiertes Farbverlauf-Logo
in `assets/logo.png` / `assets/icon.ico`, erzeugt von `assets/generate_icon.py`).
Eigenes Logo einbauen:

- `assets/icon.ico` durch dein eigenes Icon ersetzen (gleicher Dateiname, mehrere
  Groessen 16-256px eingebettet)
- `assets/logo.png` fuer Marketing/Gumroad-Seite ersetzen
- App-Name in `osu_analyzer/config.py` (`APP_NAME`) sowie `name=` in `PPCoach.spec`
  anpassen (Datei ggf. umbenennen)

## Fuer Entwickler

```
pip install -r requirements.txt
python main.py
```

Fuer den osu! API-Zugriff werden App-Zugangsdaten benoetigt (einmalig registrieren unter
https://osu.ppy.sh/home/account/edit#new-oauth-application - "Client Credentials"-App,
kein Nutzerlogin noetig). Kopiere `osu_analyzer/_app_credentials.py.example` zu
`osu_analyzer/_app_credentials.py` und trage dort deine eigene Client-ID/Secret ein.
Diese Datei ist gitignored, wird aber als normales Python-Modul automatisch mit in
die gebaute .exe eingepackt - Kunden sehen oder brauchen sie nie, sie geben nur ihren
osu! Nutzernamen ein.

**Bekannte Einschraenkung:** Das Secret steckt im kompilierten `.exe`-Binary und laesst
sich mit Tools wie `pyinstxtractor` extrahieren. Akzeptiertes Risiko fuers MVP, da der
Client-Credentials-Grant nur Zugriff auf oeffentliche osu!-Daten hat (Scope `public`) -
kein Nutzer-Login, keine privaten Daten betroffen. Schlimmstenfalls: Dritte nutzen dein
App-Rate-Limit mit, oder osu! sperrt die App bei Missbrauch. Falls das passiert: neue
App-Zugangsdaten unter https://osu.ppy.sh/home/account/edit#new-oauth-application
registrieren, in `_app_credentials.py` eintragen, neu bauen. Sauberer (aber
aufwendigerer) Fix waere ein winziger Token-Proxy-Server, der das Secret serverseitig
haelt.

### .exe bauen

```
pyinstaller PPCoach.spec
```

Die fertige `PPCoach.exe` liegt danach in `dist/`.
