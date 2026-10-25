"""Watch prices and send an alert when a product drops below a threshold.

With no setup, alerts are printed to the console.
For Telegram, set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID (environment variables).

Examples:
    python bot.py --threshold 20                # check once
    python bot.py --threshold 20 --every 3600   # check every hour
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

# Reuse the scraper from demo 1 instead of copying it
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "01-price-scraper"))
from scraper import scrape  # noqa: E402

STATE_FILE = Path(__file__).with_name("state.json")


def send_alert(message):
    token, chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        print(f"[ALERT] {message}")
        return
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": message},
        timeout=15,
    )
    response.raise_for_status()


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def check(threshold, pages):
    """Alert once per product for as long as it stays below the threshold."""
    already_alerted = load_state()
    products = scrape(pages)
    new_alerts = 0
    for p in products:
        below = p["in_stock"] and p["price"] < threshold
        if below and p["url"] not in already_alerted:
            send_alert(f"Price drop: {p['title']} at £{p['price']:.2f} (threshold £{threshold:.2f})\n{p['url']}")
            already_alerted[p["url"]] = p["price"]
            new_alerts += 1
        elif not below:
            already_alerted.pop(p["url"], None)  # back above the threshold: can alert again later
    STATE_FILE.write_text(json.dumps(already_alerted, indent=2, ensure_ascii=False))
    print(f"Checked {len(products)} products, {new_alerts} new alert(s).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--threshold", type=float, required=True, help="alert when a price is below this")
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--every", type=int, metavar="SECONDS", help="repeat at this interval")
    args = parser.parse_args()

    while True:
        try:
            check(args.threshold, args.pages)
        except requests.RequestException as error:
            print(f"Network error, will retry next round: {error}")
        if not args.every:
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
