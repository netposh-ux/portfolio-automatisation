# 3. Merge CSV files into an Excel report

**The situation:** four branches send in their weekly sales as CSV files, each exported a little
differently. One uses commas, another uses semicolons and writes `4,50` instead of `4.50`.
Someone spends Monday morning stitching it all together and adding up the totals.

**What this does:** it reads every CSV in a folder, handles the format differences on its own,
reports any line it can't read, and builds one Excel workbook with the totals and charts.

## Run it

```bash
.venv/bin/python 03-csv-report/make_sample_data.py   # creates 4 sample files in data/
.venv/bin/python 03-csv-report/merge.py --output report.xlsx
```

```
sales_levis.csv: 35 rows
sales_montreal.csv: 35 rows
sales_quebec.csv: 35 rows
sales_sherbrooke.csv: 35 rows
Merged 140 rows, total sales $29,501.00 -> report.xlsx
```

## What you get

Three sheets:

**Detail**: every row from every file, sorted and filterable.

| date | region | product | quantity | unit_price | total |
|---|---|---|---|---|---|
| 2026-10-19 | Lévis | Coffee | 56 | $4.50 | $252.00 |
| 2026-10-19 | Lévis | Juice | 56 | $5.00 | $280.00 |
| 2026-10-19 | Lévis | Muffin | 60 | $3.25 | $195.00 |

**By region** and **By product**: totals with a bar chart. The TOTAL row is a real Excel
formula, so it stays right if someone edits a number by hand.

| Region | Quantity | Sales |
|---|---|---|
| Sherbrooke | 1,160 | $7,666.00 |
| Montreal | 1,171 | $7,541.75 |
| Lévis | 1,127 | $7,487.75 |
| Quebec City | 1,009 | $6,805.50 |
| **TOTAL** | **4,467** | **$29,501.00** |

## Details worth knowing

- **Separator detection** with `csv.Sniffer`, so `,` and `;` files can sit in the same folder.
- **Decimal commas** (`4,50`) are read correctly.
- **Bad lines are skipped and named** (file and line number) instead of crashing the whole run.

## Adapting it

Point `--folder` at a shared drive or a Dropbox folder and schedule it. The same approach works for
bank exports, timesheets, inventory counts or survey results.
