# IPO Devta

A Telegram assistant for IPO fill decisions.

On days when issues close, IPO Devta sends a clear 👍 / 👎 view based on each
subscriber's filters - grey-market premium (GMP), subscription, and board -
so you know what to consider filing. A public channel carries the same-day
closing list without personal filters.

This is **information only**, not investment advice. GMP is unofficial and can
move quickly. Always read the RHP.

---

## What you get

| Surface | Purpose |
|---------|---------|
| **Bot DM** | Personalized closing-day reminders using *your* filters |
| **Preview GMP** | Last five processed issues (or live open issues), scored now |
| **Settings** | Tap buttons to set min GMP %, min subscription, and board |
| **Channel** | Unfiltered closing-day feed - no account required |

No selling. No promotions. Just timely fill reminders.

---

## Using the bot

1. Open the bot and tap **Start**.
2. Use the bottom buttons: **Preview GMP**, **Settings**, **Help**, **Channel**.
3. In **Settings**, tap GMP / subscription / board values - no typing needed.
4. Optional: join the public channel if you prefer a shared feed over DMs.

**Settings, Help, and Channel reply immediately** via a small Cloudflare Worker
webhook (see `workers/telegram/`). Closing-day IPO alerts stay on the weekday
schedule. Preview GMP acknowledges instantly, then delivers scores within about
a minute. Until the Worker is deployed, a 5-minute Actions poll is the fallback.

---

## Operator setup

1. Copy `.env.example` → `.env` (local only; never commit `.env`).
2. Create a bot with [@BotFather](https://t.me/BotFather).
3. Create a public channel; add the bot as admin with **Post Messages**.
4. Set repository secrets: `TELEGRAM_TOKEN`, `CHANNEL_ID`, `ADMIN_CHAT_ID`.
5. Deploy the instant-reply Worker (required for snappy Settings/Help):
   see [`workers/telegram/README.md`](workers/telegram/README.md).

### Modes

```bash
python -m bot.run --mode preview --chat-id 123   # scored GMP preview DM
python -m bot.run --mode dry-run                 # build alert text
python -m bot.run --mode snapshot                # evening book record
python -m bot.run --mode alert                   # morning channel + DMs
python -m bot.set_webhook set --url https://...  # point Telegram at Worker
```

Scheduled jobs (IST): weekday morning alert, weekday evening snapshot.
Button replies are handled by the Worker, not by a polling cron.

### Local discovery (BSE field names)

BSE occasionally renames JSON keys. Re-run against live fixtures if parsers break:

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m bot.discover
```

### Tests

```bash
python -m pytest
```

---

## Privacy

User filter prefs live in the Worker store (and may be mirrored to
`data/users.json`). Only Telegram `chat_id` and numeric prefs - no names or
phone numbers.

## Data sources

- **BSE** - live issue book and category demand
- **IPO Watch** - primary GMP table
- **IPO Central** - GMP ticker fallback
- **Investorgain** - additional GMP source when available

Alert delivery continues when at least two GMP sources succeed.
