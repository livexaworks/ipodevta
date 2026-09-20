# IPO Devta — free IPO screening Telegram bot

Personalized DMs from your own GMP / subscription / MAIN-vs-SME settings, plus a
public channel with the unfiltered daily GMP feed for issues closing that day.

This is **information only**, not investment advice. Verdicts are 👍 / 👎 plus
the numbers that produced them. Grey-market premium is unofficial and can be
manipulated. Read the RHP.

## Free-tier stack

- Public GitHub repo + **GitHub Actions** cron (no paid host, no database)
- State in committed `data/*.json`
- Telegram Bot API

Scheduled workflows are **disabled by GitHub after 60 days** without repo activity.
Push a commit or run the workflow manually before that window expires.

## Setup

1. Copy `.env.example` → `.env` (local only; never commit `.env`).
2. Create a bot with [@BotFather](https://t.me/BotFather).
3. Create a public channel; add the bot as admin with **Post Messages**.
4. Set GitHub Actions secrets: `TELEGRAM_TOKEN`, `CHANNEL_ID`, `ADMIN_CHAT_ID`.

## Commands (bot DM)

| Command | Meaning |
|---------|---------|
| `/start` | Register with default gates |
| `/settings` | Show current prefs |
| `/gmp 30` | Min GMP % |
| `/sub 2` | Min total subscription (x) |
| `/board main` or `/board all` | MAIN only vs MAIN+SME |
| `/status` | Same as settings |

Because the bot runs on Actions cron (not an always-on server), command replies
are processed when the next job runs (typically twice on weekdays).

## Local discovery (BSE field names)

BSE renames JSON keys between issues. Parsers in `bot/sources/bse.py` were written
against live fixtures under `fixtures/` (Sep 2026). Re-run if BSE breaks:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m bot.discover
```

## Modes

```bash
python -m bot.run --mode dry-run    # build message, send nothing
python -m bot.run --mode snapshot   # 17:15 IST — record only
python -m bot.run --mode alert      # 10:55 IST — channel + personalized DMs
```

Alert posts **one channel message** (all closing IPOs, unfiltered GMP feed) and
**one DM per registered user** (scored with their prefs). No post if nothing
closes that day.

## Tests

```bash
python -m pytest
```

## Privacy

`data/users.json` is committed on a **public** repo. It stores Telegram `chat_id`
and numeric prefs only — no names or phone numbers. Start the bot only if you
accept that.

## Notes on GMP sites

- **IPO Watch** — HTML tables (primary).
- **IPO Central** — list tables are often empty shells; scraper falls back to the
  live GMP ticker markup on `ipo-discussion`.
- **InvestorGain** — page is JS-rendered; may fail until they expose static HTML
  again. Alert mode still runs if **≥2** other sources succeed.
