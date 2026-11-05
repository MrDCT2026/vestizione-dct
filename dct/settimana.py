"""Esportazione di una settimana: file Settimana_NN_AAAA.xlsx (stesso foglio che produce la macro).
2026 Bruno Roli"""
import re
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

from .calendario import is_festivo, lunedi_settimana, numero_iso
from .copertura import Motore
from .generatore import gruppo_posizione

GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
GIORNI_BREVI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
ORDINALI = ["Primo", "Secondo", "Terzo", "Quarto", "Quinto", "Sesto", "Settimo", "Ottavo", "Nono", "Decimo"]
SUFFISSO_V = {"601", "606"}          # nei turni disponibili questi due codici si scrivono con la V
RIGHE_MIN = 8
BLOCCHI_COL = [1, 5, 9, 1, 5, 9, 1]
COL_POS, COL_NOME, COL_GR, COL_LUN = 13, 14, 15, 16
LARGH_TESTO = 30
RIGHE_NOTE_MAX = 80

BIANCO, FESTIVO, SABATO, GRIGIO, NOTE_GRIGIO = "FFFFFF", "FF6C5D", "C6EFCE", "E6E6E6", "F2F2F2"
COLORE_TIPO = {"CONG_FEST": "FFFF00", "ASS_MAL": "FFB6C1", "104": "FF9900", "CORSI": "008000", "SIND": "0070C0",
               "C_RIP": "FF00FF", "RL": "00B0F0", "MIS": "CC99FF", "RU": "9966CC"}


def colore_giorno(d):
    if is_festivo(d):
        return FESTIVO
    return {5: SABATO, 6: FESTIVO}.get(d.weekday(), BIANCO)


def soglia(d):
    if is_festivo(d):
        return 6
    return {5: 7, 6: 6}.get(d.weekday(), 8)


def conta_dct(dati_giorno):
    """DCT in servizio in un giorno: dati_giorno = {pos: CellaGiorno}."""
    n = 0
    for c in dati_giorno.values():
        if not c.nome.strip():
            continue
        v = str(c.valore)
        if c.tipo in ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND", "RU"):
            continue
        if c.tipo == "C_RIP":
            n += v == "R"
        elif c.tipo in ("MIS", "RL"):
            n += 1
        elif v != "" and v != "R":
            n += 1
    return n


def voci_note(arch, giorni_d, dati):
    """Note della settimana: [(giorno, collega, testo)]. dati = lista (un elemento per giorno) di {pos: CellaGiorno}."""
    note = {}
    if hasattr(arch, "note_celle"):
        for a in {d.year for d in giorni_d}:
            note.update(arch.note_celle(a))
    voci = []
    for g, d in enumerate(giorni_d):
        for p in range(1, 15):
            t = note.get((d, p))
            if t:
                t = pulisci_nota(t)
                if t:
                    voci.append(("%s %s" % (GIORNI_BREVI[g], d.strftime("%d/%m")), dati[g][p].nome.strip() or "Pos %d" % p, t))
    return voci


def pulisci_nota(testo):
    t = testo.replace("\r\n", "\n").replace("\r", "\n")
    righe = t.split("\n")
    inizio = 1 if len(righe) > 1 and righe[0].strip().endswith(":") else 0
    return " ".join(r.strip() for r in righe[inizio:] if r.strip()).strip()


def spezza_testo(testo, larghezza):
    righe, corrente = [], ""
    for p in [x for x in testo.split(" ") if x]:
        if corrente == "":
            corrente = p
        elif len(corrente) + 1 + len(p) <= larghezza:
            corrente += " " + p
        else:
            righe.append(corrente)
            corrente = p
        while len(corrente) > larghezza:
            righe.append(corrente[:larghezza])
            corrente = corrente[larghezza:]
    if corrente:
        righe.append(corrente)
    return righe


def _orario(i, f):
    return "%s-%s" % (i, f) if i and f else ""


