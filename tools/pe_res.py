#!/usr/bin/env python3
"""
pe_res.py — dump (and later patch) the translatable PE-resource strings in the SYGNAS
Win32 binaries: RT_MENU (4), RT_DIALOG (5), RT_STRING (6), all lang 1041 (JP).

These are the strings NOT reachable as data (the launcher's right-click menus, the per-app
item menu, dialog captions/controls, string tables) — the deferred `pe-res` translation surface.

  dump <exe>            list every menu/dialog/string entry with a stable key + the JP text
  geom <exe> [DLG...]   list RT_DIALOG control geometry (idx/class/x/y/cx/cy) for `[pe_res.layout]`

Stable keys (used later by the patch map): MENU/<resid>/<lang>#<n>, STR/<id>, DLG/<resid>#<n>.
Uses lief (in the flake). Run in `nix develop`.
"""
import sys, struct

RT_MENU, RT_DIALOG, RT_STRING = 4, 5, 6
RTN = {RT_MENU: "MENU", RT_DIALOG: "DIALOG", RT_STRING: "STRING"}


def _wsz(data, off):
    """read a NUL-terminated UTF-16LE string at off; return (text, new_off)."""
    s = []
    while off + 1 < len(data):
        ch = struct.unpack_from("<H", data, off)[0]; off += 2
        if ch == 0:
            break
        s.append(ch)
    return "".join(map(chr, s)), off


def parse_menu(data):
    """RT_MENU (standard) -> ordered list of item texts (popups + items, depth-first)."""
    out = []
    if len(data) < 4:
        return out
    ver, hdr = struct.unpack_from("<HH", data, 0)
    off = 4 + hdr

    def items(off):
        while off + 2 <= len(data):
            flags = struct.unpack_from("<H", data, off)[0]; off += 2
            popup = bool(flags & 0x0010)          # MF_POPUP
            if not popup:
                off += 2                            # skip menu id (WORD)
            text, off = _wsz(data, off)
            out.append(text)
            if popup:
                off = items(off)
            if flags & 0x0080:                      # MF_END
                break
        return off

    try:
        items(off)
    except struct.error:
        pass
    return out


def parse_stringtable(data, block_id):
    """RT_STRING block -> {string_id: text} (16 length-prefixed UTF-16 slots)."""
    out, off, idx = {}, 0, 0
    while off + 2 <= len(data) and idx < 16:
        ln = struct.unpack_from("<H", data, off)[0]; off += 2
        if ln:
            out[(block_id - 1) * 16 + idx] = data[off:off + ln * 2].decode("utf-16-le", "replace")
            off += ln * 2
        idx += 1
    return out


def _ord_or_sz(data, o):
    """sz_Or_Ord: 0xFFFF + WORD ordinal, else a NUL-terminated UTF-16 string."""
    if o + 2 > len(data):
        return ("ord", 0, o)
    if _u16r(data, o) == 0xFFFF:
        return ("ord", _u16r(data, o + 2), o + 4)
    s, o2 = _wsz(data, o)
    return ("str", s, o2)


def _u16r(d, o):
    return struct.unpack_from("<H", d, o)[0]


