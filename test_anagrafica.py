"""Prove dell'Anagrafica: le modifiche valgono dal giorno scelto in poi, il passato non cambia."""
import os, shutil, sys, tempfile
from datetime import date, timedelta
from dct.db import importa_da_xlsm, ArchivioDB
from dct.copertura import Motore
from dct import anagrafica as an
from confronta import righe_python

XLSM = sys.argv[1]
TMP = tempfile.mkdtemp()
BASE = os.path.join(TMP, "base.db")
importa_da_xlsm(XLSM, BASE)
OK = KO = 0
OGGI = date(2026, 10, 23)


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
    return ArchivioDB(p)


def giorni(arch, da, n):
    m = Motore(arch)
    return {da + timedelta(i): righe_python(m.calcola_giorno(da + timedelta(i))) for i in range(n)}


def errore(f, *a):
    try:
        f(*a)
    except an.ErroreAnagrafica as e:
        return str(e)
    return None


a = nuovo()
inizio = date(2026, 10, 19)
prima = giorni(a, inizio, 28)
suss = a.config.sussidiari["Feriale"]
ordine = [x[0] for x in suss]
nuovo_ordine = list(reversed(ordine))
dal = date(2026, 11, 2)

# 1. priorita' sussidiari feriali invertite dal 2/11
an.cambia_priorita_sussidiari(a, "Feriale", nuovo_ordine, dal, OGGI)
dopo = giorni(a, inizio, 28)
check("versioni 2", len(an.versioni(a)) == 2)
check("passato invariato", all(prima[d] == dopo[d] for d in prima if d < dal))
check("dal 2/11 cambia qualcosa", any(prima[d] != dopo[d] for d in prima if d >= dal and d.weekday() < 5))
check("letta dal giorno prima", [x[0] for x in an.leggi(a, dal - timedelta(1))["sussidiari"]["Feriale"]] == ordine)
check("letta dal giorno", [x[0] for x in an.leggi(a, dal)["sussidiari"]["Feriale"]] == nuovo_ordine)
check("gli orari seguono il codice", dict((c, i) for c, i, f in an.leggi(a, dal)["sussidiari"]["Feriale"])
      == dict((c, i) for c, i, f in suss))

# 2. persistenza: riaprendo l'archivio le versioni restano
a.salva()
b = ArchivioDB(a.con.execute("PRAGMA database_list").fetchone()[2])
check("persistente", len(an.versioni(b)) == 2 and [x[0] for x in b.config_alla(dal).sussidiari["Feriale"]] == nuovo_ordine)

# 3. regole di validazione
check("passato rifiutato", errore(an.cambia_priorita_sussidiari, a, "Feriale", ordine, date(2026, 10, 1), OGGI))
check("dopo una versione successiva rifiutato", errore(an.cambia_priorita_sussidiari, a, "Feriale", ordine, date(2026, 10, 30), OGGI))
check("codici diversi rifiutati", errore(an.cambia_priorita_sussidiari, a, "Feriale", ordine[:-1] + ["999"], date(2026, 12, 1), OGGI))
check("orario non valido", errore(an.cambia_orari_turno, a, "601", "Feriale", "25:00", "14:00", date(2026, 12, 1), OGGI))
check("orario testo", errore(an.cambia_orari_turno, a, "601", "Feriale", "abc", "14:00", date(2026, 12, 1), OGGI))
check("turno inesistente", errore(an.cambia_orari_turno, a, "999", "Feriale", "05:00", "14:00", date(2026, 12, 1), OGGI))
check("modalita' non valida", errore(an.cambia_orari_turno, a, "601", "Lunedi", "05:00", "14:00", date(2026, 12, 1), OGGI))
check("sussidiario inesistente", errore(an.cambia_orari_sussidiario, a, "Feriale", "999", "05:00", "14:00", date(2026, 12, 1), OGGI))
check("disponibilita' codici diversi", errore(an.cambia_priorita_disponibilita, a, "Feriale", ["1"], date(2026, 12, 1), OGGI))

# 4. orari di un turno (solo dove il turno esiste) e di un sussidiario, dal 1/12
turno = next(c for c, o in a.config.turni.items() if o["Feriale"][0])
vecchi = a.config.turni[turno]["Feriale"]
an.cambia_orari_turno(a, turno, "Feriale", "5:30", "13:45", date(2026, 12, 1), OGGI)
check("orari turno dal", an.leggi(a, date(2026, 12, 1))["turni"][turno]["Feriale"] == ("05:30", "13:45"))
check("orari turno prima", an.leggi(a, date(2026, 11, 30))["turni"][turno]["Feriale"] == vecchi)
check("motore usa orari nuovi", Motore(a).orario_turno(turno, "Feriale", date(2026, 12, 2)) == "05:30"
      and Motore(a).orario_turno(turno, "Feriale", date(2026, 11, 20)) == vecchi[0])
cod = nuovo_ordine[0]
an.cambia_orari_sussidiario(a, "Feriale", cod, "06:15", "14:15", date(2026, 12, 15), OGGI)
check("orario sussidiario nuovo", Motore(a).orario_suss(cod, "Feriale", date(2026, 12, 16)) == "06:15")
check("orario sussidiario prima", Motore(a).orario_suss(cod, "Feriale", date(2026, 12, 14)) != "06:15")
check("versioni 4", len(an.versioni(a)) == 4)
# le versioni successive conservano le precedenti (la modifica di dicembre non annulla l'inversione)
check("catena", [x[0] for x in an.leggi(a, date(2026, 12, 16))["sussidiari"]["Feriale"]] == nuovo_ordine
      and an.leggi(a, date(2026, 12, 16))["turni"][turno]["Feriale"] == ("05:30", "13:45"))

# 5. disponibilita'
mod = next(iter(a.config.disponibilita))
lista = a.config.disponibilita[mod]
an.cambia_priorita_disponibilita(a, mod, list(reversed(lista)), date(2027, 1, 10), OGGI)
check("disp. nuova", an.leggi(a, date(2027, 1, 10))["disponibilita"][mod] == list(reversed(lista)))
check("disp. vecchia", an.leggi(a, date(2027, 1, 9))["disponibilita"][mod] == lista)

# 6. eliminare una modifica programmata
check("elimina passata rifiutata", errore(an.elimina_versione, a, date(2026, 11, 2), date(2026, 11, 5)))
an.elimina_versione(a, date(2027, 1, 10), OGGI)
check("eliminata", an.leggi(a, date(2027, 1, 10))["disponibilita"][mod] == lista and len(an.versioni(a)) == 4)
check("origine non eliminabile", errore(an.elimina_versione, a, date.fromisoformat(min(a.versioni)), date(2000, 1, 1)))

print("   prove riuscite: %d, fallite: %d" % (OK, KO))
sys.exit(1 if KO else 0)
