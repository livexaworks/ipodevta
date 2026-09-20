# IPO Devta

A Telegram assistant for IPO fill decisions.

On days when issues close, IPO Devta sends a clear 👍 / 👎 view based on each
subscriber’s filters — grey-market premium (GMP), subscription, and board —
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
| **Channel** | Unfiltered closing-day feed — no account required |

No selling. No promotions. Just timely fill reminders.

---

## Using the bot

1. Open the bot and tap **Start**.
2. Use the bottom buttons: **Preview GMP**, **Settings**, **Help**, **Channel**.
3. In **Settings**, tap GMP / subscription / board values — no typing needed.
4. Optional: join the public channel if you prefer a shared feed over DMs.

Slash shortcuts (`/preview`, `/settings`, `/help`) still work; buttons are the
primary interface.

---

## Operator setup

1. Copy `.env.example` → `.env` (local only; never commit `.env`).
2. Create a bot with [@BotFather](https://t.me/BotFather).
3. Create a public channel; add the bot as admin with **Post Messages**.
4. Set repository secrets: `TELEGRAM_TOKEN`, `CHANNEL_ID`, `ADMIN_CHAT_ID`.

### Modes

```bash
python -m bot.run --mode commands   # reply to pending DMs / button taps
python -m bot.run --mode dry-run    # build alert text; still replies to DMs
python -m bot.run --mode snapshot   # evening book record
python -m bot.run --mode alert      # morning channel + personalized DMs
```

Scheduled jobs (weekdays, IST): morning alert, evening snapshot, and periodic
command/button processing.

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

`data/users.json` may be stored with the project. It holds Telegram `chat_id`
and numeric filter prefs only — no names or phone numbers.

## Data sources

- **BSE** — live issue book and category demand
- **IPO Watch** — primary GMP table
- **IPO Central** — GMP ticker fallback
- **Investorgain** — additional GMP source when available

Alert delivery continues when at least two GMP sources succeed.