def _dlg_walk(data, on_title, on_ctrl_text, geom=None):
    """Walk a DLGTEMPLATE[EX], calling on_title(str)->str and on_ctrl_text(str)->str.
    Returns the rebuilt bytes (identity callbacks round-trip byte-for-byte). `geom` optionally
    overrides geometry: {control_index: {x,y,cx,cy}, 'dialog': {cx,cy}} — used to widen controls
    so longer EN labels fit the originally JP-sized layout."""
    geom = geom or {}
    out = bytearray()
    o = 0
    ex = (_u16r(data, 0) == 1 and _u16r(data, 2) == 0xFFFF)

    def emit(a, b):
        out.extend(data[a:b])

    def emit_oos(o):                                   # copy one sz_Or_Ord verbatim
        k, v, o2 = _ord_or_sz(data, o); out.extend(data[o:o2]); return o2

    def align4():
        while len(out) & 3:
            out.append(0)

    def setgeom(base, g, fields, off0):
        for j, f in enumerate(fields):
            if f in g:
                _p16(out, base + off0 + j * 2, g[f])

    style = _u32(data, 12 if ex else 0)
    cdit = _u16r(data, 16 if ex else 8)
    hdr = 26 if ex else 18
    dstart = len(out)
    emit(0, hdr); o = hdr
    if "dialog" in geom:                               # dialog cx,cy live at +22 (ex) / +14
        setgeom(dstart, geom["dialog"], ("cx", "cy"), 22 if ex else 14)
    o = emit_oos(o)                                    # menu
    o = emit_oos(o)                                    # window class
    title, o = _wsz(data, o)                           # caption (plain sz)
    out.extend(on_title(title).encode("utf-16-le") + b"\x00\x00")
    if style & 0x40:                                   # DS_SETFONT
        n = 6 if ex else 2
        emit(o, o + n); o += n
        face, o = _wsz(data, o)
        out.extend(face.encode("utf-16-le") + b"\x00\x00")
    for idx in range(cdit):
        align4()
        while o & 3:
            o += 1
        cstart = len(out)
        n = 24 if ex else 18
        emit(o, o + n); o += n
        if idx in geom:                                # control x,y,cx,cy at +12 (ex) / +8
            setgeom(cstart, geom[idx], ("x", "y", "cx", "cy"), 12 if ex else 8)
        o = emit_oos(o)                                # control class
        k, v, o = _ord_or_sz(data, o)                  # control text
        if k == "str":
            out.extend(on_ctrl_text(v).encode("utf-16-le") + b"\x00\x00")
        else:
            out.extend(struct.pack("<HH", 0xFFFF, v))
        extra = _u16r(data, o); out.extend(struct.pack("<H", extra)); o += 2
        emit(o, o + extra); o += extra
    return bytes(out)


def parse_dialog(data):
    """List the translatable strings (caption + control text) of a dialog."""
    found = []
    try:
        _dlg_walk(data, lambda t: (found.append(t) or t) if t else t,
                  lambda t: (found.append(t) or t) if t else t)
    except (struct.error, IndexError):
        pass
    return found


_ATOM = {0x80: "Button", 0x81: "Edit", 0x82: "Static", 0x83: "ListBox",
         0x84: "ScrollBar", 0x85: "ComboBox"}

def dialog_controls(data):
    """Yield each control's geometry as a dict {idx,class,text,x,y,cx,cy} for a DLGTEMPLATE[EX],
    plus a leading {idx:'dialog'} row carrying the dialog cx/cy + caption. Read-only; used by the
    `geom` CLI verb to pick control indices / current x,y,cx,cy for `[pe_res.layout.*]` overrides."""
    ex = (_u16r(data, 0) == 1 and _u16r(data, 2) == 0xFFFF)
    style = _u32(data, 12 if ex else 0)
    cdit = _u16r(data, 16 if ex else 8)
    yield {"idx": "dialog", "class": "", "x": _u16r(data, 18 if ex else 10),
           "y": _u16r(data, 20 if ex else 12), "cx": _u16r(data, 22 if ex else 14),
           "cy": _u16r(data, 24 if ex else 16), "text": ""}
    o = 26 if ex else 18
    o = _ord_or_sz(data, o)[2]                          # menu
    o = _ord_or_sz(data, o)[2]                          # window class
    _, o = _wsz(data, o)                                # caption
    if style & 0x40:                                   # DS_SETFONT
        o += 6 if ex else 2
        _, o = _wsz(data, o)                            # typeface
    for idx in range(cdit):
        while o & 3:
            o += 1
        goff = 12 if ex else 8
        x, y, cx, cy = struct.unpack_from("<hhhh", data, o + goff)
        o += 24 if ex else 18
        k, v, o = _ord_or_sz(data, o)                  # control class
        cls = _ATOM.get(v, v) if k == "ord" else v
        k2, v2, o = _ord_or_sz(data, o)                # control text
        txt = v2 if k2 == "str" else "#%d" % v2
        extra = _u16r(data, o); o += 2 + extra         # creation-data blob
        yield {"idx": idx, "class": cls, "text": txt, "x": x, "y": y, "cx": cx, "cy": cy}


