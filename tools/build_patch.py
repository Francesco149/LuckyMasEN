#!/usr/bin/env python3
"""
build_patch.py — the reproducible-patch engine for LuckyMasterEN.

Reads `patch/manifest.toml` (the single source of truth for every file we patch),
mirrors the owner's OWN `originals/installed/` tree into `out/patched/`, applies each
declared op, and writes `out/patched/PATCH-LOG.txt` — a full audit of everything
patched (and everything declared-but-deferred). The output tree is the basis for the
later stages (xdelta/IPS delta, English-installer re-wrap).

Hard rule: we never ship SYGNAS bytes. This runs only against the user's own
`originals/`; the manifest + this engine + the patch sources are the redistributable
part, never the originals or the build output (`out/` is gitignored).

Stdlib only (Python 3.11+ for tomllib). Run from anywhere:
  python tools/build_patch.py [--originals DIR] [--out DIR] [--manifest FILE]

Manifest op tables (applied in this fixed order; rename always last):
  [[xvi]]        glob + src        — repack a translated cp932 Ini into each .Xvi
  [[text_keys]]  file + keys{}     — replace INI `KEY=` values, preserve all else
  [[text_subst]] file + subs[]     — literal find->replace pairs within a text file
  [[text_file]]  file + src        — replace a whole file with a tracked EN version
  [[binpatch]]   file + strings[]  — replace whole NUL-terminated (wide|narrow) strings
  [[rename]]     frm + to          — rename a file within the patched tree
Every op may set `active = false` to record intent without applying (logged DEFERRED).
String fields are templated with {install_root_jp}/{install_root_en} from [meta].
"""
import os, sys, re, shutil, tomllib, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sygnas_repack import repack_acz                       # xvi op
from sygnas_unpack import parse_acz                         # (kept importable for verify)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OP_ORDER = ['xvi', 'text_keys', 'text_subst', 'text_file', 'binpatch', 'pe_res', 'rename']


class PatchError(Exception):
    pass


def tmpl(s, meta):
    """Expand {install_root_jp}/{install_root_en} (and any [meta] key) in a string."""
    if not isinstance(s, str):
        return s
    for k, v in meta.items():
        s = s.replace('{' + k + '}', str(v))
    return s


# ── op implementations: each returns a list of human-readable log lines ──────────
def op_xvi(e, ctx):
    import glob
    log = []
    pattern = os.path.join(ctx['out'], tmpl(e['glob'], ctx['meta']))
    hits = sorted(glob.glob(pattern))
    if not hits:
        raise PatchError(f"xvi glob matched nothing: {e['glob']}")
    for xvi in hits:
        stem = os.path.splitext(os.path.basename(xvi))[0]
        src = os.path.join(REPO, tmpl(e['src'], ctx['meta']).format(stem=stem))
        if not os.path.exists(src):
            log.append(f"    SKIP {os.path.relpath(xvi, ctx['out'])} (no src {os.path.relpath(src, REPO)})")
            continue
        orig = open(xvi, 'rb').read()
        new_ini = open(src, 'rb').read()              # translated Ini, already cp932
        out = repack_acz(orig, new_ini)
        open(xvi, 'wb').write(out)
        log.append(f"    xvi  {os.path.relpath(xvi, ctx['out'])}  <- {os.path.relpath(src, REPO)}  "
                   f"(Ini {len(new_ini)}b, {len(orig)}->{len(out)}b)")
    return log


def op_text_keys(e, ctx):
    path = os.path.join(ctx['out'], tmpl(e['file'], ctx['meta']))
    enc = e.get('encoding', 'utf-8')
    text = open(path, 'rb').read().decode(enc)
    log = [f"    keys {e['file']} ({enc})"]
    for key, val in e['keys'].items():
        val = tmpl(val, ctx['meta'])
        pat = re.compile(rf'(?m)^({re.escape(key)}=)[^\r\n]*(\r?)$')
        text, n = pat.subn(lambda m: m.group(1) + val + m.group(2), text)
        if n == 0:
            raise PatchError(f"text_keys {e['file']}: key {key!r} not found")
        log.append(f"        {key} = {val}  (x{n})")
    open(path, 'wb').write(text.encode(enc))
    return log


