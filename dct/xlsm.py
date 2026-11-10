"""Lettura dei dati dal file VESTIZIONE_DCT_*.xlsm (solo per confronto e importazione iniziale)."""
from datetime import date, datetime, time
import openpyxl
from .modelli import *


def _d(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def _hhmm(v):
    if isinstance(v, time):
        return "%02d:%02d" % (v.hour, v.minute)
    if isinstance(v, datetime):
        return "%02d:%02d" % (v.hour, v.minute)
    return ""


class Archivio:
    """Tutto cio' che serve al motore, letto da un xlsm."""

    def __init__(self, percorso):
        self.wb = openpyxl.load_workbook(percorso, keep_vba=True)
        self.config = self._leggi_config()
        self.persone = self._leggi_persone()
        self.assegnazioni = self._leggi_assegnazioni()
        self._cache = {}

    def natale_alla(self, d):
        """Turni di Natale (25/12): dal foglio Config_Natale se c'e', altrimenti i valori di partenza."""
        if (d.month, d.day) != (12, 25):
            return None
        if not hasattr(self, "_natale"):
            from .db import _leggi_config_natale, NATALE_BASE, NATALE_DAL
            righe = _leggi_config_natale(self.wb) or [(NATALE_DAL,) + r for r in NATALE_BASE]
            out = {}
            for v, tipo, cod, ordine, ini, fin in sorted(righe, key=lambda r: (r[0], r[1], r[3])):
                x = out.setdefault(v, {"TURNO": [], "SUSS": [], "DISP": [], "PARAM": {}})
                if tipo == "PARAM":
                    x["PARAM"][cod] = ordine
                elif tipo in x:
                    x[tipo].append((cod, ini, fin))
            self._natale = out
        valide = [v for v in self._natale if v <= d.isoformat()]
        return self._natale[max(valide) if valide else min(self._natale)]

    def config_alla(self, d):
        return self.config

    # ---- configurazione
    def _leggi_config(self):
        wb = self.wb
        turni = {}
        for r in list(wb["Config_Turni"].iter_rows(min_row=2, values_only=True)):
            if r[0] is None:
                continue
            c = str(r[0])
            turni[c] = {"Feriale": (_hhmm(r[1]), _hhmm(r[2])),
                        "Sabato": (_hhmm(r[3]), _hhmm(r[4])),
                        "Domenica": (_hhmm(r[5]), _hhmm(r[6]))}
        disp = {}
        for r in wb["Config_Disponibilita"].iter_rows(min_row=2, values_only=True):
            if r[0] is None:
                continue
            disp.setdefault(r[0], []).append((int(r[1]), str(r[2])))
        disp = {k: [c for _, c in sorted(v)] for k, v in disp.items()}
        suss = {}
        for r in wb["Config_Sussidiari"].iter_rows(min_row=2, values_only=True):
            if r[0] is None:
                continue
            suss.setdefault(r[0], []).append((int(r[1]), str(r[2]), _hhmm(r[3]), _hhmm(r[4])))
        suss = {k: [(c, i, f) for _, c, i, f in sorted(v)] for k, v in suss.items()}
        mot = {}
        for r in wb["Config_Motivazioni"].iter_rows(min_row=2, values_only=True):
            if r[0] is None:
                continue
            mot.setdefault(str(r[0]), []).append(str(r[1]))
        return Config(turni, disp, suss, mot)

    def _leggi_persone(self):
        out = []
        ws = self.wb["Persone"]
        for r in ws.iter_rows(min_row=5, max_row=100, max_col=6, values_only=True):
            p = r[0]
            if isinstance(p, (int, float)) and 1 <= p <= 14:
                ini = _d(r[3]) or date.min
                fin = _d(r[4]) or date.max
                out.append(Persona(int(p), str(r[1] or ""), str(r[2] or ""), ini, fin))
        return out

    def _leggi_assegnazioni(self):
        out = []
        for r in self.wb["Config_Assegnazioni"].iter_rows(min_row=2, values_only=True):
            if r[0] is None:
                continue
            out.append(Assegnazione(int(r[0]), int(r[1]), _d(r[2]), str(r[3]).strip(), str(r[4]).strip()))
        return out

    # ---- calendario annuale
    def cella(self, d, pos):
        """Cella del foglio anno per data e posizione; None se fuori dal foglio."""
        nome = str(d.year)
        if nome not in self.wb.sheetnames:
            return None
        mese_inizio = 10 if d.year == 2026 else 1
        if d.month < mese_inizio:
            return None
        riga = 3 + (d.month - mese_inizio) * 19 + 2 + pos
        col = 4 + d.day - 1
        ws = self.wb[nome]
        c = ws.cell(riga, col)
        v = c.value
        if v is None:
            val = ""
        elif isinstance(v, float) and v.is_integer():
            val = str(int(v))
        else:
            val = str(v).strip()
        f = c.fill
        rgb = f.fgColor.rgb[2:] if (f.fill_type == "solid" and f.fgColor.type == "rgb") else ""
        diag = ""
        if c.border and c.border.diagonalDown and c.border.diagonal is not None:
            col = c.border.diagonal.color
            drgb = col.rgb[2:] if (col is not None and col.type == "rgb" and isinstance(col.rgb, str)) else ""
            diag = COLORE_TIPO.get(drgb, "") or "MIS"
        return Cella(val, COLORE_TIPO.get(rgb, ""), diag)

    # ---- settimane gia' calcolate (per il confronto)
    def foglio_settimana(self, anno, nn):
        nome = "Settimana_%d_%d" % (anno, nn)
        return self.wb[nome] if nome in self.wb.sheetnames else None
