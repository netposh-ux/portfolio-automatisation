"""Create data/inventory.db, a small SQLite database to back up next to Postgres.

Example: python make_sample_data.py
"""
import random
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "data" / "inventory.db"


def main():
    DB.parent.mkdir(exist_ok=True)
    (DB.parent.parent / "backups").mkdir(exist_ok=True)  # created by you, not by Docker (as root)
    DB.unlink(missing_ok=True)
    rng = random.Random(3)
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE items (sku TEXT PRIMARY KEY, name TEXT, qty INTEGER, price REAL)")
    con.executemany("INSERT INTO items VALUES (?, ?, ?, ?)",
                    [(f"SKU-{i:05d}", f"Item {i}", rng.randint(0, 400), round(rng.uniform(2, 90), 2))
                     for i in range(2000)])
    con.commit()
    con.close()
    print(f"Created {DB}")


if __name__ == "__main__":
    main()
