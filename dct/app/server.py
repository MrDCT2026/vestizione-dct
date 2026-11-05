"""Programma locale: server HTTP (solo libreria standard) + pagine nel browser.
2026 Bruno Roli"""
import json
import os
import shutil
import socket
import sys
import tempfile
import urllib.parse
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
import threading

# Il server accetta piu' connessioni insieme (WebKit, la finestra del Mac e Safari, apre a volte una connessione
# "di riserva" senza usarla: con un server a connessione singola le pagine restavano bloccate).
# Le richieste pero' vengono eseguite una alla volta, cosi' archivio e stato non si accavallano.
_UNO_ALLA_VOLTA = threading.Lock()


class Server(ThreadingHTTPServer):
    daemon_threads = True


from .. import anagrafica as an
from .. import personale as pe
from ..calendario import anno_iso, is_festivo, lunedi_settimana, modalita, numero_iso
from ..copertura import Motore
from .. import importa as imp
from ..db import ArchivioDB, genera_anno, importa_da_xlsm
from ..operazioni import Operazioni
from ..rotazione import esporta_rotazione
from ..settimana import (GIORNI, GIORNI_BREVI, colore_giorno, conta_dct, costruisci_settimana, soglia, voci_note)

STATICI = os.path.join(os.path.dirname(__file__), "static")
MODELLO = os.path.join(os.path.dirname(__file__), "..", "..", "modello", "Rotazione_modello.xlsm")
COLORI_TIPO = {"CONG_FEST": "FFFF00", "ASS_MAL": "FFC0C0", "104": "FF9900", "CORSI": "008000", "SIND": "0070C0",
               "C_RIP": "FF00FF", "RL": "00B0F0", "MIS": "CC99FF", "RU": "9966CC"}
MESI = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre",
        "Ottobre", "Novembre", "Dicembre"]


class Errore(Exception):
    pass


class Programma:
    """Stato del programma: cartella dati, archivio aperto, data di oggi."""

    def __init__(self, cartella, oggi=None):
        self.cartella = cartella
        os.makedirs(os.path.join(cartella, "backup"), exist_ok=True)
        self.percorso = os.path.join(cartella, "archivio.db")
        self.oggi = oggi or date.today()
        self.arch = None
        self.ultimo_salvataggio = None
        self.imp = None          # importazione in anteprima: {cambi, anno, nome, fuori}
        if os.path.exists(self.percorso):
            self.apri()

    def apri(self):
        self.arch = ArchivioDB(self.percorso)
        self.op = Operazioni(self.arch)
        self.mot = Motore(self.arch)

    def importa(self, dati_xlsm):
        tmp = os.path.join(self.cartella, "importazione.xlsm")
        with open(tmp, "wb") as f:
            f.write(dati_xlsm)
        nuovo = os.path.join(self.cartella, "archivio_nuovo.db")
        importa_da_xlsm(tmp, nuovo)
        os.remove(tmp)
        if os.path.exists(self.percorso):
            shutil.copy(self.percorso, os.path.join(self.cartella, "backup", "prima_importazione_%s.db" % datetime.now().strftime("%Y%m%d_%H%M%S")))
        if self.arch is not None:
            self.arch.con.close()
            self.arch = None
        os.replace(nuovo, self.percorso)
        self.apri()

    def copia_di_sicurezza(self):
        """Dopo ogni modifica: copia dell'archivio (se ne tengono 30)."""
        self.arch.con.commit()
        adesso = datetime.now()
        self.ultimo_salvataggio = adesso
        dest = os.path.join(self.cartella, "backup", "archivio_%s.db" % adesso.strftime("%Y%m%d_%H%M%S_%f"))
        try:
            shutil.copy(self.percorso, dest)
            copie = sorted(f for f in os.listdir(os.path.join(self.cartella, "backup")) if f.startswith("archivio_"))
            for f in copie[:-30]:
                os.remove(os.path.join(self.cartella, "backup", f))
        except OSError:
            pass


