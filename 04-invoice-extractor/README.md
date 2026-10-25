# 4. PDF invoice extractor

**The situation:** a small business receives supplier invoices as PDFs. Each month, someone retypes
the invoice number, date, amounts and every line item into Excel for the bookkeeper. It's slow, and
a typo in a total can go unnoticed.

**What this does:** it reads every PDF invoice in a folder and builds one Excel workbook: a summary
with one row per invoice, and a second sheet with every line item. It also checks the math on each
invoice and highlights the ones that don't add up.

## Run it

```bash
.venv/bin/python 04-invoice-extractor/make_sample_invoices.py   # creates 5 fake invoices
.venv/bin/python 04-invoice-extractor/extract.py --output invoices.xlsx
```

```
2026-0318  2026-09-22  Riverside IT Services      $   597.79  OK
2026-0331  2026-10-06  Riverside IT Services      $   450.00  Lines + taxes = $333.38
NW-1042    2026-09-03  Northwind Office Supply    $   467.06  OK
NW-1057    2026-09-17  Northwind Office Supply    $   527.62  OK
NW-1083    2026-10-14  Northwind Office Supply    $   289.51  OK

5 invoices, 13 line items, 1 to double-check -> invoices.xlsx
```

Invoice 2026-0331 has a wrong total on purpose: the extractor catches it.

## What you get

**Invoices** sheet, sorted by date. Rows that fail the check are highlighted in orange:

| Number | Date | Supplier | Subtotal | Taxes | Total | Check |
|---|---|---|---|---|---|---|
| NW-1042 | 2026-09-03 | Northwind Office Supply | $406.23 | $60.83 | $467.06 | OK |
| NW-1057 | 2026-09-17 | Northwind Office Supply | $458.90 | $68.72 | $527.62 | OK |
| 2026-0318 | 2026-09-22 | Riverside IT Services | $519.93 | $77.86 | $597.79 | OK |
| 2026-0331 | 2026-10-06 | Riverside IT Services | $289.96 | $43.42 | $450.00 | Lines + taxes = $333.38 |

**Line items** sheet:

| Invoice | Supplier | Description | Qty | Unit price | Amount |
|---|---|---|---|---|---|
| 2026-0318 | Riverside IT Services | Laptop setup and data transfer | 3 | $95.00 | $285.00 |
| 2026-0318 | Riverside IT Services | Network switch, 8 ports | 1 | $129.99 | $129.99 |
| 2026-0318 | Riverside IT Services | Ethernet cable, 3 m | 6 | $7.49 | $44.94 |

## Details worth knowing

- **Two layouts handled:** the two suppliers word things differently ("Invoice #:" vs "Invoice No.")
  and write dates differently ("2026-09-03" vs "September 22, 2026"). Adding a supplier usually
  means adding one pattern to the lists at the top of `extract.py`.
- **Text PDFs only:** this works on PDFs that contain real text, which is most invoices sent by
  email. Scanned paper invoices need an OCR step first (Tesseract), which can be added.

## Adapting it

Same idea for purchase orders, bank statements, packing slips or pay stubs. The output can also go
straight into Google Sheets or an accounting tool's import format instead of Excel.
