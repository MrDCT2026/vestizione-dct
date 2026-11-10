"""Gestione del personale: ingressi, uscite e graduatoria.
Ogni cambiamento vale da una data in poi; il passato non si tocca.
2026 Bruno Roli"""
from datetime import date, timedelta

from .modelli import Persona


class ErrorePersonale(Exception):
    pass


def _futuro(d, oggi):
    if d < oggi:
        raise ErrorePersonale("Il passato non si tocca: la data deve essere dal %s in poi." % oggi.strftime("%d/%m/%Y"))


def _iso(d):
    return None if d is None or d == date.max or d == date.min else d.isoformat()


def elenco(arch, d):
    """Chi occupa ogni posizione nel giorno d: [(pos, nome, gruppo, dal, al)]; nome vuoto = posizione libera."""
    out = []
    for pos in range(1, 15):
        righe = [p for p in arch.persone if p.pos == pos]
        gr = righe[0].gruppo if righe else ""
        att = [p for p in righe if p.nome and p.inizio <= d <= p.fine]
        if att:
            p = att[0]
            out.append((pos, p.nome, gr, None if p.inizio == date.min else p.inizio, None if p.fine == date.max else p.fine))
        else:
            out.append((pos, "", gr, None, None))
    return out


def graduatoria(arch):
    return arch.graduatoria()


def _riscrivi_graduatoria(arch, nomi):
    arch.con.execute("DELETE FROM graduatoria")
    for i, n in enumerate(nomi, 1):
        arch.con.execute("INSERT INTO graduatoria VALUES(?,?)", (i, n))
    arch.con.commit()


def aggiungi_in_graduatoria(arch, nome, posto=None):
    """Mette un nome in graduatoria (alla fine, oppure al posto indicato: 1 = primo)."""
    nome = nome.strip()
    if not nome:
        raise ErrorePersonale("Scrivi il nome.")
    nomi = arch.graduatoria()
    if nome.lower() in [n.lower() for n in nomi]:
        raise ErrorePersonale("%s è già in graduatoria." % nome)
    if posto is None or posto > len(nomi):
        nomi.append(nome)
    else:
        nomi.insert(max(posto, 1) - 1, nome)
    _riscrivi_graduatoria(arch, nomi)


def togli_dalla_graduatoria(arch, nome):
    nomi = arch.graduatoria()
    if nome not in nomi:
        raise ErrorePersonale("%s non è in graduatoria." % nome)
    nomi.remove(nome)
    _riscrivi_graduatoria(arch, nomi)


def sposta_in_graduatoria(arch, nome, posto):
    nomi = arch.graduatoria()
    if nome not in nomi:
        raise ErrorePersonale("%s non è in graduatoria." % nome)
    nomi.remove(nome)
    nomi.insert(min(max(posto, 1), len(nomi) + 1) - 1, nome)
    _riscrivi_graduatoria(arch, nomi)


def uscita(arch, pos, ultimo_giorno, oggi):
    """La persona che occupa la posizione smette di prestare servizio dopo ultimo_giorno.
    Se ha gia' un'uscita programmata, la data si puo' cambiare: prima o dopo, purche' nessuno subentri prima."""
    _futuro(ultimo_giorno, oggi)
    cand = [p for p in arch.persone if p.pos == pos and p.nome and p.inizio <= ultimo_giorno and p.fine >= oggi]
    if not cand:
        raise ErrorePersonale("La posizione %d è libera il %s." % (pos, ultimo_giorno.strftime("%d/%m/%Y")))
    p = max(cand, key=lambda x: x.inizio)
    if p.fine < ultimo_giorno:      # uscita spostata piu' avanti: nessuno deve subentrare prima
        dopo = [q for q in arch.persone if q.pos == pos and q.nome and q is not p and p.fine < q.inizio <= ultimo_giorno]
        if dopo:
            raise ErrorePersonale("Dal %s in posizione %d subentra %s: annulla prima il suo ingresso." % (
                dopo[0].inizio.strftime("%d/%m/%Y"), pos, dopo[0].nome))
    arch.con.execute("UPDATE persone SET fine=? WHERE pos=? AND nome=? AND IFNULL(inizio,'')=IFNULL(?,'')",
                     (ultimo_giorno.isoformat(), pos, p.nome, _iso(p.inizio)))
    arch.con.commit()
    arch.ricarica_persone()


