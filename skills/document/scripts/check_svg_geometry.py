#!/usr/bin/env python3
"""Geometry self-check for hand-authored report SVG figures.

Design rules enforced (see references/figure-design-system.md, distilled from
diagram-design, MIT): orthogonal rounded connectors only, ports >=8px from node
corners, no partial node overlap, no border-riding segments, no solid connector
through a non-endpoint node, labels/masks not covered, fan-out spacing >=12px.

Scope: hand-authored figures (reports/assets/*.svg). Generated figures
(graphviz/matplotlib) are auto-skipped; their tools own the geometry.

Element conventions (all optional; geometry heuristics work without them):

* connector: has marker-end/marker-start, or a class token from
  --conn-class (default: arrow, line, dash, connector, edge, flow, direct,
  indirect). Add class "skip-geometry" to exclude an element entirely.
* node: any <rect> >=40x24 that is not the background and not a container
  (a rect that fully contains another candidate rect is treated as a zone).
* Opt-outs: class "skip-geometry" (element), --force (generated-SVG guard).

Levels: ERROR (diagonal, corner port, border-riding, solid through-box,
partial overlap) exits 1; WARN (inside-node endpoint, fan-out <12px, dashed
through-box, CJK font-size <12px) does not by default; --strict escalates.

Usage:
    python3 check_svg_geometry.py FIG.svg [FIG2.svg ...] [--strict] [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

EPS = 0.75
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
NUM_RE = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")
CMD_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")

DEFAULT_CONN_TOKENS = {
    "arrow", "line", "dash", "connector", "edge", "flow", "direct", "indirect",
}


def strip_ns(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def num(v, default=0.0):
    if v is None:
        return default
    m = NUM_RE.search(str(v))
    return float(m.group(0)) if m else default


def parse_style_block(root):
    """Return (class_props, text_default) from <style> blocks."""
    class_props = {}
    text_default = {}
    for elem in root.iter():
        if strip_ns(elem.tag) != "style" or not (elem.text or "").strip():
            continue
        css = elem.text
        for selector, body in re.findall(r"([^{}]+)\{([^}]*)\}", css):
            props = {}
            for decl in body.split(";"):
                if ":" not in decl:
                    continue
                key, val = decl.split(":", 1)
                props[key.strip()] = val.strip()
            for part in selector.split(","):
                part = part.strip()
                if part.startswith("."):
                    for cls in part[1:].split("."):
                        class_props.setdefault(cls.strip(), {}).update(props)
                elif part in ("text",):
                    text_default.update(props)
    return class_props, text_default


def class_tokens(elem):
    return set((elem.get("class") or "").split())


def parse_translate(transform):
    """Return (tx, ty, supported). Only translate is supported."""
    if not transform:
        return 0.0, 0.0, True
    if re.search(r"\b(scale|rotate|matrix|skewX|skewY)\b", transform):
        return 0.0, 0.0, False
    m = re.search(r"translate\(\s*([-\d.]+)(?:[\s,]+([-\d.]+))?\s*\)", transform)
    if not m:
        return 0.0, 0.0, True
    return float(m.group(1)), float(m.group(2) or 0.0), True


def collect(elem, tx, ty, supported, out):
    sx, sy, ok = parse_translate(elem.get("transform"))
    supported = supported and ok
    tx, ty = tx + sx, ty + sy
    out.append((elem, tx, ty, supported))
    for child in list(elem):
        collect(child, tx, ty, supported, out)


def parse_path(d):
    """Parse a `d` attribute into anchors and straight segments (absolute).

    Returns (anchors, segments): anchors are absolute points at command ends;
    segments are (kind, x1, y1, x2, y2) where kind in {L, H, V, C, Q, A}.
    """
    anchors, segments = [], []
    tokens = CMD_RE.findall(d or "")
    i, n = 0, len(tokens)
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    cmd = None
    while i < n:
        tok = tokens[i]
        if re.match(r"[A-Za-z]", tok):
            cmd = tok
            i += 1
            if cmd in "Zz":
                cur = start
            continue
        if cmd is None:
            i += 1
            continue
        try:
            if cmd in "Mm":
                x, y = float(tokens[i]), float(tokens[i + 1])
                i += 2
                if cmd == "m":
                    x, y = cur[0] + x, cur[1] + y
                cur = (x, y)
                start = cur
                anchors.append(cur)
                cmd = "L" if cmd == "M" else "l"
            elif cmd in "Ll":
                x, y = float(tokens[i]), float(tokens[i + 1])
                i += 2
                if cmd == "l":
                    x, y = cur[0] + x, cur[1] + y
                if x == cur[0] or y == cur[1]:
                    kind = "H" if y == cur[1] else "V"
                else:
                    kind = "L"
                segments.append((kind, cur[0], cur[1], x, y))
                cur = (x, y)
                anchors.append(cur)
            elif cmd in "Hh":
                x = float(tokens[i])
                i += 1
                if cmd == "h":
                    x += cur[0]
                segments.append(("H", cur[0], cur[1], x, cur[1]))
                cur = (x, cur[1])
                anchors.append(cur)
            elif cmd in "Vv":
                y = float(tokens[i])
                i += 1
                if cmd == "v":
                    y += cur[1]
                segments.append(("V", cur[0], cur[1], cur[0], y))
                cur = (cur[0], y)
                anchors.append(cur)
            elif cmd in "Cc":
                vals = [float(tokens[i + k]) for k in range(6)]
                i += 6
                if cmd == "c":
                    vals = [v + (cur[0] if k % 2 == 0 else cur[1])
                            for k, v in enumerate(vals)]
                end = (vals[4], vals[5])
                segments.append(("C", cur[0], cur[1], end[0], end[1]))
                cur = end
                anchors.append(cur)
            elif cmd in "Ss":
                vals = [float(tokens[i + k]) for k in range(4)]
                i += 4
                if cmd == "s":
                    vals = [v + (cur[0] if k % 2 == 0 else cur[1])
                            for k, v in enumerate(vals)]
                end = (vals[2], vals[3])
                segments.append(("C", cur[0], cur[1], end[0], end[1]))
                cur = end
                anchors.append(cur)
            elif cmd in "Qq":
                vals = [float(tokens[i + k]) for k in range(4)]
                i += 4
                if cmd == "q":
                    vals = [v + (cur[0] if k % 2 == 0 else cur[1])
                            for k, v in enumerate(vals)]
                end = (vals[2], vals[3])
                segments.append(("Q", cur[0], cur[1], end[0], end[1]))
                cur = end
                anchors.append(cur)
            elif cmd in "Tt":
                vals = [float(tokens[i + k]) for k in range(2)]
                i += 2
                if cmd == "t":
                    vals = [vals[0] + cur[0], vals[1] + cur[1]]
                end = (vals[0], vals[1])
                segments.append(("Q", cur[0], cur[1], end[0], end[1]))
                cur = end
                anchors.append(cur)
            elif cmd in "Aa":
                vals = [float(tokens[i + k]) for k in range(7)]
                i += 7
                end = (vals[5], vals[6])
                if cmd == "a":
                    end = (cur[0] + end[0], cur[1] + end[1])
                segments.append(("A", cur[0], cur[1], end[0], end[1]))
                cur = end
                anchors.append(cur)
            else:
                i += 1
        except (IndexError, ValueError):
            break
    return anchors, segments


class Rect:
    def __init__(self, x, y, w, h, elem):
        self.x, self.y, self.w, self.h, self.elem = x, y, w, h, elem

    @property
    def x2(self):
        return self.x + self.w

    @property
    def y2(self):
        return self.y + self.h

    def contains(self, other):
        return (self.x - EPS <= other.x and self.y - EPS <= other.y
                and self.x2 + EPS >= other.x2 and self.y2 + EPS >= other.y2)

    def partial_overlap(self, other):
        ix = min(self.x2, other.x2) - max(self.x, other.x)
        iy = min(self.y2, other.y2) - max(self.y, other.y)
        if ix <= EPS or iy <= EPS:
            return False
        if self.contains(other) or other.contains(self):
            return False
        return True

    def side_of(self, px, py):
        """Return side name if point lies on this rect's border."""
        on_v = (abs(px - self.x) <= EPS or abs(px - self.x2) <= EPS)
        on_h = (abs(py - self.y) <= EPS or abs(py - self.y2) <= EPS)
        in_x = self.x - EPS <= px <= self.x2 + EPS
        in_y = self.y - EPS <= py <= self.y2 + EPS
        if on_h and in_x:
            return "top" if abs(py - self.y) <= EPS else "bottom"
        if on_v and in_y:
            return "left" if abs(px - self.x) <= EPS else "right"
        return None

    def strictly_inside(self, px, py):
        return (self.x + EPS < px < self.x2 - EPS
                and self.y + EPS < py < self.y2 - EPS)

    def corner_distance(self, px, py):
        return min(
            ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
            for cx in (self.x, self.x2)
            for cy in (self.y, self.y2)
        )


