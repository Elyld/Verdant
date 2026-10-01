#!/usr/bin/env python3
"""Generate the fern hero banner (app/static/img/fern-hero.svg).

1440x300. Fronds sweep in from the RIGHT edge and fade toward the left,
so dashboard greeting text sits clean on the left. Deep greens
(#2e5b40 back layer, #4c7a57 fore layer) over a navy gradient.

Reuses the lush filled-leaflet builder from gen_fern_nav.py so both
artworks stay stylistically in sync.
"""
from pathlib import Path

from gen_fern_nav import frond_paths, group  # noqa

W, H = 1440, 300

BACK, FORE = "#2e5b40", "#4c7a57"
BG_TOP, BG_BOT = "#1b2e42", "#243f52"


def fade_right(id_, color, peak):
    """Horizontal fade: full opacity at the right edge, gone at the left."""
    return (
        f"<linearGradient id='{id_}' gradientUnits='userSpaceOnUse' "
        f"x1='{W}' y1='0' x2='0' y2='0'>"
        f"<stop offset='0' stop-color='{color}' stop-opacity='{peak}'/>"
        f"<stop offset='1' stop-color='{color}' stop-opacity='0'/>"
        f"</linearGradient>"
    )


def main():
    # Background layer: three long, darker fronds, bigger arcs.
    back = []
    back += frond_paths((1440, 285), (1210, 300), (980, 220), (760, 150),
                        n_pairs=22, leaf_base=52.0, leaf_tip=6.0,
                        tilt_deg=30.0, up_scale=0.70,
                        width_factor=0.38, side_veins=True)
    back += frond_paths((1440, 150), (1200, 120), (990, 130), (800, 170),
                        n_pairs=20, leaf_base=48.0, leaf_tip=5.0,
                        tilt_deg=30.0, up_scale=0.70,
                        width_factor=0.38, side_veins=True)
    back += frond_paths((1440, 30), (1220, 10), (1000, 60), (820, 120),
                        n_pairs=18, leaf_base=44.0, leaf_tip=5.0,
                        tilt_deg=30.0, up_scale=0.70,
                        width_factor=0.38, side_veins=True)

    # Foreground layer: two brighter fronds with tighter arcs.
    fore = []
    fore += frond_paths((1440, 250), (1260, 265), (1080, 190), (940, 130),
                        n_pairs=20, leaf_base=46.0, leaf_tip=5.0,
                        tilt_deg=32.0, up_scale=0.70,
                        width_factor=0.36, side_veins=True)
    fore += frond_paths((1440, 90), (1260, 70), (1090, 90), (960, 140),
                        n_pairs=18, leaf_base=42.0, leaf_tip=5.0,
                        tilt_deg=32.0, up_scale=0.70,
                        width_factor=0.36, side_veins=True)

    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
        f"viewBox='0 0 {W} {H}'>"
        f"<defs>"
        f"<linearGradient id='bgHero' x1='0' y1='0' x2='0' y2='1'>"
        f"<stop offset='0' stop-color='{BG_TOP}'/>"
        f"<stop offset='1' stop-color='{BG_BOT}'/>"
        f"</linearGradient>"
        f"{fade_right('fadeBack', BACK, 0.90)}"
        f"{fade_right('fadeFore', FORE, 1.0)}"
        f"</defs>"
        f"<rect width='{W}' height='{H}' fill='url(#bgHero)'/>"
        f"<g opacity='0.65'>{group(back, 'fadeBack', 4.0)}</g>"
        f"{group(fore, 'fadeFore', 3.4)}"
        f"</svg>"
    )

    out = Path(__file__).resolve().parent / "app" / "static" / "img" / "fern-hero.svg"
    out.write_text(svg)
    print(f"wrote {out} ({len(svg)} chars)")


if __name__ == "__main__":
    main()