# ------------------------------------------------------------------ dati per le schermate
def _mesi_presenti(arch):
    righe = arch.con.execute("SELECT DISTINCT substr(data,1,7) FROM calendario ORDER BY 1").fetchall()
    return [(int(r[0][:4]), int(r[0][5:7])) for r in righe]


def stato(P):
    if P.arch is None:
        return {"aperto": False, "oggi": P.oggi.isoformat(), "programma": "Vestizione DCT", "cartella": os.path.abspath(P.cartella)}
    mesi = _mesi_presenti(P.arch)
    return {"aperto": True, "oggi": P.oggi.isoformat(), "mesi": mesi, "programma": "Vestizione DCT", "cartella": os.path.abspath(P.cartella),
            "anni": sorted({a for a, _ in mesi}),
            "salvato": P.ultimo_salvataggio.strftime("%H:%M") if P.ultimo_salvataggio else None}


def _celle_giorni(P, giorni):
    """Per ogni posizione la lista delle celle dei giorni dati."""
    arch, mot = P.arch, P.mot
    note = {}
    for a in {d.year for d in giorni}:
        note.update(arch.note_celle(a))
    dati = [mot.dati_giorno(d) for d in giorni]
    righe = []
    for pos in range(1, 15):
        nomi = []
        celle = []
        for g, d in enumerate(giorni):
            c = dati[g][pos]
            n = c.nome.strip()
            if n and n not in nomi:
                nomi.append(n)
            if c.tipo in COLORI_TIPO:
                fill = COLORI_TIPO[c.tipo]
            elif not n:
                fill = "E6E6E6"
            else:
                fill = colore_giorno(d)
            celle.append({"v": c.valore, "t": c.tipo, "diag": c.diag, "dfill": COLORI_TIPO.get(c.diag, "000000") if c.diag else "", "fill": fill, "vuota": not n,
                          "nota": note.get((d, pos), "")})
        righe.append({"pos": pos, "nome": "/".join(nomi), "gruppo": mot.gruppo(pos), "celle": celle})
    dct = []
    for g, d in enumerate(giorni):
        n, s = conta_dct(dati[g]), soglia(d)
        dct.append({"n": n, "soglia": s, "sotto": n < s})
    return righe, dct


def _testata_giorni(giorni):
    return [{"data": d.isoformat(), "g": d.day, "dow": GIORNI_BREVI[d.weekday()], "fill": colore_giorno(d),
             "festivo": is_festivo(d)} for d in giorni]


def dati_anno(P, anno, mese):
    primo = date(anno, mese, 1)
    ultimo = (date(anno + (mese == 12), mese % 12 + 1, 1) - timedelta(days=1))
    giorni = [primo + timedelta(i) for i in range((ultimo - primo).days + 1)]
    giorni = [d for d in giorni if P.arch.cella(d, 1) is not None]
    if not giorni:
        raise Errore("Il mese %s %d non è nel calendario." % (MESI[mese], anno))
    righe, dct = _celle_giorni(P, giorni)
    mancanti = sum(max(0, x["soglia"] - x["n"]) for x in dct)
    return {"anno": anno, "mese": mese, "titolo": "%s %d" % (MESI[mese], anno), "giorni": _testata_giorni(giorni),
            "righe": righe, "dct": dct, "mancanti": mancanti}


