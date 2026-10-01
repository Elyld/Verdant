"""Generate the .nav-fern watermark scene: a wide, NON-repeating composition.

Lush redesign (v2.47.0): the old "stick figure" fronds were too skinny.
Now each side gets a layered pair -- a big bold foreground frond with wide,
veined leaflets plus a smaller, paler frond behind it for depth. Stems are
thicker, leaflets are larger with side veins, opacity is a touch stronger.
Still a watermark (sage over navy), just one with actual presence.

Builds one wide scene (1440x120): fronds sweep in from the bottom-left and
bottom-right and fade out, flowing *under* the nav words along the bottom
edge rather than sitting behind every button. Everything fades to
transparent at the scene edges so cropping never shows a hard cutoff.
Outputs the CSS background-image data URI.
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


def frond_paths(p0, p1, p2, p3, n_pairs=26, leaf_base=32.0, leaf_tip=6.0,
                tilt_deg=28.0, up_scale=0.62, width_factor=0.44,
                side_veins=True):
    """One arching frond: stem + paired wide leaflets with veins + tip curl."""
    paths = []
    paths.append(
        ("stem",
         f"M{fmt(p0[0])} {fmt(p0[1])} "
         f"C{fmt(p1[0])} {fmt(p1[1])} {fmt(p2[0])} {fmt(p2[1])} {fmt(p3[0])} {fmt(p3[1])}")
    )
    tx, ty = cubic(p0, p1, p2, p3, 1.0)
    tan = cubic_tangent(p0, p1, p2, p3, 1.0)
    ang = math.atan2(tan[1], tan[0]) + math.radians(150)
    curl_r = 4.5
    paths.append(
        ("stem",
         f"M{fmt(tx)} {fmt(ty)} q{fmt(math.cos(ang) * curl_r)} {fmt(math.sin(ang) * curl_r)} "
         f"{fmt(math.cos(ang + 1.2) * curl_r)} {fmt(math.sin(ang + 1.2) * curl_r)}")
    )
    tilt = math.radians(tilt_deg)
    cos_t, sin_t = math.cos(tilt), math.sin(tilt)
    for i in range(n_pairs):
        t = 0.04 + (0.92 - 0.04) * i / (n_pairs - 1)
        px, py = cubic(p0, p1, p2, p3, t)
        ux, uy = cubic_tangent(p0, p1, p2, p3, t)
        L = leaf_base + (leaf_tip - leaf_base) * (t / 0.92)
        for side in (1, -1):
            nx, ny = (-uy * side, ux * side)
            dx = nx * cos_t + ux * sin_t
            dy = ny * cos_t + uy * sin_t
            n = math.hypot(dx, dy) or 1.0
            dx, dy = dx / n, dy / n
            Lside = L * up_scale if dy < 0 else L  # upward leaflets stay short
            tipx, tipy = px + dx * Lside, py + dy * Lside
            w = Lside * width_factor
            mx, my = px + dx * Lside * 0.52, py + dy * Lside * 0.52
            wx, wy = -dy * w, dx * w
            # Wide lens-shaped leaflet blade.
            paths.append(
                ("leaf",
                 f"M{fmt(px)} {fmt(py)} "
                 f"Q{fmt(mx + wx)} {fmt(my + wy)} {fmt(tipx)} {fmt(tipy)} "
                 f"Q{fmt(mx - wx)} {fmt(my - wy)} {fmt(px)} {fmt(py)} Z")
            )
            # Center vein.
            paths.append(("vein", f"M{fmt(px)} {fmt(py)} L{fmt(tipx)} {fmt(tipy)}"))
            # Side veins on the bigger leaflets.
            if side_veins and Lside > 15:
                for f in (0.35, 0.62):
                    vx, vy = px + dx * Lside * f, py + dy * Lside * f
                    vw = w * 0.55 * (1 - f * 0.5)
                    paths.append(
                        ("vein",
                         f"M{fmt(vx)} {fmt(vy)} "
                         f"l{fmt((-dy * 0.7 + dx * 0.35) * vw)} {fmt((dx * 0.7 + dy * 0.35) * vw)}")
                    )
                    paths.append(
                        ("vein",
                         f"M{fmt(vx)} {fmt(vy)} "
                         f"l{fmt((dy * 0.7 + dx * 0.35) * vw)} {fmt((-dx * 0.7 + dy * 0.35) * vw)}")
                    )
    return paths


# One dramatic frond per side: rises from the bottom corner, arches inward,
# tips stop before the center (no crossing).
# (Compositions live under __main__ so gen_fern_hero.py can reuse the builders.)


def fade(id_, color, peak):
    return (
        f"<linearGradient id='{id_}' gradientUnits='userSpaceOnUse' "
        f"x1='0' y1='0' x2='{W}' y2='0'>"
        f"<stop offset='0' stop-color='{color}' stop-opacity='0'/>"
        f"<stop offset='0.10' stop-color='{color}' stop-opacity='{peak}'/>"
        f"<stop offset='0.5' stop-color='{color}' stop-opacity='{peak}'/>"
        f"<stop offset='0.90' stop-color='{color}' stop-opacity='{peak}'/>"
        f"<stop offset='1' stop-color='{color}' stop-opacity='0'/>"
        f"</linearGradient>"
    )


def group(paths, grad_id, stem_w):
    stems = "".join(f"<path d='{d}'/>" for kind, d in paths if kind == "stem")
    leaves = "".join(f"<path d='{d}'/>" for kind, d in paths if kind == "leaf")
    veins = "".join(f"<path d='{d}'/>" for kind, d in paths if kind == "vein")
    return (
        f"<g stroke-linecap='round'>"
        # Stems: gradient stroke.
        f"<g fill='none' stroke='url(#{grad_id})' stroke-width='{stem_w}'>{stems}</g>"
        # Leaflets: FILLED with the gradient (this is what makes them lush
        # instead of stick-figure outlines), thin gradient edge for crispness.
        f"<g fill='url(#{grad_id})' fill-opacity='0.95' "
        f"stroke='url(#{grad_id})' stroke-width='1'>{leaves}</g>"
        # Veins: carved in dark navy at low opacity for leaf detail.
        f"<g fill='none' stroke='#14263f' stroke-opacity='0.38' "
        f"stroke-width='1.1'>{veins}</g>"
        f"</g>"
    )


def main():
    fore_left = frond_paths((40, 118), (250, 110), (480, 60), (620, 30),
                            n_pairs=20, leaf_base=46.0, leaf_tip=5.0,
                            tilt_deg=32.0, up_scale=0.70,
                            width_factor=0.36, side_veins=True)
    fore_right = frond_paths((1400, 118), (1190, 110), (960, 60), (820, 30),
                             n_pairs=20, leaf_base=46.0, leaf_tip=5.0,
                             tilt_deg=32.0, up_scale=0.70,
                             width_factor=0.36, side_veins=True)

    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
        f"viewBox='0 0 {W} {H}'>"
        f"<defs>{fade('fadeFore', '#a4c09d', 0.20)}</defs>"
        f"{group(fore_left, 'fadeFore', 3.4)}"
        f"{group(fore_right, 'fadeFore', 3.4)}"
        f"</svg>"
    )
    uri = "data:image/svg+xml," + quote(svg, safe="()*,;:@/?~!$&'")

    n_paths = sum(len(p) for p in (fore_left, fore_right))
    print(f"paths: {n_paths}; uri chars: {len(uri)}")
    print("---- preview svg ----")
    print(svg.replace(
        "viewBox='0 0 1440 120'",
        "viewBox='0 0 1440 120' style='background:#1b2a4a;display:block'"))
    print("---- css ----")
    print(".nav-fern {")
    print(f"  background-image: url(\"{uri}\");")
    print("  background-repeat: no-repeat;")
    print("  background-size: cover;")
    print("  background-position: bottom center;")
    print("}")


if __name__ == "__main__":
    main()