def build_dialog(data, mapping, geom=None):
    """Rebuild a dialog, translating caption + control text via `mapping` and optionally
    overriding control geometry via `geom` (see _dlg_walk)."""
    hit = []

    def tr(s):
        n = mapping.get(s, s)
        if n != s:
            hit.append((s, n))
        return n

    try:
        nb = _dlg_walk(data, tr, tr, geom)
    except (struct.error, IndexError):
        return data, []
    return nb, hit


def utf16_runs(data, minlen=2):
    """crude: printable UTF-16LE runs (for DIALOG, whose structure we don't fully parse)."""
    out, i, cur = [], 0, []
    while i + 1 < len(data):
        ch = struct.unpack_from("<H", data, i)[0]; i += 2
        if 0x20 <= ch <= 0xFFFD and ch != 0xFFFF:
            cur.append(ch)
        else:
            if len(cur) >= minlen:
                out.append("".join(map(chr, cur)))
            cur = []
    if len(cur) >= minlen:
        out.append("".join(map(chr, cur)))
    return out


def build_menu(data, mapping):
    """Rebuild an RT_MENU, translating item text via `mapping` (JP str -> EN str). Lengths may
    change; the caller (lief) fixes the resource-directory size. Unmapped text is kept verbatim."""
    if len(data) < 4:
        return data, []
    ver, hdr = struct.unpack_from("<HH", data, 0)
    out = bytearray(data[:4 + hdr])
    hit = []

    def emit(off):
        while off + 2 <= len(data):
            flags = struct.unpack_from("<H", data, off)[0]; off += 2
            out.extend(struct.pack("<H", flags))
            popup = bool(flags & 0x0010)
            if not popup:
                mid = struct.unpack_from("<H", data, off)[0]; off += 2
                out.extend(struct.pack("<H", mid))
            text, off = _wsz(data, off)
            new = mapping.get(text, text)
            if new != text:
                hit.append((text, new))
            out.extend(new.encode("utf-16-le") + b"\x00\x00")
            if popup:
                off = emit(off)
            if flags & 0x0080:
                break
        return off

    emit(4 + hdr)
    return bytes(out), hit


def has_jp(s):
    """True only for actual Japanese script (kana / CJK / halfwidth-kana) — NOT every
    non-ASCII char, so legitimately-translated strings with ☆/× aren't false-flagged."""
    for c in s:
        o = ord(c)
        if (0x3040 <= o <= 0x30FF or      # hiragana + katakana
                0x3400 <= o <= 0x9FFF or  # CJK (incl. ext-A)
                0xFF61 <= o <= 0xFF9F):   # halfwidth katakana
            return True
    return False


# ── surgical PE resource patch (NO lief.write — it rebuilds the whole PE and breaks XP) ──
# We touch ONLY the RT_MENU blobs: rebuild each with EN text, place it (in-place if it fits,
# else appended into .rsrc's existing file-alignment slack), and fix just that data-entry's
# (RVA,Size) + the .rsrc VirtualSize + SizeOfImage + PE checksum. Every other byte — all the
# dialogs, imports, relocs — stays byte-identical to the working original.
def _u16(d, o): return struct.unpack_from("<H", d, o)[0]
def _u32(d, o): return struct.unpack_from("<I", d, o)[0]
def _p16(d, o, v): struct.pack_into("<H", d, o, v)
def _p32(d, o, v): struct.pack_into("<I", d, o, v)


def _pe_checksum(d, csum_off):
    save = bytes(d[csum_off:csum_off + 4])
    d[csum_off:csum_off + 4] = b"\x00\x00\x00\x00"
    s = 0
    for i in range(0, len(d) & ~1, 2):
        s += _u16(d, i)
        s = (s & 0xFFFF) + (s >> 16)
    if len(d) & 1:
        s += d[-1]; s = (s & 0xFFFF) + (s >> 16)
    s = (s & 0xFFFF) + (s >> 16)
    d[csum_off:csum_off + 4] = save
    return (s + len(d)) & 0xFFFFFFFF


