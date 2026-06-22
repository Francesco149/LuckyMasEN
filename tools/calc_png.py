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
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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


def _render_label(text, size, color, stroke, S=4, stroke_color=None,
                  glow=0, glow_color=None, blur=0, bold=0, fill_grad=None):
    """Render `text` SUPERSAMPLED (at size*S) onto a tight transparent layer, then downscale by S
    with Lanczos. Supersampling preserves the font's true advance widths (so thin glyphs like 'l'
    don't collide with their neighbour the way 12px hinting makes them) and antialiases cleanly.
    Layers (back->front): `glow`/`glow_color`/`blur` = a blurred halo; `stroke`/`stroke_color` = an
    outline of that thickness around the fill; `bold` = a self-stroke that fattens the FILL (faux-
    bold, inside the outline). The wallpaper headers use all three (pink glow / white border / bolder
    magenta fill). All sizes are pre-downscale (final) px. Returns (layer, (w, h))."""
    font, _ = resolve_font(size * S)
    probe = ImageDraw.Draw(Image.new('RGBA', (4, 4)))
    l, t, r, b = probe.textbbox((0, 0), text, font=font)            # glyph bbox, no stroke
    pad = int(round((max(stroke + bold, glow) + blur + 1) * S))
    W, H = (r - l) + 2 * pad, (b - t) + 2 * pad
    ox, oy = pad - l, pad - t
    big = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    if glow and glow_color:
        gl = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(gl).text((ox, oy), text, font=font, fill=glow_color,
                                stroke_width=glow * S, stroke_fill=glow_color)
        if blur:
            gl = gl.filter(ImageFilter.GaussianBlur(blur * S))
        big.alpha_composite(gl)
    d = ImageDraw.Draw(big)
    if stroke_color and stroke > 0:                                 # outline silhouette around the (bolded) fill
        d.text((ox, oy), text, font=font, fill=stroke_color,
               stroke_width=round((stroke + bold) * S), stroke_fill=stroke_color)
    if fill_grad:                                                   # vertical gradient fill (top -> bottom)
        mask = Image.new('L', (W, H), 0)
        ImageDraw.Draw(mask).text((ox, oy), text, font=font, fill=255,
                                  stroke_width=round(bold * S), stroke_fill=255)
        ctop, cbot = fill_grad[0], fill_grad[1]
        frac = fill_grad[2] if len(fill_grad) > 2 else 1.0          # transition completes in the top `frac`
        gtop, gspan = pad, max(1, (b - t) * frac)
        col = Image.new('RGBA', (1, H))
        for y in range(H):
            f = min(1.0, max(0.0, (y - gtop) / gspan))
            col.putpixel((0, y), tuple(round(ctop[k] + (cbot[k] - ctop[k]) * f) for k in range(4)))
        big.paste(col.resize((W, H)), (0, 0), mask)
    else:
        d.text((ox, oy), text, font=font, fill=color,               # solid fill, fattened by `bold`
               stroke_width=round(bold * S), stroke_fill=color)
    w, h = max(1, round(W / S)), max(1, round(H / S))
    return big.resize((w, h), Image.LANCZOS), (w, h)


def _erase_vinterp(im, box, top, bot):
    """Rebuild the box by vertically interpolating each column between two clean text-free rows
    (`top`/`bot`, just above/below the glyphs). Preserves a horizontal gradient and — unlike a
    per-row median — never samples the JPEG chroma fringe that haloes white-on-colour text."""
    px = im.load()
    x0, y0, x1, y1 = box
    span = (bot - top) or 1
    for x in range(x0, x1):
        ct, cb = px[x, top], px[x, bot]
        for y in range(y0, y1):
            t = (y - top) / span
            px[x, y] = tuple(round(ct[k] + (cb[k] - ct[k]) * t) for k in range(len(ct)))


def tile_erase(im, box, period, clean_start):
    """Replace `box` with the background's repeating texture (e.g. the wallpaper headers' diamonds)
    copied phase-aligned from the nearest clean region to the right (`clean_start`+): each column x
    is taken from x + period*k (smallest k landing in clean texture), so the pattern continues
    seamlessly instead of a flat fill. `period` = the horizontal repeat in px (trial-and-error)."""
    import math
    orig = im.copy()
    px, opx = im.load(), orig.load()
    x0, y0, x1, y1 = box
    for x in range(x0, x1):
        xs = x + period * max(1, math.ceil((clean_start - x) / period))
        for y in range(y0, y1):
            px[x, y] = opx[xs, y]


