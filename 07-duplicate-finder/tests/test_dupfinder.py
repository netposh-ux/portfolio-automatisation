"""Acceptance tests: one test per requirement."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dupfinder import scanner
from dupfinder.cli import main


def write(path: Path, content: bytes, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "data"
    write(root / "a.txt", b"bonjour", mtime=1_000)
    write(root / "sub" / "copy_of_a.txt", b"bonjour", mtime=2_000)
    write(root / "sub" / "deep" / "a2.txt", b"bonjour", mtime=3_000)
    write(root / "b.bin", b"xyz" * 100)
    write(root / "b_copy.bin", b"xyz" * 100)
    write(root / "same_size.txt", b"bonsoir")  # same size as "bonjour", different content
    write(root / "unique.txt", b"alone")
    write(root / "empty1", b"")
    write(root / "empty2", b"")
    return root


def group_names(result):
    return sorted(sorted(Path(f).name for f in g.files) for g in result.groups)


# Requirement: size first, then SHA-256
def test_finds_duplicate_groups(tree):
    assert group_names(scanner.scan(tree)) == [
        ["a.txt", "a2.txt", "copy_of_a.txt"],
        ["b.bin", "b_copy.bin"],
    ]


def test_exact_sha256(tree):
    group = next(g for g in scanner.scan(tree).groups if len(g.files) == 3)
    assert group.sha256 == hashlib.sha256(b"bonjour").hexdigest()
    assert group.size == 7


def test_hashes_only_files_sharing_a_size(tree, monkeypatch):
    hashed = []
    original = scanner.sha256

    def spy(path):
        hashed.append(Path(path).name)
        return original(path)

    monkeypatch.setattr(scanner, "sha256", spy)
    scanner.scan(tree)
    assert "unique.txt" not in hashed
    assert sorted(hashed) == ["a.txt", "a2.txt", "b.bin", "b_copy.bin", "copy_of_a.txt", "same_size.txt"]


def test_empty_files_skipped_by_default_included_on_request(tree):
    assert all(g.size > 0 for g in scanner.scan(tree).groups)
    assert ["empty1", "empty2"] in group_names(scanner.scan(tree, min_size=0))


def test_symlinks_ignored(tree):
    (tree / "link.txt").symlink_to(tree / "a.txt")
    names = [Path(f).name for g in scanner.scan(tree).groups for f in g.files]
    assert "link.txt" not in names


def test_reclaimable_space(tree):
    assert scanner.scan(tree).reclaimable == 7 * 2 + 300


# Requirement: --dry-run by default
def test_dry_run_by_default_deletes_nothing(tree, tmp_path, capsys):
    before = sorted(p.name for p in tree.rglob("*"))
    assert main([str(tree), "--json", str(tmp_path / "r.json")]) == 0
    assert sorted(p.name for p in tree.rglob("*")) == before
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["mode"] == "dry-run" and report["deleted"] == []
    assert "dry-run" in capsys.readouterr().out.lower()


def test_dry_run_and_apply_are_exclusive(tree):
    with pytest.raises(SystemExit):
        main([str(tree), "--dry-run", "--apply"])


# Requirement: clean-up
def test_apply_keeps_oldest_by_default(tree, tmp_path):
    assert main([str(tree), "--apply", "--json", str(tmp_path / "r.json")]) == 0
    assert (tree / "a.txt").exists()
    assert not (tree / "sub" / "copy_of_a.txt").exists()
    assert not (tree / "sub" / "deep" / "a2.txt").exists()
    assert (tree / "same_size.txt").exists() and (tree / "unique.txt").exists()
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["mode"] == "apply" and len(report["deleted"]) == 3


def test_apply_keeps_shortest_path(tree):
    main([str(tree), "--apply", "--keep", "shortest"])
    assert (tree / "a.txt").exists() and (tree / "b.bin").exists()
    assert not (tree / "b_copy.bin").exists()


def test_apply_keeps_newest(tree):
    main([str(tree), "--apply", "--keep", "newest"])
    assert (tree / "sub" / "deep" / "a2.txt").exists()
    assert not (tree / "a.txt").exists()


# Requirement: JSON report
def test_json_report(tree, tmp_path):
    main([str(tree), "--json", str(tmp_path / "r.json")])
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["root"] == str(tree.resolve())
    assert report["summary"] == {"files_scanned": 7, "groups": 2, "duplicates": 3, "reclaimable_bytes": 314}
    group = next(g for g in report["groups"] if g["size"] == 7)
    assert group["keep"].endswith("a.txt") and len(group["files"]) == 3
    assert report["errors"] == []


# Requirement: HTML report
def test_html_report_escapes_file_names(tree, tmp_path):
    write(tree / "<script>x.txt", b"bonjour")
    main([str(tree), "--html", str(tmp_path / "r.html")])
    html = (tmp_path / "r.html").read_text()
    assert html.startswith("<!doctype html>")
    assert hashlib.sha256(b"bonjour").hexdigest() in html
    assert "&lt;script&gt;x.txt" in html and "<script>x" not in html


# Requirement: permission errors
@pytest.mark.skipif(os.geteuid() == 0, reason="root can read everything")
def test_unreadable_files_reported_scan_continues(tree, tmp_path):
    blocked = write(tree / "blocked.txt", b"bonjour")
    blocked.chmod(0)
    private = tree / "private"
    write(private / "x.txt", b"bonjour")
    private.chmod(0)
    try:
        code = main([str(tree), "--json", str(tmp_path / "r.json")])
        report = json.loads((tmp_path / "r.json").read_text())
    finally:
        blocked.chmod(0o644)
        private.chmod(0o755)
    assert code == 0
    paths = [e["path"] for e in report["errors"]]
    assert str(blocked) in paths and str(private) in paths
    assert report["summary"]["groups"] == 2


def test_missing_folder(tmp_path, capsys):
    assert main([str(tmp_path / "missing")]) == 2
    assert "not found" in capsys.readouterr().err


# Requirement: installable CLI
def test_runs_as_module():
    out = subprocess.run([sys.executable, "-m", "dupfinder", "--help"], capture_output=True, text=True,
                         cwd=Path(__file__).parents[1])
    assert out.returncode == 0 and "--apply" in out.stdout
