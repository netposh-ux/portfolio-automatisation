"""Generate 3D-printable badges (STL) from a few dimensions in millimetres.

A badge is three bodies: a plate (rounded rectangle, circle or hexagon) with an optional keyring hole,
a raised rim along its edge, and a raised star in the middle. They can be printed in one colour
(one STL) or in several (--split, one STL per body).

Examples:
  python badge.py -o badge.stl --preview badge.png
  python badge.py --shape hexagon --width 50 --height 50 --star-points 6 -o hex.stl --split
  python badge.py --batch badges.csv --out-dir out/
"""
import argparse
import csv
import math
import sys
from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np

SHAPES = ("rounded", "circle", "hexagon")
MARGIN = 1.0       # mm of flat plate kept between the hole, the rim and the star
SAMPLES = 360      # rays around the centre; every polygon vertex is added on top of these


@dataclass
class BadgeSpec:
    shape: str = "rounded"
    width: float = 60.0
    height: float = 40.0         # ignored for a circle (width = diameter)
    corner: float = 6.0          # corner radius of the rounded rectangle
    thickness: float = 3.0       # plate
    rim: float = 2.0             # rim width, 0 for none
    rim_height: float = 1.0
    star_points: int = 5         # 0 for no star
    star_size: float = 20.0      # tip-to-tip diameter
    star_inner: float = 0.45     # inner radius / outer radius
    emblem_height: float = 1.2
    hole: float = 4.0            # keyring hole diameter, 0 for none


# --- 2D outlines (counter-clockwise, centred on the origin) ---

def rounded_rect(w, h, r, segments=24):
    r = min(r, w / 2, h / 2)
    if r <= 0:
        return np.array([(w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2), (-w / 2, -h / 2)])
    pts = []
    for cx, cy, start in ((w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0),
                          (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)):
        for k in range(segments + 1):
            a = math.radians(start + 90 * k / segments)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return np.array(pts)


def circle(d, n=SAMPLES):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.column_stack([d / 2 * np.cos(a), d / 2 * np.sin(a)])


def hexagon(w, h):
    return np.array([(w / 2, 0), (w / 4, h / 2), (-w / 4, h / 2), (-w / 2, 0), (-w / 4, -h / 2), (w / 4, -h / 2)])


def offset_inward(poly, b):
    """Move every edge of a convex polygon inward by b; new corners are where the moved edges meet."""
    nxt = np.roll(poly, -1, axis=0)
    edge = nxt - poly
    normal = np.column_stack([-edge[:, 1], edge[:, 0]]) / np.linalg.norm(edge, axis=1)[:, None]
    p = poly + b * normal          # a point on each moved edge
    out = []
    for i in range(len(poly)):
        j = i - 1
        d1, d2 = edge[j], edge[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12:
            out.append(p[i])
            continue
        t = ((p[i][0] - p[j][0]) * d2[1] - (p[i][1] - p[j][1]) * d2[0]) / den
        out.append(p[j] + t * d1)
    return np.array(out)


def outline(spec, inset=0.0):
    if spec.shape == "rounded":
        w, h = spec.width - 2 * inset, spec.height - 2 * inset
        if min(w, h) <= 0:
            raise ValueError("the rim is wider than the plate")
        return rounded_rect(w, h, max(spec.corner - inset, 0))
    if spec.shape == "circle":
        if spec.width - 2 * inset <= 0:
            raise ValueError("the rim is wider than the plate")
        return circle(spec.width - 2 * inset)
    poly = offset_inward(hexagon(spec.width, spec.height), inset) if inset else hexagon(spec.width, spec.height)
    if inset and (cross2(np.roll(poly, -1, 0) - poly, np.roll(poly, -2, 0) - np.roll(poly, -1, 0)) <= 0).any():
        raise ValueError("the rim is wider than the plate")
    return poly


def cross2(a, b):
    """z component of the cross product of 2D vectors (NumPy 2 no longer accepts 2D in np.cross)."""
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def edge_distance(poly, c):
    """Smallest distance from point c to the edges of a convex polygon (negative if c is outside)."""
    nxt = np.roll(poly, -1, axis=0)
    e = nxt - poly
    return min(cross2(e, c - poly) / np.linalg.norm(e, axis=1))


def ray_hits(poly, c, angles):
    """Where rays from c (inside the convex polygon) leave it, one point per angle."""
    a, b = poly, np.roll(poly, -1, axis=0)
    e = b - a
    out = []
    for th in angles:
        d = np.array([math.cos(th), math.sin(th)])
        den = d[0] * e[:, 1] - d[1] * e[:, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = ((a[:, 0] - c[0]) * e[:, 1] - (a[:, 1] - c[1]) * e[:, 0]) / den
            s = ((a[:, 0] - c[0]) * d[1] - (a[:, 1] - c[1]) * d[0]) / den
        ok = (np.abs(den) > 1e-12) & (t > 1e-9) & (s >= -1e-9) & (s <= 1 + 1e-9)
        out.append(c + t[ok].min() * d)
    return np.array(out)


def angles_for(c, *polys):
    """Uniform angles plus the direction of every vertex, so corners are kept exactly."""
    a = [np.linspace(-math.pi, math.pi, SAMPLES, endpoint=False)]
    for p in polys:
        a.append(np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0]))
    a = np.sort(np.mod(np.concatenate(a) + math.pi, 2 * math.pi) - math.pi)
    # Drop near-duplicates (a vertex almost on a uniform ray): they would give zero-area triangles.
    keep = np.concatenate([[True], np.diff(a) > 1e-5])
    a = a[keep]
    if a[-1] - a[0] > 2 * math.pi - 1e-5:
        a = a[:-1]
    return a


