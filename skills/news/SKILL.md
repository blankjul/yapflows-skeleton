# news

Aggregates news from multiple platforms and sources.

## Features
- Fetch top news from HN (Hacker News)
- Fetch top news from Reddit (r/news, r/worldnews)
- Search for specific topics across web
- Filter by topic or keywords

## Usage

```bash
$PYTHON $SKILLS/news/news.py top [--source hn|reddit|all] [--limit 10]
$PYTHON $SKILLS/news/news.py search <query> [--engine google|duckduckgo]
```

## Sources
- Hacker News (web_fetch)
- Reddit (web_fetch)
- Web search (web_search)
