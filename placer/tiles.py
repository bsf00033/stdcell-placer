from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Tile:
    tid: int
    typ: str
    slots: tuple  # ((name, left, gate, right), ...)
    frozen_id: object = None


@dataclass
class Path:
    rows: list  # [row][col] = (name, s, g, d) | None
    first_type: str
    W: int


def sd(dev):
    return (dev.source, dev.drain)


def other(dev, net):
    return dev.drain if dev.source == net else dev.source


def rails(pininfo):
    return {p for p, r in pininfo.items() if r in ('P', 'G')}


def diff_counts(devices):
    """S/D net counts per type (gates ignored)."""
    c = {'N': defaultdict(int), 'P': defaultdict(int)}
    for d in devices:
        for n in set(sd(d)):
            c[d.typ][n] += 1
    return c


def _cmos_tgs(devices):
    nmos = [d for d in devices if d.typ == 'N']
    pmos = [d for d in devices if d.typ == 'P']
    used = set()
    tgs = []
    for n in nmos:
        ns = frozenset(sd(n))
        for p in pmos:
            if p.name in used:
                continue
            if frozenset(sd(p)) == ns and n.gate != p.gate:
                tgs.append((n, p))
                used.add(p.name)
                break
    return tgs


def _find_4t(tgs):
    """True two-TG pass-gate: shared mid-net, crossed complementary enables."""
    out = []
    taken = set()
    for i, (n1, p1) in enumerate(tgs):
        if i in taken:
            continue
        s1 = frozenset(sd(n1))
        for j, (n2, p2) in enumerate(tgs):
            if j <= i or j in taken:
                continue
            s2 = frozenset(sd(n2))
            if len(s1 & s2) != 1:
                continue
            if n1.gate == p2.gate and n2.gate == p1.gate and n1.gate != n2.gate:
                out.append((n1, p1, n2, p2))
                taken.update((i, j))
                break
    return out


def _orient_dev(dev, left):
    if dev.source == left:
        return (dev.name, dev.source, dev.gate, dev.drain)
    return (dev.name, dev.drain, dev.gate, dev.source)


def _chain_slots(names, adj, byname):
    deg = {n: len(adj[n]) for n in names}
    ends = [n for n in names if deg[n] <= 1]
    start = ends[0] if ends else names[0]
    slots = []
    prev = None
    cur = start
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        dev = byname[cur]
        nbrs = adj[cur]
        if prev is None:
            if not nbrs:
                slots.append((dev.name, dev.source, dev.gate, dev.drain))
                break
            o, shared = nbrs[0]
            slots.append(_orient_dev(dev, other(dev, shared)))
            prev, cur = cur, o
        else:
            entered = slots[-1][3]
            nxt = [(o, net) for o, net in nbrs if o != prev]
            if nxt:
                o, net = nxt[0]
                slots.append((dev.name, entered, dev.gate, net))
                prev, cur = cur, o
            else:
                slots.append((dev.name, entered, dev.gate, other(dev, entered)))
                cur = None
    return tuple(slots)


def _chains(type_devs, rails=(), skip_nets=()):
    byname = {d.name: d for d in type_devs}
    net_devs = defaultdict(list)
    for d in type_devs:
        for n in set(sd(d)):
            net_devs[n].append(d)
    adj = defaultdict(list)
    for net, ds in net_devs.items():
        uniq, seen = [], set()
        for d in ds:
            if d.name not in seen:
                seen.add(d.name)
                uniq.append(d)
        if len(uniq) == 2:
            if net in skip_nets:
                continue
            a, b = uniq
            prev = [x for x in adj[a.name] if x[0] == b.name]
            if not prev:
                adj[a.name].append((b.name, net))
                adj[b.name].append((a.name, net))
            elif prev[0][1] in rails and net not in rails:
                onet = prev[0][1]
                adj[a.name] = [x for x in adj[a.name] if not (x[0] == b.name and x[1] == onet)]
                adj[b.name] = [x for x in adj[b.name] if not (x[0] == a.name and x[1] == onet)]
                adj[a.name].append((b.name, net))
                adj[b.name].append((a.name, net))
    seen = set()
    chains = []
    for d in type_devs:
        if d.name in seen or d.name not in adj:
            continue
        stack = [d.name]
        comp = []
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.append(n)
            for o, _ in adj[n]:
                if o not in seen:
                    stack.append(o)
        if len(comp) >= 2:
            chains.append(_chain_slots(comp, adj, byname))
    chained = set()
    for sl in chains:
        for name, *_ in sl:
            chained.add(name)
    singles = [d for d in type_devs if d.name not in chained]
    return chains, singles


