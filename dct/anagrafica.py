"""Anagrafica: orari dei turni, orari e priorita' dei sussidiari, ordine delle disponibilita'.
Ogni modifica vale "dal" un giorno in poi (nuova versione); il passato non si tocca mai.
I codici dei turni non si cambiano: se cambiano i codici cambia tutta la rotazione (nuovo progetto).
2026 Bruno Roli"""
import copy
import re
from datetime import date

MODALITA = ("Feriale", "Sabato", "Domenica")


class ErroreAnagrafica(Exception):
    pass


def _ora(testo):
    t = str(testo).strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ErroreAnagrafica("Orario non valido: '%s' (scrivi hh:mm, per esempio 05:07)." % testo)
    return "%02d:%02d" % (int(m.group(1)), int(m.group(2)))


# ------------------------------------------------------------------ lettura
def leggi(arch, d):
    """Cio' che e' in vigore nel giorno d, per la schermata Anagrafica."""
    cfg = arch.config_alla(d)
    dal = max(v for v in arch.versioni if v <= d.isoformat()) if any(v <= d.isoformat() for v in arch.versioni) else min(arch.versioni)
    return {"valida_dal": dal, "turni": cfg.turni, "sussidiari": cfg.sussidiari, "disponibilita": cfg.disponibilita}


def versioni(arch):
    """Elenco delle date in cui la configurazione e' cambiata."""
    return sorted(arch.versioni)


# ------------------------------------------------------------------ scrittura
def _controlla_data(arch, dal, oggi):
    if dal < oggi:
        raise ErroreAnagrafica("Il passato non si tocca: la modifica può valere dal %s in poi." % oggi.strftime("%d/%m/%Y"))
    successive = [v for v in arch.versioni if v > dal.isoformat()]
    if successive:
        raise ErroreAnagrafica("Esiste già una modifica dal %s: eliminala oppure scegli una data successiva."
                               % date.fromisoformat(successive[0]).strftime("%d/%m/%Y"))


def _scrivi_versione(arch, dal, cfg):
    v = dal.isoformat()
    con = arch.con
    for t in ("cfg_turni", "cfg_disponibilita", "cfg_sussidiari"):
        con.execute("DELETE FROM %s WHERE valido_dal=?" % t, (v,))
    for cod, o in cfg.turni.items():
        con.execute("INSERT INTO cfg_turni VALUES(?,?,?,?,?,?,?,?)",
                    (v, cod, *o["Feriale"], *o["Sabato"], *o["Domenica"]))
    for m, lista in cfg.disponibilita.items():
        for i, c in enumerate(lista, 1):
            con.execute("INSERT INTO cfg_disponibilita VALUES(?,?,?,?)", (v, m, i, c))
    for k, lista in cfg.sussidiari.items():
        for i, (c, ini, fin) in enumerate(lista, 1):
            con.execute("INSERT INTO cfg_sussidiari VALUES(?,?,?,?,?,?)", (v, k, i, c, ini, fin))
    con.commit()
    arch.versioni = arch._leggi_versioni()
    arch.config = arch.config_alla(date.max)


def _modifica(arch, dal, oggi, fn):
    _controlla_data(arch, dal, oggi)
    cfg = copy.deepcopy(arch.config_alla(dal))
    fn(cfg)
    _scrivi_versione(arch, dal, cfg)


def cambia_orari_turno(arch, codice, modalita, inizio, fine, dal, oggi):
    if modalita not in MODALITA:
        raise ErroreAnagrafica("Tipo di giorno non valido: %s." % modalita)
    i, f = _ora(inizio), _ora(fine)

    def fn(cfg):
        if codice not in cfg.turni:
            raise ErroreAnagrafica("Il turno %s non esiste." % codice)
        if cfg.turni[codice][modalita] == ("", ""):
            raise ErroreAnagrafica("Il turno %s non è previsto di %s: i giorni in cui esiste fanno parte della rotazione."
                                   % (codice, modalita.lower()))
        cfg.turni[codice][modalita] = (i, f)
    _modifica(arch, dal, oggi, fn)


def cambia_orari_sussidiario(arch, chiave, codice, inizio, fine, dal, oggi):
    i, f = _ora(inizio), _ora(fine)

    def fn(cfg):
        lista = cfg.sussidiari.get(chiave)
        if not lista or codice not in [x[0] for x in lista]:
            raise ErroreAnagrafica("Il sussidiario %s non esiste per '%s'." % (codice, chiave))
        cfg.sussidiari[chiave] = [(c, i, f) if c == codice else (c, a, b) for c, a, b in lista]
    _modifica(arch, dal, oggi, fn)


def cambia_priorita_sussidiari(arch, chiave, ordine, dal, oggi):
    ordine = [str(x) for x in ordine]

    def fn(cfg):
        lista = cfg.sussidiari.get(chiave)
        if not lista:
            raise ErroreAnagrafica("Non esistono sussidiari per '%s'." % chiave)
        if sorted(ordine) != sorted(x[0] for x in lista):
            raise ErroreAnagrafica("L'ordine deve contenere esattamente gli stessi codici: %s." % ", ".join(x[0] for x in lista))
        per_codice = {c: (c, a, b) for c, a, b in lista}
        cfg.sussidiari[chiave] = [per_codice[c] for c in ordine]
    _modifica(arch, dal, oggi, fn)


