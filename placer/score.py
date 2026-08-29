from collections import defaultdict


class UF:
    def __init__(self):
        self.p = {}

    def add(self, x):
        self.p.setdefault(x, x)

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.add(a)
        self.add(b)
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _slot(row, c):
    if c < 0 or c >= len(row):
        return None
    return row[c]


def _net(slot, k):
    return slot[k] if slot else None


def fabric_uf(rows, pairs):
    uf = UF()
    W = len(rows[0]) if rows else 0
    for r, row in enumerate(rows):
        for c, sl in enumerate(row):
            if not sl:
                continue
            for k in (1, 2, 3):
                uf.add((r, c, k, sl[k]))
            # shared diffusion drain col i == source col i+1
            nxt = _slot(row, c + 1)
            if nxt and sl[3] == nxt[1]:
                uf.union((r, c, 3, sl[3]), (r, c + 1, 1, nxt[1]))
    for nr, pr in pairs:
        for c in range(W):
            a, b = _slot(rows[nr], c), _slot(rows[pr], c)
            if not a or not b:
                continue
            # same-column gate
            if a[2] == b[2]:
                uf.union((nr, c, 2, a[2]), (pr, c, 2, b[2]))
            # same-column S/D
            for ka in (1, 3):
                for kb in (1, 3):
                    if a[ka] == b[kb]:
                        uf.union((nr, c, ka, a[ka]), (pr, c, kb, b[kb]))
    return uf


def route_demand(rows, pairs, pininfo, tracks):
    """overflow, max congestion, residual WL from leftover metal spans."""
    rails = {p for p, r in pininfo.items() if r in ('P', 'G')}
    W = len(rows[0]) if rows else 0
    uf = fabric_uf(rows, pairs)
    sites = defaultdict(list)
    tapset = [set() for _ in range(W)]
    for r, row in enumerate(rows):
        for c, sl in enumerate(row):
            if not sl:
                continue
            for k in (1, 2, 3):
                sites[sl[k]].append((r, c, k))
            for k in (1, 3):
                if sl[k] in rails:
                    tapset[c].add(sl[k])
    demand = [0] * W
    wl = 0
    for net, sts in sites.items():
        if net in rails:
            continue
        comps = {}
        for r, c, k in sts:
            root = uf.find((r, c, k, net))
            comps.setdefault(root, []).append(c)
        if len(comps) <= 1:
            continue
        cols = [c for r, c, k in sts]
        lo, hi = min(cols), max(cols)
        wl += hi - lo
        for c in range(lo, hi + 1):
            demand[c] += 1
    ovf = 0
    cong = max(demand) if demand else 0
    for c in range(W):
        supply = tracks - len(tapset[c])
        ovf = max(ovf, max(0, demand[c] - supply))
    return ovf, cong, wl


def alignments(rows, pairs, tg_names):
    W = len(rows[0]) if rows else 0
    ag = asd = apg = 0
    # align_g: per column, skip first gate of a same-net run, +1 for each continuation. nil breaks.
    for c in range(W):
        prev = None
        for r in range(len(rows)):
            sl = _slot(rows[r], c)
            g = sl[2] if sl else None
            if g is None:
                prev = None
                continue
            if prev is not None and g == prev:
                ag += 1
            prev = g
    for nr, pr in pairs:
        for c in range(W):
            a, b = _slot(rows[nr], c), _slot(rows[pr], c)
            if not a or not b:
                continue
            if a[1] == b[1]:
                asd += 1
            if a[3] == b[3]:
                asd += 1
            # pass-gate vertical: stacked CMOS TG (same S/D set)
            if {a[1], a[3]} == {b[1], b[3]} and a[2] != b[2] and a[0] in tg_names:
                apg += 1
        for r in (nr, pr):
            row = rows[r]
            for c in range(W - 1):
                a, b = row[c], row[c + 1]
                if a and b and a[3] == b[1] and a[0] in tg_names and b[0] in tg_names:
                    apg += 1
    return ag, asd, apg


def _end_nets_of(rows):
    left, right = [], []
    W = len(rows[0]) if rows else 0
    for row in rows:
        for c in range(W):
            if row[c]:
                left.append(row[c][1])
                break
        for c in range(W - 1, -1, -1):
            if row[c]:
                right.append(row[c][3])
                break
    return left, right