def group(cell, types=None, brute=False):
    tgs = _cmos_tgs(cell.devices)
    fours = _find_4t(tgs)
    frozen_names = set()
    frozen = []  # {id, 'N': tile, 'P': tile}
    tid = 0
    tiles = []
    if brute:
        fours = []
    for k, (n1, p1, n2, p2) in enumerate(fours):
        frozen_names.update((n1.name, p1.name, n2.name, p2.name))
        mid = next(iter(frozenset(sd(n1)) & frozenset(sd(n2))))
        ns = (
            (n1.name, other(n1, mid), n1.gate, mid),
            (n2.name, mid, n2.gate, other(n2, mid)),
        )
        ps = (
            (p1.name, other(p1, mid), p1.gate, mid),
            (p2.name, mid, p2.gate, other(p2, mid)),
        )
        tn = Tile(tid, 'N', ns, k)
        tid += 1
        tp = Tile(tid, 'P', ps, k)
        tid += 1
        tiles.extend((tn, tp))
        frozen.append({'id': k, 'N': tn, 'P': tp})
    leftover = [d for d in cell.devices if d.name not in frozen_names]
    n_rows = {'N': 0, 'P': 0}
    for t in (types or []):
        n_rows[t] = n_rows.get(t, 0) + 1
    pins = set(cell.pininfo)
    for typ in 'NP':
        tdevs = [d for d in leftover if d.typ == typ]
        if brute:
            chains, singles = [], tdevs
        else:
            skip = pins if n_rows.get(typ, 1) > 1 else ()
            chains, singles = _chains(tdevs, rails(cell.pininfo), skip)
        for sl in chains:
            tiles.append(Tile(tid, typ, sl, None))
            tid += 1
        for d in singles:
            tiles.append(Tile(tid, typ, ((d.name, d.source, d.gate, d.drain),), None))
            tid += 1
    counts = diff_counts(cell.devices)
    # dummy sites: any S/D net with odd count (pins, rails, internals)
    end_nets = {t: {n for n, c in counts[t].items() if c % 2 == 1} for t in 'NP'}
    return tiles, frozen, end_nets, counts


def flip_slots(slots):
    return tuple((n, r, g, l) for n, l, g, r in reversed(slots))


def np_pairs(row_types):
    pairs = []
    for i in range(len(row_types) - 1):
        a, b = row_types[i], row_types[i + 1]
        if a != b:
            n = i if a == 'N' else i + 1
            p = i if a == 'P' else i + 1
            pairs.append((n, p))
    return pairs


def row_types(rows, pattern):
    """rows = cell heights. 1 → NP, 2 → NPPN (pattern tiled, 2 diffusion rows each)."""
    return [pattern[i % 4] for i in range(rows * 2)]