def seg_hits_rect_interior(x1, y1, x2, y2, rect):
    """True if an axis-aligned segment passes through rect's interior."""
    if abs(y1 - y2) <= EPS:  # horizontal
        if not (rect.y + EPS < y1 < rect.y2 - EPS):
            return False
        lo, hi = sorted((x1, x2))
        return hi > rect.x + EPS and lo < rect.x2 - EPS
    if abs(x1 - x2) <= EPS:  # vertical
        if not (rect.x + EPS < x1 < rect.x2 - EPS):
            return False
        lo, hi = sorted((y1, y2))
        return hi > rect.y + EPS and lo < rect.y2 - EPS
    return False


def rides_border(x1, y1, x2, y2, rect):
    """Segment collinear with a rect edge and overlapping it by >4px."""
    if abs(y1 - y2) <= EPS:
        if abs(y1 - rect.y) > EPS and abs(y1 - rect.y2) > EPS:
            return False
        lo, hi = sorted((x1, x2))
        overlap = min(hi, rect.x2) - max(lo, rect.x)
        return overlap > 4
    if abs(x1 - x2) <= EPS:
        if abs(x1 - rect.x) > EPS and abs(x1 - rect.x2) > EPS:
            return False
        lo, hi = sorted((y1, y2))
        overlap = min(hi, rect.y2) - max(lo, rect.y)
        return overlap > 4
    return False


