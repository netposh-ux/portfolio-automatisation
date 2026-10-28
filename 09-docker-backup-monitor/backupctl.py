"""Back up SQLite and PostgreSQL databases, check them with SHA-256, rotate old copies, report status.

Examples:
  python backupctl.py backup --sqlite data/shop.db --postgres postgresql://backup@db:5432/crm --dest backups
  python backupctl.py verify --dest backups
  python backupctl.py rotate --dest backups --keep-daily 7 --keep-weekly 4
  python backupctl.py status --dest backups --expect shop --expect crm --html status/index.html

The PostgreSQL password comes from PGPASSWORD or ~/.pgpass, never from the command line.
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

NAME = re.compile(r"^(?P<name>.+)-(?P<ts>\d{8}T\d{6}Z)\.(?P<ext>sqlite|dump)$")
STAMP = "%Y%m%dT%H%M%SZ"
LEVELS = ["OK", "WARNING", "CRITICAL"]


class BackupError(Exception):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def write_checksum(path):
    """Same format as sha256sum, so `sha256sum -c` works on the backup folder too."""
    path = Path(path)
    Path(f"{path}.sha256").write_text(f"{sha256(path)}  {path.name}\n")


def _target(dest, name, ext, now):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    final = dest / f"{name}-{(now or utcnow()).strftime(STAMP)}.{ext}"
    return final, final.with_name(final.name + ".part")


def _finish(part, final):
    os.chmod(part, 0o600)
    part.rename(final)
    write_checksum(final)
    return final


def backup_sqlite(source, dest, now=None):
    """Online backup through SQLite's backup API: consistent even while the app writes."""
    source = Path(source)
    final, part = _target(dest, source.stem, "sqlite", now)
    try:
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(part)
            with dst:
                src.backup(dst)
            dst.close()
        finally:
            src.close()
    except sqlite3.Error as e:
        part.unlink(missing_ok=True)
        raise BackupError(f"{source}: {e}") from e
    return _finish(part, final)


