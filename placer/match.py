from tiles import flip_slots
from score import prune


CAP = 256


def _right(cols):
    for sl in reversed(cols):
        if sl:
            return sl[3]
    return None


def _frozen_pos(cols_a, tiles_a):
    name_to_tile = {}
    for t in tiles_a:
        if t.frozen_id is None:
            continue
        name_to_tile[t.slots[0][0]] = (t, 0)
        name_to_tile[flip_slots(t.slots)[0][0]] = (t, 1)
    pos = {}
    c = 0
    seen = set()
    while c < len(cols_a):
        sl = cols_a[c]
        if sl and sl[0] in name_to_tile:
            t, fl = name_to_tile[sl[0]]
            if t.frozen_id not in seen:
                pos[t.frozen_id] = (c, fl, len(t.slots))
                seen.add(t.frozen_id)
                c += len(t.slots)
                continue
        c += 1
    return pos


def _overlap_reserved(start, length, reserved):
    for c in range(start, start + length):
        if c in reserved:
            return True
    return False


def phase2(cols_a, tiles_b, tiles_a, frozen, max_w, routability, W_a=None, cap=None, packed=False):
    """Match second type: place/flip/nil-skip. Frozen 4T forced once A placed its half."""
    W_a = len(cols_a) if W_a is None else W_a
    if not tiles_b:
        return [tuple([None] * W_a)]
    byid = {t.tid: t for t in tiles_b}
    pos = _frozen_pos(cols_a, tiles_a)
    reserved = {}
    for fid, (st, fl, ln) in pos.items():
        for i in range(ln):
            reserved[st + i] = fid
    beam = [((), frozenset(t.tid for t in tiles_b))]
    ntiles = len(tiles_b)
    for step in range(ntiles):
        nxt = []
        for cols, rem in beam:
            cur = len(cols)
            right = _right(cols)
            for tid in rem:
                t = byid[tid]
                is_f = t.frozen_id is not None
                flips = (0, 1)
                if is_f and t.frozen_id in pos:
                    flips = (pos[t.frozen_id][1],)
                for fl in flips:
                    sl = t.slots if not fl else flip_slots(t.slots)
                    ln = len(sl)
                    if is_f and t.frozen_id in pos:
                        n0 = pos[t.frozen_id][0] - cur
                        if n0 < 0:
                            continue
                        nil_opts = (n0,)
                    else:
                        budget = max_w - cur - ln
                        if budget < 0:
                            continue
                        abut = right is None or sl[0][1] == right
                        # never grow past type-A width for gate-align (a nil is not extra pitch)
                        max_free = max(0, W_a - cur - ln)
                        hi = min(budget, max_free)
                        if packed:
                            nil_opts = (0,) if abut else ((1,) if hi >= 1 else ())
                            if not nil_opts:
                                continue
                        else:
                            opts = set()
                            if abut:
                                opts.add(0)
                            elif hi >= 1:
                                opts.add(1)
                            g0 = sl[0][2]
                            for i, asl in enumerate(cols_a):
                                if asl and asl[2] == g0:
                                    n_nil = i - cur
                                    if 0 <= n_nil <= hi and not (n_nil == 0 and not abut):
                                        opts.add(n_nil)
                            k = 0
                            while cur + k < W_a and cols_a[cur + k] is None:
                                k += 1
                            if 0 < k <= hi:
                                opts.add(k)
                            if not opts:
                                opts.add(0 if abut or hi < 1 else 1)
                            nil_opts = opts
                    for n_nil in nil_opts:
                        start = cur + n_nil
                        if start + ln > max_w:
                            continue
                        if not is_f and _overlap_reserved(start, ln, reserved):
                            continue
                        if not is_f and any((cur + i) in reserved for i in range(n_nil)):
                            continue
                        if is_f and t.frozen_id in pos and start != pos[t.frozen_id][0]:
                            continue
                        if n_nil == 0 and right is not None and sl[0][1] != right:
                            continue
                        new = list(cols) + [None] * n_nil + list(sl)
                        nxt.append((new, rem - {tid}))
        if not nxt:
            break
        th = routability if step >= ntiles // 2 else 0.0

        def key(item):
            c, _r = item
            return (len(c), -sum(1 for x in c if x))

        kept = prune([(key(x), x) for x in nxt], key=lambda z: z[0], threshold=th, cap=cap or CAP)
        beam = [st for _, st in kept]
    out = []
    for cols, rem in beam:
        if rem:
            continue
        cols = list(cols)
        while len(cols) < W_a:
            cols.append(None)
        if len(cols) > max_w:
            continue
        out.append(tuple(cols))
    return out[:(cap or CAP)]