def retext(im, box, text, size, text_is_dark, color=None, stroke=0, fit=True, dx=0, dy=0,
           align='center', erase='rowmedian', vrows=None,
           stroke_color=None, glow=0, glow_color=None, blur=0, bold=0, fill_grad=None):
    """Erase the JP text in `box` (x0,y0,x1,y1) and draw `text` in MS PGothic, rendered supersampled.
    `color` defaults to the sampled glyph colour. `stroke`+`stroke_color` = an outline; `glow`+
    `glow_color`+`blur` = a soft halo behind (the wallpaper headers' magenta fill / white border /
    pink glow). `fit` shrinks the font until it fits the box width (center only). `align` 'center'|
    'left' (left text may extend right onto already-correct background). `erase` 'rowmedian' (per-row
    median — gradients/buttons) or 'vinterp' with `vrows=(top,bot)` (interpolate two clean rows —
    avoids the JPEG fringe on white/coloured-on-gradient headers). `dx/dy` nudge placement."""
    if color is None:
        color = sample_text_color(im, box, text_is_dark)
    if erase == 'none':                                  # caller already cleared the bg (e.g. tile_erase)
        pass
    elif erase == 'vinterp' and vrows:
        _erase_vinterp(im, box, vrows[0], vrows[1])
    else:
        _erase(im, box, text_is_dark)
    bw = box[2] - box[0]
    kw = dict(stroke_color=stroke_color, glow=glow, glow_color=glow_color, blur=blur, bold=bold,
              fill_grad=fill_grad)
    layer, (w, h) = _render_label(text, size, color, stroke, **kw)
    while fit and align == 'center' and size > 6 and w > bw:
        size -= 1
        layer, (w, h) = _render_label(text, size, color, stroke, **kw)
    bx = box[0] + dx if align == 'left' else box[0] + (bw - w) // 2 + dx
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


# ── wallpaper-picker section headers (loose img/*.jpg|.gif, driven by build_patch's [[img_text]]) ──
# The h2 bars are a magenta fill + white border + soft pink glow title (sampled from the JP original)
# on a green diamond-textured gradient; the JP run is erased by TILING the diamond pattern (period ~31)
# so the texture continues, then EN is drawn left-aligned. monitor_size is olive text on transparency.
WP_HEADERS = {
    # fill = a vertical gradient: a BRIGHT pink highlight in the top 1/3 (frac=0.33) fading to the
    # darker magenta body (stops sampled from the JP original); white border; the outer glow reuses
    # the gradient's bright stop (a pale glow washes to grey over the green).
    'h2_howto.jpg': dict(text='How to set your wallpaper', box=(6, 2, 180, 35), size=22, align='left', dx=4,
                         color=(228, 3, 107, 255), fill_grad=((250, 120, 190, 255), (200, 0, 96, 255), 0.33),
                         stroke=2, stroke_color=(255, 255, 255, 255), bold=1,
                         glow=3, glow_color=(250, 120, 190, 255), blur=2,
                         erase='tile', tile_box=(6, 0, 180, 37), tile_period=31, tile_clean=181),
    'h2_list.jpg':  dict(text='Wallpaper list', box=(6, 2, 112, 35), size=22, align='left', dx=4,
                         color=(228, 3, 107, 255), fill_grad=((250, 120, 190, 255), (200, 0, 96, 255), 0.33),
                         stroke=2, stroke_color=(255, 255, 255, 255), bold=1,
                         glow=3, glow_color=(250, 120, 190, 255), blur=2,
                         erase='tile', tile_box=(6, 0, 112, 37), tile_period=31, tile_clean=110),
    'monitor_size.gif': dict(text='Your monitor size', box=(2, 1, 201, 21), size=16, dark=True,
                             color=(136, 165, 0, 255), align='center'),
}


def apply_header(im, member_name):
    """Translate one wallpaper-header image in place per WP_HEADERS (tile-erase the textured JP run if
    asked, then draw EN). Returns the spec (for logging)."""
    spec = WP_HEADERS[member_name]
    if spec.get('erase') == 'tile':
        tile_erase(im, spec['tile_box'], spec['tile_period'], spec['tile_clean'])
    retext(im, spec['box'], spec['text'], spec['size'], spec.get('dark', False),
           color=spec.get('color'), stroke=spec.get('stroke', 0), stroke_color=spec.get('stroke_color'),
           glow=spec.get('glow', 0), glow_color=spec.get('glow_color'), blur=spec.get('blur', 0),
           bold=spec.get('bold', 0), fill_grad=spec.get('fill_grad'),
           align=spec.get('align', 'center'), dx=spec.get('dx', 0), dy=spec.get('dy', 0),
           erase='none' if spec.get('erase') == 'tile' else spec.get('erase', 'rowmedian'),
           vrows=spec.get('vrows'), fit=(spec.get('align') != 'left'))
    return spec