def backup_postgres(url, dest, now=None):
    name = urlparse(url).path.lstrip("/") or "postgres"
    final, part = _target(dest, name, "dump", now)
    r = subprocess.run(["pg_dump", "--format=custom", f"--file={part}", f"--dbname={url}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        part.unlink(missing_ok=True)
        raise BackupError(f"{name}: pg_dump failed: {r.stderr.strip()}")
    return _finish(part, final)


def backups(dest):
    for f in sorted(Path(dest).iterdir()):
        m = NAME.match(f.name)
        if m and f.is_file():
            when = datetime.strptime(m["ts"], STAMP).replace(tzinfo=timezone.utc)
            yield f, m["name"], when


def _check(f):
    side = Path(f"{f}.sha256")
    if not side.exists():
        return "NO_CHECKSUM", "no .sha256 file"
    if side.read_text().split()[0] != sha256(f):
        return "CORRUPT", "SHA-256 does not match"
    if f.suffix == ".sqlite":
        try:
            con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
            result = con.execute("PRAGMA integrity_check").fetchone()[0]
            con.close()
        except sqlite3.Error as e:
            return "CORRUPT", f"not a valid SQLite database: {e}"
        if result != "ok":
            return "CORRUPT", f"integrity_check: {result}"
    elif f.read_bytes()[:5] != b"PGDMP":
        return "CORRUPT", "not a pg_dump custom-format file"
    return "OK", ""


def verify(dest):
    results = []
    for f, name, when in backups(dest):
        state, detail = _check(f)
        results.append({"file": f.name, "name": name, "time": when.isoformat(), "size": f.stat().st_size,
                        "state": state, "detail": detail})
    return results


def rotate(dest, keep_daily=7, keep_weekly=4, now=None, dry_run=False):
    """Keep the newest backup of each of the last N days and of each of the last M ISO weeks."""
    by_name = {}
    for f, name, when in backups(dest):
        by_name.setdefault(name, []).append((when, f))
    deleted = []
    for items in by_name.values():
        items.sort(reverse=True)
        keep = set()
        for limit, period in ((keep_daily, lambda w: w.date()), (keep_weekly, lambda w: w.isocalendar()[:2])):
            seen = []
            for when, f in items:
                p = period(when)
                if p not in seen:
                    if len(seen) == limit:
                        break
                    seen.append(p)
                    keep.add(f)
        for _, f in items:
            if f not in keep:
                deleted.append(f)
                if not dry_run:
                    f.unlink()
                    Path(f"{f}.sha256").unlink(missing_ok=True)
    return deleted


def status(dest, max_age_hours=26, expected=(), min_free_percent=10, now=None):
    now = now or utcnow()
    checks = verify(dest)
    names = sorted({c["name"] for c in checks} | set(expected))
    databases = []
    for name in names:
        mine = [c for c in checks if c["name"] == name]
        if not mine:
            databases.append({"name": name, "level": "CRITICAL", "problem": "no backup", "backups": 0})
            continue
        last = max(mine, key=lambda c: c["time"])
        age = round((now - datetime.fromisoformat(last["time"])).total_seconds() / 3600, 1)
        level, problem = "OK", ""
        if last["state"] != "OK":
            level, problem = "CRITICAL", f"latest backup {last['state'].lower()}: {last['detail']}"
        elif age > max_age_hours:
            level, problem = "WARNING", f"last backup {age:g} h ago (limit {max_age_hours} h)"
        elif any(c["state"] != "OK" for c in mine):
            level, problem = "WARNING", "an older backup failed verification"
        databases.append({"name": name, "level": level, "problem": problem, "backups": len(mine),
                          "last_backup": last["time"], "age_hours": age, "last_size": last["size"]})
    usage = shutil.disk_usage(dest)
    free = round(100 * usage.free / usage.total, 1)
    disk_level = "WARNING" if free < min_free_percent else "OK"
    overall = max([d["level"] for d in databases] + [disk_level], key=LEVELS.index)
    return {"generated_at": now.isoformat(timespec="seconds"), "dest": str(dest), "status": overall,
            "disk_free_percent": free, "disk_level": disk_level, "databases": databases}


def status_html(s):
    colors = {"OK": "#0b7a3e", "WARNING": "#b54708", "CRITICAL": "#b42318"}
    e = lambda v: html.escape(str(v))  # noqa: E731
    rows = "\n".join(
        f"<tr><td>{e(d['name'])}</td><td><span class=b style='background:{colors[d['level']]}'>{e(d['level'])}</span></td>"
        f"<td>{e(d.get('last_backup', '-'))}</td><td>{e(d.get('age_hours', '-'))}</td><td>{e(d['backups'])}</td>"
        f"<td>{e(d['problem'])}</td></tr>" for d in s["databases"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="60">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Backup status</title><style>
body{{font-family:system-ui,sans-serif;margin:2rem auto;max-width:960px;padding:0 1rem;color:#1f2933;background:#f7f9fb}}
table{{border-collapse:collapse;width:100%;background:#fff}}td,th{{border:1px solid #d9e2ec;padding:.45rem .6rem;text-align:left}}
th{{background:#eef2f6}}.b{{color:#fff;border-radius:4px;padding:.1rem .5rem;font-size:.85rem}}
</style></head><body>
<h1>Backup status <span class=b style="background:{colors[s['status']]}">{e(s['status'])}</span></h1>
<p>Checked {e(s['generated_at'])} · disk free {e(s['disk_free_percent'])} % · refreshes every minute</p>
<table><tr><th>Database</th><th>Status</th><th>Last backup (UTC)</th><th>Age (h)</th><th>Copies</th><th>Problem</th></tr>
{rows}
</table></body></html>
"""


def _write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(f"{path}.tmp")
    tmp.write_text(text)
    tmp.replace(path)  # the status page never serves a half-written file


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--sqlite", action="append", default=[], metavar="FILE")
    b.add_argument("--postgres", action="append", default=[], metavar="URL")
    v = sub.add_parser("verify")
    r = sub.add_parser("rotate")
    r.add_argument("--keep-daily", type=int, default=7)
    r.add_argument("--keep-weekly", type=int, default=4)
    r.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("--max-age-hours", type=float, default=26)
    s.add_argument("--expect", action="append", default=[], metavar="NAME")
    s.add_argument("--json")
    s.add_argument("--html")
    for x in (b, v, r, s):
        x.add_argument("--dest", required=True)
    a = p.parse_args(argv)

    if a.cmd == "backup":
        failed = 0
        jobs = [(backup_sqlite, x) for x in a.sqlite] + [(backup_postgres, x) for x in a.postgres]
        for fn, src in jobs:
            try:
                out = fn(src, a.dest)
                print(f"OK      {out.name} ({out.stat().st_size} bytes)")
            except BackupError as e:
                failed += 1
                print(f"FAILED  {e}", file=sys.stderr)
        return 1 if failed else 0
    if a.cmd == "verify":
        results = verify(a.dest)
        for c in results:
            print(f"{c['state']:<12} {c['file']}  {c['detail']}")
        return 0 if all(c["state"] == "OK" for c in results) else 1
    if a.cmd == "rotate":
        for f in rotate(a.dest, a.keep_daily, a.keep_weekly, dry_run=a.dry_run):
            print(f"{'would delete' if a.dry_run else 'deleted'}  {f.name}")
        return 0
    st = status(a.dest, a.max_age_hours, a.expect)
    if a.json:
        _write(a.json, json.dumps(st, indent=2))
    if a.html:
        _write(a.html, status_html(st))
    print(f"{st['status']}: " + ", ".join(f"{d['name']} {d['level']}" for d in st["databases"]))
    return LEVELS.index(st["status"])


if __name__ == "__main__":
    sys.exit(main())
