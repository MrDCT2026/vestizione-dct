"""Prove automatiche delle operazioni: ogni caso corrisponde a una regola o a un test fatto sul VBA."""
import os, shutil, sys, tempfile
from datetime import date
from dct.db import importa_da_xlsm, ArchivioDB
from dct.operazioni import Operazioni
from dct.copertura import Motore

XLSM = sys.argv[1]
TMP = tempfile.mkdtemp()
BASE = os.path.join(TMP, "base.db")
importa_da_xlsm(XLSM, BASE)
OK = KO = 0


def nuovo():
    p = os.path.join(TMP, "t.db")
    shutil.copy(BASE, p)
    a = ArchivioDB(p)
    return a, Operazioni(a), Motore(a)


def check(nome, cond, extra=""):
    global OK, KO
    if cond:
        OK += 1
    else:
        KO += 1
        print("  FALLITO:", nome, extra)


def pos_valore(op, d, valore, escludi=()):
    for p in range(1, 15):
        if op.val(d, p) == valore and not op.vuota(d, p) and p not in escludi and op.tipo(d, p) == "":
            return p


def pos_riposo(op, d, n=1, escludi=()):
    out = []
    for p in range(1, 15):
        if op.val(d, p) == "R" and not op.vuota(d, p) and op.tipo(d, p) == "" and p not in escludi:
            out.append(p)
    return out[:n]


def riga(g, codice):
    for t in g.turni:
        if t.codice == codice:
            return t


def giorno_pulito(feriale):
    """Primo giorno da dicembre 2026 senza nulla inserito: feriale (giovedi', non post festivo) o domenica.
    Cosi' le prove non dipendono da cosa e' stato inserito nel file Excel di riferimento."""
    from datetime import timedelta
    from dct.calendario import is_festivo, primo_feriale_dopo_festivo
    a0 = ArchivioDB(BASE)
    op0 = Operazioni(a0)
    occupati = {x.data for x in a0.assegnazioni}
    d = date(2026, 12, 1)
    while d.year < 2028:
        adatto = (d.weekday() == 3 and not is_festivo(d) and not primo_feriale_dopo_festivo(d)) if feriale \
            else d.weekday() == 6
        if adatto and d not in occupati and a0.cella(d, 1) is not None \
                and all(op0.tipo(d, q) == "" for q in range(1, 15)) \
                and len(pos_riposo(op0, d, 3)) >= 2 \
                and (not feriale or all(pos_valore(op0, d, t) for t in ("601", "603", "604", "605", "608", "610"))) \
                and any(op0.vuota(d, q) for q in range(1, 15)):
            a0.con.close()
            return d
        d += timedelta(days=1)
    raise SystemExit("nessun giorno libero per le prove")


G = giorno_pulito(True)    # giovedi' feriale con almeno due riposi (nessun dato inserito)
D = giorno_pulito(False)   # domenica senza dati inseriti
print("   giorni di prova:", G.strftime("%d/%m/%Y"), D.strftime("%d/%m/%Y"))

# 1 assenza su turno e ripristino
a, op, m = nuovo()
p = pos_valore(op, G, "605")
e = op.applica_tasto("CONG_FEST", [(G, p)])
check("cong su turno", e.ok and e.colorate == 1 and op.tipo(G, p) == "CONG_FEST")
check("titolare scoperto", riga(m.calcola_giorno(G), "605").nome != "" )
e = op.applica_tasto("CONG_FEST", [(G, p)])
check("secondo click ripristina", e.ripristinate == 1 and op.tipo(G, p) == "")

# 2 assenza su riposo rifiutata, posizione vuota saltata
a, op, m = nuovo()
r = pos_riposo(op, G)[0]
e = op.applica_tasto("ASS_MAL", [(G, r)])
check("assenza su riposo saltata", e.saltate == 1 and op.tipo(G, r) == "")
e = op.applica_tasto("CORSI", [(G, 4)])
check("pos vuota saltata", e.saltate == 1)
e = op.applica_tasto("CORSI", [(G, 1), (G, 2)])
check("corsi solo una cella", not e.ok)
e = op.applica_tasto("CONG_FEST", [(G, 1), (G, 2)])
check("cong multi", e.ok and e.colorate == 2)

# 3 RL: turno scoperto, validazioni
a, op, m = nuovo()
p610 = pos_valore(op, G, "610")
r1, r2 = pos_riposo(op, G, 2)
e = op.rl(G, r1, "610")
check("RL su turno non scoperto rifiutato", not e.ok and "non è scoperto" in e.msg)
op.applica_tasto("ASS_MAL", [(G, p610)])
e = op.rl(G, r1, "601")
check("RL turno non scoperto (601) rifiutato", not e.ok)
e = op.rl(G, r1, "610")
check("RL ok", e.ok and op.tipo(G, r1) == "RL" and any(x.pos == r1 and x.turno == "610" for x in a.assegnazioni))
t = riga(m.calcola_giorno(G), "610")
check("RL copre il turno", t.nome == m.chi_in_servizio(r1, G) and t.nota == "RL" and not t.scoperto)
e = op.rl(G, r2, "610")
check("turno gia' coperto", not e.ok and "già coperto" in e.msg)
e = op.rl(G, r1, "610")
check("RL su cella RL propone cancellazione", e.chiede_cancellazione == "RL")
e = op.rl(G, p610, "610")
check("RL su turno rifiutato", not e.ok)
e = op.cancella(G, r1)
check("cancella RL", e.ok and op.tipo(G, r1) == "" and not a.assegnazioni[-1].pos == r1)