def _res_leaves(d, base):
    """Walk the 3-level resource tree; yield menu-relevant leaves with the file offset of
    their IMAGE_RESOURCE_DATA_ENTRY and the (rva,size) it holds."""
    def ents(diroff):
        p = base + diroff
        n = _u16(d, p + 12) + _u16(d, p + 14)
        return [(_u32(d, p + 16 + i * 8), _u32(d, p + 16 + i * 8 + 4)) for i in range(n)]

    def name_at(off):
        p = base + off; n = _u16(d, p)
        return d[p + 2:p + 2 + n * 2].decode("utf-16-le", "replace")

    out = []
    for tname, toff in ents(0):
        tid = tname & 0x7FFFFFFF if tname & 0x80000000 else tname
        if not toff & 0x80000000:
            continue
        for nname, noff in ents(toff & 0x7FFFFFFF):
            rname = name_at(nname & 0x7FFFFFFF) if nname & 0x80000000 else nname
            if not noff & 0x80000000:
                continue
            for lname, loff in ents(noff & 0x7FFFFFFF):
                if loff & 0x80000000:
                    continue
                de = base + loff
                out.append({"type": tid, "name": rname, "lang": lname,
                            "de_off": de, "rva": _u32(d, de), "size": _u32(d, de + 4)})
    return out


def patch(inp, outp, mapping, layout=None):
    """Translate RT_MENU + RT_DIALOG strings by `mapping` (and apply per-dialog `layout`
    geometry overrides), writing `outp` with a surgical edit. `layout` =
    {dialog_name: {control_index: {x,y,cx,cy}, 'dialog': {cx,cy}}}.
    Returns {'hits':[(jp,en)...], 'remaining_jp':[...], 'grew':int}."""
    d = bytearray(open(inp, "rb").read())
    e_lfanew = _u32(d, 0x3C)
    coff = e_lfanew + 4
    opt = coff + 20
    nsec = _u16(d, coff + 2)
    sectbl = opt + _u16(d, coff + 16)
    salign = _u32(d, opt + 32)
    res_rva = _u32(d, opt + 112)                      # DataDirectory[RESOURCE].VirtualAddress

    secs = []
    for i in range(nsec):
        o = sectbl + i * 40
        secs.append({"o": o, "vsize": _u32(d, o + 8), "vaddr": _u32(d, o + 12),
                     "rawsize": _u32(d, o + 16), "rawptr": _u32(d, o + 20)})
    rs = next(s for s in secs if s["vaddr"] <= res_rva < s["vaddr"] + s["vsize"])
    base = rs["rawptr"]                                # .rsrc file base

    hits, remaining = [], []
    append_cur = (rs["vsize"] + 3) & ~3               # append point (file-align slack), 4-byte aligned
    for lf in _res_leaves(d, base):
        if lf["type"] not in (RT_MENU, RT_DIALOG):
            continue
        blob_off = base + (lf["rva"] - rs["vaddr"])
        old = bytes(d[blob_off:blob_off + lf["size"]])
        if lf["type"] == RT_DIALOG:
            new, hit = build_dialog(old, mapping, (layout or {}).get(lf["name"]))
            reparse = parse_dialog
        else:
            new, hit = build_menu(old, mapping)
            reparse = parse_menu
        hits += hit
        if new != old:
            if len(new) <= lf["size"]:                # fits in place
                d[blob_off:blob_off + len(new)] = new
                for i in range(blob_off + len(new), blob_off + lf["size"]):
                    d[i] = 0
                _p32(d, lf["de_off"] + 4, len(new))
            else:                                     # relocate into .rsrc slack, fix RVA+Size
                end = base + append_cur + len(new)
                if end > base + rs["rawsize"]:
                    raise PatchError("resource won't fit in .rsrc slack (raw growth unimplemented)")
                d[base + append_cur:base + append_cur + len(new)] = new
                _p32(d, lf["de_off"], rs["vaddr"] + append_cur)
                _p32(d, lf["de_off"] + 4, len(new))
                append_cur = (append_cur + len(new) + 3) & ~3
        for t in reparse(new):
            if has_jp(t):
                remaining.append(t)

    grew = max(0, append_cur - ((rs["vsize"] + 3) & ~3))
    if grew:                                          # extend .rsrc vsize + image, keep data-dir in sync
        new_vsize = append_cur
        nxt = min((s["vaddr"] for s in secs if s["vaddr"] > rs["vaddr"]), default=None)
        if nxt is not None and rs["vaddr"] + new_vsize > nxt:
            raise PatchError("menu growth overruns the next section (raw growth unimplemented)")
        _p32(d, rs["o"] + 8, new_vsize)               # section VirtualSize
        end_va = max(s["vaddr"] + (new_vsize if s is rs else s["vsize"]) for s in secs)
        _p32(d, opt + 56, (end_va + salign - 1) & ~(salign - 1))   # SizeOfImage
        if _u32(d, opt + 116) < new_vsize:            # DataDirectory[RESOURCE].Size
            _p32(d, opt + 116, new_vsize)
    _p32(d, opt + 64, _pe_checksum(d, opt + 64))      # fix PE checksum
    open(outp, "wb").write(bytes(d))
    return {"hits": hits, "remaining_jp": remaining, "grew": grew}


