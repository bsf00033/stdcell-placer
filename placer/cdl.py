from dataclasses import dataclass


@dataclass
class Device:
    name: str
    typ: str
    drain: str
    gate: str
    source: str
    bulk: str
    w: str
    l: str


@dataclass
class Cell:
    name: str
    pins: list
    pininfo: dict
    devices: list


def _strip(raw):
    """Drop * comments and $ comments. Keep $W= params."""
    s = []
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == '*':
            break
        if c == '$':
            rest = raw[i + 1:]
            if rest[:1].isalpha() and '=' in rest.split()[0]:
                s.append(c)
                i += 1
                continue
            break
        s.append(c)
        i += 1
    return ''.join(s).strip()


def _lines(path):
    """Join SPICE/CDL + continuations."""
    buf = []
    for raw in open(path):
        line = _strip(raw)
        if not line:
            continue
        if line[0] == '+':
            if buf:
                buf[-1] = buf[-1] + ' ' + line[1:].strip()
            continue
        buf.append(line)
    return buf


def _mos_type(model):
    mu = model.upper()
    ni, pi = mu.find('N'), mu.find('P')
    if ni < 0 and pi < 0:
        raise ValueError('bad MOS model ' + model)
    return 'N' if pi < 0 or (ni >= 0 and ni < pi) else 'P'


def infer_pininfo(pins, devices, pininfo):
    """Rails from S/D (not bulk). N-only S/D pin is VSS, P-only is VDD. Bulk ignored."""
    out = dict(pininfo)
    n_sd, p_sd = set(), set()
    for d in devices:
        sd = {d.source, d.drain}
        if d.typ == 'N':
            n_sd |= sd
        else:
            p_sd |= sd
    pinset = set(pins)

    def pick(cands, role):
        if role in out.values():
            return
        cands = [n for n in cands if n]
        if pinset:
            cands = [n for n in cands if n in pinset] or cands
        if not cands:
            return
        g = next((p for p in pins if p in cands), cands[0])
        out.setdefault(g, role)

    pick(n_sd - p_sd, 'G')
    pick(p_sd - n_sd, 'P')
    for pin in pins:
        out.setdefault(pin, 'I')
    return out


def parse(path):
    name, pins, pininfo, devices = None, [], {}, []
    for line in _lines(path):
        u = line.upper()
        if u.startswith('.SUBCKT'):
            if name:
                break
            parts = line.replace('(', ' ').replace(')', ' ').split()
            name, pins = parts[1], [x.upper() for x in parts[2:]]
        elif u.startswith('.PININFO'):
            for tok in line.split()[1:]:
                if ':' in tok:
                    p, r = tok.split(':', 1)
                    pininfo[p.upper()] = r.upper()
        elif u.startswith('.ENDS'):
            break
        elif u[0] == 'M':
            parts = line.replace('(', ' ').replace(')', ' ').split()
            if len(parts) < 6:
                raise ValueError('bad MOS line ' + line)
            d, g, s, b = [x.upper() for x in parts[1:5]]
            model = parts[5]
            kv = {}
            for t in parts[6:]:
                if '=' in t:
                    k, v = t.split('=', 1)
                    kv[k.upper().lstrip('$')] = v
            devices.append(Device(parts[0], _mos_type(model), d, g, s, b,
                                  kv.get('W', ''), kv.get('L', '')))
    if not name or not devices:
        raise ValueError('bad CDL: need .SUBCKT and at least one MOS')
    pininfo = infer_pininfo(pins, devices, pininfo)
    return Cell(name, pins, pininfo, devices)