# 4 turno non valido per la modalita' (601 di domenica)
a, op, m = nuovo()
r = pos_riposo(op, D)[0]
e = op.rl(D, r, "601")
check("turno non valido di domenica", not e.ok and "non valido" in e.msg)

# 5 MIS e RU
a, op, m = nuovo()
p = pos_valore(op, G, "603")
op.applica_tasto("ASS_MAL", [(G, p)])
r = pos_riposo(op, G)[0]
e = op.cambio_riposo_servizio(G, r, "603")
check("MIS", e.ok and op.tipo(G, r) == "MIS")
t = riga(m.calcola_giorno(G), "603")
check("MIS copre", t.nota == "MIS" and not t.scoperto)
q = pos_valore(op, G, "608")
e = op.cambio_riposo_servizio(G, q)
check("RU su turno", e.ok and op.tipo(G, q) == "RU")
g = m.calcola_giorno(G)
check("RU assente e turno scoperto", any(x.motivazione == "RU" for x in g.assenti))
e = op.cancella(G, q)
check("cancella RU", e.ok and op.tipo(G, q) == "")
e = op.cambio_riposo_servizio(G, r, "608")
check("C.Rip servizio su MIS propone cancellazione", e.chiede_cancellazione == "MIS")

# 6 cambio riposo personale + annulla da entrambe le celle
a, op, m = nuovo()
pt = pos_valore(op, G, "604")
pr = pos_riposo(op, G)[0]
e = op.cambio_riposo_personale(G, pt, pr)
check("C_RIP personale", e.ok and op.tipo(G, pt) == "C_RIP" and op.tipo(G, pr) == "C_RIP")
g = m.calcola_giorno(G)
t = riga(g, "604")
check("C_RIP: rientrante copre", t.nome == m.chi_in_servizio(pr, G) and t.nota == "C. Rip.")
check("C_RIP: uscente assente", any(x.motivazione == "C. Rip." for x in g.assenti))
e = op.cancella(G, pt)
check("cancella da cella turno", e.ok and op.tipo(G, pt) == "" and op.tipo(G, pr) == "" and not any(x.tipo == "C_RIP" and x.data == G for x in a.assegnazioni))
op.cambio_riposo_personale(G, pr, pt)
e = op.cancella(G, pr)
check("cancella da cella riposo", e.ok and op.tipo(G, pt) == "" and op.tipo(G, pr) == "")

# 7 blocchi C.Rip.
a, op, m = nuovo()
pt = pos_valore(op, G, "604")
pr, pr2 = pos_riposo(op, G, 2)
op.applica_tasto("ASS_MAL", [(G, pt)])
e = op.cambio_riposo_personale(G, pt, pr)
check("C.Rip. su cella assente rifiutato", not e.ok)
op.rl(G, pr, "604")
e = op.cambio_riposo_personale(G, pr, pr2)
check("C.Rip. su cella gia' colorata rifiutato", not e.ok)
e = op.cambio_riposo_personale(G, pr2, pr2)
check("stessa cella rifiutata", not e.ok)
e = op.cambio_riposo_personale(G, pr2, next(q for q in range(1, 15) if op.vuota(G, q)))
check("seconda cella posizione vuota rifiutata", not e.ok)

# 8 corso sopra MIS (diagonale)
a, op, m = nuovo()
pt = pos_valore(op, G, "603")
op.applica_tasto("ASS_MAL", [(G, pt)])
r = pos_riposo(op, G)[0]
op.cambio_riposo_servizio(G, r, "603")
e = op.applica_tasto("CORSI", [(G, r)])
check("corso su MIS", e.ok and op.tipo(G, r) == "CORSI" and op.diag(G, r) == "MIS")
g = m.calcola_giorno(G)
check("corso su MIS: il rientrante non copre e risulta assente \"MIS (Corso)\"", riga(g, "603").nota != "MIS" and riga(g, "603").nome != m.chi_in_servizio(r, G) and any(x.motivazione == "MIS (Corso)" and x.nome == m.chi_in_servizio(r, G) for x in g.assenti))
e = op.rl(G, r, "603")
check("RL su diagonale bloccato", not e.ok)
e = op.cancella(G, r)
check("cancella MIS sotto corso bloccata", not e.ok)
e = op.applica_tasto("CORSI", [(G, r)])
check("tolgo il corso: torna MIS", e.ripristinate == 1 and op.tipo(G, r) == "MIS" and op.diag(G, r) == "")
g = m.calcola_giorno(G)
check("MIS di nuovo attivo", riga(g, "603").nota == "MIS")