# --- 3D bodies (arrays of triangles, shape (n, 3, 3), outward normals) ---

def prism(outer, z0, z1, inner=None, center=None):
    """Extrude the area between two loops sampled at the same angles (or a loop and its centre)."""
    n = len(outer)
    tris = []
    for i in range(n):
        j = (i + 1) % n
        o0, o1 = outer[i], outer[j]
        if inner is None:
            c = center
            tris += [((*c, z1), (*o0, z1), (*o1, z1)), ((*c, z0), (*o1, z0), (*o0, z0))]
        else:
            i0, i1 = inner[i], inner[j]
            tris += [((*i0, z1), (*o0, z1), (*o1, z1)), ((*i0, z1), (*o1, z1), (*i1, z1)),
                     ((*i0, z0), (*o1, z0), (*o0, z0)), ((*i0, z0), (*i1, z0), (*o1, z0)),
                     ((*i1, z0), (*i0, z0), (*i0, z1)), ((*i1, z0), (*i0, z1), (*i1, z1))]
        tris += [((*o0, z0), (*o1, z0), (*o1, z1)), ((*o0, z0), (*o1, z1), (*o0, z1))]
    return np.array(tris, dtype=float)


def star(points, size, inner_ratio, c):
    a = math.pi / 2 + np.arange(2 * points) * math.pi / points
    r = np.where(np.arange(2 * points) % 2 == 0, size / 2, size / 2 * inner_ratio)
    return np.column_stack([c[0] + r * np.cos(a), c[1] + r * np.sin(a)])


def build(spec: BadgeSpec) -> dict:
    if spec.shape not in SHAPES:
        raise ValueError(f"unknown shape {spec.shape!r} (choose from {', '.join(SHAPES)})")
    if min(spec.width, spec.height, spec.thickness) <= 0:
        raise ValueError("width, height and thickness must be positive")
    if spec.rim < 0 or spec.hole < 0 or spec.star_size < 0:
        raise ValueError("rim, hole and star size cannot be negative")
    origin = np.zeros(2)
    plate = outline(spec)
    inner = outline(spec, spec.rim) if spec.rim else plate
    z_top = spec.thickness
    bodies = {}

    star_r = spec.star_size / 2 if spec.star_points else 0
    if star_r and edge_distance(inner, origin) < star_r + MARGIN:
        raise ValueError(f"the star ({spec.star_size} mm) does not fit inside the rim")

    if spec.hole:
        hr = spec.hole / 2
        top = inner[:, 1].max()
        h = np.array([0.0, top - MARGIN - hr])
        if edge_distance(inner, h) < hr + MARGIN - 0.01:  # 0.01 mm: a circle's facets sit slightly inside it
            raise ValueError(f"the {spec.hole} mm hole does not fit inside the rim")
        if star_r and (h[1] - hr) - star_r < MARGIN:
            raise ValueError("the hole overlaps the star: make the star smaller or the badge taller")
        angles = angles_for(h, plate)
        hole_loop = np.column_stack([h[0] + hr * np.cos(angles), h[1] + hr * np.sin(angles)])
        bodies["plate"] = prism(ray_hits(plate, h, angles), 0, z_top, inner=hole_loop)
    else:
        angles = angles_for(origin, plate)
        bodies["plate"] = prism(ray_hits(plate, origin, angles), 0, z_top, center=origin)

    if spec.rim:
        angles = angles_for(origin, plate, inner)
        bodies["rim"] = prism(ray_hits(plate, origin, angles), z_top, z_top + spec.rim_height,
                              inner=ray_hits(inner, origin, angles))
    if spec.star_points:
        if spec.star_points < 3 or not 0 < spec.star_inner < 1:
            raise ValueError("a star needs at least 3 points and 0 < star_inner < 1")
        bodies["emblem"] = prism(star(spec.star_points, spec.star_size, spec.star_inner, origin),
                                 z_top, z_top + spec.emblem_height, center=origin)
    return bodies


