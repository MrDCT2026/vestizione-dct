"""Prova: ricostruisce la Rotazione partendo dallo stato di una Rotazione esistente e la confronta con l'originale."""
import sys, os, shutil, tempfile, openpyxl
from datetime import date, timedelta
from dct.db import importa_da_xlsm, ArchivioDB
from dct.xlsm import Archivio
from dct.rotazione import esporta_rotazione

VEST, ROT = sys.argv[1], sys.argv[2]
tmp = tempfile.mkdtemp()
db = os.path.join(tmp, "t.db")
importa_da_xlsm(VEST, db)
a = ArchivioDB(db)
r = Archivio.__new__(Archivio)
r.wb = openpyxl.load_workbook(ROT, keep_vba=True)
d = date(2026, 10, 1)
while d <= date(2026, 12, 31):
    for pos in range(1, 15):
        c = r.cella(d, pos)
        a.imposta_cella(d, pos, c.tipo, c.diag)
    d += timedelta(days=1)
a.salva()
out = os.path.join(tmp, "out.xlsm")
esporta_rotazione(a, 2026, ROT, out)
shutil.copy(out, sys.argv[3])