def op_text_subst(e, ctx):
    path = os.path.join(ctx['out'], tmpl(e['file'], ctx['meta']))
    enc = e.get('encoding', 'utf-8')
    text = open(path, 'rb').read().decode(enc)
    log = [f"    subst {e['file']} ({enc})"]
    total = 0
    for sub in e['subs']:
        frm, to = tmpl(sub['from'], ctx['meta']), tmpl(sub['to'], ctx['meta'])
        n = text.count(frm)
        if n == 0 and sub.get('require', True):
            raise PatchError(f"text_subst {e['file']}: {frm!r} not found")
        text = text.replace(frm, to)
        total += n
        log.append(f"        {frm!r} -> {to!r}  (x{n})")
    open(path, 'wb').write(text.encode(enc))
    return log


def op_text_file(e, ctx):
    """Replace a whole file with a tracked EN version. We author sources as UTF-8/LF;
    `encoding` transcodes (e.g. cp932 for XP Notepad) and `crlf` normalizes line ends."""
    dst = os.path.join(ctx['out'], tmpl(e['file'], ctx['meta']))
    src = os.path.join(REPO, tmpl(e['src'], ctx['meta']))
    if not os.path.exists(src):
        raise PatchError(f"text_file src missing: {e['src']}")
    old = os.path.getsize(dst) if os.path.exists(dst) else 0
    enc, crlf = e.get('encoding'), e.get('crlf', False)
    if enc is None and not crlf:
        shutil.copyfile(src, dst)                                  # raw byte copy
    else:
        text = open(src, encoding='utf-8', newline='').read()
        if crlf:
            text = text.replace('\r\n', '\n').replace('\n', '\r\n')
        open(dst, 'wb').write(text.encode(enc or 'utf-8'))
    tail = f" [{enc or 'raw'}{', crlf' if crlf else ''}]"
    return [f"    file {e['file']}  <- {e['src']}  ({old} -> {os.path.getsize(dst)}b){tail}"]


def _enc_str(s, wide):
    return s.encode('utf-16-le' if wide else 'latin1')


def op_binpatch(e, ctx):
    path = os.path.join(ctx['out'], tmpl(e['file'], ctx['meta']))
    wide = e.get('wide', False)
    cs = 2 if wide else 1
    data = bytearray(open(path, 'rb').read())
    log = [f"    bin  {e['file']} ({'wide' if wide else 'narrow'})"]
    for s in e['strings']:
        old, new = tmpl(s['old'], ctx['meta']), tmpl(s['new'], ctx['meta'])
        oe, ne = _enc_str(old, wide), _enc_str(new, wide)
        if len(ne) > len(oe):
            raise PatchError(f"binpatch {e['file']}: new {new!r} longer than old {old!r}")
        term = b'\x00' * cs
        needle = oe + term                          # match a COMPLETE NUL-terminated string
        n = data.count(needle)
        if n != 1:
            raise PatchError(f"binpatch {e['file']}: {old!r} matched {n} complete strings (want 1)")
        i = data.find(needle)
        data[i:i + len(oe)] = ne + b'\x00' * (len(oe) - len(ne))   # shrink in place; tail->NUL
        log.append(f"        {old!r} -> {new!r}  @0x{i:x}  (pad {len(oe) - len(ne)}b)")
    open(path, 'wb').write(bytes(data))
    return log


