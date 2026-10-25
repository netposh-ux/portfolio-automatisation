# 2. Price drop alerts

**The situation:** someone wants to buy a product (or restock inventory) when the price drops below
a certain amount, but doesn't want to refresh the page ten times a day.

**What this does:** it checks the prices and sends a Telegram message when a product goes under
your threshold. It reuses the scraper from demo 1.

## Run it

With no setup, alerts are printed in the terminal:

```bash
.venv/bin/python 02-price-alerts/bot.py --threshold 15
```

```
Page 1: 20 products
[ALERT] Price drop: Starving Hearts (Triangular Trade Trilogy, #1) at £13.99 (threshold £15.00)
https://books.toscrape.com/catalogue/starving-hearts-triangular-trade-trilogy-1_990/index.html
Checked 20 products, 1 new alert(s).
```

Run it a second time and nothing is sent, because that product was already reported:

```
Page 1: 20 products
Checked 20 products, 0 new alert(s).
```

## Getting the alerts on your phone

1. In Telegram, talk to `@BotFather` and create a bot. It gives you a token.
2. Send any message to your new bot, then get your chat ID from
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.
3. Run it with both values, here checking every hour:

```bash
export TELEGRAM_TOKEN=...
export TELEGRAM_CHAT_ID=...
.venv/bin/python 02-price-alerts/bot.py --threshold 20 --every 3600
```

## Details worth knowing

- **No duplicate messages:** what was already reported is saved in `state.json`. If the price goes
  back up and drops again later, you get a new alert.
- **A network hiccup doesn't kill it:** in loop mode, a failed check is logged and retried next round.

## Adapting it

The same pattern works for a restock ("In stock" appears), a new listing on a classifieds site, or
any change on a page. The message can go to Discord, Slack or email instead of Telegram.