class _Foglio:
    """Raccoglie valori e stili, poi li scrive: i bordi di un'area unita stanno sulla cella in alto a sinistra."""

    def __init__(self, ws):
        self.ws, self.bordi, self.unioni = ws, {}, []

    def set(self, r, c, valore=None, *, b=False, i=False, sz=11, col=None, h=None, v=None, wrap=None, fill=None):
        cella = self.ws.cell(r, c)
        if isinstance(valore, str) and re.fullmatch(r"[1-9]\d*", valore):
            valore = int(valore)          # come fa Excel scrivendo un numero in una cella
        if valore is not None:
            cella.value = valore
        cella.font = Font(name="Calibri", size=sz, bold=b, italic=i, color=col)
        if h or v or wrap:
            cella.alignment = Alignment(horizontal=h, vertical=v, wrap_text=wrap)
        if fill:
            cella.fill = PatternFill("solid", fgColor="FF" + fill)

    def lato(self, r, c, lato, stile):
        self.bordi.setdefault((r, c), {})[lato] = stile

    def griglia(self, r1, c1, r2, c2, stile="thin"):
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                for l in "ltrb":
                    self.lato(r, c, l, stile)

    def intorno(self, r1, c1, r2, c2, stile="medium"):
        for c in range(c1, c2 + 1):
            self.lato(r1, c, "t", stile)
            self.lato(r2, c, "b", stile)
        for r in range(r1, r2 + 1):
            self.lato(r, c1, "l", stile)
            self.lato(r, c2, "r", stile)

    def unisci(self, r1, c1, r2, c2, unione=True):
        self.unioni.append((r1, c1, r2, c2, unione))

    @staticmethod
    def _bordo(lati):
        def sd(k):
            return Side(style=lati[k]) if k in lati else Side()
        return Border(left=sd("l"), right=sd("r"), top=sd("t"), bottom=sd("b"))

    def scrivi(self):
        for (r1, c1, r2, c2, unione) in self.unioni:
            if not unione:
                continue
            tl = self.bordi.setdefault((r1, c1), {})
            for lato, (r, c) in (("l", (r1, c1)), ("t", (r1, c1)), ("r", (r1, c2)), ("b", (r2, c1))):
                s = self.bordi.get((r, c), {}).get(lato)
                if s:
                    tl[lato] = s
                else:
                    tl.pop(lato, None)
        for (r, c), lati in list(self.bordi.items()):      # un bordo spesso condiviso resta sulla cella sopra/a sinistra
            if lati.get("t") == "medium" and self.bordi.get((r - 1, c), {}).get("b") == "medium":
                del lati["t"]
            if lati.get("l") == "medium" and self.bordi.get((r, c - 1), {}).get("r") == "medium":
                del lati["l"]
        for (r, c), lati in self.bordi.items():
            self.ws.cell(r, c).border = self._bordo(lati)
        for (r1, c1, r2, c2, _u) in self.unioni:
            self.ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
        for (r, c), lati in self.bordi.items():        # openpyxl ricopia i bordi sulle celle unite: rimetto i nostri
            self.ws.cell(r, c).border = self._bordo(lati)


def _etichette_disp(codici):
    n = len(codici)
    out = []
    for i, c in enumerate(codici):
        nome = c + ("V" if c in SUFFISSO_V else "")
        out.append("%s %s turno disp." % (nome, "Ultimo" if i == n - 1 else ORDINALI[i]))
    return out


