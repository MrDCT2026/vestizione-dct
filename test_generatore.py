"""La rotazione generata deve coincidere con quella del file (ott-dic 2026) e restare coerente nel 2027."""
import os, shutil, sys, tempfile
from datetime import date, timedelta
from dct.db import importa_da_xlsm, ArchivioDB, genera_anno
from dct.generatore import genera_valori

tmp = tempfile.mkdtemp()
p = os.path.join(tmp, "t.db")
importa_da_xlsm(sys.argv[1], p)
a = ArchivioDB(p)
v = genera_valori(2026)
diff = [(k, a.cella(*k).valore, x) for k, x in v.items() if a.cella(*k) and a.cella(*k).valore != x]
n = sum(1 for k in v if a.cella(*k))
print("2026: %d celle del file confrontate, differenze: %d" % (n, len(diff)))
assert not diff and n > 0
if a.cella(date(2027, 1, 1), 1) is None:
    genera_anno(a, 2027)
else:
    # il file contiene gia' il 2027: la rotazione generata deve coincidere con quella del file
    v7 = genera_valori(2027)
    d7 = [(k, a.cella(*k).valore, x) for k, x in v7.items() if a.cella(*k) and a.cella(*k).valore != x]
    print("2027 (gia' nel file): %d celle confrontate, differenze: %d" % (sum(1 for k in v7 if a.cella(*k)), len(d7)), d7[:5])
    assert not d7
try:
    genera_anno(a, 2027)
    raise SystemExit("doveva rifiutare la rigenerazione")
except ValueError:
    pass
d = date(2027, 1, 1)
anom = 0
while d <= date(2027, 12, 31):
    vals = [a.cella(d, q).valore for q in range(1, 15)]
    lav = sum(x != "R" for x in vals)
    assert lav in (8, 9, 10, 11, 12), (d, lav)
    if d.weekday() < 5:
        for t in ("601", "602", "603", "604", "605", "606", "608", "610"):
            if vals.count(t) != 1:
                anom += 1
    d += timedelta(days=1)
print("2027: giorni feriali con un turno principale mancante o doppio:", anom)
assert anom == 0
print("OK")
