"""Generate the .nav-fern watermark tile: one horizontal arching fern frond.

One long frond per tile (168x72), stem gently arching left-to-right, many
paired lanceolate leaflets with center veins, tapering toward the tip.
Everything stays inside the tile with margins so the repeat stays seamless.
Outputs the CSS background-image data URI + background-size lines.
"""
import math
from urllib.parse import quote

W, H = 168, 72
MARGIN = 7

# Stem: cubic bezier from base (left) to tip (right), gently arching up.
P0 = (14.0, 56.0)
P1 = (62.0, 54.0)
P2 = (108.0, 30.0)
P3 = (156.0, 26.0)


def bez(t):
    x = (1 - t) ** 3 * P0[0] + 3 * (1 - t) ** 2 * t * P1[0] + 3 * (1 - t) * t ** 2 * P2[0] + t ** 3 * P3[0]
    y = (1 - t) ** 3 * P0[1] + 3 * (1 - t) ** 2 * t * P1[1] + 3 * (1 - t) * t ** 2 * P2[1] + t ** 3 * P3[1]
    return (x, y)


def bez_tangent(t):
    dx = 3 * (1 - t) ** 2 * (P1[0] - P0[0]) + 6 * (1 - t) * t * (P2[0] - P1[0]) + 3 * t ** 2 * (P3[0] - P2[0])
    dy = 3 * (1 - t) ** 2 * (P1[1] - P0[1]) + 6 * (1 - t) * t * (P2[1] - P1[1]) + 3 * t ** 2 * (P3[1] - P2[1])
    n = math.hypot(dx, dy)
    return (dx / n, dy / n)


def fmt(v):
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


N_PAIRS = 14
LEAF_BASE = 15.0   # longest leaflet length (near base)
LEAF_TIP = 4.5     # shortest leaflet length (near tip)
TILT = math.radians(24)  # leaflets tilt toward the frond tip

paths = []

# Stem
paths.append(
    f"M{fmt(P0[0])} {fmt(P0[1])} "
    f"C{fmt(P1[0])} {fmt(P1[1])} {fmt(P2[0])} {fmt(P2[1])} {fmt(P3[0])} {fmt(P3[1])}"
)

# Small curled crozier hint at the frond tip
tx, ty = bez(1.0)
tan = bez_tangent(1.0)
ang = math.atan2(tan[1], tan[0]) + math.radians(150)
curl_r = 3.0
paths.append(
    f"M{fmt(tx)} {fmt(ty)} q{fmt(math.cos(ang) * curl_r)} {fmt(math.sin(ang) * curl_r)} "
    f"{fmt(math.cos(ang + 1.2) * curl_r)} {fmt(math.sin(ang + 1.2) * curl_r)}"
)

cos_tilt, sin_tilt = math.cos(TILT), math.sin(TILT)
for i in range(N_PAIRS):
    t = 0.045 + (0.90 - 0.045) * i / (N_PAIRS - 1)
    px, py = bez(t)
    tx_, ty_ = bez_tangent(t)
    # taper: longest near base, shrinking toward tip
    L = LEAF_BASE + (LEAF_TIP - LEAF_BASE) * (t / 0.90)
    for side in (1, -1):
        # outward normal, tilted toward the tip
        nx, ny = (-ty_ * side, tx_ * side)
        dx = nx * cos_tilt + tx_ * sin_tilt
        dy = ny * cos_tilt + ty_ * sin_tilt
        n = math.hypot(dx, dy)
        dx, dy = dx / n, dy / n
        # keep the tip inside the tile margins: shrink if needed
        tipx, tipy = px + dx * L, py + dy * L
        over = max(
            MARGIN - tipx, tipx - (W - MARGIN),
            MARGIN - tipy, tipy - (H - MARGIN), 0.0,
        )
        L2 = max(L - over - 1.0, 2.5) if over > 0 else L
        tipx, tipy = px + dx * L2, py + dy * L2
        w = L2 * 0.36  # half-width of the blade
        # blade: two quadratics base->tip->base, controls offset by half-width at mid-blade
        mx, my = px + dx * L2 * 0.52, py + dy * L2 * 0.52
        wx, wy = -dy * w, dx * w
        paths.append(
            f"M{fmt(px)} {fmt(py)} "
            f"Q{fmt(mx + wx)} {fmt(my + wy)} {fmt(tipx)} {fmt(tipy)} "
            f"Q{fmt(mx - wx)} {fmt(my - wy)} {fmt(px)} {fmt(py)} Z"
        )
        # center vein
        paths.append(f"M{fmt(px)} {fmt(py)} L{fmt(tipx)} {fmt(tipy)}")

path_els = "".join(f"<path d='{p}'/>" for p in paths)
svg = (
    f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
    f"viewBox='0 0 {W} {H}'><g fill='none' stroke='#a4c09d' stroke-opacity='0.10' "
    f"stroke-width='1.4' stroke-linecap='round'>"
    f"{path_els}</g></svg>"
)
uri = "data:image/svg+xml," + quote(svg, safe="()*,;:@/?~!$&'")

print(f"paths: {len(paths)}")
print("---- raw svg (for preview) ----")
print(f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>"
      f"<rect width='{W}' height='{H}' fill='#1b2a4a'/>"
      f"<g fill='none' stroke='#a4c09d' stroke-opacity='0.9' stroke-width='1.4' stroke-linecap='round'>"
      f"{path_els}</g></svg>")
print("---- css ----")
print(".nav-fern {")
print(f"  background-image: url(\"{uri}\");")
print(f"  background-size: {W}px {H}px;")
print("}")
