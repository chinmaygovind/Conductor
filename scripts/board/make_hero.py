#!/usr/bin/env python3
"""Build `static/images/board-hero.svg`, the picture behind the landing and
login pages.

It is `board.svg` - our own traced coastline - with the whole route network laid
over it and a few trains running on it. Nothing here is authored twice: the
segment positions come from `route_segments.py` and the colours from
`game_data_na.py`, the same two files the game itself draws from, so a route
that moves on the board moves here on the next run.

Why it exists at all: the backgrounds used to be a scan of the retail board,
which was deleted in Sep 2026 (see CLAUDE.md, "Board art"). `board.svg` on its
own is a bare landmass - under the page's dark overlay it reads as a shapeless
blob, because everything that made the scan legible at 25% opacity was the
routes and the cities. This puts that information back in artwork we own.

Run it after changing `route_segments.py`, `game_data_na.py` or `board.svg`:

    python3 scripts/board/make_hero.py

It is deterministic - the trains are placed from a fixed list of route ids, not
at random - so re-running it with nothing changed rewrites the same bytes.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from game_data_na import ROUTES, CARD_COLOR_HEX, BOARD_WIDTH, BOARD_HEIGHT
from route_segments import ROUTE_SEGMENTS

BOARD_SVG = os.path.join(ROOT, "static", "images", "board.svg")
OUT_SVG = os.path.join(ROOT, "static", "images", "board-hero.svg")

# The game's own segment box (game.js: segW/segH). Matching it is the point -
# this should look like the board you are about to play on, not like a diagram
# of it.
SEG_W, SEG_H = 30, 8

# Grey is not a card colour, so it has no entry in CARD_COLOR_HEX; the game
# substitutes this exact value when it draws an unclaimed grey route.
GREY = "#9ca3af"

# Which routes carry a train. Chosen for two things and neither is a rule the
# code could apply: they are long runs that read as a journey at a glance, and
# they sit around the edges of the map. The middle is deliberately empty -
# the wordmark and the login panel cover the centre of the board at every
# window size, so a train placed there is both hidden and fighting the type.
#
#     96 Seattle-Calgary        31 Calgary-Winnipeg     92 Montreal-Sault
#     7  Portland-San Francisco 36 Duluth-Toronto
#     16 Los Angeles-El Paso    53 El Paso-Houston      73 Atlanta-Miami
#
# A train needs at least TRAIN_LEN segments to sit on; anything here that is
# too short is reported and skipped rather than silently drawn short.
TRAIN_ROUTES = [96, 31, 92, 36, 7, 16, 53, 73]
TRAIN_LEN = 3          # locomotive + 2 carriages
TRAIN_BODY = "#2b2620"  # near-black, so a train reads as a solid on any colour
TRAIN_TRIM = "#e8c97a"  # --gold-light, the site's own


def board_inner():
    """The contents of board.svg, minus its <svg> wrapper and XML prolog."""
    with open(BOARD_SVG, encoding="utf-8") as fh:
        svg = fh.read()
    body = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")]
    return body.strip()


def route_colour(route):
    if route["color"] == "gray":
        return GREY
    return CARD_COLOR_HEX.get(route["color"], "#888888")


def segments_svg():
    """Every route, as the game draws it: a rounded box per car, rotated."""
    out = []
    for route in ROUTES:
        segs = ROUTE_SEGMENTS.get(route["id"]) or []
        fill = route_colour(route)
        for cx, cy, angle in segs:
            out.append(
                '<rect x="%.1f" y="%.1f" width="%d" height="%d" rx="2" '
                'transform="rotate(%.1f %.1f %.1f)" fill="%s" '
                'fill-opacity="0.85" stroke="rgba(255,255,255,0.35)" '
                'stroke-width="1"/>'
                % (cx - SEG_W / 2.0, cy - SEG_H / 2.0, SEG_W, SEG_H,
                   angle, cx, cy, fill)
            )
    return out


def train_svg(cx, cy, angle, loco):
    """One vehicle, drawn pointing +x in a 26x13 box around (0,0) and then
    rotated onto the route. A locomotive gets a chimney, a cab and a cowcatcher;
    a carriage is a box with windows. Both are deliberately a couple of units
    wider than a segment so a train sits *on* the route rather than in it."""
    g = ['<g transform="translate(%.1f %.1f) rotate(%.1f)">' % (cx, cy, angle)]
    if loco:
        g.append('<path d="M9 4 L12 4 L13 -1 L9 -1 Z" fill="%s"/>' % TRAIN_BODY)
        g.append('<rect x="-11" y="-4.5" width="17" height="9" rx="2" fill="%s"/>' % TRAIN_BODY)
        g.append('<rect x="-11" y="-7.5" width="7" height="5" rx="1.5" fill="%s"/>' % TRAIN_BODY)
        g.append('<rect x="3" y="-8" width="3.5" height="4" rx="1" fill="%s"/>' % TRAIN_BODY)
        g.append('<rect x="-9.5" y="-6.5" width="4" height="3" rx="0.8" fill="%s"/>' % TRAIN_TRIM)
        g.append('<circle cx="-6" cy="5" r="2.4" fill="%s"/>' % TRAIN_BODY)
        g.append('<circle cx="2" cy="5" r="2.4" fill="%s"/>' % TRAIN_BODY)
    else:
        g.append('<rect x="-9" y="-4" width="18" height="8" rx="2" fill="%s"/>' % TRAIN_BODY)
        g.append('<rect x="-5.5" y="-2" width="3" height="3" rx="0.6" fill="%s"/>' % TRAIN_TRIM)
        g.append('<rect x="-0.5" y="-2" width="3" height="3" rx="0.6" fill="%s"/>' % TRAIN_TRIM)
        g.append('<rect x="4.5" y="-2" width="3" height="3" rx="0.6" fill="%s"/>' % TRAIN_TRIM)
        g.append('<circle cx="-5" cy="4.5" r="2" fill="%s"/>' % TRAIN_BODY)
        g.append('<circle cx="5" cy="4.5" r="2" fill="%s"/>' % TRAIN_BODY)
    g.append("</g>")
    return "".join(g)


def trains_svg():
    out, placed, skipped = [], 0, []
    for rid in TRAIN_ROUTES:
        segs = ROUTE_SEGMENTS.get(rid) or []
        if len(segs) < TRAIN_LEN:
            skipped.append(rid)
            continue
        # The locomotive takes the last segment so the train reads as heading
        # towards the far city, and the carriages follow it back down the route.
        run = segs[-TRAIN_LEN:]
        for i, (cx, cy, angle) in enumerate(reversed(run)):
            out.append(train_svg(cx, cy, angle, loco=(i == 0)))
        placed += 1
    if skipped:
        print("  ! no train on route(s) %s - fewer than %d segments"
              % (", ".join(str(s) for s in skipped), TRAIN_LEN))
    return out, placed


def main():
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!-- GENERATED by scripts/board/make_hero.py - do not edit by hand. -->',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
        'width="%d" height="%d">' % (BOARD_WIDTH, BOARD_HEIGHT,
                                     BOARD_WIDTH, BOARD_HEIGHT),
        board_inner(),
        '<g id="routes">',
    ]
    segs = segments_svg()
    parts.extend(segs)
    parts.append("</g>")
    parts.append('<g id="trains">')
    trains, placed = trains_svg()
    parts.extend(trains)
    parts.append("</g>")
    parts.append("</svg>")

    with open(OUT_SVG, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts) + "\n")

    size = os.path.getsize(OUT_SVG)
    print("wrote %s" % os.path.relpath(OUT_SVG, ROOT))
    print("  %d routes, %d segments, %d trains, %.1f kB"
          % (len(ROUTES), len(segs), placed, size / 1000.0))


if __name__ == "__main__":
    main()
