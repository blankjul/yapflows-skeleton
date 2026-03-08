# seattle_activities

Search Seattle Parks & Recreation activity registrations at community centers. Uses the logged-in browser — no API key required.

## Commands

| Command | Description |
|---------|-------------|
| `search [options]` | Search activities, returns list with URLs |
| `detail URL_OR_ID` | Fetch full details for one activity |
| `list-sites` | List all community centers with their IDs |

## search options

| Flag | Description |
|------|-------------|
| `--where NAME_OR_ID` | Community center name (partial match ok) or site ID (default: Green Lake CC) |
| `--name TEXT` | Filter by activity name or number |
| `--after TIME` | Activities starting at or after this time (e.g. `5pm`, `17:00`) |
| `--before TIME` | Activities starting before this time (e.g. `9pm`, `21:00`) |
| `--min-age N` | Minimum participant age |
| `--max-age N` | Maximum participant age |
| `--available` | Only show activities with open spots |

## search output fields

Each activity includes: `name`, `id`, `url`, `age`, `openings`, `location`, `dates`, `schedule`, `price`, `status`, `available`.

## detail output fields

`name`, `description`, `meeting_dates`, `instructor`, `supervisor`, `num_sessions`, `registration_dates`, `url`.

> **Note:** `detail` accepts either the `url` from search output, or a bare registration number
> (`87781` or `#87781`). When a registration number is given, it automatically looks up the correct URL.

## Examples

```bash
# Activities at Green Lake after 5pm with open spots
$PYTHON $SKILLS/seattle_activities/tool.py search --after 5pm --available

# Get details — pass the url from search output
$PYTHON $SKILLS/seattle_activities/tool.py detail "https://apm.activecommunities.com/seattle/Activity_Search/drop-in-adult-volleyball/82457?locale=en-US"

# Or pass the registration number directly (auto-lookup)
$PYTHON $SKILLS/seattle_activities/tool.py detail 87781

# Pottery classes at Ballard Community Center
$PYTHON $SKILLS/seattle_activities/tool.py search --where "Ballard Community Center" --name pottery

# Kids soccer ages 5-9 after 4pm
$PYTHON $SKILLS/seattle_activities/tool.py search --name soccer --after 4pm --min-age 5 --max-age 9

# List all community centers
$PYTHON $SKILLS/seattle_activities/tool.py list-sites
```

## How filters work

All filters are passed as URL parameters — the server pre-filters results before the page loads. No UI interaction required.

| URL param | CLI flag | Format |
|-----------|----------|--------|
| `site_ids` | `--where` | numeric ID |
| `activity_keyword` | `--name` | free text |
| `time_after_str` | `--after` | `HH:MM` 24h |
| `time_before_str` | `--before` | `HH:MM` 24h |
| `min_age` / `max_age` | `--min-age` / `--max-age` | integer |

**Lazy loading:** The page loads 20 activities at a time. The tool clicks **View more** repeatedly until all results are loaded.

## Requirements
Browser must be running. No additional packages needed.
