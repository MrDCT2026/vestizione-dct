"""Prove dell'importazione: ogni caso corrisponde a una regola del confronto a tre."""
import os, shutil, sys, tempfile
from datetime import date
import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import PatternFill
from dct.db import importa_da_xlsm, ArchivioDB
from dct.operazioni import Operazioni
from dct.copertura import Motore
from dct.rotazione import esporta_rotazione, TIPO_COLORE
from dct.importa import analizza, applica, riepilogo, ErroreImport, colore_cella, _tema_rgb

XLSM = sys.argv[1]
MODELLO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modello", "Rotazione_modello.xlsm")
TMP = tempfile.mkdtemp()
BASE = os.path.join(TMP, "base.db")
importa_da_xlsm(XLSM, BASE)
OK = KO = 0
SETT = 49   # 30/11 - 6/12/2026
G = date(2026, 12, 3)


def check(nome, cond, extra=""):
    global OK, KO
    if cond:
        OK += 1
    else:
        KO += 1
        print("  FALLITO:", nome, extra)


def nuovo():
    p = os.path.join(TMP, "t.db")
    shutil.copy(BASE, p)
    a = ArchivioDB(p)
    return a, Operazioni(a)


def cella_xl(d, pos):
    return (3 + (d.month - 10) * 19 + 2 + pos, 3 + d.day)


def esporta(a, nome="rot.xlsm"):
    p = os.path.join(TMP, nome)
    esporta_rotazione(a, 2026, MODELLO, p)
    return p


def modifica(p, colori=(), note=(), nome_out="coll.xlsx"):
    """Simula il collega: colora celle e scrive note nel file esportato."""
    wb = openpyxl.load_workbook(p)
    ws = wb["2026"]
    for d, pos, tipo in colori:
        r, c = cella_xl(d, pos)
        ws.cell(r, c).fill = PatternFill("solid", fgColor="FF" + TIPO_COLORE[tipo])
    for d, pos, testo in note:
        r, c = cella_xl(d, pos)
        ws.cell(r, c).comment = Comment(testo, "Autore")
    out = os.path.join(TMP, nome_out)
    wb.save(out)
    return out


def pos_val(op, d, v):
    for p in range(1, 15):
        if op.val(d, p) == v and not op.vuota(d, p) and op.tipo(d, p) == "":
            return p


def riposi(op, d, n):
    return [p for p in range(1, 15) if op.val(d, p) == "R" and not op.vuota(d, p) and op.tipo(d, p) == ""][:n]


# 1 nessuna modifica: nessuna differenza
a, op = nuovo()
f = esporta(a)
cambi, fuori, anno = analizza(a, modifica(f), 2026, SETT, SETT)
check("nessuna differenza", cambi == [] and anno == 2026)

# 2 assenza colorata dal collega: APPLICA, poi applicata
p605 = pos_val(op, G, "605")
f2 = modifica(f, colori=[(G, p605, "CONG_FEST")])
cambi, _, _ = analizza(a, f2, 2026, SETT, SETT)
check("assenza: una riga APPLICA", len(cambi) == 1 and cambi[0].stato == "APPLICA" and cambi[0].nuovo == "Cong./Fest.")
n_col, n_note = applica(a, cambi, 2026, "coll.xlsx")
check("assenza applicata", a.cella(G, p605).tipo == "CONG_FEST" and n_col == 1)
check("log scritto", a.con.execute("select count(*) from log_import").fetchone()[0] == 1)
cambi2, _, _ = analizza(a, f2, 2026, SETT, SETT)
check("riletto dopo l'applicazione: nessun conflitto", all(c.stato != "CONFLITTO" for c in cambi2))

# 3 conflitto: principale modificato dopo l'esportazione, collega cambia la stessa cella
a, op = nuovo()
f = esporta(a)
p605 = pos_val(op, G, "605")
op.applica_tasto("ASS_MAL", [(G, p605)])
cambi, _, _ = analizza(a, modifica(f, colori=[(G, p605, "CONG_FEST")]), 2026, SETT, SETT)
check("conflitto", len(cambi) == 1 and cambi[0].stato == "CONFLITTO")
applica(a, cambi, 2026, "x")
check("il conflitto non viene toccato", a.cella(G, p605).tipo == "ASS_MAL")

# 4 modificata solo nel principale: MANTENUTA
a, op = nuovo()
f = esporta(a)
p605 = pos_val(op, G, "605")
op.applica_tasto("ASS_MAL", [(G, p605)])
cambi, _, _ = analizza(a, modifica(f), 2026, SETT, SETT)
check("mantenuta", len(cambi) == 1 and cambi[0].stato == "MANTENUTA")

# 5 RL colorato dal collega: manuale
a, op = nuovo()
f = esporta(a)
r = riposi(op, G, 1)[0]
cambi, _, _ = analizza(a, modifica(f, colori=[(G, r, "RL")]), 2026, SETT, SETT)
check("RL: manuale", len(cambi) == 1 and cambi[0].stato == "MANUALE")

# 6 assenza su un riposo: saltata
cambi, _, _ = analizza(a, modifica(f, colori=[(G, r, "CONG_FEST")]), 2026, SETT, SETT)
check("assenza su riposo: saltata", len(cambi) == 1 and cambi[0].stato == "SALTATA")

