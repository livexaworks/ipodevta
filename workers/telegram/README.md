# Worker (instant replies)

Telegram webhook for Settings, Help, Channel, Feedback, and Preview ack.

Weekdays at 10:55 IST (`25 5 * * 1-5` UTC) the Worker cron fires GitHub
`repository_dispatch` event `alert`. GitHub Actions at 11:15 IST is a fallback
that skips the IPO Guru collect when `data/sent.json` already has today's brief.

Full steps: create KV `PREFS`, set secrets (`TELEGRAM_TOKEN`, `CHANNEL_ID`, `ADMIN_CHAT_ID`, `WEBHOOK_SECRET`, `EXPORT_SECRET`, `GITHUB_TOKEN`, `GITHUB_REPO`), `wrangler deploy`, then:

```bash
python -m bot.set_webhook set --url https://ipo-devta-bot.<you>.workers.dev
```

If IPODevta is already live for you, you do not need this.
