# Strava API App Setup

Before running `strava.py auth`, you need a Strava API application.

## Steps

### 1. Log into Strava in the VNC browser
Open the yapflows browser and go to https://www.strava.com/login.
Sign in with your Strava account.

### 2. Create an API application
Go to https://www.strava.com/settings/api.

If you don't have an app yet, fill in:
- **Application Name** — anything (e.g. `yapflows`)
- **Category** — Other
- **Club** — leave blank
- **Website** — `http://localhost`
- **Authorization Callback Domain** — `localhost`

Click **Create**.

### 3. Note your credentials
After creating the app you'll see:
- **Client ID** — a number (e.g. `173086`)
- **Client Secret** — click **Show** to reveal the secret string

### 4. Add to settings.json
Add under `integrations` in `$USER_DIR/settings.json`:

```json
{
  "integrations": {
    "strava": {
      "client_id": "YOUR_CLIENT_ID",
      "client_secret": "YOUR_CLIENT_SECRET"
    }
  }
}
```

Or just run `$PYTHON $SKILLS/strava/strava.py auth` — it will extract
the credentials automatically from the VNC browser if you're logged in.

## Notes
- The callback domain **must** be `localhost` (not `localhost:8765`)
- You can have multiple apps; the skill uses whichever credentials are in settings.json
- To revoke access: https://www.strava.com/settings/apps
