# 1. Price scraper to Excel

**The situation:** a shop owner checks competitors' websites every week and copies prices into a
spreadsheet by hand. It takes an hour, and it's easy to miss a product.

**What this does:** it walks through an online catalog page by page and writes an Excel file with
each product's title, price, availability, rating and link, sorted from cheapest to most expensive.

## Run it

```bash
.venv/bin/python 01-price-scraper/scraper.py --pages 2 --output prices.xlsx
```

```
Page 1: 20 products
Page 2: 20 products
Saved 40 products to prices.xlsx (average price: £34.96)
```

## What you get

An Excel file with a frozen header row and filters on every column:

| Title | Price (£) | In stock | Rating /5 | Link |
|---|---|---|---|---|
| In Her Wake | 12.84 | Yes | 1 | https://books.toscrape.com/catalogue/in-her-wake_980/... |
| Starving Hearts (Triangular Trade Trilogy, #1) | 13.99 | Yes | 2 | https://books.toscrape.com/catalogue/starving-hearts-... |
| Sophie's World | 15.94 | Yes | 5 | https://books.toscrape.com/catalogue/sophies-world_966/... |

## Details worth knowing

- **It's polite to the site:** one page per second at most, and a clear User-Agent.
- **It follows pagination** on its own until it reaches `--pages` or the last page.
- **It stops on errors** (`raise_for_status`) instead of saving half a file without telling you.

## Adapting it

For another site, change `START_URL` and the CSS selectors in `read_page()`. Common additions:
several competitor sites in one file, a column showing the price change since last week, or a daily
run with cron. Before taking on this kind of job, I check that the site's terms of use allow it.
