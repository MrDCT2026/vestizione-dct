"""Prove dell'esportazione settimana: confronto con la macro e Anagrafica nelle tabelle."""
import os, subprocess, sys, tempfile
from datetime import date
import openpyxl
from dct.db import importa_da_xlsm, ArchivioDB
from dct import anagrafica as an
from dct.settimana import esporta_settimana

XLSM = sys.argv[1]
OK = KO = 0


def check(nome, cond, extra=""):
    global OK, KO
    if cond:
        OK += 1
    else:
        KO += 1
        print("  FALLITO:", nome, extra)


r = subprocess.run([sys.executable, "confronta_settimana.py", XLSM, "43", "44", "45"], capture_output=True, text=True)
for riga in r.stdout.strip().splitlines():
    if riga.startswith("settimana"):
        check("macro " + riga, riga.endswith("UGUALE"), r.stdout)

t = tempfile.mkdtemp()
importa_da_xlsm(XLSM, os.path.join(t, "a.db"))
a = ArchivioDB(os.path.join(t, "a.db"))

# regola 606: il disponibile 606 della domenica copre il turno principale scoperto piu' tardi
from dct.copertura import Motore
g = Motore(a).calcola_giorno(date(2026, 11, 8))
rr = {x.codice: x for x in g.turni}
check("606 copre il 610 (8/11)", rr["610"].nome == "Bianchi" and not rr["610"].scoperto, rr["610"].nome)
check("608 coperto da Roli in RL (8/11)", rr["608"].nome == "Roli" and rr["608"].nota == "RL" and not rr["608"].scoperto, rr["608"].nome)
p = esporta_settimana(a, 2026, 45, t)
check("nome file", os.path.basename(p) == "Settimana_45_2026.xlsx")
wb = openpyxl.load_workbook(p)
check("nome foglio", wb.sheetnames == ["Settimana_2026_45"])
ws = wb.active
check("niente macro", not p.endswith("m"))

# l'Anagrafica arriva nelle tabelle: orario 603 feriale x
an.cambia_orari_turno(a, "603", "Feriale", "04:55", "11:33", date(2026, 11, 2), date(2026, 10, 23))
an.cambia_priorita_disponibilita(a, "Feriale", ["Dd8", "607V", "Dd2", "Dd5"], date(2026, 11, 2), date(2026, 10, 23))
p2 = esporta_settimana(a, 2026, 44, t)       # settimana 44 (26 ott-1 nov): non cambia
p3 = esporta_settimana(a, 2026, 45, t)       # settimana 45 (2-8 nov): cambia
w44, w45 = openpyxl.load_workbook(p2).active, openpyxl.load_workbook(p3).active
check("sett. 44 orario vecchio", w44["N20"].value == "04:50-11:28", w44["N20"].value)
check("sett. 45 orario nuovo", w45["N20"].value == "04:55-11:33", w45["N20"].value)
check("sett. 44 ordine disp. vecchio", w44["M36"].value == "607V Primo turno disp.", w44["M36"].value)
check("sett. 45 ordine disp. nuovo", w45["M36"].value == "Dd8 Primo turno disp." and w45["M39"].value == "Dd5 Ultimo turno disp.", w45["M36"].value)
print("   prove riuscite: %d, fallite: %d" % (OK, KO))
sys.exit(1 if KO else 0)
