"""JSON and HTML reports."""
from __future__ import annotations

import json
from datetime import datetime
from html import escape

from .scanner import Result


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def build(result: Result, mode: str, rule: str, keep: dict[str, str], deleted: list[str]) -> dict:
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": result.root,
        "mode": mode,
        "keep_rule": rule,
        "summary": {
            "files_scanned": result.files_scanned,
            "groups": len(result.groups),
            "duplicates": sum(len(g.files) - 1 for g in result.groups),
            "reclaimable_bytes": result.reclaimable,
        },
        "groups": [{"sha256": g.sha256, "size": g.size, "keep": keep[g.sha256], "files": g.files}
                   for g in result.groups],
        "deleted": deleted,
        "errors": [{"path": e.path, "message": e.message} for e in result.errors],
    }


def write_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


STYLE = """
body{font-family:system-ui,sans-serif;margin:2rem auto;max-width:1100px;padding:0 1rem;color:#1f2933;background:#f7f9fb}
h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:2rem}
.cards{display:flex;gap:1rem;flex-wrap:wrap}.card{background:#fff;border:1px solid #d9e2ec;border-radius:8px;padding:.8rem 1.2rem}
.card b{display:block;font-size:1.4rem}
table{border-collapse:collapse;width:100%;background:#fff;margin-bottom:1rem}
td,th{border:1px solid #d9e2ec;padding:.4rem .6rem;text-align:left;font-size:.9rem;word-break:break-all}
th{background:#eef2f6}.keep{color:#0b7a3e;font-weight:600}.gone{color:#b42318;text-decoration:line-through}
code{font-size:.8rem;color:#52606d}.mode{display:inline-block;padding:.2rem .6rem;border-radius:4px;background:#fff3c4}
"""


def html(d: dict) -> str:
    s = d["summary"]
    deleted = set(d["deleted"])
    parts = []
    for i, g in enumerate(d["groups"], 1):
        parts.append(f"<h2>Group {i} · {len(g['files'])} files · {escape(human_size(g['size']))}</h2>"
                     f"<code>SHA-256 {escape(g['sha256'])}</code><table><tr><th>File</th><th>Action</th></tr>")
        for f in g["files"]:
            if f == g["keep"]:
                css, action = "keep", "kept"
            elif f in deleted:
                css, action = "gone", "deleted"
            else:
                css, action = "", "would be deleted" if d["mode"] == "dry-run" else "not deleted"
            parts.append(f'<tr><td class="{css}">{escape(f)}</td><td>{action}</td></tr>')
        parts.append("</table>")
    if d["errors"]:
        parts.append("<h2>Errors</h2><table><tr><th>Path</th><th>Message</th></tr>")
        parts += [f"<tr><td>{escape(e['path'])}</td><td>{escape(e['message'])}</td></tr>" for e in d["errors"]]
        parts.append("</table>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Duplicate files report</title><style>{STYLE}</style></head><body>
<h1>Duplicate files report</h1>
<p>{escape(d['root'])} · {escape(d['generated_at'])} · <span class="mode">{escape(d['mode'])} mode</span>
· keep: {escape(d['keep_rule'])}</p>
<div class="cards">
<div class="card"><b>{s['files_scanned']}</b>files scanned</div>
<div class="card"><b>{s['groups']}</b>duplicate groups</div>
<div class="card"><b>{s['duplicates']}</b>duplicates</div>
<div class="card"><b>{escape(human_size(s['reclaimable_bytes']))}</b>reclaimable</div>
<div class="card"><b>{len(d['errors'])}</b>errors</div>
</div>
{''.join(parts) or '<p>No duplicates found.</p>'}
</body></html>
"""


def write_html(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(html(data))