# 9 corso sopra cambio riposo personale
a, op, m = nuovo()
pt = pos_valore(op, G, "605")
pr = pos_riposo(op, G)[0]
op.cambio_riposo_personale(G, pt, pr)
e = op.applica_tasto("ASS_MAL", [(G, pt)])
check("assenza su chi esce bloccata", e.saltate == 1)
e = op.applica_tasto("CORSI", [(G, pr)])
check("corso su rientrante C_RIP", e.ok and op.diag(G, pr) == "C_RIP")
g = m.calcola_giorno(G)
check("copertura con corso su rientrante", riga(g, "605").nome != m.chi_in_servizio(pr, G) and any(x.motivazione == "C. Rip. (Corso)" for x in g.assenti) and len([x for x in g.assenti if x.motivazione == "C. Rip."]) == 1)
e = op.cancella(G, pt)
check("cancella da turno con corso sul rientrante bloccata", not e.ok)
e = op.cambio_riposo_servizio(G, pr, "605")
check("C.Rip. su diagonale bloccato", not e.ok)
op.applica_tasto("CORSI", [(G, pr)])
e = op.cancella(G, pt)
check("tolto il corso, cancellazione ok", e.ok and op.tipo(G, pt) == "" and op.tipo(G, pr) == "")

# 10 due cambi riposo personali nello stesso giorno: la cancellazione non confonde le coppie
a, op, m = nuovo()
t1 = pos_valore(op, G, "605")
t2 = pos_valore(op, G, "604")
r1, r2 = pos_riposo(op, G, 2)
op.cambio_riposo_personale(G, t1, r1)
op.cambio_riposo_personale(G, t2, r2)
op.cancella(G, t2)
check("coppie indipendenti", op.tipo(G, t1) == "C_RIP" and op.tipo(G, r1) == "C_RIP" and op.tipo(G, t2) == "" and op.tipo(G, r2) == "")
op.cancella(G, r1)
check("coppie indipendenti (2)", op.tipo(G, t1) == "" and op.tipo(G, r1) == "")

# 11 un RL/MIS per persona al giorno
a, op, m = nuovo()
p610 = pos_valore(op, G, "610"); p605 = pos_valore(op, G, "605")
op.applica_tasto("ASS_MAL", [(G, p610)]); op.applica_tasto("ASS_MAL", [(G, p605)])
r = pos_riposo(op, G)[0]
op.rl(G, r, "610")
e = op.rl(G, r, "605")
check("RL su cella RL propone cancellazione, non ne crea un secondo", e.chiede_cancellazione == "RL" and len([x for x in a.assegnazioni if x.pos == r and x.data == G]) == 1)

# 12 lunedi' post festivo: 9 dicembre
m2 = Motore(ArchivioDB(BASE))
check("9 dicembre e' post festivo", len(m2.turni_principali("Feriale", date(2026, 12, 9))) in (8, 9))

# 13 FOR: rientro solo per un corso (Excel v13b)
a, op, m = nuovo()
r, r2 = pos_riposo(op, G, 2)
prima = [(t.codice, t.nome, t.scoperto) for t in m.calcola_giorno(G).turni]
e = op.cambio_riposo_servizio(G, r, "for")
check("FOR accettato senza turno scoperto", e.ok and op.tipo(G, r) == "CORSI" and op.diag(G, r) == "MIS")
check("FOR: registro MIS con turno CORSO", any(x.pos == r and x.data == G and x.tipo == "MIS" and x.turno == "CORSO" for x in a.assegnazioni))
g = m.calcola_giorno(G)
check("FOR: copertura invariata", [(t.codice, t.nome, t.scoperto) for t in g.turni] == prima)
check("FOR: assente \"MIS (Corso)\"", any(x.motivazione == "MIS (Corso)" and x.nome == m.chi_in_servizio(r, G) for x in g.assenti))
e = op.cambio_riposo_servizio(G, r2, "FOR")
check("FOR: due colleghi nello stesso giorno", e.ok)
e = op.cancella(G, r)
check("FOR: 'C' bloccata finche' c'e' il corso", not e.ok)
e = op.rl(G, r, "610")
check("FOR: RL bloccato", not e.ok)
e = op.applica_tasto("CORSI", [(G, r)])
check("FOR: tolgo il corso, resta MIS", e.ripristinate == 1 and op.tipo(G, r) == "MIS" and op.diag(G, r) == "")
check("FOR: MIS senza turno non copre nessun turno", not any(t.nota == "MIS" for t in m.calcola_giorno(G).turni))
e = op.cancella(G, r)
check("FOR: poi 'C' cancella", e.ok and op.tipo(G, r) == "" and not any(x.pos == r and x.data == G for x in a.assegnazioni))
a2 = ArchivioDB(os.path.join(TMP, "t.db"))
check("FOR: salvato nell'archivio", any(x.pos == r2 and x.data == G and x.turno == "CORSO" for x in a2.assegnazioni) and a2.cella(G, r2).diag == "MIS")
p603 = pos_valore(op, G, "603")
e = op.cambio_riposo_servizio(G, p603, "FOR")
check("FOR su un turno: e' un RU (uscita a riposo)", e.ok and op.tipo(G, p603) == "RU")

print("prove riuscite: %d, fallite: %d" % (OK, KO))
sys.exit(1 if KO else 0)
