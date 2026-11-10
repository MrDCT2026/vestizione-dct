"""Archivio SQLite: i dati veri (non i colori delle celle). 2026 Bruno Roli"""
import os
import sqlite3
from datetime import date
from .modelli import *

DAL_ORIGINE = "2000-01-01"   # data di validita' della configurazione di partenza

# Turni di Natale (25/12), come Config_Natale del VBA v18 (09/11/2026): (tipo, codice, ordine, inizio, fine).
# Tipi: TURNO (principali), SUSS (sussidiari), DISP (coda dei disponibili), PARAM (TurniCoperti: valore in ordine).
NATALE_DAL = "2026-12-25"
NATALE_BASE = [      # v18b: il 630 e' un turno principale, nessun sussidiario
    ("TURNO", "603", 1, "07:45", "11:45"), ("TURNO", "605", 2, "08:30", "12:30"),
    ("TURNO", "604", 3, "12:00", "16:00"), ("TURNO", "608", 4, "12:30", "16:30"),
    ("TURNO", "606", 5, "16:00", "20:00"), ("TURNO", "602", 6, "16:30", "20:30"),
    ("TURNO", "630", 7, "20:15", "00:15"), ("TURNO", "610", 8, "20:30", "00:30"),
    ("DISP", "601", 1, "", ""), ("DISP", "607V", 2, "", ""), ("DISP", "Dd8", 3, "", ""),
    ("DISP", "Dd2", 4, "", ""), ("DISP", "Dd5", 5, "", ""),
    ("PARAM", "TurniCoperti", 8, "", ""),
]
# valori di partenza della v0.29 (630 sussidiario): se un archivio li ha ancora cosi', si sostituiscono
_NATALE_BASE_V029 = [
    ("TURNO", "603", 1, "07:45", "11:45"), ("TURNO", "605", 2, "08:30", "12:30"),
    ("TURNO", "604", 3, "12:00", "16:00"), ("TURNO", "608", 4, "12:30", "16:30"),
    ("TURNO", "606", 5, "16:00", "20:00"), ("TURNO", "602", 6, "16:30", "20:30"),
    ("TURNO", "610", 7, "20:30", "00:30"), ("SUSS", "630", 1, "20:15", "00:15"),
    ("DISP", "601", 1, "", ""), ("DISP", "607V", 2, "", ""), ("DISP", "Dd8", 3, "", ""),
    ("DISP", "Dd2", 4, "", ""), ("DISP", "Dd5", 5, "", ""),
    ("PARAM", "TurniCoperti", 8, "", ""),
]


