from tiles import flip_slots
from score import prune

CAP = 256


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


def phase2(cols_a, tiles_b, tiles_a, frozen, max_w, routability, W_a=None, cap=None, packed=False):
    """Match second type: place/flip/nil-skip. Frozen 4T forced once A placed its half."""
    W_a = len(cols_a) if W_a is None else W_a
    if not tiles_b:
        return [tuple([None] * W_a)]
    byid = {t.tid: t for t in tiles_b}
    orients = {t.tid: (t.slots, flip_slots(t.slots)) for t in tiles_b}
    pos = _frozen_pos(cols_a, tiles_a)
    reserved = {}
    for fid, (st, fl, ln) in pos.items():
        for i in range(ln):
            reserved[st + i] = fid
    empty_res = not reserved
    gate_at = []
    none_a = []
    for i, asl in enumerate(cols_a):
        gate_at.append(asl[2] if asl else None)
        if asl is None:
            none_a.append(i)
    gate_cols = {}
    for i, g in enumerate(gate_at):
        if g is not None:
            gate_cols.setdefault(g, []).append(i)

    rem0 = frozenset(t.tid for t in tiles_b)
    # cols, rem, right_net, n_occ
    beam = [((), rem0, None, 0)]
    ntiles = len(tiles_b)
    capn = cap or CAP
    for step in range(ntiles):
        nxt = []
        for cols, rem, right, n_occ in beam:
            cur = len(cols)
            for tid in rem:
                t = byid[tid]
                is_f = t.frozen_id is not None
                locked = is_f and t.frozen_id in pos
                if locked:
                    sls = (orients[tid][pos[t.frozen_id][1]],)
                else:
                    sls = orients[tid]
                nrem = rem - {tid}
                for sl in sls:
                    ln = len(sl)
                    if locked:
                        n0 = pos[t.frozen_id][0] - cur
                        if n0 < 0:
                            continue
                        nil_opts = (n0,)
                    else:
                        budget = max_w - cur - ln
                        if budget < 0:
                            continue
                        abut = right is None or sl[0][1] == right
                        max_free = W_a - cur - ln
                        if max_free < 0:
                            max_free = 0
                        hi = budget if budget < max_free else max_free
                        if packed:
                            if abut:
                                nil_opts = (0,)
                            elif hi >= 1:
                                nil_opts = (1,)
                            else:
                                continue
                        else:
                            opts = []
                            seen = set()
                            def add(n):
                                if n not in seen:
                                    seen.add(n)
                                    opts.append(n)
                            if abut:
                                add(0)
                            elif hi >= 1:
                                add(1)
                            g0 = sl[0][2]
                            for i in gate_cols.get(g0, ()):
                                n_nil = i - cur
                                if 0 <= n_nil <= hi and not (n_nil == 0 and not abut):
                                    add(n_nil)
                            k = 0
                            while cur + k < W_a and gate_at[cur + k] is None:
                                k += 1
                            if 0 < k <= hi:
                                add(k)
                            if not opts:
                                add(0 if abut or hi < 1 else 1)
                            nil_opts = opts
                    for n_nil in nil_opts:
                        start = cur + n_nil
                        end = start + ln
                        if end > max_w:
                            continue
                        if not empty_res:
                            if not is_f:
                                bad = False
                                for c in range(start, end):
                                    if c in reserved:
                                        bad = True
                                        break
                                if bad:
                                    continue
                                bad = False
                                for i in range(n_nil):
                                    if (cur + i) in reserved:
                                        bad = True
                                        break
                                if bad:
                                    continue
                            elif locked and start != pos[t.frozen_id][0]:
                                continue
                        if n_nil == 0 and right is not None and sl[0][1] != right:
                            continue
                        if n_nil:
                            new = cols + (None,) * n_nil + sl
                        else:
                            new = cols + sl
                        nxt.append((new, nrem, sl[-1][3], n_occ + ln))
        if not nxt:
            break
        th = routability if step >= ntiles // 2 else 0.0
        ranked = [((len(c), -occ), (c, r, rt, occ)) for c, r, rt, occ in nxt]
        kept = prune(ranked, key=lambda z: z[0], threshold=th, cap=capn)
        beam = [st for _, st in kept]
    out = []
    for cols, rem, _rt, _occ in beam:
        if rem:
            continue
        if len(cols) < W_a:
            cols = cols + (None,) * (W_a - len(cols))
        if len(cols) > max_w:
            continue
        out.append(cols)
    return out[:capn]
