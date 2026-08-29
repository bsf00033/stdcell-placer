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


def parse(path):
    name, pins, pininfo, devices = None, [], {}, []
    for raw in open(path):
        line = raw.split('*', 1)[0].strip()
        if not line:
            continue
        u = line.upper()
        if u.startswith('.SUBCKT'):
            parts = line.split()
            name, pins = parts[1], parts[2:]
        elif u.startswith('.PININFO'):
            for tok in line.split()[1:]:
                p, r = tok.split(':')
                pininfo[p] = r.upper()
        elif u.startswith('.ENDS'):
            break
        elif u[0] == 'M':
            parts = line.split()
            d, g, s, b, model = parts[1:6]
            kv = {}
            for t in parts[6:]:
                if '=' in t:
                    k, v = t.split('=', 1)
                    kv[k.upper()] = v
            mu = model.upper()
            # technology-agnostic: first N or P in the model name (nch_lvt, pch, nmos, pfet, ...)
            ni, pi = mu.find('N'), mu.find('P')
            if ni < 0 and pi < 0:
                raise ValueError('bad MOS model ' + model)
            typ = 'N' if pi < 0 or (ni >= 0 and ni < pi) else 'P'
            devices.append(Device(parts[0], typ, d, g, s, b, kv.get('W', ''), kv.get('L', '')))
    if not name or not pininfo or not devices:
        raise ValueError('bad CDL')
    return Cell(name, pins, pininfo, devices)
