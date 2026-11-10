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
check("608 resta scoperto (8/11)", rr["608"].scoperto and rr["608"].nome == "Scoperto")
# regola Dd5 (06/11/2026): nei feriali e il sabato il Dd5 (ultimo della coda) copre il turno principale scoperto
# che inizia piu' tardi; la domenica quel ruolo e' del 606 e il Dd5 resta nella coda normale
g = Motore(a).calcola_giorno(date(2026, 11, 16))
rr = {x.codice: x for x in g.turni}
check("Dd5 copre il 610, il piu' tardi (16/11)", rr["610"].nome == "Canta", rr["610"].nome)
check("605 resta scoperto (16/11)", rr["605"].scoperto)
g = Motore(a).calcola_giorno(date(2026, 10, 25))
rr = {x.codice: x for x in g.turni}
check("domenica: Dd5 nella coda normale (25/10)", rr["602"].nome == "Baietti" and any(s.codice == "630" and s.nome == "Roli" for s in g.sussidiari), rr["602"].nome)
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
# su tutti i giorni da ottobre a dicembre: l'ultimo della coda (Dd5 feriali/sabato) ha il turno che inizia piu' tardi
# tra quelli coperti dai disponibili o rimasti scoperti, sussidiari compresi; sussidiari in ordine di orario
from datetime import timedelta as _td
mm = Motore(a); ko = []; casi = 0
dd = date(2026, 10, 1)
while dd <= date(2026, 12, 31):
    g = mm.calcola_giorno(dd)
    coda = mm.coda_disp(g.modalita, dd)
    disp = mm._raccogli_disponibilita(mm.dati_giorno(dd), g.modalita, dd)
    nomi_disp = {x[2] for x in disp}
    ult = [x[2] for x in disp if coda and x[1] == coda[-1] and coda[-1] != "606"]
    ora = lambda r, s: (mm.orario_suss(r.codice, g.modalita, dd) if s else mm.orario_turno(r.codice, g.modalita, dd)) or "99:99"
    righe = [(r, False) for r in g.turni] + [(r, True) for r in g.sussidiari]
    if ult:
        mio = [ora(r, s_) for r, s_ in righe if r.nome == ult[0] and (r.nome in nomi_disp)]
        altri = [ora(r, s_) for r, s_ in righe if (r.scoperto or r.nome in nomi_disp) and r.nome != ult[0]]
        if mio:
            casi += 1
            if altri and mio[0] < max(altri):
                ko.append(dd)
    oo = [mm.orario_suss(r.codice, g.modalita, dd) for r in g.sussidiari]
    if oo != sorted(oo):
        ko.append(("ordine sussidiari", dd))
    dd += _td(days=1)
check("Dd5 sempre sul turno piu' tardi e sussidiari in ordine (%d casi)" % casi, not ko and casi > 0, ko[:5])

# domenica e festivi (09/11/2026): al massimo 7 turni coperti, eccedenti tra gli assenti con FU/CU, nessuno sparisce
ko = []; casi = 0
dd = date(2026, 10, 1)
while dd <= date(2027, 12, 31):
    if a.cella(dd, 1) is None:
        dd += _td(days=1); continue
    g = mm.calcola_giorno(dd)
    dati = mm.dati_giorno(dd)
    nomi = {t.nome for t in g.turni} | {s_.nome for s_ in g.sussidiari} | {x.nome for x in g.assenti}
    if any(dati[p].nome and dati[p].nome not in nomi for p in range(1, 15)):
        ko.append(("sparito", dd))
    if g.modalita == "Domenica":
        ecc = [x for x in g.assenti if x.motivazione in ("FU", "CU")]
        mx = mm.max_turni_festivi(dd)     # 7, a Natale 8
        if len(g.turni) + len(g.sussidiari) > mx:
            ko.append(("piu' di %d" % mx, dd))
        if g.presenti > mx:
            casi += 1
            if len(ecc) != g.presenti - mx:
                ko.append(("eccedenti", dd, len(ecc), g.presenti))
            if any(x.motivazione != ("CU" if dd.weekday() == 6 else "FU") for x in ecc):
                ko.append(("FU/CU", dd))
    dd += _td(days=1)
check("domenica/festivi: max 7 turni, eccedenti FU/CU, nessuno sparito (%d casi)" % casi, not ko, ko[:5])

# turni di Natale (09/11/2026, VBA v18): solo il 25/12, 7 principali + 630, coda senza 606, eccedenti FU dal nono
for anno_n in (2026, 2027):
    dn = date(anno_n, 12, 25)
    g = mm.calcola_giorno(dn)
    cod = [t.codice for t in g.turni]
    check("Natale %d: 8 principali col 606 e il 630" % anno_n, cod == ["603", "605", "604", "608", "606", "602", "630", "610"], cod)
    check("Natale %d: nessun sussidiario" % anno_n, not g.sussidiari)
    ecc = [x for x in g.assenti if x.motivazione in ("FU", "CU")]
    check("Natale %d: eccedenti in FU" % anno_n, len(ecc) == max(0, g.presenti - 8) and all(x.motivazione == "FU" for x in ecc), (g.presenti, ecc))
    check("Natale %d: coda senza 606" % anno_n, mm.coda_disp(g.modalita, dn) == ["601", "607V", "Dd8", "Dd2", "Dd5"])
    check("Natale %d: orari propri" % anno_n, mm.orario_turno("603", g.modalita, dn) == "07:45" and mm.orario_turno("630", g.modalita, dn) == "20:15")
    dsp = {x[1]: x[2] for x in mm._raccogli_disponibilita(mm.dati_giorno(dn), g.modalita, dn)}
    if "Dd5" in dsp:
        check("Natale %d: il Dd5 non e' mai eccedente" % anno_n, not any(x.nome == dsp["Dd5"] and x.motivazione == "FU" for x in g.assenti))
g26 = mm.calcola_giorno(date(2026, 12, 26))
check("26/12 festivo normale", [t.codice for t in g26.turni] == ["603", "605", "604", "608", "602", "610"] and "606" in mm.coda_disp(g26.modalita, date(2026, 12, 26)))
g24 = mm.calcola_giorno(date(2026, 12, 24))
check("24/12 orari normali", mm.orario_turno("603", g24.modalita, date(2026, 12, 24)) != "07:45")
# Config_Natale letto dal file Excel (foglio nascosto del VBA v18)
import openpyxl as _ox
from datetime import time as _tm, datetime as _dtm
from dct.db import _leggi_config_natale
_wb = _ox.Workbook(); _ws = _wb.active; _ws.title = "Config_Natale"
_ws.append(["ValidoDal", "Tipo", "Codice", "Ordine", "Inizio", "Fine"])
_ws.append([_dtm(2028, 12, 25), "TURNO", "603", 1, _tm(8, 0), _tm(12, 0)])
_ws.append([_dtm(2028, 12, 25), "PARAM", "TurniCoperti", 9, None, None])
rr_ = _leggi_config_natale(_wb)
check("Config_Natale dal file", rr_ == [("2028-12-25", "TURNO", "603", 1, "08:00", "12:00"), ("2028-12-25", "PARAM", "TurniCoperti", 9, "", "")], rr_)

print("   prove riuscite: %d, fallite: %d" % (OK, KO))
sys.exit(1 if KO else 0)