def dati_settimana(P, anno, nn):
    lun = lunedi_settimana(anno, nn)
    giorni = [lun + timedelta(i) for i in range(7)]
    if any(P.arch.cella(d, 1) is None for d in giorni[:1]) and all(P.arch.cella(d, 1) is None for d in giorni):
        raise Errore("La settimana %d/%d non è nel calendario." % (nn, anno))
    righe, dct = _celle_giorni(P, giorni)
    note = [{"giorno": g, "nome": n, "testo": t} for g, n, t in voci_note(P.arch, giorni, [P.mot.dati_giorno(d) for d in giorni])]
    blocchi = []
    for g, d in enumerate(giorni):
        gc = P.mot.calcola_giorno(d)
        rr = [{"cod": t.codice, "nome": t.nome, "nota": t.nota, "scoperto": bool(t.scoperto), "tipo": "T"} for t in gc.turni]
        rr += [{"cod": s.codice, "nome": s.nome, "nota": s.nota, "scoperto": False, "tipo": "S"}
               for s in gc.sussidiari if not s.scoperto and s.nome.strip()]
        for k, a in enumerate(gc.assenti):
            rr.append({"cod": "Ass.:" if k == 0 else "", "nome": a.nome, "nota": a.motivazione, "scoperto": False, "tipo": "A"})
        blocchi.append({"data": d.isoformat(), "titolo": "%s  %s" % (GIORNI[g], d.strftime("%d/%m/%Y")),
                        "fill": colore_giorno(d), "righe": rr, "modalita": gc.modalita})
    cfg = P.arch.config_alla(lun)
    scoperti = sum(1 for b in blocchi for r in b["righe"] if r["scoperto"])
    return {"anno": anno, "nn": nn, "dal": lun.isoformat(), "al": giorni[-1].isoformat(),
            "giorni": _testata_giorni(giorni), "righe": righe, "dct": dct, "blocchi": blocchi,
            "note": note, "scoperti": scoperti, "generata": datetime.now().strftime("%H:%M")}


MAX_RIGHE_ANTEPRIMA = 2000


def _anteprima(P):
    i = P.imp
    return {"nome": i["nome"], "anno": i["anno"], "fuori": i["fuori"], "riepilogo": imp.riepilogo(i["cambi"]),
            "righe": [{"data": c.data.isoformat(), "nome": c.nome, "pos": c.pos, "tipo": c.tipo, "vecchio": c.vecchio,
                       "nuovo": c.nuovo, "stato": c.stato, "motivo": c.motivo} for c in i["cambi"][:MAX_RIGHE_ANTEPRIMA]]}


def import_analizza(P, corpo, q):
    if P.arch is None:
        raise Errore("Nessun archivio: importa prima il file Vestizione dalla Home.")
    if not corpo:
        raise Errore("Scegli il file della Rotazione.")
    tmp = os.path.join(P.cartella, "rotazione_da_importare.xlsm")
    with open(tmp, "wb") as f:
        f.write(corpo)
    try:
        cambi, fuori, anno = imp.analizza(P.arch, tmp, int(q["anno"]), int(q["da"]), int(q["a"]))
    except imp.ErroreImport as e:
        raise Errore(str(e))
    except Exception as e:
        raise Errore("Il file non si riesce a leggere come Rotazione (%s)." % e)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    P.imp = {"cambi": cambi, "anno": anno, "nome": q.get("nome") or "Rotazione.xlsm", "fuori": fuori}
    return _anteprima(P)


def import_applica(P):
    if not P.imp:
        raise Errore("Nessuna importazione in anteprima: analizza prima un file.")
    i = P.imp
    n_colori, n_note = imp.applica(P.arch, i["cambi"], i["anno"], i["nome"])
    P.imp = None
    P.mot = Motore(P.arch)
    P.op = Operazioni(P.arch)
    P.copia_di_sicurezza()
    return {"ok": True, "colori": n_colori, "note": n_note}


def dati_rl(P, anno):
    righe = []
    for x in sorted(P.arch.assegnazioni, key=lambda x: (x.data, x.pos)):
        if x.anno == anno and x.tipo == "RL":
            righe.append({"data": x.data.isoformat(), "pos": x.pos, "nome": P.mot.chi_in_servizio(x.pos, x.data) or "(posizione libera)",
                          "gruppo": P.mot.gruppo(x.pos), "turno": x.turno})
    mesi = {}
    colleghi = {}
    for r in righe:
        m = int(r["data"][5:7])
        mesi[m] = mesi.get(m, 0) + 1
        colleghi[r["nome"]] = colleghi.get(r["nome"], 0) + 1
    inizio = min([m for a, m in _mesi_presenti(P.arch) if a == anno] or [1])
    return {"anno": anno, "righe": righe, "totale": len(righe),
            "mesi": [{"mese": m, "nome": MESI[m], "n": mesi.get(m, 0)} for m in range(inizio, 13)],
            "colleghi": sorted(({"nome": n, "n": c} for n, c in colleghi.items()), key=lambda x: (-x["n"], x["nome"]))}