# --- validation ---

def check_mesh(tris):
    """Closed (every edge shared by exactly two triangles), consistently oriented, positive volume."""
    pts = np.round(tris.reshape(-1, 3), 6)
    _, ids = np.unique(pts, axis=0, return_inverse=True)
    ids = ids.reshape(-1, 3)
    directed = np.concatenate([ids[:, [0, 1]], ids[:, [1, 2]], ids[:, [2, 0]]])
    undirected = np.sort(directed, axis=1)
    _, counts = np.unique(undirected, axis=0, return_counts=True)
    _, dcounts = np.unique(directed, axis=0, return_counts=True)
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    areas = np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1) / 2
    return {
        "triangles": len(tris),
        "watertight": bool((counts == 2).all()),
        "consistent": bool((dcounts == 1).all() and (counts == 2).all()),
        "volume": float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6),
        "degenerate": int((areas < 1e-9).sum()),
    }


# --- output ---

def write_stl(bodies, path, split=False):
    from stl import mesh as stlmesh

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    groups = {f"{path.stem}-{k}": v for k, v in bodies.items()} if split else {path.stem: np.concatenate(list(bodies.values()))}
    written = []
    for name, tris in groups.items():
        m = stlmesh.Mesh(np.zeros(len(tris), dtype=stlmesh.Mesh.dtype))
        m.vectors[:] = tris
        m.update_normals()
        out = path.with_name(f"{name}.stl")
        m.save(str(out))
        written.append(out)
    return written


