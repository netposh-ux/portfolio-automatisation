"""Geometry tests: every body is a closed, consistently oriented mesh with the requested dimensions."""
import csv
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from stl import mesh as stlmesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import badge  # noqa: E402

TOL = 0.01  # mm


def dims(tris):
    pts = tris.reshape(-1, 3)
    return pts.max(axis=0) - pts.min(axis=0)


@pytest.mark.parametrize("shape", ["rounded", "circle", "hexagon"])
def test_plate_is_watertight_with_exact_dimensions(shape):
    spec = badge.BadgeSpec(shape=shape, width=60, height=40, thickness=3, rim=0, star_points=0, hole=0)
    plate = badge.build(spec)["plate"]
    report = badge.check_mesh(plate)
    assert report["watertight"] and report["consistent"] and report["volume"] > 0
    w, h, t = dims(plate)
    expected_h = 60 if shape == "circle" else 40  # a circle uses the width as its diameter
    assert abs(w - 60) < TOL and abs(h - expected_h) < 0.1 and abs(t - 3) < TOL


def test_rounded_plate_volume_matches_the_formula():
    spec = badge.BadgeSpec(shape="rounded", width=60, height=40, corner=6, thickness=3, rim=0, star_points=0, hole=0)
    volume = badge.check_mesh(badge.build(spec)["plate"])["volume"]
    exact = (60 * 40 - (4 - math.pi) * 6 ** 2) * 3
    assert volume == pytest.approx(exact, rel=0.002)


def test_keyring_hole_removes_the_right_volume():
    base = badge.BadgeSpec(shape="rounded", width=60, height=40, thickness=3, rim=0, star_points=0, hole=0)
    holed = badge.BadgeSpec(shape="rounded", width=60, height=40, thickness=3, rim=0, star_points=0, hole=4)
    v0 = badge.check_mesh(badge.build(base)["plate"])["volume"]
    v1 = badge.check_mesh(badge.build(holed)["plate"])["volume"]
    assert v0 - v1 == pytest.approx(math.pi * 2 ** 2 * 3, rel=0.01)
    report = badge.check_mesh(badge.build(holed)["plate"])
    assert report["watertight"] and report["consistent"]


def test_full_badge_bodies_are_all_valid():
    bodies = badge.build(badge.BadgeSpec())
    assert set(bodies) == {"plate", "rim", "emblem"}
    for name, tris in bodies.items():
        r = badge.check_mesh(tris)
        assert r["watertight"] and r["consistent"] and r["volume"] > 0, name
        assert r["degenerate"] == 0, name


def test_total_height_is_plate_plus_tallest_relief():
    spec = badge.BadgeSpec(thickness=3, rim_height=1, emblem_height=1.5)
    allt = np.concatenate(list(badge.build(spec).values()))
    assert abs(dims(allt)[2] - 4.5) < TOL


def test_star_volume_matches_the_formula():
    spec = badge.BadgeSpec(star_points=5, star_size=20, star_inner=0.5, emblem_height=2)
    vol = badge.check_mesh(badge.build(spec)["emblem"])["volume"]
    r_out, r_in = 10, 5
    area = 5 * r_out * r_in * math.sin(math.pi / 5)  # 2n triangles of (R * r * sin(pi/n)) / 2
    assert vol == pytest.approx(area * 2, rel=1e-6)


def test_relief_stays_inside_the_plate():
    spec = badge.BadgeSpec(shape="hexagon", width=50, height=50, star_size=30)
    bodies = badge.build(spec)
    plate_pts = bodies["plate"].reshape(-1, 3)
    for name in ("rim", "emblem"):
        pts = bodies[name].reshape(-1, 3)
        assert pts[:, 0].min() >= plate_pts[:, 0].min() - TOL and pts[:, 0].max() <= plate_pts[:, 0].max() + TOL
        assert pts[:, 1].min() >= plate_pts[:, 1].min() - TOL and pts[:, 1].max() <= plate_pts[:, 1].max() + TOL
        assert pts[:, 2].min() >= spec.thickness - TOL


@pytest.mark.parametrize("bad", [
    dict(star_size=80),                        # star wider than the plate
    dict(hole=30),                             # hole bigger than the plate allows
    dict(rim=25),                              # rim eats the whole plate
    dict(thickness=0),
    dict(shape="triangle"),
])
def test_impossible_parameters_are_refused(bad):
    with pytest.raises(ValueError):
        badge.build(badge.BadgeSpec(**bad))


def test_check_mesh_detects_a_hole_in_the_mesh():
    tris = badge.build(badge.BadgeSpec(rim=0, star_points=0, hole=0))["plate"]
    r = badge.check_mesh(tris[1:])
    assert not r["watertight"]


def test_check_mesh_detects_a_flipped_triangle():
    tris = badge.build(badge.BadgeSpec(rim=0, star_points=0, hole=0))["plate"].copy()
    tris[0] = tris[0][::-1]
    assert not badge.check_mesh(tris)["consistent"]


def test_writes_a_readable_binary_stl(tmp_path):
    out = tmp_path / "badge.stl"
    badge.write_stl(badge.build(badge.BadgeSpec()), out)
    m = stlmesh.Mesh.from_file(str(out))
    assert len(m.vectors) > 100
    assert m.is_closed()


def test_split_writes_one_file_per_body_for_multicolor_printing(tmp_path):
    files = badge.write_stl(badge.build(badge.BadgeSpec()), tmp_path / "badge.stl", split=True)
    assert sorted(f.name for f in files) == ["badge-emblem.stl", "badge-plate.stl", "badge-rim.stl"]


def test_cli_batch_from_csv(tmp_path):
    rows = [{"name": "team-blue", "shape": "circle", "width": "45", "star_points": "6"},
            {"name": "team-red", "shape": "hexagon", "width": "50", "height": "50", "hole": "0"}]
    with open(tmp_path / "badges.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "shape", "width", "height", "star_points", "hole"])
        w.writeheader()
        w.writerows(rows)
    code = badge.main(["--batch", str(tmp_path / "badges.csv"), "--out-dir", str(tmp_path / "out")])
    assert code == 0
    assert sorted(p.name for p in (tmp_path / "out").glob("*.stl")) == ["team-blue.stl", "team-red.stl"]


def test_cli_reports_bad_parameters(tmp_path, capsys):
    assert badge.main(["--star-size", "90", "-o", str(tmp_path / "x.stl")]) == 2
    assert "star" in capsys.readouterr().err


def test_preview_drawing_is_written(tmp_path):
    pytest.importorskip("matplotlib")
    badge.preview(badge.BadgeSpec(), tmp_path / "p.png")
    assert (tmp_path / "p.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
