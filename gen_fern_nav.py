"""Generate the .nav-fern watermark scene: a wide, NON-repeating composition.

Instead of a tiled frond (which reads as a weird repeating pattern), this
builds one wide scene (1440x120): two long arching fronds that sweep in
from the bottom-left and bottom-right and fade out, flowing *under* the
nav words along the bottom edge rather than sitting behind every button.
Everything fades to transparent at the scene edges so cropping never shows
a hard cutoff. Outputs the CSS background-image data URI.
"""
import math
from urllib.parse import quote

W, H = 1440, 120


def fmt(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def cubic(p0, p1, p2, p3, t):
    x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0]
    y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t ** 2 * p2[1] + t ** 3 * p3[1]
    return (x, y)


def cubic_tangent(p0, p1, p2, p3, t):
    dx = 3 * (1 - t) ** 2 * (p1[0] - p0[0]) + 6 * (1 - t) * t * (p2[0] - p1[0]) + 3 * t ** 2 * (p3[0] - p2[0])
    dy = 3 * (1 - t) ** 2 * (p1[1] - p0[1]) + 6 * (1 - t) * t * (p2[1] - p1[1]) + 3 * t ** 2 * (p3[1] - p2[1])
    n = math.hypot(dx, dy) or 1.0
    return (dx / n, dy / n)


def frond_paths(p0, p1, p2, p3, n_pairs=16, leaf_base=16.0, leaf_tip=5.0,
                tilt_deg=24.0, up_scale=0.55):
    """One arching frond: stem + paired lanceolate leaflets + tip curl."""
    paths = []
    paths.append(
        f"M{fmt(p0[0])} {fmt(p0[1])} "
        f"C{fmt(p1[0])} {fmt(p1[1])} {fmt(p2[0])} {fmt(p2[1])} {fmt(p3[0])} {fmt(p3[1])}"
    )
    tx, ty = cubic(p0, p1, p2, p3, 1.0)
    tan = cubic_tangent(p0, p1, p2, p3, 1.0)
    ang = math.atan2(tan[1], tan[0]) + math.radians(150)
    curl_r = 3.2
    paths.append(
        f"M{fmt(tx)} {fmt(ty)} q{fmt(math.cos(ang) * curl_r)} {fmt(math.sin(ang) * curl_r)} "
        f"{fmt(math.cos(ang + 1.2) * curl_r)} {fmt(math.sin(ang + 1.2) * curl_r)}"
    )
    tilt = math.radians(tilt_deg)
    cos_t, sin_t = math.cos(tilt), math.sin(tilt)
    for i in range(n_pairs):
        t = 0.05 + (0.90 - 0.05) * i / (n_pairs - 1)
        px, py = cubic(p0, p1, p2, p3, t)
        ux, uy = cubic_tangent(p0, p1, p2, p3, t)
        L = leaf_base + (leaf_tip - leaf_base) * (t / 0.90)
        for side in (1, -1):
            nx, ny = (-uy * side, ux * side)
            dx = nx * cos_t + ux * sin_t
            dy = ny * cos_t + uy * sin_t
            n = math.hypot(dx, dy) or 1.0
            dx, dy = dx / n, dy / n
            Lside = L * up_scale if dy < 0 else L  # upward leaflets stay short
            tipx, tipy = px + dx * Lside, py + dy * Lside
            w = Lside * 0.36
            mx, my = px + dx * Lside * 0.52, py + dy * Lside * 0.52
            wx, wy = -dy * w, dx * w
            paths.append(
                f"M{fmt(px)} {fmt(py)} "
                f"Q{fmt(mx + wx)} {fmt(my + wy)} {fmt(tipx)} {fmt(tipy)} "
                f"Q{fmt(mx - wx)} {fmt(my - wy)} {fmt(px)} {fmt(py)} Z"
            )
            paths.append(f"M{fmt(px)} {fmt(py)} L{fmt(tipx)} {fmt(tipy)}")
    return paths


# Two fronds sweeping along the bottom edge, tips rising toward the middle.
# Left frond: enters bottom-left, arches gently, tip curls up-right.
left = frond_paths(
    (30, 100), (320, 98), (580, 92), (800, 88),
    n_pairs=19, leaf_base=19.0, leaf_tip=5.0,
)
# Right frond: mirror sweep from bottom-right, slightly smaller and sparser.
right = frond_paths(
    (1410, 100), (1140, 98), (920, 94), (720, 90),
    n_pairs=16, leaf_base=16.0, leaf_tip=4.5,
)

left_els = "".join(f"<path d='{p}'/>" for p in left)
right_els = "".join(f"<path d='{p}'/>" for p in right)

# Horizontal fade: transparent at both scene edges so any crop is invisible.
svg = (
    f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
    f"viewBox='0 0 {W} {H}'>"
    f"<defs><linearGradient id='fade' gradientUnits='userSpaceOnUse' "
    f"x1='0' y1='0' x2='{W}' y2='0'>"
    f"<stop offset='0' stop-color='#a4c09d' stop-opacity='0'/>"
    f"<stop offset='0.10' stop-color='#a4c09d' stop-opacity='0.11'/>"
    f"<stop offset='0.5' stop-color='#a4c09d' stop-opacity='0.11'/>"
    f"<stop offset='0.90' stop-color='#a4c09d' stop-opacity='0.11'/>"
    f"<stop offset='1' stop-color='#a4c09d' stop-opacity='0'/>"
    f"</linearGradient></defs>"
    f"<g fill='none' stroke='url(#fade)' stroke-width='1.5' stroke-linecap='round'>"
    f"{left_els}{right_els}</g></svg>"
)
uri = "data:image/svg+xml," + quote(svg, safe="()*,;:@/?~!$&'")

print(f"paths: {len(left) + len(right)}; uri chars: {len(uri)}")
print("---- preview svg ----")
print(svg.replace("width='1440'", "width='720'").replace(
    "<svg ", "<svg ", 1).replace(
    "viewBox='0 0 1440 120'",
    "viewBox='0 0 1440 120' style='background:#1b2a4a;display:block'"))
print("---- css ----")
print(".nav-fern {")
print(f"  background-image: url(\"{uri}\");")
print("  background-repeat: no-repeat;")
print("  background-size: cover;")
print("  background-position: bottom center;")
print("}")
