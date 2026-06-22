#!/usr/bin/env python3
"""
calc_png.py — translate the baked-in JP text on the themed-calculator button PNGs
(members of app/calc/data.pak: the 電卓/単位換算 mode tabs, 変換/コピー, 税+/税-, ページ数).

The calc's button labels are rasterised into the PNGs (not drawn at runtime), so they can't
be string-patched. `retext()` erases the JP glyphs by reconstructing the button background
per-row (median of the non-text pixels in each row — handles the smooth gradients) and draws
an English label in MS PGothic (the app's own font → consistent look) over it.

We NEVER ship a SYGNAS PNG: this runs against the user's OWN extracted data.pak at build time
(driven by build_patch's `[[pak]]` `gen` members) and emits a delta only. Needs pillow (flake)
and, for the faithful font, the builder-supplied out/font/msgothic.ttc (else falls back to a
sans on PATH, logged). PIL is imported lazily by the caller.
"""
import os
from PIL import Image, ImageDraw, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONT_CACHE = {}


def resolve_font(size, index=1):
    """MS PGothic (msgothic.ttc index 1) if the builder supplied it; else a sans fallback.
    Returns (font, name) so the caller can log which was used."""
    ttc = os.path.join(REPO, 'out', 'font', 'msgothic.ttc')
    key = (size, index)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    if os.path.exists(ttc):
        try:
            f = (ImageFont.truetype(ttc, size, index=index), 'MS PGothic')
            _FONT_CACHE[key] = f
            return f
        except Exception:
            pass
    for cand in ('DejaVuSans.ttf', 'LiberationSans-Regular.ttf', 'FreeSans.ttf'):
        try:
            f = (ImageFont.truetype(cand, size), cand)
            _FONT_CACHE[key] = f
            return f
        except Exception:
            continue
    f = (ImageFont.load_default(), 'PIL-default')
    _FONT_CACHE[key] = f
    return f


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def sample_text_color(im, box, text_is_dark):
    """The dominant glyph colour inside `box`: the darkest (text_is_dark) / brightest pixels."""
    px = im.load()
    pts = [px[x, y] for y in range(box[1], box[3]) for x in range(box[0], box[2])]
    pts.sort(key=_lum, reverse=not text_is_dark)
    core = pts[: max(4, len(pts) // 12)]                  # the extreme ~8%
    return tuple(int(sum(c[k] for c in core) / len(core)) for k in range(3)) + (255,)


def _erase(im, box, text_is_dark):
    """Reconstruct the background under the text: per row, fill with the median of the pixels
    that are NOT the text (brighter than mid for dark text; darker than mid for light text)."""
    px = im.load()
    for y in range(box[1], box[3]):
        row = [px[x, y] for x in range(box[0], box[2])]
        ls = [_lum(c) for c in row]
        thr = (min(ls) + max(ls)) / 2
        bg = [c for c, l in zip(row, ls) if (l > thr if text_is_dark else l < thr)]
        if len(bg) < 2:
            continue
        med = tuple(sorted(c[k] for c in bg)[len(bg) // 2] for k in range(len(bg[0])))
        for x in range(box[0], box[2]):
            px[x, y] = med


def _render_label(text, size, color, stroke, S=4):
    """Render `text` SUPERSAMPLED (at size*S) onto a tight transparent layer, then downscale by S
    with Lanczos. Supersampling preserves the font's true advance widths (so thin glyphs like 'l'
    don't collide with their neighbour the way 12px hinting makes them) and antialiases cleanly.
    Returns (layer, (w, h))."""
    font, _ = resolve_font(size * S)
    probe = ImageDraw.Draw(Image.new('RGBA', (4, 4)))
    l, t, r, b = probe.textbbox((0, 0), text, font=font, stroke_width=stroke * S)
    big = Image.new('RGBA', (r - l + 2 * S, b - t + 2 * S), (0, 0, 0, 0))
    ImageDraw.Draw(big).text((-l + S, -t + S), text, font=font, fill=color,
                             stroke_width=stroke * S, stroke_fill=color)
    w, h = max(1, round(big.width / S)), max(1, round(big.height / S))
    return big.resize((w, h), Image.LANCZOS), (w, h)


def retext(im, box, text, size, text_is_dark, color=None, stroke=0, fit=True, dx=0, dy=0):
    """Erase the JP text in `box` (x0,y0,x1,y1) and draw `text` centered in MS PGothic, rendered
    supersampled. `color` defaults to the sampled glyph colour; `stroke` fakes bold; `fit` shrinks
    the font until the label fits the box width; `dx/dy` nudge the final placement."""
    if color is None:
        color = sample_text_color(im, box, text_is_dark)
    _erase(im, box, text_is_dark)
    bw = box[2] - box[0]
    layer, (w, h) = _render_label(text, size, color, stroke)
    while fit and size > 6 and w > bw:
        size -= 1
        layer, (w, h) = _render_label(text, size, color, stroke)
    bx = box[0] + (bw - w) // 2 + dx
    by = box[1] + ((box[3] - box[1]) - h) // 2 + dy
    im.alpha_composite(layer, (max(0, bx), max(0, by)))
    return im


# ── per-button translation spec: name -> dict(text, box, dark, size, stroke?, color?, dx/dy?)
# Boxes are the interior glyph region (inside any border). `_press` variants reuse the base
# spec (same geometry/colour role; only the source image differs).
SPECS = {
    # mode tabs (81x18, white text on a blue/green gradient) — size 12 (matches pages/Copy; owner-set)
    'btn_mode_calc':         dict(text='Calc',     box=(4, 1, 77, 17), dark=False, size=12, color=(255, 255, 255, 255)),
    'btn_mode_kansan':       dict(text='Convert',  box=(4, 1, 77, 17), dark=False, size=12, color=(255, 255, 255, 255)),
    # convert-mode action buttons (60x24, dark gothic on light-gray button)
    'conv_btn_conv':         dict(text='Convert',  box=(7, 5, 53, 20), dark=True,  size=12),
    'conv_btn_copy':         dict(text='Copy',     box=(7, 5, 53, 20), dark=True,  size=12),
    # tax in/out (30x24, blue text) — tight, so smaller
    'calc_btn_taxin':        dict(text='Tax+',     box=(3, 5, 27, 20), dark=True,  size=10),
    'calc_btn_taxout':       dict(text='Tax-',     box=(3, 5, 27, 20), dark=True,  size=10),
    # paper-count converter rows: replace ONLY "ページ数" (x14-65 / x5-56), keep " -> mm".
    # size 20 = PGothic x-height 9px == the original baked "mm" x-height (so "pages" doesn't look
    # out of place next to the tall mm; owner-matched). Comes out ~50px wide, ≈ the JP ページ数 (51px).
    'conv_btn_select_paper2mm':  dict(text='pages', box=(12, 2, 68, 22), dark=True, size=20, dy=1),
    'conv_select_type_paper2mm': dict(text='pages', box=(3, 1, 59, 19), dark=True, size=20, dy=1),
}


def variants(base):
    """The data.pak member names for a spec base: the button + its _press twin (both `.png`).
    The caller checks which actually exist in the container (selectors have no _press twin)."""
    return [base + '.png', base + '_press.png']


def generate(png_bytes, member_name):
    """Retext one button-PNG member (by its data.pak name, e.g. 'btn_mode_calc_press.png';
    `_press` reuses its base spec) and return (new_png_bytes, spec, font_name). Used by
    build_patch's `[[pak]] gen` path."""
    import io
    base = member_name[:-4] if member_name.endswith('.png') else member_name
    if base.endswith('_press'):
        base = base[:-6]
    spec = SPECS[base]
    im = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
    _, font_name = resolve_font(spec['size'])
    retext(im, spec['box'], spec['text'], spec['size'], spec['dark'],
           color=spec.get('color'), stroke=spec.get('stroke', 0),
           dx=spec.get('dx', 0), dy=spec.get('dy', 0))
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return buf.getvalue(), spec, font_name
