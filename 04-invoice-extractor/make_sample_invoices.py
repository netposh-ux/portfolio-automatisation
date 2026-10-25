"""Create a few fake PDF invoices to test the extractor.

Two suppliers use two different layouts (label wording, date format), like real invoices do.
One invoice has a deliberate math error so you can see the extractor flag it.
"""
from pathlib import Path

from fpdf import FPDF

FOLDER = Path(__file__).with_name("invoices")

INVOICES = [
    # supplier, layout, number, date, items [(description, qty, unit price)], total override
    ("Northwind Office Supply", "A", "NW-1042", "2026-09-03",
     [("Printer paper, case of 10", 4, 42.50), ("Black toner cartridge", 2, 89.99), ("Sticky notes, 24 pack", 3, 18.75)], None),
    ("Northwind Office Supply", "A", "NW-1057", "2026-09-17",
     [("Ergonomic office chair", 1, 349.00), ("Desk lamp, LED", 2, 54.95)], None),
    ("Riverside IT Services", "B", "2026-0318", "September 22, 2026",
     [("Laptop setup and data transfer", 3, 95.00), ("Network switch, 8 ports", 1, 129.99),
      ("Ethernet cable, 3 m", 6, 7.49), ("Monthly backup monitoring", 1, 60.00)], None),
    ("Riverside IT Services", "B", "2026-0331", "October 6, 2026",
     [("On-site support (hours)", 2, 95.00), ("Wireless mouse", 4, 24.99)], 450.00),  # wrong total on purpose
    ("Northwind Office Supply", "A", "NW-1083", "2026-10-14",
     [("Whiteboard markers, 12 pack", 2, 16.40), ("Filing cabinet, 3 drawers", 1, 219.00)], None),
]
TAX_RATE = 0.14975  # GST + QST in Quebec


def money(value):
    return f"${value:,.2f}"


def draw(supplier, layout, number, date, items, total_override):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, supplier, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, "123 Example Street, Quebec City, QC", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    pdf.set_font("Helvetica", size=11)
    if layout == "A":
        pdf.cell(0, 6, f"Invoice #: {number}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Date: {date}", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 6, f"Invoice No. {number}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Issued on {date}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Bill to: Cap-Rouge Bakery Inc.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    widths = (100, 20, 35, 35)
    pdf.set_font("Helvetica", "B", 10)
    for text, width in zip(("Description", "Qty", "Unit price", "Amount"), widths):
        pdf.cell(width, 8, text, border=1, align="L" if text == "Description" else "R")
    pdf.ln()
    pdf.set_font("Helvetica", size=10)
    subtotal = 0
    for description, qty, unit in items:
        amount = round(qty * unit, 2)
        subtotal += amount
        for text, width, align in ((description, widths[0], "L"), (str(qty), widths[1], "R"),
                                   (money(unit), widths[2], "R"), (money(amount), widths[3], "R")):
            pdf.cell(width, 7, text, border=1, align=align)
        pdf.ln()

    tax = round(subtotal * TAX_RATE, 2)
    total = total_override if total_override is not None else round(subtotal + tax, 2)
    pdf.ln(3)
    for label, value in (("Subtotal", subtotal), ("Taxes (GST + QST)", tax), ("Total", total)):
        pdf.set_font("Helvetica", "B" if label == "Total" else "", 11)
        pdf.cell(155, 7, label, align="R")
        pdf.cell(35, 7, money(value), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.output(FOLDER / f"invoice_{number}.pdf")


def main():
    FOLDER.mkdir(exist_ok=True)
    for invoice in INVOICES:
        draw(*invoice)
    print(f"Created {len(INVOICES)} invoices in {FOLDER}")


if __name__ == "__main__":
    main()