def is_generated(text):
    head = text[:3000]
    return ("Generated by graphviz" in head or "Graphviz" in head
            or "Matplotlib" in head or "matplotlib" in head)


def check_file(path, conn_tokens, strict, force):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    findings = []
    if is_generated(text) and not force:
        return findings, True
    if "<!ENTITY" in text:
        return [("ERROR", "unsafe XML",
                 "internal entity declarations are not supported", None)], False
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text, count=1)

    root = ET.fromstring(text)
    class_props, text_default = parse_style_block(root)

    flat = []
    collect(root, 0.0, 0.0, True, flat)

    # canvas size for background detection
    svg_w = svg_h = None
    for elem, tx, ty, ok in flat:
        if strip_ns(elem.tag) == "svg":
            svg_w, svg_h = num(elem.get("width")), num(elem.get("height"))
            vb = NUM_RE.findall(elem.get("viewBox") or "")
            if len(vb) == 4:
                svg_w = svg_w or float(vb[2])
                svg_h = svg_h or float(vb[3])
            break

    # ---- node rects
    rects, skipped_unsupported = [], False
    for elem, tx, ty, ok in flat:
        if not ok:
            skipped_unsupported = True
            continue
        if strip_ns(elem.tag) != "rect":
            continue
        w, h = num(elem.get("width")), num(elem.get("height"))
        if w < 40 or h < 24:
            continue
        if svg_w and svg_h and w >= 0.9 * svg_w and h >= 0.9 * svg_h:
            continue
        if "skip-geometry" in class_tokens(elem):
            continue
        r = Rect(num(elem.get("x")) + tx, num(elem.get("y")) + ty, w, h, elem)
        rects.append(r)

    containers = [r for r in rects if any(
        r.contains(o) and o is not r for o in rects)]
    nodes = [r for r in rects if r not in containers]

    def pos(r):
        return "rect@(%.0f,%.0f %gx%g)" % (r.x, r.y, r.w, r.h)

    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if a.partial_overlap(b):
                findings.append(("ERROR", "node overlap",
                                 "%s overlaps %s" % (pos(a), pos(b)), None))

    # ---- connectors
    for elem, tx, ty, ok in flat:
        if not ok or "skip-geometry" in class_tokens(elem):
            continue
        tag = strip_ns(elem.tag)
        if tag not in ("path", "line", "polyline"):
            continue
        tokens = class_tokens(elem)
        has_marker = bool(elem.get("marker-end") or elem.get("marker-start"))
        if not has_marker and not (tokens & conn_tokens):
            continue
        dashed = "stroke-dasharray" in (elem.get("style") or "")
        if not dashed:
            dashed = bool(elem.get("stroke-dasharray"))
        if not dashed:
            for cls in tokens:
                if "stroke-dasharray" in class_props.get(cls, {}):
                    dashed = True
                    break

        anchors, segments = [], []
        if tag == "path":
            anchors, segments = parse_path(elem.get("d"))
            anchors = [(x + tx, y + ty) for x, y in anchors]
            segments = [(k, x1 + tx, y1 + ty, x2 + tx, y2 + ty)
                        for k, x1, y1, x2, y2 in segments]
        elif tag == "line":
            p1 = (num(elem.get("x1")) + tx, num(elem.get("y1")) + ty)
            p2 = (num(elem.get("x2")) + tx, num(elem.get("y2")) + ty)
            anchors = [p1, p2]
            kind = "H" if abs(p1[1] - p2[1]) <= EPS else (
                "V" if abs(p1[0] - p2[0]) <= EPS else "L")
            segments = [(kind, p1[0], p1[1], p2[0], p2[1])]
        else:
            pts = [float(v) for v in NUM_RE.findall(elem.get("points") or "")]
            pts = [(pts[i] + tx, pts[i + 1] + ty)
                   for i in range(0, len(pts) - 1, 2)]
            anchors = pts
            for a, b in zip(pts, pts[1:]):
                kind = "H" if abs(a[1] - b[1]) <= EPS else (
                    "V" if abs(a[0] - b[0]) <= EPS else "L")
                segments.append((kind, a[0], a[1], b[0], b[1]))

        label = "%s with class %r" % (tag, " ".join(sorted(tokens)) or "-")

        for kind, x1, y1, x2, y2 in segments:
            if kind == "L":
                findings.append(("ERROR", "diagonal connector",
                                 "%s: slanted segment (%.0f,%.0f)->(%.0f,%.0f)"
                                 % (label, x1, y1, x2, y2), None))

        # attach points: connector anchors on a node border (subpath starts/final
        # anchors only for corner/inside checks)
        attach = {}
        for px, py in anchors:
            for r in nodes:
                side = r.side_of(px, py)
                if side:
                    key = (id(r), side)
                    attach.setdefault(key, (r, side, []))[2].append((px, py))

        sub_ends = set()
        if anchors:
            sub_ends.add(anchors[0])
            sub_ends.add(anchors[-1])
        for px, py in sub_ends:
            for r in nodes:
                if r.strictly_inside(px, py):
                    findings.append(("WARN", "endpoint inside node",
                                     "%s: endpoint (%.0f,%.0f) is inside %s"
                                     % (label, px, py, pos(r)), None))
                elif r.side_of(px, py) and r.corner_distance(px, py) < 8:
                    findings.append(("ERROR", "corner port",
                                     "%s: endpoint (%.0f,%.0f) is %.1fpx from a "
                                     "corner of %s (need >=8px)"
                                     % (label, px, py,
                                        r.corner_distance(px, py), pos(r)), None))

        for (_, _side_key), (r, side, pts) in attach.items():
            pts_sorted = sorted(pts, key=lambda p: p[0] + p[1])
            for (a, b) in zip(pts_sorted, pts_sorted[1:]):
                gap = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                if EPS < gap < 12:
                    findings.append(("WARN", "fan-out spacing",
                                     "%s: attach points %.0fpx apart on %s %s "
                                     "(need >=12px)" % (label, gap, side, pos(r)),
                                     None))

        connected = {id(r) for r, _, _ in attach.values()}
        for kind, x1, y1, x2, y2 in segments:
            if kind == "A":
                continue
            for r in nodes:
                if id(r) in connected:
                    continue
                if rides_border(x1, y1, x2, y2, r):
                    findings.append(("ERROR", "border-riding segment",
                                     "%s: segment (%.0f,%.0f)->(%.0f,%.0f) runs "
                                     "on the border of %s"
                                     % (label, x1, y1, x2, y2, pos(r)), None))
                elif seg_hits_rect_interior(x1, y1, x2, y2, r):
                    level = "WARN" if dashed else "ERROR"
                    findings.append((level, "connector through node",
                                     "%s: segment (%.0f,%.0f)->(%.0f,%.0f) crosses "
                                     "%s%s" % (label, x1, y1, x2, y2, pos(r),
                                               " (dashed transit)" if dashed
                                               else ""), None))

    # ---- CJK font-size floor
    for elem, tx, ty, ok in flat:
        if not ok or strip_ns(elem.tag) not in ("text", "tspan"):
            continue
        content = "".join(elem.itertext())
        if not CJK_RE.search(content or ""):
            continue
        size = None
        if elem.get("font-size"):
            size = num(elem.get("font-size"), None)
        elif "font-size" in (elem.get("style") or ""):
            m = re.search(r"font-size\s*:\s*([-\d.]+)", elem.get("style"))
            size = float(m.group(1)) if m else None
        else:
            tokens = class_tokens(elem)
            best = None
            for cls in tokens:
                if "font-size" in class_props.get(cls, {}):
                    best = num(class_props[cls]["font-size"], None)
            if best is None and "font-size" in text_default:
                best = num(text_default["font-size"], None)
            size = best
        if size is not None and size < 12:
            snippet = content.strip()[:18]
            findings.append(("WARN", "CJK font too small",
                             "text %r at %gpx (<12px floor)" % (snippet, size),
                             None))

    if skipped_unsupported:
        findings.append(("WARN", "unsupported transform",
                        "some elements use scale/rotate/matrix; their geometry "
                        "was skipped", None))

    if strict:
        findings = [("ERROR", k, m, e) if lvl == "WARN" else (lvl, k, m, e)
                    for lvl, k, m, e in findings]
    return findings, False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--force", action="store_true",
                    help="run on generated (graphviz/matplotlib) SVGs too")
    ap.add_argument("--conn-class", default="",
                    help="extra comma-separated class tokens marking connectors")
    args = ap.parse_args()

    conn_tokens = set(DEFAULT_CONN_TOKENS)
    if args.conn_class:
        conn_tokens |= {t.strip() for t in args.conn_class.split(",") if t.strip()}

    total_err = total_warn = 0
    results = {}
    for path in args.files:
        try:
            findings, skipped = check_file(path, conn_tokens, args.strict, args.force)
        except ET.ParseError as exc:
            findings, skipped = [("ERROR", "parse error", str(exc), None)], False
        results[path] = {"skipped": skipped, "findings": [
            {"level": lvl, "check": kind, "message": msg}
            for lvl, kind, msg, _ in findings]}
        errs = [f for f in findings if f[0] == "ERROR"]
        warns = [f for f in findings if f[0] == "WARN"]
        total_err += len(errs)
        total_warn += len(warns)
        if args.json:
            continue
        if skipped:
            print("%s: generated SVG (graphviz/matplotlib) — geometry check "
                  "skipped (use --force to override)" % path)
            continue
        if not findings:
            print("%s: OK (no geometry findings)" % path)
            continue
        print("%s:" % path)
        for lvl, kind, msg, _ in findings:
            print("  [%s] %s: %s" % (lvl, kind, msg))

    if args.json:
        print(json.dumps({"files": results, "errors": total_err,
                          "warnings": total_warn}, ensure_ascii=False, indent=2))
    else:
        print("\nsummary: %d error(s), %d warning(s)" % (total_err, total_warn))
    return 1 if total_err else 0


if __name__ == "__main__":
    sys.exit(main())