def esporta_rl(P, anno, cartella):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    d = dati_rl(P, anno)
    wb = Workbook()
    ws = wb.active
    ws.title = "RL_%d" % anno
    sottile = Side(style="thin", color="000000")
    bordo = Border(left=sottile, right=sottile, top=sottile, bottom=sottile)
    ws["A1"] = "Riposi lavorati (RL) %d" % anno
    ws["A1"].font = Font(name="Calibri", bold=True, size=14)
    ws.row_dimensions[1].height = 22
    r = 3
    for col, t in zip("ABCDE", ("", "Data", "Collega", "Gruppo", "Turno coperto")):
        c = ws["%s%d" % (col, r)]
        c.value = t or None
        c.font = Font(name="Calibri", bold=True)
        c.fill = PatternFill("solid", fgColor="FFE3E9F1")
        c.border = bordo
        c.alignment = Alignment(horizontal="center", vertical="center")
    for x in d["righe"]:
        r += 1
        ws.cell(r, 1).fill = PatternFill("solid", fgColor="FF00B0F0")
        ws.cell(r, 2, date.fromisoformat(x["data"])).number_format = "dd/mm/yyyy"
        ws.cell(r, 3, x["nome"])
        ws.cell(r, 4, x["gruppo"])
        ws.cell(r, 5, x["turno"])
        for c in range(1, 6):
            ws.cell(r, c).border = bordo
            ws.cell(r, c).alignment = Alignment(horizontal="left" if c == 3 else "center", vertical="center")
    r += 2
    ws.cell(r, 2, "Riepilogo per collega").font = Font(name="Calibri", bold=True)
    for c in d["colleghi"]:
        r += 1
        ws.cell(r, 2, c["nome"])
        ws.cell(r, 5, c["n"]).alignment = Alignment(horizontal="center")
    r += 1
    ws.cell(r, 2, "Totale anno").font = Font(name="Calibri", bold=True)
    ws.cell(r, 5, d["totale"]).font = Font(name="Calibri", bold=True)
    ws.cell(r, 5).alignment = Alignment(horizontal="center")
    for riga in ws.iter_rows():
        for c in riga:
            if c.value is not None and c.font.name != "Calibri":
                c.font = Font(name="Calibri", size=c.font.size or 11, bold=c.font.b)
    for col, w in zip("ABCDE", (3, 13, 24, 9, 16)):
        ws.column_dimensions[col].width = w
    f = os.path.join(cartella, "RL_%d.xlsx" % anno)
    wb.save(f)
    return f


def esito_json(e):
    return {"ok": e.ok, "msg": e.msg, "colorate": e.colorate, "ripristinate": e.ripristinate, "saltate": e.saltate,
            "motivi": e.motivi, "chiede_cancellazione": e.chiede_cancellazione}


def _data(s):
    return date.fromisoformat(s)