def preview(spec, path):
    """Dimensioned drawing: top view and side profile, in millimetres."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plate, origin = outline(spec), np.zeros(2)
    fig, (top, side) = plt.subplots(2, 1, figsize=(7, 6.4), dpi=130, gridspec_kw={"height_ratios": [4, 1]})
    closed = lambda pts: np.vstack([pts, pts[:1]])  # noqa: E731
    top.fill(*closed(plate).T, color="#3b6ea8", alpha=0.25, lw=0)
    top.plot(*closed(plate).T, color="#3b6ea8", lw=1.5)
    if spec.rim:
        inner = outline(spec, spec.rim)
        top.fill(*np.vstack([closed(plate), closed(inner)[::-1]]).T, color="#e0b84c", lw=0)
    else:
        inner = plate
    if spec.star_points:
        top.fill(*closed(star(spec.star_points, spec.star_size, spec.star_inner, origin)).T, color="#e0b84c")
    hole_y = None
    if spec.hole:
        hole_y = inner[:, 1].max() - MARGIN - spec.hole / 2
        top.add_patch(plt.Circle((0, hole_y), spec.hole / 2, color="white", ec="#3b6ea8", lw=1.2))

    w = plate[:, 0].max() - plate[:, 0].min()
    h = plate[:, 1].max() - plate[:, 1].min()
    lo, hi = plate.min(axis=0), plate.max(axis=0)
    arrow = dict(arrowstyle="<->", color="#333", lw=0.8)
    top.annotate("", (lo[0], lo[1] - 5), (hi[0], lo[1] - 5), arrowprops=arrow)
    top.text(0, lo[1] - 7, f"{w:g} mm", ha="center", va="top")
    top.annotate("", (hi[0] + 5, lo[1]), (hi[0] + 5, hi[1]), arrowprops=arrow)
    top.text(hi[0] + 7, 0, f"{h:g} mm", va="center", rotation=90)
    notes = [f"rim {spec.rim:g} mm" if spec.rim else None,
             f"star Ø {spec.star_size:g} mm, {spec.star_points} points" if spec.star_points else None,
             f"hole Ø {spec.hole:g} mm" if spec.hole else None]
    top.set_title(f"{spec.shape} badge, top view", loc="left", fontsize=11)
    top.text(lo[0], hi[1] + 3, " · ".join(n for n in notes if n), fontsize=9, color="#444")
    top.set_aspect("equal")
    top.set_xlim(lo[0] - 4, hi[0] + 14)
    top.set_ylim(lo[1] - 13, hi[1] + 7)
    top.axis("off")

    # Side profile through the centre: plate, rim on both edges, star in the middle.
    t, z_rim, z_star = spec.thickness, spec.thickness + spec.rim_height, spec.thickness + spec.emblem_height
    side.fill_between([lo[0], hi[0]], 0, t, color="#3b6ea8", alpha=0.6, lw=0)
    if spec.rim:
        for x0 in (lo[0], hi[0] - spec.rim):
            side.fill_between([x0, x0 + spec.rim], t, z_rim, color="#e0b84c", lw=0)
    if spec.star_points:
        side.fill_between([-spec.star_size / 2, spec.star_size / 2], t, z_star, color="#e0b84c", lw=0)
    parts = [f"plate {t:g} mm"] + ([f"rim +{spec.rim_height:g} mm"] if spec.rim else []) \
        + ([f"star +{spec.emblem_height:g} mm"] if spec.star_points else [])
    side.text(lo[0], -1.5, " · ".join(parts) + f" · total {max(z_rim if spec.rim else t, z_star if spec.star_points else t):g} mm",
              va="top", fontsize=9, color="#444")
    side.set_title("side profile (heights)", loc="left", fontsize=10)
    side.set_aspect("equal")
    side.set_xlim(lo[0] - 4, hi[0] + 14)
    side.set_ylim(-5, max(z_rim, z_star) + 1)
    side.axis("off")
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def describe(name, spec, bodies):
    pts = np.concatenate(list(bodies.values())).reshape(-1, 3)
    size = pts.max(axis=0) - pts.min(axis=0)
    checks = {k: check_mesh(v) for k, v in bodies.items()}
    ok = all(c["watertight"] and c["consistent"] and c["volume"] > 0 for c in checks.values())
    volume = sum(c["volume"] for c in checks.values())
    print(f"{name}: {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} mm, {volume / 1000:.2f} cm3, "
          f"{sum(c['triangles'] for c in checks.values())} triangles, mesh {'OK' if ok else 'INVALID'}")
    return ok


def spec_from(values: dict) -> BadgeSpec:
    types = {f.name: f.type for f in fields(BadgeSpec)}
    kwargs = {}
    for k, v in values.items():
        k = k.replace("-", "_")
        if k in types and v not in (None, ""):
            kwargs[k] = {"float": float, "int": int, "str": str}[types[k] if isinstance(types[k], str) else types[k].__name__](v)
    return BadgeSpec(**kwargs)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for f in fields(BadgeSpec):
        p.add_argument(f"--{f.name.replace('_', '-')}", default=None,
                       help=f"default {f.default}" + (f" ({', '.join(SHAPES)})" if f.name == "shape" else ""))
    p.add_argument("-o", "--output", default="badge.stl")
    p.add_argument("--split", action="store_true", help="one STL per body, for multi-colour printing")
    p.add_argument("--preview", metavar="PNG", help="also render a preview image")
    p.add_argument("--batch", metavar="CSV", help="one badge per row; columns: name + any option above")
    p.add_argument("--out-dir", default="out")
    a = p.parse_args(argv)

    if a.batch:
        with open(a.batch, newline="") as f:
            jobs = [(row["name"], spec_from(row), Path(a.out_dir) / f"{row['name']}.stl") for row in csv.DictReader(f)]
    else:
        jobs = [(Path(a.output).stem, spec_from(vars(a)), Path(a.output))]

    status = 0
    for name, spec, out in jobs:
        try:
            bodies = build(spec)
        except ValueError as e:
            print(f"{name}: {e}", file=sys.stderr)
            status = 2
            continue
        if not describe(name, spec, bodies):
            status = 1
        write_stl(bodies, out, split=a.split)
        if a.preview and not a.batch:
            preview(spec, a.preview)
    return status


if __name__ == "__main__":
    sys.exit(main())
