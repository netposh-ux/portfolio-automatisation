"""Tests for backupctl: backups, SHA-256 checks, rotation and status."""
import json
import os
import sqlite3
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backupctl  # noqa: E402

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "shop.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, total REAL)")
    con.executemany("INSERT INTO orders (total) VALUES (?)", [(i * 1.5,) for i in range(100)])
    con.commit()
    con.close()
    return path


@pytest.fixture
def dest(tmp_path):
    d = tmp_path / "backups"
    d.mkdir()
    return d


def fake_backup(dest, name, when, content=b"data"):
    """A backup file with its checksum, as backupctl writes them."""
    f = dest / f"{name}-{when:%Y%m%dT%H%M%SZ}.sqlite"
    f.write_bytes(content)
    backupctl.write_checksum(f)
    return f


# --- backup ---

def test_sqlite_backup_is_a_consistent_copy(db, dest):
    out = backupctl.backup_sqlite(db, dest, now=NOW)
    assert out.name == "shop-20261027T120000Z.sqlite"
    con = sqlite3.connect(out)
    assert con.execute("SELECT COUNT(*), SUM(total) FROM orders").fetchone() == (100, sum(i * 1.5 for i in range(100)))


def test_backup_writes_a_sha256_sidecar(db, dest):
    out = backupctl.backup_sqlite(db, dest, now=NOW)
    line = Path(f"{out}.sha256").read_text()
    assert line == f"{backupctl.sha256(out)}  {out.name}\n"  # same format as sha256sum


def test_backup_files_are_private(db, dest):
    out = backupctl.backup_sqlite(db, dest, now=NOW)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_postgres_backup_uses_pg_dump(dest, tmp_path, monkeypatch):
    fake = tmp_path / "bin" / "pg_dump"
    fake.parent.mkdir()
    fake.write_text('#!/bin/sh\necho "args: $@" > "$PGDUMP_ARGS_LOG"\nprintf "PGDMP-fake" > "$(echo "$@" | sed -n "s/.*--file=\\([^ ]*\\).*/\\1/p")"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake.parent}:{os.environ['PATH']}")
    monkeypatch.setenv("PGDUMP_ARGS_LOG", str(tmp_path / "args.log"))
    out = backupctl.backup_postgres("postgresql://backup@db:5432/shop", dest, now=NOW)
    assert out.name == "shop-20261027T120000Z.dump"
    assert out.read_bytes() == b"PGDMP-fake"
    args = (tmp_path / "args.log").read_text()
    assert "--format=custom" in args and "postgresql://backup@db:5432/shop" in args
    assert Path(f"{out}.sha256").exists()


def test_failed_pg_dump_leaves_no_partial_file(dest, tmp_path, monkeypatch):
    fake = tmp_path / "bin" / "pg_dump"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\necho 'connection refused' >&2\nexit 1\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake.parent}:{os.environ['PATH']}")
    with pytest.raises(backupctl.BackupError, match="connection refused"):
        backupctl.backup_postgres("postgresql://backup@db/shop", dest, now=NOW)
    assert list(dest.iterdir()) == []


# --- verify ---

def test_verify_ok(db, dest):
    backupctl.backup_sqlite(db, dest, now=NOW)
    results = backupctl.verify(dest)
    assert [r["state"] for r in results] == ["OK"]


def test_verify_detects_a_corrupted_backup(db, dest):
    out = backupctl.backup_sqlite(db, dest, now=NOW)
    data = bytearray(out.read_bytes())
    data[200] ^= 0xFF
    out.write_bytes(bytes(data))
    assert backupctl.verify(dest)[0]["state"] == "CORRUPT"


def test_verify_flags_a_missing_checksum(dest):
    (dest / "shop-20261027T120000Z.sqlite").write_bytes(b"x")
    assert backupctl.verify(dest)[0]["state"] == "NO_CHECKSUM"


def test_verify_runs_sqlite_integrity_check(dest):
    f = dest / "shop-20261027T120000Z.sqlite"
    f.write_bytes(b"this is not a database")
    backupctl.write_checksum(f)  # checksum matches, but the file is useless
    assert backupctl.verify(dest)[0]["state"] == "CORRUPT"


# --- rotate ---