class PatchError(Exception):
    pass


def dump(path):
    import lief
    b = lief.parse(path)
    if b is None or b.resources is None:
        print("no resources"); return
    for typ in b.resources.childs:
        if typ.id not in RTN:
            continue
        for nm in typ.childs:
            resid = nm.name if nm.has_name else nm.id
            for lang in nm.childs:
                data = bytes(lang.content)
                tag = f"{RTN[typ.id]}/{resid}/lang{lang.id}"
                if typ.id == RT_MENU:
                    for n, t in enumerate(parse_menu(data)):
                        mark = " *JP*" if has_jp(t) else ""
                        print(f"{tag}#{n}\t{t!r}{mark}")
                elif typ.id == RT_STRING:
                    for sid, t in parse_stringtable(data, resid).items():
                        if t.strip():
                            mark = " *JP*" if has_jp(t) else ""
                            print(f"STR/{sid}/lang{lang.id}\t{t!r}{mark}")
                elif typ.id == RT_DIALOG:
                    for n, t in enumerate(parse_dialog(data)):
                        mark = " *JP*" if has_jp(t) else ""
                        print(f"{tag}#{n}\t{t!r}{mark}")


def geom(path, names=None):
    """Print RT_DIALOG control geometry (index/class/x/y/cx/cy/x+cx/text). `names` filters by
    dialog resource id. Feeds the `[pe_res.layout.<DLG>]` overrides (keys = control index)."""
    import lief
    b = lief.parse(path)
    if b is None or b.resources is None:
        print("no resources"); return
    for typ in b.resources.childs:
        if typ.id != RT_DIALOG:
            continue
        for nm in typ.childs:
            resid = nm.name if nm.has_name else nm.id
            if names and str(resid) not in names:
                continue
            for lang in nm.childs:
                try:
                    ctrls = list(dialog_controls(bytes(lang.content)))
                except (struct.error, IndexError) as e:
                    print(f"DIALOG/{resid}: parse error: {e}"); continue
                dlg = ctrls[0]
                print(f"\n=== DIALOG/{resid}/lang{lang.id}  cx={dlg['cx']} cy={dlg['cy']} ===")
                for c in ctrls[1:]:
                    mark = " *JP*" if has_jp(c["text"]) else ""
                    print(f"  #{c['idx']:<2} {str(c['class']):<8} "
                          f"x={c['x']:<4} y={c['y']:<4} cx={c['cx']:<4} cy={c['cy']:<4} "
                          f"x+cx={c['x']+c['cx']:<4} {c['text']!r}{mark}")


def main(argv):
    if len(argv) == 2 and argv[0] == "dump":
        dump(argv[1]); return 0
    if len(argv) >= 2 and argv[0] == "geom":
        geom(argv[1], argv[2:] or None); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
