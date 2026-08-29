#!/usr/bin/env python3
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdl, tiles, beam, match, score, ascii, db as DBmod

TABLE = 20


def fmt_t(s):
    return '%.1fms' % (s * 1000) if s < 1 else '%.2fs' % s


def _pad(cols, W):
    cols = list(cols)
    while len(cols) < W:
        cols.append(None)
    return cols


def _orders(first, tn, tp):
    if first in ('nfirst', 'N'):
        return ['N']
    if first in ('pfirst', 'P'):
        return ['P']
    if first == 'both':
        return ['N', 'P']
    return ['N'] if len(tn) <= len(tp) else ['P']


def _pair_search(tn, tp, frozen, first, max_w, threshold, routability, end_nets, rails=None, cap=None, packed=False):
    """Two-phase beam on one NP pair. Returns (cands, t1, t2).
    cand = (n_cols, p_cols, first_type)"""
    t1 = t2 = 0.0
    cands = []
    for ft in _orders(first, tn, tp):
        a, b = (tn, tp) if ft == 'N' else (tp, tn)
        t0 = time.perf_counter()
        a_cols = beam.phase1(a, end_nets, max_w, threshold, rails, cap=cap)
        t1 += time.perf_counter() - t0
        t0 = time.perf_counter()
        a_cols = list(dict.fromkeys(a_cols))
        for ac in a_cols:
            bcs = match.phase2(ac, b, a, frozen, max_w, routability, cap=cap, packed=packed)
            for bc in bcs:
                W = max(len(ac), len(bc))
                if ft == 'N':
                    cands.append((_pad(ac, W), _pad(bc, W), ft))
                else:
                    cands.append((_pad(bc, W), _pad(ac, W), ft))
        t2 += time.perf_counter() - t0
    return cands, t1, t2


def _clk_cols(n_cols, p_cols):
    out = []
    for i, sl in enumerate(n_cols):
        if sl and ('CK' in sl[2].upper() or 'CLK' in sl[2].upper()):
            out.append(i)
    for i, sl in enumerate(p_cols):
        if sl and ('CK' in sl[2].upper() or 'CLK' in sl[2].upper()):
            out.append(i)
    return out


def _shift(cols, k):
    return [None] * k + list(cols)


def _flip_row(cols):
    out = []
    for sl in reversed(cols):
        if not sl:
            out.append(None)
        else:
            n, src, g, d = sl
            out.append((n, d, g, src))
    return out


def _align_g(grid):
    if not grid or not grid[0]:
        return 0
    W, ag = len(grid[0]), 0
    for c in range(W):
        prev = None
        for row in grid:
            sl = row[c] if c < len(row) else None
            g = sl[2] if sl else None
            if g is None:
                prev = None
                continue
            if prev is not None and g == prev:
                ag += 1
            prev = g
    return ag