def test_rotation_keeps_daily_and_weekly_backups(dest):
    # Two backups a day (02:00 and 08:00) for 60 days. NOW is Tuesday 2026-10-27 12:00 UTC.
    for days_ago in range(60):
        for hour in (2, 8):
            fake_backup(dest, "shop", NOW.replace(hour=hour) - timedelta(days=days_ago))
    deleted = backupctl.rotate(dest, keep_daily=7, keep_weekly=4, now=NOW)
    kept = sorted(f.name for f in dest.glob("*.sqlite"))
    # Newest of each of the last 7 days, plus newest of each of the last 4 ISO weeks
    # (the weeks of Oct 26 and Oct 19 are already covered by the daily ones).
    expected = [f"shop-202610{d:02d}T080000Z.sqlite" for d in (11, 18, 21, 22, 23, 24, 25, 26, 27)]
    assert kept == expected
    assert len(deleted) == 120 - 9
    assert not any(Path(f"{f}.sha256").exists() for f in deleted)


def test_rotation_is_per_database(dest):
    for days_ago in range(10):
        fake_backup(dest, "shop", NOW - timedelta(days=days_ago))
        fake_backup(dest, "crm", NOW - timedelta(days=days_ago))
    backupctl.rotate(dest, keep_daily=3, keep_weekly=0, now=NOW)
    assert len(list(dest.glob("shop-*.sqlite"))) == 3
    assert len(list(dest.glob("crm-*.sqlite"))) == 3


def test_rotation_dry_run_deletes_nothing(dest):
    for days_ago in range(10):
        fake_backup(dest, "shop", NOW - timedelta(days=days_ago))
    deleted = backupctl.rotate(dest, keep_daily=3, keep_weekly=0, now=NOW, dry_run=True)
    assert len(deleted) == 7 and len(list(dest.glob("*.sqlite"))) == 10


# --- status ---

def test_status_ok(db, dest):
    backupctl.backup_sqlite(db, dest, now=NOW - timedelta(hours=3))
    s = backupctl.status(dest, max_age_hours=26, now=NOW)
    assert s["status"] == "OK"
    assert s["databases"][0]["name"] == "shop" and s["databases"][0]["age_hours"] == 3


def test_status_warns_on_an_old_backup(db, dest):
    backupctl.backup_sqlite(db, dest, now=NOW - timedelta(hours=30))
    s = backupctl.status(dest, max_age_hours=26, now=NOW)
    assert s["status"] == "WARNING"
    assert "30 h" in s["databases"][0]["problem"]


def test_status_is_critical_on_corruption(db, dest):
    out = backupctl.backup_sqlite(db, dest, now=NOW)
    out.write_bytes(b"broken")
    assert backupctl.status(dest, now=NOW)["status"] == "CRITICAL"


def test_status_is_critical_when_an_expected_database_has_no_backup(db, dest):
    backupctl.backup_sqlite(db, dest, now=NOW)
    s = backupctl.status(dest, expected=["shop", "orders"], now=NOW)
    assert s["status"] == "CRITICAL"
    assert any(d["name"] == "orders" and d["problem"] == "no backup" for d in s["databases"])


def test_cli_status_writes_json_and_html_and_returns_exit_code(db, dest, tmp_path):
    backupctl.backup_sqlite(db, dest)
    code = backupctl.main(["status", "--dest", str(dest), "--json", str(tmp_path / "s.json"),
                           "--html", str(tmp_path / "s.html")])
    assert code == 0
    assert json.loads((tmp_path / "s.json").read_text())["status"] == "OK"
    assert (tmp_path / "s.html").read_text().startswith("<!doctype html>")


def test_cli_backup_all(db, dest):
    assert backupctl.main(["backup", "--sqlite", str(db), "--dest", str(dest)]) == 0
    assert len(list(dest.glob("shop-*.sqlite"))) == 1


def test_cli_backup_reports_failures_but_continues(db, dest, tmp_path):
    code = backupctl.main(["backup", "--sqlite", str(tmp_path / "missing.db"), "--sqlite", str(db), "--dest", str(dest)])
    assert code == 1
    assert len(list(dest.glob("shop-*.sqlite"))) == 1


# --- scheduler.sh (the loop run by the Docker container) ---

def test_scheduler_one_cycle(db, tmp_path):
    import subprocess
    script = Path(__file__).resolve().parents[1] / "scheduler.sh"
    env = {**os.environ, "ONESHOT": "1", "DEST": str(tmp_path / "b"), "STATUS_DIR": str(tmp_path / "status"),
           "SQLITE_FILES": str(db), "POSTGRES_URLS": "", "APP_DIR": str(script.parent), "PYTHON": sys.executable}
    r = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert len(list((tmp_path / "b").glob("shop-*.sqlite"))) == 1
    assert json.loads((tmp_path / "status" / "status.json").read_text())["status"] == "OK"
    assert (tmp_path / "status" / "index.html").exists()
