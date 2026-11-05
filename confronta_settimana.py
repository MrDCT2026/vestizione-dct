"""Confronta il foglio settimana prodotto da Python con quello prodotto dalla macro nel file xlsm."""
import os, sys, tempfile
import openpyxl
from dct.db import importa_da_xlsm, ArchivioDB
from dct.settimana import costruisci_settimana


def col(c):
    if c is None:
        return None
    if c.type == "rgb":
        return c.rgb[-6:] if c.rgb not in (None, "00000000") else None
    if c.type == "theme":
        return "T%d" % c.theme if c.theme != 1 else None
    return "I%s" % c.indexed


def firma(c, unita):
    f, b, a = c.font, c.border, c.alignment
    fill = c.fill.fgColor.rgb[-6:] if c.fill.fill_type == "solid" else None
    v = c.value
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if v == "":
        v = None
    return dict(v=v, sz=f.sz, b=bool(f.b), i=bool(f.i), col=col(f.color), fill=fill,
                h=a.horizontal, va=a.vertical, wrap=bool(a.wrap_text),
                bord=(b.left.style, b.right.style, b.top.style, b.bottom.style))


def confronta(xlsm, anno, nn, db):
    wb0 = openpyxl.load_workbook(xlsm)
    ws0 = wb0["Settimana_%d_%d" % (anno, nn)]
    wb1, _ = costruisci_settimana(db, anno, nn)
    ws1 = wb1.active
    diff = []
    m0 = {str(r) for r in ws0.merged_cells.ranges}
    m1 = {str(r) for r in ws1.merged_cells.ranges}
    if m0 != m1:
        diff.append(("unioni", sorted(m0 - m1), sorted(m1 - m0)))
    interni0 = set()
    for r in ws0.merged_cells.ranges:
        for rr in range(r.min_row, r.max_row + 1):
            for cc in range(r.min_col, r.max_col + 1):
                if (rr, cc) != (r.min_row, r.min_col):
                    interni0.add((rr, cc))
    for r in range(1, 76):
        for c in range(1, 25):
            if (r, c) in interni0:
                continue
            a, b = firma(ws0.cell(r, c), 0), firma(ws1.cell(r, c), 1)
            vuota0 = a["v"] is None and a["fill"] is None and a["bord"] == (None,) * 4
            vuota1 = b["v"] is None and b["fill"] is None and b["bord"] == (None,) * 4
            if vuota0 and vuota1:
                continue
            if a["v"] is None and b["v"] is None:      # celle vuote: contano fondo e bordi
                a = {k: a[k] for k in ("fill", "bord")}
                b = {k: b[k] for k in ("fill", "bord")}
            if a["v"] == "Ass.:" if "v" in a else False:   # l'allineamento di "Ass.:" dipende da cosa c'era prima nella cella
                a["h"] = b["h"] = None
            if a != b:
                diff.append((ws0.cell(r, c).coordinate, {k: (a[k], b[k]) for k in a if a[k] != b.get(k)}))
    for r in range(1, 3):
        pass
    return diff


if __name__ == "__main__":
    xlsm = sys.argv[1]
    t = tempfile.mkdtemp()
    dbp = os.path.join(t, "a.db")
    importa_da_xlsm(xlsm, dbp)
    db = ArchivioDB(dbp)
    ok = True
    for nn in map(int, sys.argv[2:]):
        d = confronta(xlsm, 2026, nn, db)
        # correzione voluta (26/10/2026): l'8/11 il 606 copre il 610 (e resta scoperto il 608); il foglio della vecchia macro ha il contrario
        if nn == 45:
            d = [x for x in d if x[0] not in ("B37", "B39")]
        print("settimana", nn, "->", "UGUALE" if not d else "%d differenze" % len(d))
        for x in d[:40]:
            print("  ", x)
        ok = ok and not d
    sys.exit(0 if ok else 1)
