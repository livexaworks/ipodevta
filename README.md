# IPODevta

Clear IPO fill signals on Telegram: 👍 / 👎 with GMP and subscription, using filters you set.

**Already live on Telegram.** Use the existing bot and channel. Do not waste time cloning this just to file IPOs.

Channel: [t.me/ipodevta](https://t.me/ipodevta)

Happy filing. All the best for allotments.

---

## Fork

Have another idea? Fork this repo and build your own. Message copy lives mainly in `bot/render.py` and `workers/telegram/worker.js`.

## Run your own

1. Copy `.env.example` → `.env`
2. Add Telegram secrets on GitHub Actions
3. Deploy the Worker: `workers/telegram/README.md`
4. `python -m pytest`

```bash
python -m bot.run --mode alert      # closing-day posts
python -m bot.run --mode snapshot   # evening book
python -m bot.run --mode preview --chat-id YOUR_ID
```

Information only. Not investment advice. Read the RHP.