# 7 cambio riposo personale riconosciuto e registrato
a, op = nuovo()
f = esporta(a)
pt, pr = pos_val(op, G, "604"), riposi(op, G, 1)[0]
cambi, _, _ = analizza(a, modifica(f, colori=[(G, pt, "C_RIP"), (G, pr, "C_RIP")]), 2026, SETT, SETT)
check("cambio riposo personale: 2 righe APPLICA", len(cambi) == 2 and all(c.stato == "APPLICA" for c in cambi))
applica(a, cambi, 2026, "x")
check("celle e registro", a.cella(G, pt).tipo == "C_RIP" and a.cella(G, pr).tipo == "C_RIP"
      and any(x.pos == pr and x.turno == "604" and x.tipo == "C_RIP" for x in a.assegnazioni))
t = [t for t in Motore(a).calcola_giorno(G).turni if t.codice == "604"][0]
check("il rientrante copre il turno", t.nome == Motore(a).chi_in_servizio(pr, G) and t.nota == "C. Rip.")
e = Operazioni(a).cancella(G, pt)
check("si puo' cancellare come dal programma", e.ok and a.cella(G, pt).tipo == "" and a.cella(G, pr).tipo == "")

# 8 una sola cella magenta: resta manuale
a, op = nuovo()
f = esporta(a)
cambi, _, _ = analizza(a, modifica(f, colori=[(G, pos_val(op, G, "604"), "C_RIP")]), 2026, SETT, SETT)
check("una sola magenta: manuale", len(cambi) == 1 and cambi[0].stato == "MANUALE")

# 9 note: nuova nota, nota anche nel principale (conflitto)
a, op = nuovo()
f = esporta(a)
p = pos_val(op, G, "603")
cambi, _, _ = analizza(a, modifica(f, note=[(G, p, "Autore:\nvisita medica")]), 2026, SETT, SETT)
check("nota nuova: APPLICA", len(cambi) == 1 and cambi[0].tipo == "NOTA" and cambi[0].stato == "APPLICA")
applica(a, cambi, 2026, "x")
check("nota scritta", "visita medica" in a.note_celle(2026)[(G, p)])
a, op = nuovo()
f = esporta(a)
a.imposta_nota(G, p, "Autore:\nnota del principale")
a.salva()
cambi, _, _ = analizza(a, modifica(f, note=[(G, p, "Autore:\nnota del collega")]), 2026, SETT, SETT)
check("nota in conflitto", len(cambi) == 1 and cambi[0].stato == "CONFLITTO")

# 10 solo le settimane richieste; giorni di un altro anno
a, op = nuovo()
f = esporta(a)
fuori = date(2026, 11, 10)
p = pos_val(op, fuori, "605")
cambi, _, _ = analizza(a, modifica(f, colori=[(fuori, p, "CONG_FEST")]), 2026, SETT, SETT)
check("modifiche fuori dalle settimane scelte ignorate", cambi == [])
cambi, nf, _ = analizza(a, modifica(f), 2026, 53, 53)
check("settimana a cavallo d'anno: giorni del 2027 non letti", nf == 3, nf)

# 11 posizione vuota ignorata
p = 4
cambi, _, _ = analizza(a, modifica(f, colori=[(G, p, "CONG_FEST")]), 2026, SETT, SETT)
check("posizione vuota ignorata", cambi == [])

# 12 file non valido
try:
    analizza(a, XLSM, 2026, SETT, SETT)
    check("file non valido rifiutato", False)
except ErroreImport:
    check("file non valido rifiutato", True)
except Exception as e:
    check("file non valido rifiutato", False, repr(e))
try:
    analizza(a, f, 2026, 40, 50)
    check("intervallo troppo ampio", False)
except ErroreImport:
    check("intervallo troppo ampio", True)

# 13 colori del tema (colleghi che scelgono il colore dalla tavolozza, es. su iPad)
wb = openpyxl.load_workbook(f)
tema = _tema_rgb(wb)
c = wb["2026"].cell(10, 10)
from openpyxl.styles.colors import Color
c.fill = PatternFill("solid", fgColor=Color(theme=0))
check("colore di tema bianco", colore_cella(c, tema) == 16777215)
c.fill = PatternFill("solid", fgColor=Color(rgb="FFFFFF00"))
check("colore rgb giallo", colore_cella(c, tema) == 65535)

# 14 applicazione atomica: se qualcosa fallisce non resta niente a meta'
a, op = nuovo()
f = esporta(a)
p1, p2 = pos_val(op, G, "605"), pos_val(op, G, "604")
cambi, _, _ = analizza(a, modifica(f, colori=[(G, p1, "CONG_FEST"), (G, p2, "ASS_MAL")]), 2026, SETT, SETT)
cambi[1].data = None   # guasto simulato
try:
    applica(a, cambi, 2026, "x")
except Exception:
    pass
check("tutto o niente", a.cella(G, p1).tipo == "" and a.con.execute("select count(*) from log_import").fetchone()[0] == 0)

print("prove riuscite: %d, fallite: %d" % (OK, KO))
sys.exit(1 if KO else 0)