# ------------------------------------------------------------------ API
def api_get(P, percorso, q):
    if percorso == "/api/stato":
        return stato(P)
    if P.arch is None:
        raise Errore("Nessun archivio: importa prima il file Vestizione dalla Home.")
    if percorso == "/api/anno":
        return dati_anno(P, int(q["anno"]), int(q["mese"]))
    if percorso == "/api/settimana":
        return dati_settimana(P, int(q["anno"]), int(q["nn"]))
    if percorso == "/api/settimana_di":
        d = _data(q["data"])
        return {"anno": anno_iso(d), "nn": numero_iso(d)}
    if percorso == "/api/personale":
        d = _data(q["data"]) if q.get("data") else P.oggi
        return {"data": d.isoformat(),
                "elenco": [{"pos": a, "nome": n, "gruppo": g, "dal": dal and dal.isoformat(), "al": al and al.isoformat()}
                           for a, n, g, dal, al in pe.elenco(P.arch, d)],
                "graduatoria": P.arch.graduatoria(),
                "programmati": [{"tipo": t, "pos": p, "nome": n, "data": dd.isoformat()}
                                for t, p, n, dd in pe.programmati(P.arch, P.oggi)]}
    if percorso == "/api/import/anteprima":
        ultima = P.arch.con.execute("SELECT quando, file FROM log_import ORDER BY quando DESC LIMIT 1").fetchone()
        r = {"ultima": {"quando": ultima[0], "file": ultima[1]} if ultima and ultima[0] else None}
        if P.imp:
            r["anteprima"] = _anteprima(P)
        return r
    if percorso == "/api/rl":
        return dati_rl(P, int(q["anno"]))
    if percorso == "/api/anagrafica":
        d = _data(q["data"]) if q.get("data") else P.oggi
        a = an.leggi(P.arch, d)
        return {"data": d.isoformat(), "valida_dal": a["valida_dal"],
                "turni": [{"codice": c, "orari": {m: list(o) for m, o in mm.items()}} for c, mm in a["turni"].items()],
                "sussidiari": {k: [{"codice": c, "inizio": i, "fine": f} for c, i, f in v] for k, v in a["sussidiari"].items()},
                "disponibilita": a["disponibilita"],
                "programmate": [v for v in an.versioni(P.arch) if v > P.oggi.isoformat()]}
    if percorso == "/api/rl_turni":
        d = _data(q["data"])
        mod = modalita(d)
        turni = [t for t in P.mot.turni_principali(mod, d) if P.op.turno_scoperto(t, d)]
        t = P.op.tipo(d, int(q["pos"]))
        return {"turni": turni, "tipo": t, "riposo": P.op.val(d, int(q["pos"])) == "R"}
    raise Errore("Richiesta sconosciuta.")


