# IPO GMP Alerts

IPO GMP and subscription on Telegram, one clean message per IPO.

- **Channel [@ipogmpalerts](https://t.me/ipogmpalerts), 10:00 AM IST.** Every open IPO, no filters. For people who don't want to set anything up.
- **Bot [@ipogmpalertsbot](https://t.me/ipogmpalertsbot), 11:00 AM IST.** Only the IPOs that pass *your* filters (board, GMP %). Each card has two buttons: 📢 Today's IPOs (opens today's channel post) and ⚙️ Filters. If IPOs are open but none pass, you get a single 🚫 message telling you to stay out that day. If no IPOs are open at all, nobody gets anything: no channel post and no DM.

Both use the same SEO card (company name first, hashtags, plain searchable text).

Runs only on NSE trading days (`data/holidays.json`; add each year's dates when NSE publishes them in December, and the admin summary warns if the current year is missing). Information only, not investment advice. GMP is unofficial grey-market data.

---

## How it runs (all free tier)

```
Cloudflare Worker cron 10:00 IST --repository_dispatch channel-->  GitHub Actions: python -m bot.run channel
Cloudflare Worker cron 11:00 IST --repository_dispatch bot------>  GitHub Actions: python -m bot.run bot
GitHub Actions --POST /market--> Worker KV  (powers the instant "Check now" button)
Telegram --webhook--> Worker (Start, Check now, Settings/filter, Channel, Help, Feedback)
```

| Piece | Free limit | Usage |
|-------|------------|-------|
| [IPO Guru API](https://www.ipoguru.in/ipo-gmp-details-developer-api): calendar, price, GMP | 10 requests/day | 2/day |
| BSE public bookbuilding JSON: QIB/NII/Retail/Total subscription | none | 2 runs/day |
| GitHub Actions | unlimited on public repos | 2 to 4 short runs/day |
| Cloudflare Workers + KV | 100k requests, 1k KV writes/day | tiny |

GitHub's own cron is only a late fallback (10:20 / 11:20 IST). Every run is idempotent: the sent log in `data/sent.json` records each message, so a rerun only sends what is missing. Runs after 13:00 (channel) or 14:00 (bot) are skipped and the admin is told, so nobody gets stale posts.

`data/sent.json` never stores Telegram chat ids. Users are keyed by an HMAC of the chat id using the `EXPORT_SECRET` secret, because this repo is public. User filters live only in Cloudflare KV.

## Layout

```
bot/
  run.py          channel / bot runs, dry-run, admin report
  collect.py      IPO Guru + BSE merge, open-today filter, ordering
  filters.py      board / GMP % pass-fail (mirrors worker.js)
  cards.py        the one IPO card, channel header, no-match message, DM buttons
  hashtags.py     company + board SEO hashtags
  telegram.py     paced sends, 429 retries, admin alerts
  state.py        per-message sent log (14-day retention)
  worker_api.py   read users from / push market cards to the Worker
  set_webhook.py  one-time webhook + bot profile setup
  profile.py      setMy* / getMy* profile helpers
  sources/        ipoguru.py, bse.py
scripts/
  setup_bot_profile.py   apply + verify bot name/descriptions/commands
shared/copy.json  every user-facing string (Python and Worker)
workers/telegram/ Cloudflare Worker (webhook, Check now, crons)
```

## Run your own

1. Copy `.env.example` to `.env` and fill it in (`CHANNEL_ID=@ipogmpalerts`, etc.).
2. Add the same values as GitHub Actions secrets: `TELEGRAM_TOKEN`, `CHANNEL_ID`, `ADMIN_CHAT_ID`, `WEBHOOK_BASE_URL`, `EXPORT_SECRET`, `IPOGURU_API_KEY`.
3. Deploy the Worker: see [workers/telegram/README.md](workers/telegram/README.md). Also set `CHANNEL_ID` on the Worker with wrangler (separate from GitHub secrets).
4. `pip install -r requirements-dev.txt && python -m pytest` (CI runs the same on every push)
5. Optional: `python scripts/setup_bot_profile.py` to push Bot API name/descriptions/commands from `shared/copy.json`.

```bash
python -m bot.run channel --dry-run --force --fixture tests/fixtures/market.json   # offline preview
python -m bot.run bot --dry-run --only-chat YOUR_CHAT_ID                         # live data, prints only
python -m bot.run channel                                                         # real post
```

Edit copy in `shared/copy.json`, then run `python workers/telegram/sync_copy.py` before deploying the Worker.

## Production checks

```bash
python scripts/check_prod.py          # env, profile, webhook, Worker /health, /help smoke
python scripts/setup_bot_profile.py   # re-apply Bot API name/descriptions/commands
```

Live Worker: https://ipogmpalerts.livexaworks.workers.dev · Channel: [@ipogmpalerts](https://t.me/ipogmpalerts) · Bot: [@ipogmpalertsbot](https://t.me/ipogmpalertsbot)
