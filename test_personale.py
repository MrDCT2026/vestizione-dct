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

# Baietti (pos 6) esce il 30/11; entra il primo della graduatoria dal 1/12
pe.uscita(a, 6, date(2026, 11, 30), OGGI)
check("uscita registrata", pe.elenco(a, date(2026, 11, 30))[5][1] == "Baietti" and pe.elenco(a, date(2026, 12, 1))[5][1] == "")
check("posizione occupata rifiutata", errore(pe.ingresso, a, 6, "Famà", date(2026, 11, 20), OGGI))
pe.ingresso(a, 6, grad0[0], date(2026, 12, 1), OGGI)
check("subentrato", pe.elenco(a, date(2026, 12, 1))[5][1] == "Famà" and pe.elenco(a, date(2026, 11, 30))[5][1] == "Baietti")
check("esce dalla graduatoria", pe.graduatoria(a) == grad0[1:])
dopo = giorni(date(2026, 11, 16), 28)
check("passato invariato", all(prima[d] == dopo[d] for d in prima if d < date(2026, 12, 1)))
check("dal 1/12 si vede Famà al posto di Baietti",
      any("Famà" in str(dopo[d]) for d in dopo if d >= date(2026, 12, 1)) and not any("Baietti" in str(dopo[d]) for d in dopo if d >= date(2026, 12, 1)))

# posizione libera (4): ingresso diretto
pe.ingresso(a, 4, "Nuovo Nome", date(2027, 1, 11), OGGI, da_graduatoria=False)
check("pos. libera: prima vuota", pe.elenco(a, date(2027, 1, 10))[3][1] == "")
check("pos. libera: dopo occupata", pe.elenco(a, date(2027, 1, 11))[3][1] == "Nuovo Nome")
check("gruppo conservato", pe.elenco(a, date(2027, 1, 11))[3][2] == "G")

# persistenza
a.salva()
b = ArchivioDB(os.path.join(TMP, "a.db"))
check("persistente", Motore(b).chi_in_servizio(6, date(2026, 12, 5)) == "Famà" and Motore(b).chi_in_servizio(6, date(2026, 11, 5)) == "Baietti")

# regole
check("passato rifiutato", errore(pe.uscita, a, 6, date(2026, 10, 1), OGGI))
check("uscita su posizione libera", errore(pe.uscita, a, 12, date(2026, 12, 1), OGGI))
check("gia' in servizio altrove", errore(pe.ingresso, a, 12, "Conte", date(2026, 12, 1), OGGI))
check("nome vuoto", errore(pe.ingresso, a, 12, " ", date(2026, 12, 1), OGGI))
check("posizione non valida", errore(pe.ingresso, a, 15, "X", date(2026, 12, 1), OGGI))

# annullamenti
pe.annulla_ingresso(a, 4, date(2027, 1, 11), OGGI)
check("ingresso annullato", pe.elenco(a, date(2027, 1, 12))[3][1] == "")
pe.uscita(a, 13, date(2027, 2, 28), OGGI)
pe.ingresso(a, 13, "Altro", date(2027, 3, 1), OGGI, da_graduatoria=False)
check("annulla uscita con subentro rifiutato", errore(pe.annulla_uscita, a, 13, OGGI) is not None)
pe.annulla_ingresso(a, 13, date(2027, 3, 1), OGGI)
pe.annulla_uscita(a, 13, OGGI)
check("uscita annullata", pe.elenco(a, date(2027, 3, 1))[12][1] == "Canta")
check("annulla senza uscita", errore(pe.annulla_uscita, a, 13, OGGI))

# graduatoria
pe.aggiungi_in_graduatoria(a, "Rossi")
check("in fondo", pe.graduatoria(a)[-1] == "Rossi")
pe.aggiungi_in_graduatoria(a, "Bruni", 1)
check("in testa", pe.graduatoria(a)[0] == "Bruni")
pe.sposta_in_graduatoria(a, "Rossi", 2)
check("spostato", pe.graduatoria(a)[:3] == ["Bruni", "Rossi", grad0[1]])
check("doppione rifiutato", errore(pe.aggiungi_in_graduatoria, a, "rossi"))
pe.togli_dalla_graduatoria(a, "Bruni")
check("tolto", "Bruni" not in pe.graduatoria(a))
check("togli inesistente", errore(pe.togli_dalla_graduatoria, a, "Bruni"))
check("numerazione continua", [r[0] for r in a.con.execute("SELECT ordine FROM graduatoria ORDER BY ordine")] == list(range(1, len(pe.graduatoria(a)) + 1)))

# uscita: la data si puo' cambiare anche in avanti (06/11/2026); sostituzione in un colpo solo
a2p = os.path.join(TMP, "b.db"); shutil.copy(os.path.join(TMP, "a.db"), a2p)
importa_da_xlsm(XLSM, a2p)
b = ArchivioDB(a2p)
chi = Motore(b).chi_in_servizio(7, date(2026, 11, 2))
pe.uscita(b, 7, date(2026, 11, 20), OGGI)
pe.uscita(b, 7, date(2026, 12, 15), OGGI)
check("uscita spostata in avanti", Motore(b).chi_in_servizio(7, date(2026, 12, 15)) == chi and Motore(b).chi_in_servizio(7, date(2026, 12, 16)) == "")
pe.uscita(b, 7, date(2026, 11, 25), OGGI)
check("uscita spostata indietro", Motore(b).chi_in_servizio(7, date(2026, 11, 26)) == "")
pe.ingresso(b, 7, "Nuovo Sette", date(2026, 12, 1), OGGI, da_graduatoria=False)
pe.uscita(b, 7, date(2026, 12, 10), OGGI)       # il 10/12 in posizione 7 c'e' il nuovo: e' la sua uscita
check("uscita del nuovo, il vecchio resta com'era", Motore(b).chi_in_servizio(7, date(2026, 12, 10)) == "Nuovo Sette"
      and Motore(b).chi_in_servizio(7, date(2026, 12, 11)) == "" and Motore(b).chi_in_servizio(7, date(2026, 11, 26)) == "")
chi8 = Motore(b).chi_in_servizio(8, date(2026, 11, 2))
g0 = pe.graduatoria(b)[0]
pe.sostituisci(b, 8, g0, date(2026, 11, 16), OGGI)
m = Motore(b)
check("sostituisci: esce il giorno prima", m.chi_in_servizio(8, date(2026, 11, 15)) == chi8 and m.chi_in_servizio(8, date(2026, 11, 16)) == g0)
check("sostituisci: tolto dalla graduatoria", g0 not in pe.graduatoria(b))
check("sostituisci: gia' in servizio rifiutato", errore(pe.sostituisci, b, 9, Motore(b).chi_in_servizio(10, date(2026, 11, 20)), date(2026, 11, 20), OGGI))
check("sostituisci: chi subentra gia' rifiutato", errore(pe.sostituisci, b, 8, "Altro", date(2026, 11, 10), OGGI))
check("sostituisci: passato rifiutato", errore(pe.sostituisci, b, 9, "Altro", OGGI, OGGI))

print("   prove riuscite: %d, fallite: %d" % (OK, KO))
sys.exit(1 if KO else 0)
