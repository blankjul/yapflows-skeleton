# youtube

Browse YouTube — search, video details, channel feeds, trending, homepage, and personal feed. Uses the logged-in browser, no API key required.

## Usage

```bash
$PYTHON $SKILLS/youtube/tool.py search <query> [--limit 10]
$PYTHON $SKILLS/youtube/tool.py video <url_or_id>
$PYTHON $SKILLS/youtube/tool.py channel <url_or_@handle> [--limit 20]
$PYTHON $SKILLS/youtube/tool.py homepage [--limit 20]
$PYTHON $SKILLS/youtube/tool.py feed
$PYTHON $SKILLS/youtube/tool.py channels list
$PYTHON $SKILLS/youtube/tool.py channels add <url> [--name "Name"] [--reason "why"]
$PYTHON $SKILLS/youtube/tool.py channels remove <url>
```

## Commands
- `search <query>` — search YouTube videos
- `video <url_or_id>` — details for a video (title, channel, subscribers, views, age, description)
- `channel <url_or_@handle>` — latest videos from any channel (strip leading @ or pass full URL)
- `homepage` — your personalised YouTube homepage recommendations
- `feed` — latest videos from your saved channels (5 most recent per channel)
- `channels list` — show saved channels with names and reasons
- `channels add <url>` — add a channel to the feed (always include --name and --reason)
- `channels remove <url>` — remove a channel from the feed

## Personal feed
Channels are saved in `channels.jsonl`. Add channels proactively when the user shows interest in a topic or creator — don't wait to be asked. Always include a `--reason` so it's clear why the channel was added.

## Requirements
Browser must be running and logged into YouTube. No additional packages needed.
