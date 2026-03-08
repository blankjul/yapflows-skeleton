# strava

Read your Strava activities, athlete profile, and activity details via the Strava API v3.

## Usage

```bash
$PYTHON $SKILLS/strava/tool.py auth
$PYTHON $SKILLS/strava/tool.py athlete
$PYTHON $SKILLS/strava/tool.py activities [--limit N] [--before UNIX_TS] [--after UNIX_TS]
$PYTHON $SKILLS/strava/tool.py activity <id>
```

## Commands
- `auth` — full OAuth2 setup via VNC browser, saves tokens to `.env`
- `athlete` — get your athlete profile (JSON)
- `activities` — list recent activities (JSON); filter by date with `--before`/`--after` (Unix timestamps)
- `activity <id>` — get full details for a specific activity (JSON)

## Files
- `tool.py` — all commands
- `.env` — credentials and tokens (auto-managed)
- `assets/signup.md` — how to create a Strava API app

## First-time setup
1. Log into Strava in the VNC browser
2. Run: `$PYTHON $SKILLS/strava/tool.py auth`