def rails_of(pininfo):
    r = {}
    for p, role in pininfo.items():
        if role == 'P':
            r['P'] = p
        elif role == 'G':
            r['N'] = p
    return r


def dummy_bonus(rows, odd_nets, types):
    """Odd S/D count facing out (dummy at boundary). +2 left, +1 right. Beats rail."""
    left, right = _end_nets_of(rows)
    b = 0
    for i, n in enumerate(left):
        if n in odd_nets.get(types[i], ()):
            b += 2
    for i, n in enumerate(right):
        if n in odd_nets.get(types[i], ()):
            b += 1
    return b


def end_bonus(rows, end_nets, types):
    return dummy_bonus(rows, end_nets, types)


def rail_bonus(rows, types, pininfo):
    """First device in a row: rail (VDD on P, VSS on N) facing outside. +2 left, +1 right."""
    rails = rails_of(pininfo)
    left, right = _end_nets_of(rows)
    b = 0
    for i, n in enumerate(left):
        if n == rails.get(types[i]):
            b += 2
    for i, n in enumerate(right):
        if n == rails.get(types[i]):
            b += 1
    return b


def clk_bonus(rows, pairs):
    def isclk(n):
        u = n.upper()
        return 'CK' in u or 'CLK' in u
    W = len(rows[0]) if rows else 0
    b = 0
    for nr, pr in pairs:
        for c in range(W):
            a, bsl = _slot(rows[nr], c), _slot(rows[pr], c)
            if a and bsl and a[2] == bsl[2] and isclk(a[2]):
                b += 2
            if a and isclk(a[2]):
                b += 1
            if bsl and isclk(bsl[2]):
                b += 1
            if c + 1 < W:
                for row in (rows[nr], rows[pr]):
                    x, y = row[c], row[c + 1]
                    if x and y and isclk(x[2]) and isclk(y[2]):
                        b += 1
    return b


def pin_bonus(rows):
    """D/SI left + Q right; weaker than a diffusion break (W already primary)."""
    left, right = _end_nets_of(rows)
    b = 0
    for n in left:
        if n in ('D', 'SI'):
            b += 1
    for n in right:
        if n == 'Q':
            b += 1
    return b


def tg_device_names(devices):
    nmos = [d for d in devices if d.typ == 'N']
    pmos = [d for d in devices if d.typ == 'P']
    names = set()
    for n in nmos:
        ns = frozenset((n.source, n.drain))
        for p in pmos:
            if frozenset((p.source, p.drain)) == ns and n.gate != p.gate:
                names.add(n.name)
                names.add(p.name)
    return names


def metrics(rows, types, pininfo, tracks, end_nets, tg_names):
    from tiles import np_pairs
    pairs = np_pairs(types)
    W = len(rows[0]) if rows else 0
    ovf, cong, wl = route_demand(rows, pairs, pininfo, tracks)
    ag, asd, apg = alignments(rows, pairs, tg_names)
    dummy = dummy_bonus(rows, end_nets, types)
    rail = rail_bonus(rows, types, pininfo)
    clk = clk_bonus(rows, pairs)
    pin = pin_bonus(rows)
    route = ovf * 10000 + cong * 100 + wl
    return {
        'W': W, 'ovf': ovf, 'cong': cong, 'wl': wl,
        'align_g': ag, 'align_sd': asd, 'align_pg': apg,
        'route': route, 'dummy': dummy, 'end': dummy, 'rail': rail, 'clk': clk, 'pin': pin,
    }


def cost_tuple(m):
    # W, ovf, then rail-outside (first device). Never buy rail with extra col.
    # dummy (odd S/D at boundary) before rail: saves a dummy column
    return (m['W'], m['ovf'], -m.get('dummy', 0), -m.get('rail', 0), m['cong'], m['wl'],
            -m['align_g'], -m['align_sd'], -m['align_pg'],
            -m.get('clk', 0), -m.get('pin', 0))


def prune(paths, key, threshold, cap=256):
    """Prune only among same-length paths. threshold 0..1 scales all→1; cap 256. Rank width first."""
    paths = sorted(paths, key=key)
    n = len(paths)
    if not n:
        return []
    keep = max(1, int(round(n * (1.0 - threshold))))
    keep = min(keep, cap, n)
    return paths[:keep]