def api_post(P, percorso, corpo):
    if P.arch is None:
        raise Errore("Nessun archivio: importa prima il file Vestizione dalla Home.")
    if percorso == "/api/tasto":
        e = P.op.applica_tasto(corpo["tasto"], [(_data(d), int(p)) for d, p in corpo["celle"]])
    elif percorso == "/api/cancella":
        e = P.op.cancella(_data(corpo["data"]), int(corpo["pos"]))
    elif percorso == "/api/rl":
        e = P.op.rl(_data(corpo["data"]), int(corpo["pos"]), corpo.get("turno"))
    elif percorso == "/api/cambio_servizio":
        e = P.op.cambio_riposo_servizio(_data(corpo["data"]), int(corpo["pos"]), corpo.get("turno"))
    elif percorso == "/api/cambio_personale":
        e = P.op.cambio_riposo_personale(_data(corpo["data"]), int(corpo["pos1"]), int(corpo["pos2"]))
    elif percorso.startswith("/api/personale/"):
        az = percorso.rsplit("/", 1)[1]
        A, oggi = P.arch, P.oggi
        if az == "uscita":
            pe.uscita(A, int(corpo["pos"]), _data(corpo["data"]), oggi)
        elif az == "ingresso":
            pe.ingresso(A, int(corpo["pos"]), corpo["nome"], _data(corpo["data"]), oggi, bool(corpo.get("da_graduatoria", True)))
        elif az == "annulla_uscita":
            pe.annulla_uscita(A, int(corpo["pos"]), oggi)
        elif az == "annulla_ingresso":
            pe.annulla_ingresso(A, int(corpo["pos"]), _data(corpo["data"]), oggi)
        elif az == "aggiungi":
            pe.aggiungi_in_graduatoria(A, corpo["nome"], corpo.get("posto"))
        elif az == "togli":
            pe.togli_dalla_graduatoria(A, corpo["nome"])
        elif az == "sposta":
            pe.sposta_in_graduatoria(A, corpo["nome"], int(corpo["posto"]))
        else:
            raise Errore("Richiesta sconosciuta.")
        P.copia_di_sicurezza()
        return {"ok": True}
    elif percorso.startswith("/api/anagrafica/"):
        az = percorso.rsplit("/", 1)[1]
        A, oggi, dal = P.arch, P.oggi, _data(corpo["dal"]) if corpo.get("dal") else None
        if dal is None:
            raise Errore("Indica da quale giorno vale la modifica.")
        if az == "turno":
            an.imposta_orari_turno(A, corpo["codice"], {m: tuple(o) for m, o in corpo["orari"].items()}, dal, oggi)
        elif az == "sussidiari":
            an.imposta_sussidiari(A, corpo["chiave"], [(r["codice"], r["inizio"], r["fine"]) for r in corpo["righe"]], dal, oggi)
        elif az == "disponibilita":
            an.cambia_priorita_disponibilita(A, corpo["modalita"], corpo["ordine"], dal, oggi)
        elif az == "elimina":
            an.elimina_versione(A, dal, oggi)
        else:
            raise Errore("Richiesta sconosciuta.")
        P.mot = Motore(A)
        P.op = Operazioni(A)
        P.copia_di_sicurezza()
        return {"ok": True}
    elif percorso == "/api/nota":
        P.arch.imposta_nota(_data(corpo["data"]), int(corpo["pos"]), corpo.get("testo", ""))
        P.arch.salva()
        P.copia_di_sicurezza()
        return {"ok": True}
    else:
        raise Errore("Richiesta sconosciuta.")
    if e.ok:
        P.copia_di_sicurezza()
    return esito_json(e)