def _ora(v):
    """Orario come testo hh:mm da un valore Excel (time, datetime, frazione di giorno o testo)."""
    if v is None or v == "":
        return ""
    if hasattr(v, "hour"):
        return "%02d:%02d" % (v.hour, v.minute)
    if isinstance(v, (int, float)):
        m = int(round(float(v) % 1 * 1440))
        return "%02d:%02d" % (m // 60 % 24, m % 60)
    return str(v).strip()[:5]


def _leggi_config_natale(wb):
    """Righe di Config_Natale (foglio nascosto del VBA v18), se c'e'; intestazioni cercate per nome."""
    if "Config_Natale" not in wb.sheetnames:
        return None
    ws = wb["Config_Natale"]
    righe = list(ws.iter_rows(values_only=True))
    for k, r in enumerate(righe):
        nomi = [str(x).strip().lower() if x is not None else "" for x in r]
        if "validodal" in nomi and "tipo" in nomi and "codice" in nomi:
            col = {n: nomi.index(n) for n in ("validodal", "tipo", "codice", "ordine", "inizio", "fine") if n in nomi}
            out = []
            for r2 in righe[k + 1:]:
                g = lambda n: r2[col[n]] if n in col and col[n] < len(r2) else None
                v, tipo, cod = g("validodal"), (g("tipo") or ""), g("codice")
                if not v or not tipo or cod in (None, ""):
                    continue
                vd = v.date().isoformat() if hasattr(v, "date") else str(v)[:10]
                tipo = str(tipo).strip().upper()
                ordv = g("ordine")
                if tipo == "PARAM":   # il valore puo' stare in Ordine, Inizio o Fine
                    for x in (g("ordine"), g("inizio"), g("fine")):
                        if isinstance(x, (int, float)) or (isinstance(x, str) and x.strip().isdigit()):
                            ordv = int(float(x)); break
                    out.append((vd, tipo, str(cod).strip(), int(ordv or 0), "", ""))
                else:
                    out.append((vd, tipo, str(cod).strip(), int(float(ordv or 0)), _ora(g("inizio")), _ora(g("fine"))))
            return out
    return None

SCHEMA = """
CREATE TABLE IF NOT EXISTS persone(pos INTEGER, nome TEXT, gruppo TEXT, inizio TEXT, fine TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS graduatoria(ordine INTEGER, nome TEXT);
CREATE TABLE IF NOT EXISTS cfg_turni(valido_dal TEXT, codice TEXT, fer_i TEXT, fer_f TEXT, sab_i TEXT, sab_f TEXT, dom_i TEXT, dom_f TEXT);
CREATE TABLE IF NOT EXISTS cfg_disponibilita(valido_dal TEXT, modalita TEXT, posizione INTEGER, codice TEXT);
CREATE TABLE IF NOT EXISTS cfg_sussidiari(valido_dal TEXT, chiave TEXT, priorita INTEGER, codice TEXT, inizio TEXT, fine TEXT);
CREATE TABLE IF NOT EXISTS cfg_motivazioni(tipo TEXT, codice TEXT);
CREATE TABLE IF NOT EXISTS calendario(data TEXT, pos INTEGER, valore TEXT, tipo TEXT, diag TEXT, PRIMARY KEY(data,pos));
CREATE TABLE IF NOT EXISTS assegnazioni(anno INTEGER, pos INTEGER, data TEXT, turno TEXT, tipo TEXT);
CREATE TABLE IF NOT EXISTS note_celle(data TEXT, pos INTEGER, testo TEXT, PRIMARY KEY(data,pos));
CREATE TABLE IF NOT EXISTS note_settimana(anno INTEGER, settimana INTEGER, giorno TEXT, collega TEXT, nota TEXT);
CREATE TABLE IF NOT EXISTS log_import(quando TEXT, file TEXT, anno INTEGER, data TEXT, pos INTEGER, nome TEXT, cosa TEXT, da TEXT, a TEXT);
CREATE TABLE IF NOT EXISTS meta(chiave TEXT PRIMARY KEY, valore TEXT);
CREATE TABLE IF NOT EXISTS cfg_natale(valido_dal TEXT, tipo TEXT, codice TEXT, ordine INTEGER, inizio TEXT, fine TEXT);
"""


def importa_da_xlsm(percorso_xlsm, percorso_db, fine_anno=None):
    from .xlsm import Archivio
    from datetime import timedelta
    a = Archivio(percorso_xlsm)
    con = sqlite3.connect(percorso_db)
    con.executescript(SCHEMA)
    for t in ("persone", "graduatoria", "cfg_turni", "cfg_disponibilita", "cfg_sussidiari",
              "cfg_motivazioni", "calendario", "assegnazioni", "note_settimana", "note_celle", "cfg_natale"):
        con.execute("DELETE FROM " + t)
    wb = a.wb
    nat = _leggi_config_natale(wb) or [(NATALE_DAL,) + r for r in NATALE_BASE]
    con.executemany("INSERT INTO cfg_natale VALUES(?,?,?,?,?,?)", nat)
    for r in wb["Persone"].iter_rows(min_row=5, max_row=100, max_col=6, values_only=True):
        if isinstance(r[0], (int, float)) and 1 <= r[0] <= 14:
            f = lambda v: v.date().isoformat() if hasattr(v, "date") else None
            con.execute("INSERT INTO persone VALUES(?,?,?,?,?,?)",
                        (int(r[0]), r[1] or "", r[2] or "", f(r[3]), f(r[4]), r[5] or ""))
    # graduatoria DCT: righe sotto l'intestazione, nome in B e ordine in F
    ws = wb["Persone"]
    riga = None
    for r in range(1, 60):
        if str(ws.cell(r, 2).value or "").strip() == "Graduatoria DCT":
            riga = r
    if riga:
        for r in range(riga + 1, riga + 40):
            n, o = ws.cell(r, 2).value, ws.cell(r, 6).value
            if n and isinstance(o, (int, float)):
                con.execute("INSERT INTO graduatoria VALUES(?,?)", (int(o), str(n)))
    for c, t in a.config.turni.items():
        con.execute("INSERT INTO cfg_turni VALUES(?,?,?,?,?,?,?,?)",
                    (DAL_ORIGINE, c, *t["Feriale"], *t["Sabato"], *t["Domenica"]))
    for m, cod in a.config.disponibilita.items():
        for i, c in enumerate(cod, 1):
            con.execute("INSERT INTO cfg_disponibilita VALUES(?,?,?,?)", (DAL_ORIGINE, m, i, c))
    for k, v in a.config.sussidiari.items():
        for i, (c, ini, fin) in enumerate(v, 1):
            con.execute("INSERT INTO cfg_sussidiari VALUES(?,?,?,?,?,?)", (DAL_ORIGINE, k, i, c, ini, fin))
    for t, cod in a.config.motivazioni.items():
        for c in cod:
            con.execute("INSERT INTO cfg_motivazioni VALUES(?,?)", (t, c))
    for x in a.assegnazioni:
        con.execute("INSERT INTO assegnazioni VALUES(?,?,?,?,?)", (x.anno, x.pos, x.data.isoformat(), x.turno, x.tipo))
    # calendario: tutti i giorni presenti nei fogli anno
    for nome in wb.sheetnames:
        if nome.isdigit():
            anno = int(nome)
            mi = 10 if anno == 2026 else 1
            for mese in range(mi, 13):
                d = date(anno, mese, 1)
                while d.month == mese:
                    for pos in range(1, 15):
                        c = a.cella(d, pos)
                        if c is not None:
                            con.execute("INSERT INTO calendario VALUES(?,?,?,?,?)",
                                        (d.isoformat(), pos, c.valore, c.tipo, c.diag))
                    d += timedelta(days=1)
    # note (commenti) sulle celle dei fogli anno
    for nome in wb.sheetnames:
        if nome.isdigit():
            ws_a = wb[nome]
            anno = int(nome)
            mi = 10 if anno == 2026 else 1
            for mese in range(mi, 13):
                base = 3 + (mese - mi) * 19
                ng = (date(anno + (mese == 12), mese % 12 + 1, 1) - date(anno, mese, 1)).days
                for pos in range(1, 15):
                    for g in range(1, ng + 1):
                        cm = ws_a.cell(base + 2 + pos, 4 + g - 1).comment
                        if cm is not None and cm.text:
                            con.execute("INSERT INTO note_celle VALUES(?,?,?)", (date(anno, mese, g).isoformat(), pos, cm.text))
    # note delle settimane (il testo lungo e' spezzato su piu' righe nel foglio)
    note = []
    for nome in wb.sheetnames:
        if nome.startswith("Settimana_"):
            _, anno, nn = nome.split("_")
            w = wb[nome]
            ultima = None
            for r in range(34, 60):
                g, col, nota = w.cell(r, 5).value, w.cell(r, 7).value, w.cell(r, 9).value
                if (g or col) and nota:
                    ultima = [int(anno), int(nn), str(g or ""), str(col or ""), str(nota)]
                    note.append(ultima)
                elif nota and not (g or col) and ultima:
                    ultima[4] += " " + str(nota)  # riga di continuazione
            for n in note:
                con.execute("INSERT INTO note_settimana VALUES(?,?,?,?,?)", tuple(n))
            note = []
    con.execute("INSERT OR REPLACE INTO meta VALUES('origine',?)", (os.path.basename(str(percorso_xlsm)),))
    con.commit()
    con.close()


class ArchivioDB:
    """Stessa interfaccia di xlsm.Archivio, ma legge dal database."""

    def __init__(self, percorso_db):
        self.con = sqlite3.connect(percorso_db, check_same_thread=False)  # il server gira in un thread proprio (un solo thread alla volta)
        c = self.con
        # archivi creati prima dei turni di Natale: tabella e valori di partenza
        c.execute("CREATE TABLE IF NOT EXISTS cfg_natale(valido_dal TEXT, tipo TEXT, codice TEXT, ordine INTEGER, inizio TEXT, fine TEXT)")
        if not c.execute("SELECT 1 FROM cfg_natale LIMIT 1").fetchone():
            c.executemany("INSERT INTO cfg_natale VALUES(?,?,?,?,?,?)", [(NATALE_DAL,) + r for r in NATALE_BASE])
            c.commit()
        else:   # v0.29 -> v18b: valori di partenza col 630 sussidiario sostituiti (le versioni cambiate a mano restano)
            for (v,) in c.execute("SELECT DISTINCT valido_dal FROM cfg_natale").fetchall():
                righe = sorted(tuple(r) for r in c.execute(
                    "SELECT tipo, codice, ordine, inizio, fine FROM cfg_natale WHERE valido_dal=?", (v,)))
                if righe == sorted(_NATALE_BASE_V029):
                    c.execute("DELETE FROM cfg_natale WHERE valido_dal=?", (v,))
                    c.executemany("INSERT INTO cfg_natale VALUES(?,?,?,?,?,?)", [(v,) + r for r in NATALE_BASE])
            c.commit()
        self.natale = self._leggi_natale()
        self.versioni = self._leggi_versioni()
        self.config = self.config_alla(date.max)   # la piu' recente
        mot = {}
        for t, cod in c.execute("SELECT * FROM cfg_motivazioni"):
            mot.setdefault(t, []).append(cod)
        self.motivazioni = mot
        d = lambda s: date.fromisoformat(s) if s else None
        self.persone = [Persona(r[0], r[1], r[2], d(r[3]) or date.min, d(r[4]) or date.max)
                        for r in c.execute("SELECT pos,nome,gruppo,inizio,fine FROM persone")]
        self.assegnazioni = [Assegnazione(r[0], r[1], date.fromisoformat(r[2]), r[3], r[4])
                             for r in c.execute("SELECT * FROM assegnazioni")]
        self._cal = {(r[0], r[1]): Cella(r[2], r[3], r[4] or "")
                     for r in c.execute("SELECT * FROM calendario")}

    def _leggi_versioni(self):
        c = self.con
        date_v = sorted({r[0] for r in c.execute("SELECT valido_dal FROM cfg_turni")})
        mot = {}
        for t, cod in c.execute("SELECT * FROM cfg_motivazioni"):
            mot.setdefault(t, []).append(cod)
        out = {}
        for v in date_v:
            turni = {}
            for r in c.execute("SELECT * FROM cfg_turni WHERE valido_dal=?", (v,)):
                turni[r[1]] = {"Feriale": (r[2], r[3]), "Sabato": (r[4], r[5]), "Domenica": (r[6], r[7])}
            disp = {}
            for m, p, cod in c.execute("SELECT modalita, posizione, codice FROM cfg_disponibilita WHERE valido_dal=? "
                                       "ORDER BY modalita, posizione", (v,)):
                disp.setdefault(m, []).append(cod)
            suss = {}
            for k, p, cod, ini, fin in c.execute("SELECT chiave, priorita, codice, inizio, fine FROM cfg_sussidiari WHERE valido_dal=? "
                                            "ORDER BY chiave, priorita", (v,)):
                suss.setdefault(k, []).append((cod, ini, fin))
            out[v] = Config(turni, disp, suss, mot)
        return out

    def _leggi_natale(self):
        out = {}
        for v, tipo, cod, ordine, ini, fin in self.con.execute(
                "SELECT valido_dal, tipo, codice, ordine, inizio, fine FROM cfg_natale ORDER BY valido_dal, tipo, ordine"):
            x = out.setdefault(v, {"TURNO": [], "SUSS": [], "DISP": [], "PARAM": {}})
            if tipo == "PARAM":
                x["PARAM"][cod] = ordine
            elif tipo in x:
                x[tipo].append((cod, ini or "", fin or ""))
        return out

    def natale_alla(self, d):
        """Configurazione dei turni di Natale se d e' il 25/12 (versione piu' recente con valido_dal <= d,
        se nessuna la piu' antica), altrimenti None."""
        if (d.month, d.day) != (12, 25) or not self.natale:
            return None
        valide = [v for v in self.natale if v <= d.isoformat()]
        return self.natale[max(valide) if valide else min(self.natale)]

    def config_alla(self, d):
        """Configurazione (orari e priorita') in vigore nel giorno d: l'ultima versione con valido_dal <= d."""
        chiave = d.isoformat() if d != date.max else "9999-12-31"
        valide = [v for v in self.versioni if v <= chiave]
        return self.versioni[max(valide)] if valide else self.versioni[min(self.versioni)]

    def cella(self, d, pos):
        return self._cal.get((d.isoformat(), pos))

    def note_celle(self, anno):
        return {(date.fromisoformat(r[0]), r[1]): r[2]
                for r in self.con.execute("SELECT * FROM note_celle WHERE data BETWEEN ? AND ?",
                                          ("%d-01-01" % anno, "%d-12-31" % anno))}

    def graduatoria(self):
        return [r[1] for r in self.con.execute("SELECT * FROM graduatoria ORDER BY ordine")]

    # ---------- scrittura (usata dalle operazioni)
    def imposta_cella(self, d, pos, tipo, diag=""):
        k = (d.isoformat(), pos)
        old = self._cal.get(k)
        val = old.valore if old else ""
        self._cal[k] = Cella(val, tipo, diag)
        self.con.execute("INSERT OR REPLACE INTO calendario VALUES(?,?,?,?,?)", (k[0], pos, val, tipo, diag))

    def aggiungi_assegnazione(self, anno, pos, d, turno, tipo):
        self.assegnazioni.append(Assegnazione(anno, pos, d, turno, tipo))
        self.con.execute("INSERT INTO assegnazioni VALUES(?,?,?,?,?)", (anno, pos, d.isoformat(), turno, tipo))

    def rimuovi_assegnazione(self, anno, pos, d):
        """Come il VBA: toglie la prima riga che corrisponde, partendo dal fondo."""
        for i in range(len(self.assegnazioni) - 1, -1, -1):
            x = self.assegnazioni[i]
            if x.anno == anno and x.pos == pos and x.data == d:
                del self.assegnazioni[i]
                rows = self.con.execute("SELECT rowid FROM assegnazioni WHERE anno=? AND pos=? AND data=? ORDER BY rowid DESC",
                                        (anno, pos, d.isoformat())).fetchall()
                if rows:
                    self.con.execute("DELETE FROM assegnazioni WHERE rowid=?", (rows[0][0],))
                return True
        return False

    def imposta_nota(self, d, pos, testo):
        if testo:
            self.con.execute("INSERT OR REPLACE INTO note_celle VALUES(?,?,?)", (d.isoformat(), pos, testo))
        else:
            self.con.execute("DELETE FROM note_celle WHERE data=? AND pos=?", (d.isoformat(), pos))

    def ricarica_persone(self):
        d = lambda s: date.fromisoformat(s) if s else None
        self.persone = [Persona(r[0], r[1], r[2], d(r[3]) or date.min, d(r[4]) or date.max)
                        for r in self.con.execute("SELECT pos,nome,gruppo,inizio,fine FROM persone ORDER BY rowid")]

    def ricarica(self):
        """Rilegge dal database lo stato in memoria (dopo un annullamento)."""
        self.ricarica_persone()
        self.natale = self._leggi_natale()
        self.assegnazioni = [Assegnazione(r[0], r[1], date.fromisoformat(r[2]), r[3], r[4])
                             for r in self.con.execute("SELECT * FROM assegnazioni")]
        self._cal = {(r[0], r[1]): Cella(r[2], r[3], r[4] or "")
                     for r in self.con.execute("SELECT * FROM calendario")}

    def salva(self):
        self.con.commit()

    def annulla(self):
        self.con.rollback()


def genera_anno(db, anno, rigenera=False):
    """Scrive nell'archivio la rotazione dell'anno. Non sovrascrive mai un anno gia' presente
    a meno che rigenera=True (in quel caso i colori/assenze inseriti dell'anno vengono persi)."""
    from datetime import timedelta
    from .generatore import genera_valori
    prima = anno == 2026 and 10 or 1
    esiste = db.con.execute("SELECT COUNT(*) FROM calendario WHERE data BETWEEN ? AND ?",
                            ("%d-01-01" % anno, "%d-12-31" % anno)).fetchone()[0]
    if esiste and not rigenera:
        raise ValueError("L'anno %d esiste gia' (%d celle)." % (anno, esiste))
    if esiste:
        db.con.execute("DELETE FROM calendario WHERE data BETWEEN ? AND ?", ("%d-01-01" % anno, "%d-12-31" % anno))
    righe = [(d.isoformat(), pos, v, "", "") for (d, pos), v in genera_valori(anno).items()]
    db.con.executemany("INSERT INTO calendario VALUES(?,?,?,?,?)", righe)
    db.con.commit()
    db._cal = {(r[0], r[1]): Cella(r[2], r[3], r[4] or "")
               for r in db.con.execute("SELECT * FROM calendario")}
    return len(righe)
