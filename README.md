# Python automation examples

I'm Jean-François, a Python developer based in Quebec City. I write scripts that take over the
repetitive parts of people's work: copying data from websites, merging spreadsheets, reading
invoices, watching prices, building small dashboards.

This repo holds six small, working examples of that kind of job. Each one solves a problem I keep
seeing in freelance job posts, and each one runs in a few seconds on sample data so you can try it
yourself.

| # | Demo | The problem it solves | Main tools |
|---|---|---|---|
| 1 | [Price scraper](01-price-scraper/) | "I copy my competitors' prices into a spreadsheet every week." | requests, BeautifulSoup, openpyxl |
| 2 | [Price drop alerts](02-price-alerts/) | "Tell me on my phone when a product gets cheaper." | Telegram Bot API |
| 3 | [CSV merge and report](03-csv-report/) | "Every Monday I merge sales files from four branches by hand." | csv, openpyxl charts |
| 4 | [Invoice extractor](04-invoice-extractor/) | "I retype supplier invoices from PDFs into Excel." | pdfplumber, openpyxl |
| 5 | [Exchange rates from an API](05-exchange-rates/) | "I need daily exchange rates in a spreadsheet, without doing it myself." | REST API, SQLite, matplotlib |
| 6 | [Sales dashboard](06-sales-dashboard/) | "I want to see my numbers in a browser, not in ten Excel files." | Flask, Chart.js |

## A quick look

The sales dashboard (demo 6), built on the same messy CSV files as demo 3:

![Sales dashboard](docs/sales-dashboard.png)

Exchange rates pulled from the European Central Bank's data (demo 5):

![Exchange rate chart](docs/exchange-rates.png)

## Try them

You need Python 3.10 or newer.

```bash
git clone https://github.com/netposh-ux/portfolio-automatisation.git
cd portfolio-automatisation
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Then run any demo. Each folder has its own README with what it does and what the output looks like.

```bash
.venv/bin/python 01-price-scraper/scraper.py --pages 2
.venv/bin/python 02-price-alerts/bot.py --threshold 20
.venv/bin/python 03-csv-report/make_sample_data.py && .venv/bin/python 03-csv-report/merge.py
.venv/bin/python 04-invoice-extractor/make_sample_invoices.py && .venv/bin/python 04-invoice-extractor/extract.py
.venv/bin/python 05-exchange-rates/rates.py
.venv/bin/python 06-sales-dashboard/app.py    # then open http://127.0.0.1:5050
```

The scraping demos use [books.toscrape.com](https://books.toscrape.com), a site made for
practicing web scraping. All the other data (sales, invoices) is generated and fake.

## How I work

- I start by asking what you do today, step by step, and what the result should look like.
- You get a script you can read: plain Python, comments where it matters, and a short README.
- I test it on your real files or pages before calling it done, and I fix it if a site changes.
- I don't take scraping jobs that break a site's terms of use, or anything involving fake accounts or spam.

## Other things I've built

- A trading bot connected to Coinbase and Kraken, with its own web dashboard.
- A home dashboard for security cameras and sensors.
- A website for a non-profit.

Interested in something similar? Reach me through my GitHub profile: [@netposh-ux](https://github.com/netposh-ux).
