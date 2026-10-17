# Worker (webhook, Check now, daily triggers)

The Cloudflare Worker does three things on the free plan:

- **Telegram webhook:** Start, 🔎 Check now, ⚙️ Settings / `/filter`, 📢 Channel, Help and Feedback reply instantly. User filters live in KV (`prefs:<chat_id>`).
- **Check now:** filters the latest cards that GitHub Actions stored with `POST /market` and sends one card per passing IPO, or the 🚫 no-match message.
- **Crons (weekdays):** `30 4 * * 1-5` (10:00 IST) dispatches the `channel` run and `30 5 * * 1-5` (11:00 IST) dispatches the `bot` run to GitHub Actions. If a dispatch fails, the admin gets a Telegram message.

## Deploy

```bash
cd workers/telegram
python sync_copy.py            # after editing shared/copy.json
npx wrangler secret put TELEGRAM_TOKEN
npx wrangler secret put CHANNEL_ID          # @ipogmpalerts
npx wrangler secret put ADMIN_CHAT_ID
npx wrangler secret put WEBHOOK_SECRET
npx wrangler secret put EXPORT_SECRET       # same value as the GitHub secret
npx wrangler secret put GITHUB_TOKEN        # fine-grained PAT, this repo, Contents: read & write
npx wrangler secret put GITHUB_REPO         # livexaworks/ipodevta
npx wrangler secret put TELEGRAM_TOKEN
npx wrangler deploy
```

Production Worker URL: `https://ipogmpalerts.livexaworks.workers.dev`

Then, from the repo root:

```bash
python -m bot.set_webhook set --url https://ipogmpalerts.livexaworks.workers.dev
python scripts/setup_bot_profile.py   # or: python -m bot.set_webhook profile
python scripts/check_prod.py          # smoke: profile, webhook, /health, /help
```

Check that the crons are live with `npx wrangler deployments list` or in the Cloudflare dashboard under Triggers.
