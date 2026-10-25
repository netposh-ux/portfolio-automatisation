"""A small web dashboard for the sales data from demo 3.

Reads the CSV files directly (same messy formats as demo 3), so when a branch drops a new
file in the folder, the dashboard picks it up on the next page load.

Example: python app.py   then open http://127.0.0.1:5050
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request

HERE = Path(__file__).resolve().parent
# Reuse the CSV reader from demo 3 instead of copying it
sys.path.insert(0, str(HERE.parent / "03-csv-report"))
from merge import read_csv  # noqa: E402

app = Flask(__name__)
app.config["DATA_FOLDER"] = HERE.parent / "03-csv-report" / "data"


def load_rows():
    rows = []
    for path in sorted(Path(app.config["DATA_FOLDER"]).glob("*.csv")):
        rows.extend(read_csv(path))
    return rows


def summarize(rows):
    by_region, by_product, by_day = defaultdict(float), defaultdict(float), defaultdict(float)
    for r in rows:
        by_region[r["region"]] += r["total"]
        by_product[r["product"]] += r["total"]
        by_day[r["date"]] += r["total"]

    def ranked(d):
        return [{"name": k, "sales": round(v, 2)} for k, v in sorted(d.items(), key=lambda kv: -kv[1])]

    return {
        "total_sales": round(sum(r["total"] for r in rows), 2),
        "units": sum(r["quantity"] for r in rows),
        "orders": len(rows),
        "by_region": ranked(by_region),
        "by_product": ranked(by_product),
        "by_day": [{"day": k, "sales": round(v, 2)} for k, v in sorted(by_day.items())],
    }


@app.route("/")
def index():
    rows = load_rows()
    return render_template("index.html", regions=sorted({r["region"] for r in rows}))


@app.route("/api/summary")
def api_summary():
    rows = load_rows()
    region = request.args.get("region")
    if region:
        rows = [r for r in rows if r["region"] == region]
    return jsonify(summarize(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()
    if not any(Path(app.config["DATA_FOLDER"]).glob("*.csv")):
        raise SystemExit("No sales data yet: run 03-csv-report/make_sample_data.py first")
    app.run(host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
