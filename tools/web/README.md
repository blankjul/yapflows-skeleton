Three tools for fetching web content, ordered by speed and capability:

- **fetch** — Plain HTTP request. Fastest. No JavaScript, no cookies, no browser. Use for static pages, articles, documentation, public APIs, raw files.
- **search** — Headless browser search (Bing/Google/DuckDuckGo). Returns ranked results with titles, URLs, and snippets. Use when you need to discover URLs or find current information without a known starting URL.
- **browser** — Full browser automation with VNC, cookies, and persistent sessions. Slowest. Use only when the page requires JavaScript rendering, login/authentication, or interactive navigation (clicking, form filling).

**Decision guide:** Start with `fetch` — it's instant and has no overhead. If the page is JS-rendered or behind auth, use `browser`. If you don't know where to look, use `search` first to get candidate URLs, then `fetch` or `browser` the result. `search` and `browser` share session state — pass `--session` to continue across tools.
