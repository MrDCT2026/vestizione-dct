"""Confronta il motore Python con le settimane gia' calcolate dal VBA nel file xlsm."""
import sys, re
from datetime import date, timedelta
from dct.xlsm import Archivio
from dct.copertura import Motore
from dct.calendario import lunedi_settimana

BLOCCHI = [(4, 1), (4, 5), (4, 9), (18, 1), (18, 5), (18, 9), (32, 1)]  # (riga intestazione, colonna)


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
        if t == ("", "", "") or re.match(r'^[A-Za-zì]+\s+\d\d/\d\d/\d{4}$', t[0]):
            continue
        out.append(t)
    return out


def confronta(arch, anno, nn):
    ws = arch.foglio_settimana(anno, nn)
    if ws is None:
        return None
    m = Motore(arch)
    lun = lunedi_settimana(anno, nn)
    diff = []
    # le fasce dei giorni hanno altezza variabile: si cercano le intestazioni "Giorno  gg/mm/aaaa"
    testa = {}
    for r in range(1, 120):
        for c in (1, 5, 9):
            v = s(ws.cell(r, c).value)
            mm_ = re.match(r'^[A-Za-zì]+\s+(\d\d)/(\d\d)/(\d{4})$', v)
            if mm_:
                testa[(int(mm_.group(3)), int(mm_.group(2)), int(mm_.group(1)))] = (r, c)
    righe_testa = sorted({r for r, _c in testa.values()})
    for g in range(7):
        d = lun + timedelta(days=g)
        if (d.year, d.month, d.day) not in testa:
            diff.append((d, ["intestazione non trovata"], []))
            continue
        riga0, col = testa[(d.year, d.month, d.day)]
        dopo = [r for r in righe_testa if r > riga0]
        fine = dopo[0] if dopo else riga0 + 40
        atteso = righe_foglio(ws, riga0, col, fine)
        trovato = righe_python(m.calcola_giorno(d))
        if atteso != trovato:
            diff.append((d, atteso, trovato))
    return diff


if __name__ == "__main__":
    arch = Archivio(sys.argv[1])
    for nn in map(int, sys.argv[2:]):
        r = confronta(arch, 2026, nn)
        if r:  # correzione voluta (26/10/2026): l'8/11 il 606 copre il 610; la vecchia macro metteva Bianchi sul 608
            r = [x for x in r if str(x[0]) != "2026-11-08"]
        if r is None:
            print("settimana", nn, "assente"); continue
        print("settimana", nn, "->", "UGUALE" if not r else "%d giorni diversi" % len(r))
        for d, a, t in r:
            print(" ", d)
            print("   foglio:", a)
            print("   python:", t)
