"""Prove della gestione del personale: ingressi, uscite, graduatoria; il passato non cambia."""
import os, shutil, sys, tempfile
from datetime import date, timedelta
from dct.db import importa_da_xlsm, ArchivioDB
from dct.copertura import Motore
from dct import personale as pe
from confronta import righe_python

XLSM = sys.argv[1]
TMP = tempfile.mkdtemp()
importa_da_xlsm(XLSM, os.path.join(TMP, "a.db"))
a = ArchivioDB(os.path.join(TMP, "a.db"))
OK = KO = 0
OGGI = date(2026, 10, 23)


def check(nome, cond, extra=""):
    global OK, KO
    if cond:
        OK += 1
    else:
        KO += 1
        print("  FALLITO:", nome, extra)


def errore(f, *x):
    try:
        f(*x)
    except pe.ErrorePersonale as e:
        return str(e)


def giorni(da, n):
    m = Motore(a)
    return {da + timedelta(i): righe_python(m.calcola_giorno(da + timedelta(i))) for i in range(n)}


prima = giorni(date(2026, 11, 16), 28)
grad0 = pe.graduatoria(a)
check("graduatoria letta", grad0[0] == "Famà" and len(grad0) == 8)

# dati di VESTIZIONE_DCT_15: Baietti (pos 6) e Canta (pos 13) escono il 6/12, dal 7/12 entrano Giordano e Famà
check("subentri gia' programmati", pe.elenco(a, date(2026, 12, 6))[5][1] == "Baietti" and pe.elenco(a, date(2026, 12, 7))[5][1] == "Giordano"
      and pe.elenco(a, date(2026, 12, 7))[12][1] == "Famà")
check("posizione occupata rifiutata", errore(pe.ingresso, a, 6, "Romano", date(2026, 12, 20), OGGI))
check("gia' programmato altrove", errore(pe.ingresso, a, 12, "Famà", date(2027, 1, 1), OGGI))

# Conte (pos 8) esce il 30/11; entra dalla graduatoria il primo non gia' programmato, dal 1/12
nuovo = [n for n in grad0 if n not in ("Famà", "Giordano")][0]
pe.uscita(a, 8, date(2026, 11, 30), OGGI)
check("uscita registrata", pe.elenco(a, date(2026, 11, 30))[7][1] == "Conte" and pe.elenco(a, date(2026, 12, 1))[7][1] == "")
pe.ingresso(a, 8, nuovo, date(2026, 12, 1), OGGI)
check("subentrato", pe.elenco(a, date(2026, 12, 1))[7][1] == nuovo and pe.elenco(a, date(2026, 11, 30))[7][1] == "Conte")
check("esce dalla graduatoria", pe.graduatoria(a) == [n for n in grad0 if n != nuovo])
dopo = giorni(date(2026, 11, 16), 28)
check("passato invariato", all(prima[d] == dopo[d] for d in prima if d < date(2026, 12, 1)))
check("dal 1/12 si vede il nuovo al posto di Conte",
      any(nuovo in str(dopo[d]) for d in dopo if d >= date(2026, 12, 1)) and not any("Conte" in str(dopo[d]) for d in dopo if d >= date(2026, 12, 1)))

# posizione libera (4): ingresso diretto
pe.ingresso(a, 4, "Nuovo Nome", date(2027, 1, 11), OGGI, da_graduatoria=False)
check("pos. libera: prima vuota", pe.elenco(a, date(2027, 1, 10))[3][1] == "")
check("pos. libera: dopo occupata", pe.elenco(a, date(2027, 1, 11))[3][1] == "Nuovo Nome")
check("gruppo conservato", pe.elenco(a, date(2027, 1, 11))[3][2] == "G")

# persistenza
a.salva()
b = ArchivioDB(os.path.join(TMP, "a.db"))
mb = Motore(b)
check("persistente", mb.chi_in_servizio(8, date(2026, 12, 5)) == nuovo and mb.chi_in_servizio(8, date(2026, 11, 5)) == "Conte"
      and mb.chi_in_servizio(6, date(2026, 12, 8)) == "Giordano")

# regole
check("passato rifiutato", errore(pe.uscita, a, 6, date(2026, 10, 1), OGGI))
check("uscita su posizione libera", errore(pe.uscita, a, 12, date(2026, 12, 1), OGGI))
check("gia' in servizio altrove", errore(pe.ingresso, a, 12, "Moro", date(2026, 12, 1), OGGI))
check("nome vuoto", errore(pe.ingresso, a, 12, " ", date(2026, 12, 1), OGGI))
check("posizione non valida", errore(pe.ingresso, a, 15, "X", date(2026, 12, 1), OGGI))

# annullamenti
pe.annulla_ingresso(a, 4, date(2027, 1, 11), OGGI)
check("ingresso annullato", pe.elenco(a, date(2027, 1, 12))[3][1] == "")
pe.uscita(a, 14, date(2027, 2, 28), OGGI)
pe.ingresso(a, 14, "Altro", date(2027, 3, 1), OGGI, da_graduatoria=False)
check("annulla uscita con subentro rifiutato", errore(pe.annulla_uscita, a, 14, OGGI) is not None)
pe.annulla_ingresso(a, 14, date(2027, 3, 1), OGGI)
pe.annulla_uscita(a, 14, OGGI)
check("uscita annullata", pe.elenco(a, date(2027, 3, 1))[13][1] == "Ghiorzi")
check("annulla senza uscita", errore(pe.annulla_uscita, a, 14, OGGI))

# graduatoria
pe.aggiungi_in_graduatoria(a, "Rossi")
check("in fondo", pe.graduatoria(a)[-1] == "Rossi")
pe.aggiungi_in_graduatoria(a, "Bruni", 1)
check("in testa", pe.graduatoria(a)[0] == "Bruni")
pe.sposta_in_graduatoria(a, "Rossi", 2)
check("spostato", pe.graduatoria(a)[:3] == ["Bruni", "Rossi", grad0[0]])
check("doppione rifiutato", errore(pe.aggiungi_in_graduatoria, a, "rossi"))
pe.togli_dalla_graduatoria(a, "Bruni")
check("tolto", "Bruni" not in pe.graduatoria(a))
check("togli inesistente", errore(pe.togli_dalla_graduatoria, a, "Bruni"))
check("numerazione continua", [r[0] for r in a.con.execute("SELECT ordine FROM graduatoria ORDER BY ordine")] == list(range(1, len(pe.graduatoria(a)) + 1)))

print("   prove riuscite: %d, fallite: %d" % (OK, KO))
sys.exit(1 if KO else 0)