def place(cdl_path, rows=1, pattern='NPPN', tracks=4, threshold=0.0,
          routability=0.0, first='auto', dumNumAdd=0, db='place.db', bruteForce=False):
    if pattern not in ('NPPN', 'PNNP'):
        raise SystemExit('pattern must be NPPN or PNNP')
    cell = cdl.parse(cdl_path)
    types = tiles.row_types(rows, pattern)
    if bruteForce:
        threshold = routability = 0.0
    all_tiles, frozen, end_nets, counts = tiles.group(cell, types, brute=bruteForce)
    wmin = tiles.cell_width(len(cell.devices), rows)
    all_tiles = tiles.cap_bricks(all_tiles, wmin)
    tg_names = score.tg_device_names(cell.devices)
    pairs = tiles.np_pairs(types)
    req = dumNumAdd
    cap = req + 5
    skip = set(cell.pininfo) if len(pairs) > 1 else set()
    buckets = tiles.assign_pairs(all_tiles, frozen, max(1, len(pairs)), wmin, skip)
    max_w = wmin + req if bruteForce else wmin + cap

    t1s = t2s = 0.0
    pair_lists = []
    for pi, (nr, pr) in enumerate(pairs):
        b = buckets[pi]
        tn = b['N'] + [f['N'] for f in b['F']]
        tp = b['P'] + [f['P'] for f in b['F']]
        bcap = 50000 if bruteForce else None
        cands, t1, t2 = _pair_search(tn, tp, b['F'], first, max_w, threshold, routability, end_nets,
                                       score.rails_of(cell.pininfo), cap=bcap, packed=bruteForce)
        t1s += t1
        t2s += t2
        pair_lists.append(cands)
    t_total = t1s + t2s

    # combine pair results (cartesian of a few best, or single pair)
    combined = []
    if not pair_lists or not all(pair_lists):
        combined = []
    elif len(pairs) == 1:
        for n, p, ft in pair_lists[0]:
            grid = [None] * len(types)
            nr, pr = pairs[0]
            W = max(len(n), len(p))
            grid[nr] = _pad(n, W)
            grid[pr] = _pad(p, W)
            for i, t in enumerate(types):
                if grid[i] is None:
                    grid[i] = [None] * W
            combined.append((grid, ft))
    else:
        # cartesian of pair results; stitch with flip+shift to max full-height align_g
        tops = [lst[:16] for lst in pair_lists]
        import itertools

        def variants(n, p):
            yield n, p
            yield _flip_row(n), _flip_row(p)

        for combo in itertools.product(*tops):
            widths = [max(len(c[0]), len(c[1])) for c in combo]
            W0 = max(widths)
            best_ag, best_ft, best_grids = -1, combo[0][2], []
            v1 = list(variants(combo[0][0], combo[0][1]))
            rest = [list(variants(c[0], c[1])) for c in combo[1:]]
            for n0, p0 in v1:
                for prod in itertools.product(*rest) if rest else [()]:
                    parts = [(n0, p0)] + list(prod)
                    W = max(max(len(n), len(p)) for n, p in parts)
                    def rec(i, placed):
                        nonlocal best_ag, best_grids
                        if i == len(parts):
                            grid = [[None] * W for _ in types]
                            for k, (nr, pr) in enumerate(pairs):
                                n, p, s = placed[k]
                                wn = max(len(n), len(p))
                                grid[nr] = _pad(_shift(_pad(n, wn), s), W)
                                grid[pr] = _pad(_shift(_pad(p, wn), s), W)
                            ag = _align_g(grid)
                            if ag > best_ag:
                                best_ag, best_grids = ag, [grid]
                            elif ag == best_ag:
                                best_grids.append(grid)
                            return
                        n, p = parts[i]
                        wi = max(len(n), len(p))
                        for s in range(0, W - wi + 1):
                            rec(i + 1, placed + [(n, p, s)])
                    rec(1, [(n0, p0, 0)])
            for g in best_grids:
                combined.append((g, best_ft))

    scored = []
    for grid, ft in combined:
        m = score.metrics(grid, types, cell.pininfo, tracks, end_nets, tg_names)
        m['first_type'] = ft
        m['grid'] = {'types': types, 'cells': grid, 'pininfo': cell.pininfo}
        m['_cost'] = score.cost_tuple(m)
        scored.append(m)
    scored.sort(key=lambda m: m['_cost'])

    used = req
    pool = []
    while used <= req + 5:
        pool = [m for m in scored if m['W'] <= wmin + used]
        if pool:
            break
        used += 1
    if not pool and scored:
        used = min(req + 5, max(m['W'] - wmin for m in scored))
        pool = [m for m in scored if m['W'] <= wmin + used]
    if used != req and pool:
        print('dumNumAdd %d empty, using %d' % (req, used))
    by_cost = pool[:TABLE]
    extra = []
    if pool:
        mx = max(m['align_g'] for m in pool)
        extra = [m for m in pool if m['align_g'] == mx]
    seen, merged = set(), []
    for m in extra + by_cost:
        k = json.dumps(m['grid']['cells'])
        if k in seen:
            continue
        seen.add(k)
        merged.append(m)
    pool = merged[:TABLE * 2]
    meta = dict(cell=cell.name, cdl=os.path.abspath(cdl_path), rows=rows, pattern=pattern,
                tracks=tracks, threshold=threshold, routability=routability, first=first,
                dumNumAdd_requested=req, dumNumAdd_used=used,
                t_phase1=t1s, t_phase2=t2s, t_total=t_total)
    cx = DBmod.connect(db)
    rid = DBmod.save_run(cx, meta, pool)
    cx.close()
    n = len(pool)
    wm = min((m['W'] for m in pool), default=None)
    print('run %d cell=%s Wmin=%s dumNumAdd_used=%d n=%d' % (rid, cell.name, wmin, used, n))
    print('phase1 %s  phase2 %s  total %s  n=%d' % (fmt_t(t1s), fmt_t(t2s), fmt_t(t_total), n))
    return rid


SORT_KEYS = {
    'width': lambda m: (m['W'], m['_cost']),
    'cost': lambda m: m['_cost'],
    'route': lambda m: (m['route'], m['_cost']),
    'cong': lambda m: (m['cong'], m['_cost']),
    'wl': lambda m: (m['wl'], m['_cost']),
    'align': lambda m: (-(m['align_g'] + m['align_sd'] + m['align_pg']), m['_cost']),
    'align_g': lambda m: (-m['align_g'], m['_cost']),
    'rail': lambda m: (-m.get('rail', 0), m['_cost']),
}


def _row_to_m(r, tracks=4):
    grid = json.loads(r['grid_json'])
    m = {k: r[k] for k in ('W', 'ovf', 'cong', 'wl', 'align_g', 'align_sd', 'align_pg', 'route', 'first_type')}
    m['grid'] = grid
    pininfo = grid.get('pininfo') or {}
    types = grid.get('types') or []
    if pininfo and types:
        mm = score.metrics(grid['cells'], types, pininfo, tracks, {'N': set(), 'P': set()}, set())
        m.update(mm)
        m['grid'] = grid
        m['first_type'] = r['first_type']
    m['_cost'] = score.cost_tuple(m)
    return m


