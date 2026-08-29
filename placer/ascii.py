def _colw(rows, kind):
    W = len(rows[0]) if rows else 0
    ws = [3] * W
    for c in range(W):
        for row in rows:
            sl = row[c]
            if kind == 'dev':
                s = 'nil' if not sl else sl[0]
            else:
                s = 'nil nil nil' if not sl else '%s %s %s' % (sl[1], sl[2], sl[3])
            if len(s) > ws[c]:
                ws[c] = len(s)
    return ws


def _rowline(label, row, ws, kind):
    parts = [label]
    for c, sl in enumerate(row):
        if kind == 'dev':
            s = 'nil' if not sl else sl[0]
        else:
            s = 'nil nil nil' if not sl else '%s %s %s' % (sl[1], sl[2], sl[3])
        parts.append(s.ljust(ws[c]))
    return ' '.join(parts)


def render(rows, types, header, kind='dev'):
    ws = _colw(rows, kind)
    lines = [header]
    # top to bottom: last row first
    for i in range(len(rows) - 1, -1, -1):
        lab = '%s%d' % (types[i], i)
        lines.append(_rowline(lab.ljust(4), rows[i], ws, kind))
    return '\n'.join(lines)


def dump(rows, types, rank_line):
    a = render(rows, types, rank_line, 'dev')
    b = render(rows, types, rank_line, 'net')
    return a + '\n\n' + b


def order_line(rows, bydev):
    """NPPN top-to-bottom: '*name' if flipped (MY), else name (R0).
    'names; names, MY R0; R0 R0, W, 0'  nil columns omitted from names."""
    name_rows, ori_rows = [], []
    W = len(rows[0]) if rows else 0
    for i in range(len(rows) - 1, -1, -1):
        names, oris = [], []
        for sl in rows[i]:
            if not sl:
                continue
            nm = sl[0]
            d = bydev.get(nm)
            flipped = bool(d) and sl[1] != d.source
            names.append(('*' if flipped else '') + nm)
            oris.append('MY' if flipped else 'R0')
        name_rows.append(' '.join(names))
        ori_rows.append(' '.join(oris))
    return '%s, %s, %d, 0' % ('; '.join(name_rows), '; '.join(ori_rows), W)