def op_pe_res(e, ctx):
    """Translate PE-resource strings (lang 1041 menus, later dialogs) via lief — these are
    Unicode resources, so no ASCII constraint. `strings` maps JP source -> EN."""
    import pe_res
    path = os.path.join(ctx['out'], tmpl(e['file'], ctx['meta']))
    mapping = {tmpl(k, ctx['meta']): tmpl(v, ctx['meta']) for k, v in e['strings'].items()}
    layout = {dlg: {(int(k) if str(k).lstrip('-').isdigit() else k): v for k, v in ov.items()}
              for dlg, ov in e.get('layout', {}).items()}
    res = pe_res.patch(path, path, mapping, layout)
    geo = f", geom:{','.join(layout)}" if layout else ""
    log = [f"    pe-res {e['file']}  ({len(res['hits'])} strings translated{geo})"]
    for jp, en in res['hits']:
        log.append(f"        {jp!r} -> {en!r}")
    if res['remaining_jp']:
        log.append(f"        !! {len(res['remaining_jp'])} menu string(s) still JP "
                   f"(unmapped key?): " + ", ".join(repr(x) for x in res['remaining_jp'][:12]))
    return log


def op_rename(e, ctx):
    frm = os.path.join(ctx['out'], tmpl(e['frm'], ctx['meta']))
    to = os.path.join(ctx['out'], tmpl(e['to'], ctx['meta']))
    if not os.path.exists(frm):
        raise PatchError(f"rename src missing: {e['frm']}")
    os.makedirs(os.path.dirname(to), exist_ok=True)
    os.rename(frm, to)
    return [f"    mv   {e['frm']}  ->  {e['to']}"]


OPS = {'xvi': op_xvi, 'text_keys': op_text_keys, 'text_subst': op_text_subst,
       'text_file': op_text_file, 'binpatch': op_binpatch, 'pe_res': op_pe_res,
       'rename': op_rename}


def build(originals, out, manifest_path):
    with open(manifest_path, 'rb') as f:
        man = tomllib.load(f)
    meta = man.get('meta', {})

    inst = os.path.join(originals, 'installed')
    if not os.path.isdir(os.path.join(inst, 'app')):
        raise PatchError(f"originals not found: expected {inst}/app (the user's own copy). "
                         f"See originals/README.md.")

    # 1) mirror the user's own tree so unpatched files pass through untouched
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(inst, out)

    # 2) apply ops in fixed order; collect a full audit log
    audit = ["LuckyMasterEN — patch build log",
             f"manifest: {os.path.relpath(manifest_path, REPO)}",
             f"install root: {meta.get('install_root_jp','?')} -> {meta.get('install_root_en','?')}",
             ""]
    ctx = {'out': out, 'meta': meta}
    applied = deferred = 0
    for kind in OP_ORDER:
        entries = man.get(kind, [])
        if not entries:
            continue
        audit.append(f"[{kind}]")
        for e in entries:
            title = e.get('note', e.get('file', e.get('glob', e.get('frm', ''))))
            if not e.get('active', True):
                audit.append(f"  DEFERRED: {title}")
                if e.get('todo'):
                    audit.append(f"    TODO: {e['todo']}")
                deferred += 1
                continue
            audit.append(f"  {title}")
            audit += OPS[kind](e, ctx)
            applied += 1
        audit.append("")

    summary = f"applied {applied} op(s), {deferred} deferred"
    audit.append(summary)
    open(os.path.join(out, 'PATCH-LOG.txt'), 'w', encoding='utf-8').write('\n'.join(audit) + '\n')
    return applied, deferred, summary


def main(argv):
    ap = argparse.ArgumentParser(description="apply the reproducible patch to a copy of the originals")
    ap.add_argument('--originals', default=os.path.join(REPO, 'originals'))
    ap.add_argument('--out', default=os.path.join(REPO, 'out', 'patched'))
    ap.add_argument('--manifest', default=os.path.join(REPO, 'patch', 'manifest.toml'))
    a = ap.parse_args(argv)
    try:
        applied, deferred, summary = build(a.originals, a.out, a.manifest)
    except PatchError as ex:
        print(f"build_patch: ERROR: {ex}", file=sys.stderr)
        return 1
    print(f"build_patch: {summary} -> {os.path.relpath(a.out, REPO)}/  (see PATCH-LOG.txt)")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
