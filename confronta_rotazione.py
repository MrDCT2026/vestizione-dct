"""Confronta due file Rotazione: celle (valori, riempimento, carattere, bordi), unioni, note, _base, _note."""
import sys, openpyxl


def sig(c):
    f, fo, b = c.fill, c.font, c.border
    fg = f.fgColor.rgb if (f.fill_type == "solid" and f.fgColor.type == "rgb") else None
    col = fo.color.rgb if (fo.color is not None and fo.color.type == "rgb") else None
    bs = tuple((getattr(b, s).style if getattr(b, s) is not None else None) for s in ("left", "right", "top", "bottom"))
    dg = (b.diagonal.style if b.diagonalDown and b.diagonal is not None else None)
    al = c.alignment
    return (fg, bool(fo.b), bool(fo.i), fo.sz, col, bs, dg, al.horizontal, al.vertical, bool(al.wrap_text))


def conf(pa, pb):
    A = openpyxl.load_workbook(pa, keep_vba=True)
    B = openpyxl.load_workbook(pb, keep_vba=True)
    print("fogli:", A.sheetnames, B.sheetnames)
    wa, wb = A[A.sheetnames[0]], B[B.sheetnames[0]]
    dv = ds = 0
    esempi = []
    for r in range(1, 70):
        for c in range(1, 37):
            ca, cb = wa.cell(r, c), wb.cell(r, c)
            if ca.value != cb.value:
                dv += 1
                if len(esempi) < 8: esempi.append(("valore", ca.coordinate, ca.value, cb.value))
            if sig(ca) != sig(cb):
                ds += 1
                if len(esempi) < 16: esempi.append(("stile", ca.coordinate, sig(ca), sig(cb)))
    print("celle con valore diverso:", dv, " con stile diverso:", ds)
    for e in esempi: print("  ", e)
    ma, mb = sorted(map(str, wa.merged_cells.ranges)), sorted(map(str, wb.merged_cells.ranges))
    print("unioni uguali:", ma == mb, "" if ma == mb else (set(ma) ^ set(mb)))
    ha = {r: wa.row_dimensions[r].height for r in range(1, 61)}
    hb = {r: wb.row_dimensions[r].height for r in range(1, 61)}
    print("altezze righe uguali:", ha == hb)
    wid = lambda w: {k: v.width for k, v in w.column_dimensions.items()}
    print("larghezze colonne uguali:", wid(wa) == wid(wb))
    na = {c.coordinate: c.comment.text for row in wa.iter_rows() for c in row if c.comment}
    nb = {c.coordinate: c.comment.text for row in wb.iter_rows() for c in row if c.comment}
    print("note sulle celle:", na == nb, len(na), len(nb))
    ba, bb = A["_base"], B["_base"]
    d = sum(1 for r in range(1, 501) for c in range(1, 36) if ba.cell(r, c).value != bb.cell(r, c).value)
    print("_base: celle diverse:", d, " anno:", ba["AL1"].value, bb["AL1"].value)
    print("_note:", [[c.value for c in r] for r in B["_note"].iter_rows(max_row=3)])
    print("macro presente:", A.vba_archive is not None, B.vba_archive is not None)


conf(sys.argv[1], sys.argv[2])