class Gestore(BaseHTTPRequestHandler):
    P = None
    server_version = "VestizioneDCT/0.1"

    def log_message(self, *a):
        pass

    def _invia(self, codice, tipo, corpo, extra=None):
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, obj, codice=200):
        self._invia(codice, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    timeout = 60   # una connessione aperta e mai usata viene chiusa dopo un minuto

    def handle_one_request(self):
        # la lettura della richiesta avviene fuori dal blocco; l'esecuzione dentro, una alla volta
        try:
            self.raw_requestline = self.rfile.readline(65537)
        except (TimeoutError, OSError):
            self.close_connection = True
            return
        if len(self.raw_requestline) > 65536:
            self.requestline = self.request_version = self.command = ""
            self.send_error(414)
            return
        if not self.raw_requestline:
            self.close_connection = True
            return
        if not self.parse_request():
            return
        metodo = getattr(self, "do_" + self.command, None)
        if metodo is None:
            self.send_error(501, "Unsupported method (%r)" % self.command)
            return
        # il contenuto inviato (es. un file) si legge prima del turno: un invio lento o interrotto
        # non deve far aspettare le altre richieste (menu, pagine)
        self._corpo = b""
        if self.command == "POST":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                self._corpo = self.rfile.read(n) if n > 0 else b""
            except (TimeoutError, OSError, ValueError):
                self.close_connection = True
                return
            if n > 0 and len(self._corpo) < n:      # invio interrotto
                self.close_connection = True
                return
        with _UNO_ALLA_VOLTA:
            metodo()
        self.wfile.flush()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path.startswith("/api/esporta/"):
                return self._esporta(u.path, q)
            if u.path.startswith("/api/"):
                return self._json(api_get(self.P, u.path, q))
            nome = "index.html" if u.path in ("/", "") else u.path.lstrip("/")
            f = os.path.normpath(os.path.join(STATICI, nome))
            if not f.startswith(STATICI) or not os.path.isfile(f):
                return self._invia(404, "text/plain", b"Non trovato")
            tipo = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8",
                    "css": "text/css; charset=utf-8", "svg": "image/svg+xml"}.get(f.rsplit(".", 1)[-1], "application/octet-stream")
            with open(f, "rb") as fh:
                self._invia(200, tipo, fh.read())
        except Errore as e:
            self._json({"errore": str(e)}, 400)
        except (KeyError, ValueError) as e:
            self._json({"errore": "Richiesta non valida (%s)." % e}, 400)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        corpo = getattr(self, "_corpo", b"")
        try:
            if u.path == "/api/import/analizza":
                q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
                return self._json(import_analizza(self.P, corpo, q))
            if u.path == "/api/import/applica":
                return self._json(import_applica(self.P))
            if u.path == "/api/import/annulla":
                self.P.imp = None
                return self._json({"ok": True})
            if u.path == "/api/importa":
                self.P.importa(corpo)
                return self._json(stato(self.P))
            if u.path == "/api/genera_anno":
                anno = int(json.loads(corpo)["anno"])
                if self.P.arch is None:
                    raise Errore("Nessun archivio.")
                genera_anno(self.P.arch, anno)
                self.P.copia_di_sicurezza()
                return self._json(stato(self.P))
            self._json(api_post(self.P, u.path, json.loads(corpo or b"{}")))
        except Errore as e:
            self._json({"errore": str(e)}, 400)
        except (KeyError, ValueError, an.ErroreAnagrafica, pe.ErrorePersonale) as e:
            self._json({"errore": str(e)}, 400)

    def _esporta(self, percorso, q):
        P = self.P
        if P.arch is None:
            raise Errore("Nessun archivio.")
        tmp = tempfile.mkdtemp()
        if percorso == "/api/esporta/settimana":
            from ..settimana import esporta_settimana
            anno, nn = int(q["anno"]), int(q["nn"])
            f = esporta_settimana(P.arch, anno, nn, tmp)
            tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif percorso == "/api/esporta/rl":
            f = esporta_rl(P, int(q["anno"]), tmp)
            tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif percorso == "/api/esporta/rotazione":
            anno = int(q["anno"])
            f = os.path.join(tmp, "Rotazione_%d.xlsm" % anno)
            esporta_rotazione(P.arch, anno, MODELLO, f)
            tipo = "application/vnd.ms-excel.sheet.macroEnabled.12"
        else:
            raise Errore("Richiesta sconosciuta.")
        with open(f, "rb") as fh:
            dati = fh.read()
        shutil.rmtree(tmp, ignore_errors=True)
        self._invia(200, tipo, dati, {"Content-Disposition": 'attachment; filename="%s"' % os.path.basename(f)})


def indirizzo_rete():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def prepara(cartella=None, porta=8765, rete=False, oggi=None):
    """Crea il server (senza avviarlo). Restituisce (server, porta, cartella) oppure None se non c'e' una porta libera."""
    cartella = cartella or os.path.join(os.path.expanduser("~"), "VestizioneDCT")
    Gestore.P = Programma(cartella, oggi)
    host = "0.0.0.0" if rete else "127.0.0.1"
    for p in range(porta, porta + 20):
        try:
            return Server((host, p), Gestore), p, cartella
        except OSError:
            continue
    return None


def avvia(cartella=None, porta=8765, rete=False, apri_browser=True, oggi=None):
    r = prepara(cartella, porta, rete, oggi)
    if r is None:
        print("Nessuna porta libera.")
        return
    server, porta, cartella = r
    print("Vestizione DCT in funzione: http://127.0.0.1:%d" % porta)
    if rete:
        ip = indirizzo_rete()
        if ip:
            print("Dall'iPad (stessa rete Wi-Fi): http://%s:%d" % (ip, porta))
        print("Attenzione: in rete chiunque sia collegato può aprire il programma.")
    print("Dati in:", cartella)
    print("Per chiudere: Ctrl+C in questa finestra.")
    if apri_browser:
        webbrowser.open("http://127.0.0.1:%d" % porta)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nChiuso.")
