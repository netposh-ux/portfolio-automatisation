"""Command line interface."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report, scanner


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dupfinder",
        description="Find duplicate files (size, then SHA-256). Nothing is deleted without --apply.")
    p.add_argument("folder", help="folder to scan (recursive)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only, delete nothing (default)")
    mode.add_argument("--apply", action="store_true", help="delete duplicates, keep one file per group")
    p.add_argument("--keep", choices=scanner.KEEP_RULES, default="oldest",
                   help="file to keep: oldest (default), newest, or shortest path")
    p.add_argument("--min-size", type=int, default=1, metavar="BYTES",
                   help="smallest file size to consider (default 1: skip empty files)")
    p.add_argument("--json", metavar="FILE", help="write the JSON report")
    p.add_argument("--html", metavar="FILE", help="write the HTML report")
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    if not Path(a.folder).is_dir():
        print(f"dupfinder: folder not found: {a.folder}", file=sys.stderr)
        return 2

    result = scanner.scan(a.folder, min_size=a.min_size)
    # Decide what to keep before deleting anything: deleted files no longer have a date.
    keep = {g.sha256: scanner.file_to_keep(g, a.keep) for g in result.groups}
    deleted = scanner.clean(result, keep) if a.apply else []
    data = report.build(result, "apply" if a.apply else "dry-run", a.keep, keep, deleted)

    if a.json:
        report.write_json(data, a.json)
    if a.html:
        report.write_html(data, a.html)

    s = data["summary"]
    print(f"{s['files_scanned']} files scanned, {s['groups']} groups, {s['duplicates']} duplicates, "
          f"{report.human_size(s['reclaimable_bytes'])} reclaimable, {len(data['errors'])} errors.")
    if a.apply:
        print(f"Apply mode: {len(deleted)} files deleted.")
    else:
        print("Dry-run mode: nothing deleted (add --apply to clean up).")
    return 0
