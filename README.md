# IPODevta

IPO GMP and subscription on Telegram, one clean message per IPO.

- **Channel [@ipodevta](https://t.me/ipodevta), 9:30 AM IST.** Every open IPO, no filters. For people who don't want to set anything up.
- **Bot, 2:30 PM IST.** Only the IPOs that pass *your* filters (board, GMP %, subscription). Each card has two buttons: 📢 Today's IPOs (opens today's channel post) and ⚙️ Filters. If nothing passes, you get a single 🚫 message telling you to stay out that day.

Both use the same card:

```
Vishal Nirmiti
Mainboard · 🔴 Closes today
📅 Open 6 Oct → Close 8 Oct
💰 Price ₹220
📈 GMP ₹80 (+36.4%)
📊 Subscription 2.4x (live 2:30 PM)
```

Runs only on NSE trading days (`data/holidays.json`; add each year's dates when NSE publishes them in December, and the admin summary warns if the current year is missing). Information only, not investment advice. GMP is unofficial grey-market data.

---

## How it runs (all free tier)

```
Cloudflare Worker cron 9:30 IST  --repository_dispatch channel-->  GitHub Actions: python -m bot.run channel
Cloudflare Worker cron 14:30 IST --repository_dispatch bot------>  GitHub Actions: python -m bot.run bot
GitHub Actions --POST /market--> Worker KV  (powers the instant "Check now" button)
Telegram --webhook--> Worker (Start, Check now, Settings, Channel, Help, Feedback)
```

| Piece | Free limit | Usage |
|-------|------------|-------|
| [IPO Guru API](https://www.ipoguru.in/ipo-gmp-details-developer-api): calendar, price, GMP | 10 requests/day | 2/day |
| BSE public bookbuilding JSON: QIB/NII/Retail/Total subscription | none | 2 runs/day |
| GitHub Actions | unlimited on public repos | 2 to 4 short runs/day |
| Cloudflare Workers + KV | 100k requests, 1k KV writes/day | tiny |

GitHub's own cron is only a late fallback (09:50 / 14:50 IST). Every run is idempotent: the sent log in `data/sent.json` records each message, so a rerun only sends what is missing. Runs after 13:00 (channel) or 16:30 (bot) are skipped and the admin is told, so nobody gets stale posts.

`data/sent.json` never stores Telegram chat ids. Users are keyed by an HMAC of the chat id using the `EXPORT_SECRET` secret, because this repo is public. User filters live only in Cloudflare KV.

## Layout

```
bot/
  run.py          channel / bot runs, dry-run, admin report
  collect.py      IPO Guru + BSE merge, open-today filter, ordering
  filters.py      board / GMP % / subscription pass-fail (mirrors worker.js)
  cards.py        the one IPO card, channel header, no-match message, DM buttons
  telegram.py     paced sends (3.2 s per channel post), 429 retries, admin alerts
  state.py        per-message sent log (14-day retention)
  worker_api.py   read users from / push market cards to the Worker
  set_webhook.py  one-time webhook + bot profile setup
  sources/        ipoguru.py, bse.py
shared/copy.json  every user-facing string (Python and Worker)
workers/telegram/ Cloudflare Worker (webhook, Check now, crons)
```

## Run your own

1. Copy `.env.example` to `.env` and fill it in.
2. Add the same values as GitHub Actions secrets: `TELEGRAM_TOKEN`, `CHANNEL_ID`, `ADMIN_CHAT_ID`, `WEBHOOK_BASE_URL`, `EXPORT_SECRET`, `IPOGURU_API_KEY`.
3. Deploy the Worker: see [workers/telegram/README.md](workers/telegram/README.md).
4. `pip install -r requirements-dev.txt && python -m pytest` (CI runs the same on every push)

```bash
python -m bot.run channel --dry-run --force --fixture tests/fixtures/market.json   # offline preview
python -m bot.run bot --dry-run --only-chat YOUR_CHAT_ID                         # live data, prints only
python -m bot.run channel                                                         # real post
```

Edit copy in `shared/copy.json`, then run `python workers/telegram/sync_copy.py` before deploying the Worker.

## Purging old chat ids from git history

Before October 2026 the repo committed `data/users.json` and raw chat ids in `data/sent.json`. They are gone from the working tree, but still in history. To remove them, rewrite history with [git-filter-repo](https://github.com/newren/git-filter-repo) (`git filter-repo --path data/users.json --path data/sent.json --invert-paths`) and force-push. This rewrites every commit, so coordinate with anyone who has a clone.
