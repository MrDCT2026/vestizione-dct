"""Confronta il motore Python con le settimane gia' calcolate dal VBA nel file xlsm."""
import sys, re
from datetime import date, timedelta
from dct.xlsm import Archivio
from dct.copertura import Motore
from dct.calendario import lunedi_settimana



def righe_python(g):
    out = []
    for t in g.turni:
        out.append((t.codice, t.nome, t.nota))
    for s in g.sussidiari:
        if not s.scoperto and s.nome.strip():
            out.append((s.codice, s.nome, s.nota))
    for i, a in enumerate(g.assenti):
        out.append(("Ass.:" if i == 0 else "", a.nome, a.motivazione))
    return out


def s(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def righe_foglio(ws, riga0, col, fine):
    out = []
    for r in range(riga0 + 1, fine):
        t = (s(ws.cell(r, col).value), s(ws.cell(r, col + 1).value), s(ws.cell(r, col + 2).value))
        if t == ("", "", ""):      # il giorno finisce alla prima riga vuota (sotto ci sono le note)
            break
        if re.match(r'^[A-Za-zì]+\s+\d\d/\d\d/\d{4}$', t[0]):
            continue
        out.append(t)
    return out


INTESTAZIONE = re.compile(r'^[A-Za-zì]+\s+(\d\d)/(\d\d)/(\d{4})$')


def blocchi(ws):
    """{data: (riga intestazione, colonna, riga di fine)}: le intestazioni dei giorni si cercano nel foglio,
    perche' la macro le sposta in basso quando un giorno della riga sopra ha piu' righe (es. settimana 45)."""
    out = {}
    for col in (1, 5, 9):
        teste = []
        for r in range(1, 80):
            m = INTESTAZIONE.match(s(ws.cell(r, col).value))
            if m:
                teste.append((r, date(int(m.group(3)), int(m.group(2)), int(m.group(1)))))
        for i, (r, d) in enumerate(teste):
            out[d] = (r, col, teste[i + 1][0] if i + 1 < len(teste) else 80)
    return out


def confronta(arch, anno, nn):
    ws = arch.foglio_settimana(anno, nn)
    if ws is None:
        return None
    m = Motore(arch)
    lun = lunedi_settimana(anno, nn)
    pos = blocchi(ws)
    diff = []
    for g in range(7):
        d = lun + timedelta(days=g)
        if d not in pos:
            diff.append((d, "giorno non trovato nel foglio", None))
            continue
        riga0, col, fine = pos[d]
        atteso = righe_foglio(ws, riga0, col, fine)
        trovato = righe_python(m.calcola_giorno(d))
        if atteso != trovato:
            diff.append((d, atteso, trovato))
    return diff


if __name__ == "__main__":
    arch = Archivio(sys.argv[1])
    for nn in map(int, sys.argv[2:]):
        r = confronta(arch, 2026, nn)
        if r is None:
            print("settimana", nn, "assente"); continue
        print("settimana", nn, "->", "UGUALE" if not r else "%d giorni diversi" % len(r))
        for d, a, t in r:
            print(" ", d)
            print("   foglio:", a)
            print("   python:", t)