def sostituisci(arch, pos, nome, dal, oggi, da_graduatoria=True):
    """Chi occupa la posizione esce il giorno prima di dal e nella stessa posizione entra nome, dal giorno dal."""
    nome = (nome or "").strip()
    if not nome:
        raise ErrorePersonale("Scrivi il nome.")
    ieri = dal - timedelta(days=1)
    if ieri < oggi:
        raise ErrorePersonale("Il passato non si tocca: il primo giorno del nuovo deve essere dal %s in poi." % (
            (oggi + timedelta(days=1)).strftime("%d/%m/%Y")))
    for p in arch.persone:
        if p.nome.lower() == nome.lower() and p.fine >= dal:
            raise ErrorePersonale("%s è già in servizio in posizione %d." % (nome, p.pos))
    dopo = [q for q in arch.persone if q.pos == pos and q.nome and q.inizio >= dal]
    if dopo:
        raise ErrorePersonale("Dal %s in posizione %d subentra già %s: annulla prima quell'ingresso." % (
            dopo[0].inizio.strftime("%d/%m/%Y"), pos, dopo[0].nome))
    uscita(arch, pos, ieri, oggi)
    ingresso(arch, pos, nome, dal, oggi, da_graduatoria)


def annulla_uscita(arch, pos, oggi):
    """Toglie un'uscita programmata (non ancora avvenuta): la persona resta."""
    prog = [p for p in arch.persone if p.pos == pos and p.nome and p.fine != date.max and p.fine >= oggi]
    if not prog:
        raise ErrorePersonale("Nessuna uscita programmata per la posizione %d." % pos)
    p = prog[-1]
    successive = [q for q in arch.persone if q.pos == pos and q.nome and q.inizio > p.fine]
    if successive:
        raise ErrorePersonale("C'è già chi subentra dal %s: annulla prima l'ingresso." % successive[0].inizio.strftime("%d/%m/%Y"))
    arch.con.execute("UPDATE persone SET fine=NULL WHERE pos=? AND nome=? AND IFNULL(inizio,'')=IFNULL(?,'')",
                     (pos, p.nome, _iso(p.inizio)))
    arch.con.commit()
    arch.ricarica_persone()


def ingresso(arch, pos, nome, dal, oggi, da_graduatoria=True):
    """Una persona entra nella posizione dal giorno dal. Se era in graduatoria ne esce."""
    _futuro(dal, oggi)
    nome = nome.strip()
    if not nome:
        raise ErrorePersonale("Scrivi il nome.")
    if not 1 <= pos <= 14:
        raise ErrorePersonale("Posizione non valida: %d." % pos)
    occupanti = [p for p in arch.persone if p.pos == pos and p.nome and p.fine >= dal]
    if occupanti:
        p = occupanti[0]
        raise ErrorePersonale("La posizione %d è occupata da %s fino al %s: registra prima l'uscita." % (
            pos, p.nome, "sempre" if p.fine == date.max else p.fine.strftime("%d/%m/%Y")))
    for p in arch.persone:
        if p.nome == nome and p.pos != pos and p.fine >= dal:
            raise ErrorePersonale("%s è già in servizio in posizione %d." % (nome, p.pos))
    righe = [p for p in arch.persone if p.pos == pos]
    gruppo = righe[0].gruppo if righe else ""
    arch.con.execute("INSERT INTO persone VALUES(?,?,?,?,NULL,'')", (pos, nome, gruppo, dal.isoformat()))
    if da_graduatoria and nome in arch.graduatoria():
        _riscrivi_graduatoria(arch, [n for n in arch.graduatoria() if n != nome])
    arch.con.commit()
    arch.ricarica_persone()


def annulla_ingresso(arch, pos, dal, oggi):
    """Elimina un ingresso programmato (non ancora avvenuto)."""
    _futuro(dal, oggi)
    q = [p for p in arch.persone if p.pos == pos and p.nome and p.inizio == dal]
    if not q:
        raise ErrorePersonale("Nessun ingresso programmato in posizione %d per quella data." % pos)
    arch.con.execute("DELETE FROM persone WHERE pos=? AND nome=? AND inizio=?", (pos, q[0].nome, dal.isoformat()))
    arch.con.commit()
    arch.ricarica_persone()


def programmati(arch, oggi):
    """Ingressi e uscite non ancora avvenuti: [(tipo, pos, nome, data)] ordinati per data."""
    out = []
    for p in arch.persone:
        if not p.nome:
            continue
        if p.inizio != date.min and p.inizio >= oggi:
            out.append(("ingresso", p.pos, p.nome, p.inizio))
        if p.fine != date.max and p.fine >= oggi:
            out.append(("uscita", p.pos, p.nome, p.fine))
    return sorted(out, key=lambda x: (x[3], x[1]))
