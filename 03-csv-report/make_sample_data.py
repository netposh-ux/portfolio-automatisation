"""Create fake, deliberately messy sales CSV files for the merge demo.

Every branch exports its own way: comma or semicolon separators, and some use a decimal
comma (4,50 instead of 4.50), just like in real life.
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

FOLDER = Path(__file__).with_name("data")
BRANCHES = {
    "quebec": ("Quebec City", ","),
    "levis": ("Lévis", ";"),
    "montreal": ("Montreal", ","),
    "sherbrooke": ("Sherbrooke", ";"),
}
PRODUCTS = {"Coffee": 4.50, "Muffin": 3.25, "Sandwich": 9.75, "Salad": 11.00, "Juice": 5.00}


def main():
    random.seed(42)
    FOLDER.mkdir(exist_ok=True)
    monday = date(2026, 10, 19)
    for code, (city, separator) in BRANCHES.items():
        with open(FOLDER / f"sales_{code}.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=separator)
            writer.writerow(["date", "region", "product", "quantity", "unit_price"])
            for day in range(7):
                for product, price in PRODUCTS.items():
                    price_text = f"{price:.2f}".replace(".", ",") if separator == ";" else f"{price:.2f}"
                    writer.writerow([monday + timedelta(days=day), city, product, random.randint(5, 60), price_text])
    print(f"Created {len(BRANCHES)} files in {FOLDER}")


if __name__ == "__main__":
    main()