def cambia_priorita_disponibilita(arch, modalita, ordine, dal, oggi):
    ordine = [str(x) for x in ordine]

    def fn(cfg):
        lista = cfg.disponibilita.get(modalita)
        if not lista:
            raise ErroreAnagrafica("Non esistono disponibilità per '%s'." % modalita)
        if sorted(ordine) != sorted(lista):
            raise ErroreAnagrafica("L'ordine deve contenere esattamente gli stessi codici: %s." % ", ".join(lista))
        cfg.disponibilita[modalita] = ordine
    _modifica(arch, dal, oggi, fn)


def elimina_versione(arch, dal, oggi):
    """Annulla una modifica programmata (solo se non e' ancora in vigore)."""
    if dal < oggi:
        raise ErroreAnagrafica("Il passato non si tocca.")
    v = dal.isoformat()
    if v not in arch.versioni or len(arch.versioni) == 1 or v == min(arch.versioni):
        raise ErroreAnagrafica("Non c'è una modifica programmata a quella data.")
    for t in ("cfg_turni", "cfg_disponibilita", "cfg_sussidiari"):
        arch.con.execute("DELETE FROM %s WHERE valido_dal=?" % t, (v,))
    arch.con.commit()
    arch.versioni = arch._leggi_versioni()
    arch.config = arch.config_alla(date.max)


# ---------------------------------------------------------------- modifiche "a blocchi" (per la schermata)
def imposta_orari_turno(arch, codice, orari, dal, oggi):
    """orari = {"Feriale": (inizio, fine), "Sabato": ..., "Domenica": ...}: solo i giorni in cui il turno esiste."""
    nuovi = {m: (_ora(i), _ora(f)) for m, (i, f) in orari.items()}

    def fn(cfg):
        if codice not in cfg.turni:
            raise ErroreAnagrafica("Il turno %s non esiste." % codice)
        for m, o in nuovi.items():
            if m not in MODALITA:
                raise ErroreAnagrafica("Tipo di giorno non valido: %s." % m)
            if cfg.turni[codice][m] == ("", ""):
                raise ErroreAnagrafica("Il turno %s non è previsto di %s." % (codice, m.lower()))
            cfg.turni[codice][m] = o
    _modifica(arch, dal, oggi, fn)


def imposta_sussidiari(arch, chiave, righe, dal, oggi):
    """righe = [(codice, inizio, fine)] nell'ordine di priorita' voluto: stessi codici di prima."""
    righe = [(str(c), _ora(i), _ora(f)) for c, i, f in righe]

    def fn(cfg):
        lista = cfg.sussidiari.get(chiave)
        if not lista:
            raise ErroreAnagrafica("Non esistono sussidiari per '%s'." % chiave)
        if sorted(c for c, _, _ in righe) != sorted(x[0] for x in lista):
            raise ErroreAnagrafica("L'elenco deve contenere esattamente gli stessi codici: %s." % ", ".join(x[0] for x in lista))
        cfg.sussidiari[chiave] = righe
    _modifica(arch, dal, oggi, fn)


# ------------------------------------------------------------------ turni di Natale (25/12)
def natale_leggi(arch, d):
    """Configurazione di Natale in vigore dal giorno d (versione piu' recente con valido_dal <= d)."""
    if not arch.natale:
        return None
    valide = [v for v in arch.natale if v <= d.isoformat()]
    v = max(valide) if valide else min(arch.natale)
    x = arch.natale[v]
    return {"valida_dal": v, "turni": x["TURNO"], "sussidiari": x["SUSS"], "disponibili": [c for c, _i, _f in x["DISP"]],
            "turni_coperti": x["PARAM"].get("TurniCoperti", 8),
            "programmate": sorted(w for w in arch.natale if w > v)}


def imposta_orari_natale(arch, orari, dal, oggi):
    """Nuovi orari dei turni di Natale (codice -> (inizio, fine)) validi dal giorno dal: nuova versione."""
    if dal < oggi:
        raise ErroreAnagrafica("Il passato non si tocca: la modifica può valere dal %s in poi." % oggi.strftime("%d/%m/%Y"))
    # conta solo il 25/12: la modifica vale dal primo Natale da dal in poi (e sostituisce la versione di quel Natale)
    dal = date(dal.year, 12, 25) if dal <= date(dal.year, 12, 25) else date(dal.year + 1, 12, 25)
    successive = [v for v in arch.natale if v > dal.isoformat()]
    if successive:
        raise ErroreAnagrafica("Esiste già una modifica dei turni di Natale dal %s."
                               % date.fromisoformat(successive[0]).strftime("%d/%m/%Y"))
    base = natale_leggi(arch, dal)
    v = dal.isoformat()
    righe = []
    for tipo, lista in (("TURNO", base["turni"]), ("SUSS", base["sussidiari"])):
        for k, (c, i, f) in enumerate(lista, 1):
            i2, f2 = orari.get(c, (i, f))
            righe.append((v, tipo, c, k, _ora(i2), _ora(f2)))
    for k, c in enumerate(base["disponibili"], 1):
        righe.append((v, "DISP", c, k, "", ""))
    righe.append((v, "PARAM", "TurniCoperti", int(base["turni_coperti"]), "", ""))
    arch.con.execute("DELETE FROM cfg_natale WHERE valido_dal=?", (v,))
    arch.con.executemany("INSERT INTO cfg_natale VALUES(?,?,?,?,?,?)", righe)
    arch.con.commit()
    arch.natale = arch._leggi_natale()
    return dal