def costruisci_settimana(arch, anno, nn):
    """Restituisce (Workbook, nome_foglio) della settimana ISO nn dell'anno anno."""
    lun = lunedi_settimana(anno, nn)
    giorni_d = [lun + timedelta(days=g) for g in range(7)]
    mot = Motore(arch)
    cop = [mot.calcola_giorno(d) for d in giorni_d]
    dati = [mot.dati_giorno(d) for d in giorni_d]
    cfg = arch.config_alla(lun)

    def n_righe(g):
        n = len(g.turni) + sum(1 for s in g.sussidiari if not s.scoperto and s.nome.strip()) + len(g.assenti)
        return max(n, RIGHE_MIN)

    rg = [n_righe(g) for g in cop]
    fasce = [max(rg[0:3]), max(rg[3:6]), rg[6]]
    r_lun = 4
    r_gio = r_lun + fasce[0] + 2
    r_dom = r_gio + fasce[1] + 2
    basi = [r_lun, r_lun, r_lun, r_gio, r_gio, r_gio, r_dom]

    wb = Workbook()
    ws = wb.active
    nome_foglio = "Settimana_%d_%02d" % (anno, nn)
    ws.title = nome_foglio
    ws.sheet_properties.tabColor = None
    F = _Foglio(ws)

    # larghezze
    for c, w in zip(range(1, 25), [5, 10, 14, 1, 5, 10, 14, 1, 5, 10, 14, 1, 5, 18, 4, 5, 5, 5, 5, 5, 5, 5, 5, 10]):
        ws.column_dimensions[L(c)].width = w
    ws.row_dimensions[1].height = 18.6
    ws.row_dimensions[2].height = 37.95

    # ---- intestazioni
    F.set(1, 1, "Settimana %d" % nn, b=True, sz=14, h="left", v="center")
    F.unisci(1, 1, 2, 3)
    F.set(1, 9, "Servizio DCT", b=True, sz=14, h="right", v="center")
    F.unisci(1, 9, 2, 11)
    F.set(1, 13, "Settimana", b=True, sz=14, h="center", v="center")
    F.unisci(1, 13, 1, 15)
    F.set(1, 16, nn, b=True, sz=14, h="left", v="center")
    F.unisci(1, 16, 1, 22)
    F.set(2, COL_POS, "Pos", b=True, h="center")
    F.set(2, COL_NOME, "Nome", b=True, h="center")
    F.set(2, COL_GR, "Gr.", b=True, h="center")
    for g, d in enumerate(giorni_d):
        F.set(2, COL_LUN + g, "%s\n%d" % (GIORNI_BREVI[g], d.day), b=True, sz=9, h="center", v="center", wrap=True)

    # ---- vista per persona
    for p in range(1, 15):
        r = 2 + p
        nomi = ""
        for g in range(7):
            n = dati[g][p].nome.strip()
            if n:
                if not nomi:
                    nomi = n
                elif n not in nomi:
                    nomi += "/" + n
        F.set(r, COL_POS, p, h="center", v="center")
        F.set(r, COL_GR, gruppo_posizione(p), h="center", v="center")
        F.set(r, COL_NOME, nomi, b=True, h="left", v="center")
        vuota = not nomi
        for g in range(7):
            c = dati[g][p]
            if c.tipo in COLORE_TIPO:
                fill = COLORE_TIPO[c.tipo]
            elif not c.nome.strip():
                fill = GRIGIO
            else:
                fill = colore_giorno(giorni_d[g])
            riposo = str(c.valore).strip() == "R"
            F.set(r, COL_LUN + g, c.valore if c.valore != "" else None, b=riposo, sz=12 if riposo else 10,
                  h="center", v="center", fill=fill)
        if vuota:
            for col in range(COL_POS, COL_LUN + 7):
                ws.cell(r, col).fill = PatternFill("solid", fgColor="FF" + GRIGIO)

    # ---- DCT in servizio
    r_dct = 17
    F.set(r_dct, COL_POS, "DCT IN SERVIZIO", b=True, i=True, sz=10, h="center", v="center")
    F.unisci(r_dct, COL_POS, r_dct, COL_GR)
    for g, d in enumerate(giorni_d):
        n = conta_dct(dati[g])
        sotto = n < soglia(d)
        F.set(r_dct, COL_LUN + g, n, b=sotto, i=True, sz=10, col="FFFFFF00" if sotto else "FF000000",
              h="center", v="center", fill="000000" if sotto else None)

    # ---- bordi vista per persona e intestazioni
    F.griglia(2, COL_POS, 17, COL_LUN + 6, "thin")
    F.intorno(2, COL_POS, 17, COL_LUN + 6, "medium")
    F.intorno(1, 1, 2, 11, "medium")
    F.intorno(1, 13, 1, 22, "medium")

    # ---- blocchi dei giorni
    for g, d in enumerate(giorni_d):
        rb, cb, gg = basi[g], BLOCCHI_COL[g], cop[g]
        F.set(rb, cb, "%s  %s" % (GIORNI[g], d.strftime("%d/%m/%Y")), b=True, h="left", v="center",
              fill=colore_giorno(d))
        for k in (1, 2):
            ws.cell(rb, cb + k).fill = PatternFill("solid", fgColor="FF" + colore_giorno(d))
        F.unisci(rb, cb, rb, cb + 2)
        riga = rb + 1
        for t in gg.turni:
            F.set(riga, cb, t.codice, b=True, h="center")
            F.set(riga, cb + 1, t.nome or None, i=t.scoperto, h="left", v="center")
            F.set(riga, cb + 2, t.nota or None, h="left", v="center")
            riga += 1
        for s in gg.sussidiari:
            if not s.scoperto and s.nome.strip():
                F.set(riga, cb, s.codice, b=True, h="center")
                F.set(riga, cb + 1, s.nome, h="left", v="center")
                F.set(riga, cb + 2, s.nota or None, h="left", v="center")
                riga += 1
        for k, a in enumerate(gg.assenti):
            if k == 0:
                F.set(riga, cb, "Ass.:", b=True, i=True)
            F.set(riga, cb + 1, a.nome, h="left", v="center")
            F.set(riga, cb + 2, a.motivazione or None, i=True, h="left", v="center")
            riga += 1
        F.griglia(rb, cb, rb + rg[g], cb + 2, "thin")
        F.intorno(rb, cb, rb + rg[g], cb + 2, "medium")
        for r in range(rb + 1, rb + rg[g] + 1):
            for k, h in ((0, None), (1, "left"), (2, "left")):
                c = ws.cell(r, cb + k)
                if c.font is None or c.value is None and c.font.name != "Calibri":
                    F.set(r, cb + k, None, h=h, v="center" if k else None)

    # ---- note della settimana (colonne E:K, accanto alla domenica)
    voci = voci_note(arch, giorni_d, dati)
    if voci:
        r = r_dom
        F.set(r, 5, "Note della settimana", b=True, h="left", fill=NOTE_GRIGIO)
        for c in range(6, 12):
            ws.cell(r, c).fill = PatternFill("solid", fgColor="FF" + NOTE_GRIGIO)
        F.unisci(r, 5, r, 11)

        def riga_nota(r, giorno, nome, testo, intest):
            for c in range(5, 12):
                F.set(r, c, None, b=intest, h="left", v="center", fill=NOTE_GRIGIO if intest else None)
                ws.cell(r, c).number_format = "@"
            ws.cell(r, 5).value, ws.cell(r, 7).value, ws.cell(r, 9).value = giorno or None, nome or None, testo or None
            F.griglia(r, 5, r, 11, "thin")
            F.unisci(r, 5, r, 6, False)
            F.unisci(r, 7, r, 8, False)
            F.unisci(r, 9, r, 11, False)

        r += 1
        riga_nota(r, "Giorno", "DCT", "Nota", True)
        r += 1
        for giorno, nome, testo in voci:
            for k, parte in enumerate(spezza_testo(testo, LARGH_TESTO)):
                if r > r_dom + RIGHE_NOTE_MAX:
                    break
                riga_nota(r, giorno if k == 0 else "", nome if k == 0 else "", parte, False)
                r += 1
        F.intorno(r_dom, 5, r - 1, 11, "medium")

    # ---- schema turni (M19:V..)
    F.set(19, 13, "Turno", b=True, h="center", v="center")
    F.set(19, 14, "Feriale", b=True, h="center", v="center")
    F.set(19, 15, "Sabato", b=True, h="center", v="center")
    F.unisci(19, 15, 19, 18)
    F.set(19, 19, "Domenica/Festivo", b=True, h="center", v="center")
    F.unisci(19, 19, 19, 22)
    r = 20
    righe_schema = []
    for cod, o in cfg.turni.items():
        righe_schema.append((cod, _orario(*o["Feriale"]), _orario(*o["Sabato"]), _orario(*o["Domenica"])))
    visti = set(cfg.turni)
    ordine_chiavi = sorted(cfg.sussidiari, key=lambda k: (["Feriale", "Sabato", "Domenica"].index(k) if k in ("Feriale", "Sabato", "Domenica") else 9, k))
    for chiave in ordine_chiavi:
        for cod, i, f in cfg.sussidiari[chiave]:
            if cod not in visti:
                visti.add(cod)
                o = _orario(i, f)
                righe_schema.append((cod, o, o, o))
    for cod, fer, sab, dom in righe_schema:
        F.set(r, 13, cod, h="center", v="center")
        F.set(r, 14, fer or None, h="center", v="center")
        F.set(r, 15, sab or None, h="center", v="center")
        F.unisci(r, 15, r, 18)
        F.set(r, 19, dom or None, h="center", v="center")
        F.unisci(r, 19, r, 22)
        r += 1
    F.griglia(19, 13, r - 1, 22, "thin")

    # ---- blocco info
    F.set(33, 13, "ORDINE DISP. E VUOTI", b=True)
    for riga0, col, titolo, mod in ((35, 13, "FERIALE:", "Feriale"), (35, 16, "SABATO:", "Sabato"),
                                    (35, 21, "DOMENICA/FESTIVO:", "Domenica")):
        F.set(riga0, col, titolo, b=True)
        for k, t in enumerate(_etichette_disp(cfg.disponibilita.get(mod, []))):
            F.set(riga0 + 1 + k, col, t)
    F.set(45, 13, "CU e FU:", b=True)
    for k, t in enumerate(["1° - Dd5", "2° - Dd2", "3° - Dd8", "4° - 607", "5° - 606", "6° - 601"]):
        F.set(46 + k, 13, t)
    F.set(45, 15, "Rientri dal 6° al 1° su")
    F.set(46, 15, "eventuali turni che si liberano")

    F.scrivi()
    return wb, nome_foglio


def esporta_settimana(arch, anno, nn, cartella):
    """Scrive Settimana_NN_AAAA.xlsx nella cartella e ne restituisce il percorso."""
    import os
    wb, _ = costruisci_settimana(arch, anno, nn)
    percorso = os.path.join(cartella, "Settimana_%02d_%d.xlsx" % (nn, anno))
    wb.save(percorso)
    return percorso