def show(db='place.db', sort='cost', nshow=5, leaders=False, cell=None, run=None,
         dumNumAdd=None):
    cx = DBmod.connect(db)
    runrow, pls = DBmod.get_run(cx, run_id=run, cell=cell)
    cx.close()
    ms = [_row_to_m(p, runrow['tracks']) for p in pls]
    wmin = min((m['W'] for m in ms), default=0)
    # theoretical stored; use run's used unless tightening
    req = runrow['dumNumAdd_used'] if dumNumAdd is None else dumNumAdd
    used = req
    # Wmin here: min stored W is achieved; tightening filters W <= achieved_min + dum?
    # spec: --dumNumAdd on show only tightens (then bump if empty)
    ach = min((m['W'] for m in ms), default=0)
    pool = ms
    if dumNumAdd is not None:
        while used <= dumNumAdd + 5:
            pool = [m for m in ms if m['W'] <= ach + used]
            if pool:
                break
            used += 1
        if used != dumNumAdd:
            print('dumNumAdd %d empty, using %d' % (dumNumAdd, used))
    key = SORT_KEYS.get(sort, SORT_KEYS['cost'])
    pool.sort(key=key)
    print('run %d %s rows=%d pattern=%s tracks=%d first=%s dumNumAdd %d->%d' % (
        runrow['id'], runrow['cell'], runrow['rows'], runrow['pattern'],
        runrow['tracks'], runrow['first'], runrow['dumNumAdd_requested'], runrow['dumNumAdd_used']))
    print('phase1 %s  phase2 %s  total %s' % (
        fmt_t(runrow['t_phase1'] or 0), fmt_t(runrow['t_phase2'] or 0), fmt_t(runrow['t_total'] or 0)))
    hdr = '%4s %3s %3s %4s %4s %4s %7s %8s %8s %6s' % (
        '#', 'W', 'ovf', 'rail', 'cong', 'wl', 'align_g', 'align_sd', 'align_pg', 'route')
    print(hdr)
    for i, m in enumerate(pool, 1):
        print('%4d %3d %3d %4d %4d %4d %7d %8d %8d %6d' % (
            i, m['W'], m['ovf'], m.get('rail', 0), m['cong'], m['wl'],
            m['align_g'], m['align_sd'], m['align_pg'], m['route']))
    types = pool[0]['grid']['types'] if pool else []

    def sig(m):
        return json.dumps(m['grid']['cells'])

    dumped = set()
    def do_dump(m, label):
        s = sig(m)
        if s in dumped:
            print('\n%s (same as earlier)' % label)
            return
        dumped.add(s)
        rows = m['grid']['cells']
        print()
        print(ascii.dump(rows, types, label))

    if leaders:
        keys = ('width', 'cost', 'route', 'cong', 'wl', 'align', 'rail')
        for k in keys:
            ranked = sorted(pool, key=SORT_KEYS[k])
            if not ranked:
                continue
            m = ranked[0]
            do_dump(m, '#1 %s  W=%d ovf=%d rail=%d cong=%d wl=%d' % (
                k, m['W'], m['ovf'], m.get('rail', 0), m['cong'], m['wl']))
    else:
        for i, m in enumerate(pool[:nshow], 1):
            do_dump(m, '#%d %s  W=%d ovf=%d rail=%d cong=%d wl=%d' % (
                i, sort, m['W'], m['ovf'], m.get('rail', 0), m['cong'], m['wl']))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    g = sub.add_parser('gen')
    g.add_argument('cdl')
    g.add_argument('--rows', type=int, default=1, help='cell heights: 1=NP, 2=NPPN')
    g.add_argument('--pattern', default='NPPN')
    g.add_argument('--tracks', type=int, default=4)
    g.add_argument('--threshold', type=float, default=0.0)
    g.add_argument('--routability', type=float, default=0.0)
    g.add_argument('--first', default='auto')
    g.add_argument('--dumNumAdd', type=int, default=0)
    g.add_argument('--db', default='place.db')
    g.add_argument('--bruteForce', action='store_true', help='no island bricks, enumerate')
    s = sub.add_parser('show')
    s.add_argument('--sort', default='cost')
    s.add_argument('--show', type=int, default=5, dest='nshow')
    s.add_argument('--leaders', action='store_true')
    s.add_argument('--cell')
    s.add_argument('--run', type=int)
    s.add_argument('--dumNumAdd', type=int, default=None)
    s.add_argument('--db', default='place.db')
    a = p.parse_args()
    if a.cmd == 'gen':
        place(a.cdl, a.rows, a.pattern, a.tracks, a.threshold, a.routability,
              a.first, a.dumNumAdd, a.db, bruteForce=a.bruteForce)
    else:
        show(a.db, a.sort, a.nshow, a.leaders, a.cell, a.run, a.dumNumAdd)


if __name__ == '__main__':
    main()
