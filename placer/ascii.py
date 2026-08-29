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
