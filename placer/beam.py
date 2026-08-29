from tiles import flip_slots
from score import prune


CAP = 256


def _end_net(cols):
    for sl in reversed(cols):
        if sl:
            return sl[3]
    return None


def _place(cols, slots, gap):
    out = list(cols)
    if gap:
        out.append(None)
    for sl in slots:
        out.append(sl)
    return out


def phase1(tiles, end_nets, max_w, threshold, rails=None, cap=None):
    """Unconstrained first-type sequencing; gaps only when abutment would short."""
    if not tiles:
        return [()]
    typ = tiles[0].typ
    ends = end_nets.get(typ, set())
    rail = (rails or {}).get(typ)
    beam = [((), frozenset(t.tid for t in tiles))]
    byid = {t.tid: t for t in tiles}
    ntiles = len(tiles)
    for _ in range(ntiles):
        nxt = []
        for cols, rem in beam:
            right = _end_net(cols)
            for tid in rem:
                t = byid[tid]
                for fl in (0, 1):
                    sl = t.slots if not fl else flip_slots(t.slots)
                    abut = (right is None) or (right == sl[0][1])
                    gap = 0 if abut else 1
                    new = _place(cols, sl, gap)
                    if len(new) > max_w:
                        continue
                    nrem = rem - {tid}
                    bonus = 0
                    if not cols:
                        left = sl[0][1]
                        if left in ends:
                            bonus += 4
                        elif left == rail:
                            bonus += 2
                    nxt.append((new, nrem, bonus, gap))
        # prune only among same-length paths (one more tile each); rank width first
        ranked = [((len(c), -b, -sum(1 for x in c if x)), (tuple(c), r)) for c, r, b, g in nxt]
        ranked.sort(key=lambda x: x[0])
        beam = prune(ranked, key=lambda x: x[0], threshold=threshold, cap=cap or CAP)
        beam = [st for _, st in beam]
    out = []
    for cols, rem in beam:
        if rem:
            continue
        cols = tuple(cols)
        bonus = 0
        if cols:
            left = next((s[1] for s in cols if s), None)
            right = _end_net(cols)
            if left in ends:
                bonus += 4
            elif left == rail:
                bonus += 2
            if right in ends:
                bonus += 2
            elif right == rail:
                bonus += 1
        out.append((len(cols), -bonus, cols))
    out.sort(key=lambda x: (x[0], x[1]))
    cap = cap or CAP
    return [c for _, _, c in out[:cap]]