def cell_width(n_tran, rows):
    """numTran / rows / 2, ceil. NAND4 16/2/2 = 4."""
    ndiff = max(1, rows * 2)
    return max(1, (n_tran + ndiff - 1) // ndiff)


def dummy_wmin(n_tran, rows, types, counts):
    """Best-case W: pack plus interior dummy pitches.
    Each odd S/D net needs one dummy. 2 per row (L/R) are free.
    Remaining pair into interior breaks (2 odds per extra poly pitch).
    Extra is max(N, P). Lower bound; chains can force more."""
    pack = cell_width(n_tran, rows)
    n_rows = {'N': 0, 'P': 0}
    for t in types:
        n_rows[t] += 1
    info = {}
    extra = 0
    for typ in 'NP':
        odd = sum(1 for c in counts[typ].values() if c % 2 == 1)
        bound = 2 * n_rows[typ]
        remain = max(0, odd - bound)
        interior = (remain + 1) // 2
        info[typ] = dict(odd=odd, bound=bound, remain=remain, interior=interior, rows=n_rows[typ])
        extra = max(extra, interior)
    return pack, pack + extra, info


def fmt_dummy_wmin(pack, best, info):
    return ('Wmin pack=%d best=%d  odd N=%d P=%d  bound N=%d P=%d  remain N=%d P=%d  extra=%d' % (
        pack, best, info['N']['odd'], info['P']['odd'],
        info['N']['bound'], info['P']['bound'],
        info['N']['remain'], info['P']['remain'], extra_of(info)))


def extra_of(info):
    return max(info['N']['interior'], info['P']['interior'])


def cap_bricks(tile_list, width):
    """Brick cannot be bigger than width. Split leftover chains; frozen 4T stays."""
    out = []
    tid = max((t.tid for t in tile_list), default=-1) + 1
    for t in tile_list:
        if t.frozen_id is not None or len(t.slots) <= width:
            out.append(t)
            continue
        sl = t.slots
        for i in range(0, len(sl), width):
            out.append(Tile(tid, t.typ, sl[i:i + width], None))
            tid += 1
    return out


def _tile_comps(tile_list, skip_nets=()):
    """Connected components on forced abut (an S/D net on exactly two tiles).
    Pin/rail nets in skip_nets are ignored so stacks are not welded through Z/VSS."""
    net_ts = defaultdict(list)
    for t in tile_list:
        nets = set()
        for sl in t.slots:
            nets.add(sl[1])
            nets.add(sl[3])
        for n in nets:
            net_ts[n].append(t)
    adj = defaultdict(set)
    for net, ts in net_ts.items():
        if net in skip_nets:
            continue
        uniq, seen = [], set()
        for t in ts:
            if t.tid not in seen:
                seen.add(t.tid)
                uniq.append(t)
        if len(uniq) == 2:
            a, b = uniq
            adj[a.tid].add(b.tid)
            adj[b.tid].add(a.tid)
    byid = {t.tid: t for t in tile_list}
    seen = set()
    comps, isolates = [], []
    for t in tile_list:
        if t.tid in seen:
            continue
        if t.tid not in adj:
            isolates.append(t)
            seen.add(t.tid)
            continue
        stack = [t.tid]
        comp = []
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            comp.append(byid[i])
            stack.extend(adj[i] - seen)
        if len(comp) >= 2:
            comps.append(comp)
        else:
            isolates.extend(comp)
    return comps, isolates


def assign_pairs(tiles, frozen, n_pairs, width=None, skip_nets=()):
    """Keep a forced-abut component on one pair. Isolated tiles round-robin.
    Brute singles of a series stack stay together; parallel P stripe by CDL order."""
    buckets = [{'N': [], 'P': [], 'F': []} for _ in range(n_pairs)]
    for i, f in enumerate(frozen):
        buckets[i % n_pairs]['F'].append(f)
    skip = set(skip_nets) if skip_nets else set()

    def load_of(k, typ):
        b = buckets[k]
        return sum(len(x.slots) for x in b[typ]) + 2 * len(b['F'])

    def place_one(t, typ):
        ln = len(t.slots)
        room = [k for k in range(n_pairs)
                if width is None or load_of(k, typ) + ln <= width]
        j = min(room if room else range(n_pairs), key=lambda k: load_of(k, typ))
        buckets[j][typ].append(t)

    for typ in 'NP':
        rem = [t for t in tiles if t.typ == typ and t.frozen_id is None]
        comps, isolates = _tile_comps(rem, skip)
        comps.sort(key=lambda c: -sum(len(t.slots) for t in c))
        for comp in comps:
            size = sum(len(t.slots) for t in comp)
            room = [k for k in range(n_pairs)
                    if width is None or load_of(k, typ) + size <= width]
            if room:
                j = min(room, key=lambda k: load_of(k, typ))
                for t in comp:
                    buckets[j][typ].append(t)
            else:
                for t in comp:
                    place_one(t, typ)
        isolates.sort(key=lambda t: -len(t.slots))
        for t in isolates:
            place_one(t, typ)
    return buckets
