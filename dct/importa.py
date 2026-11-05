"""Importazione dei cambiamenti dalla Rotazione dei colleghi, con confronto a tre
(file principale / copia di partenza _base / file dei colleghi). Porting di ImportaSettimane (modExport, v11).
2026 Bruno Roli"""
import colorsys
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import openpyxl
from openpyxl.styles.colors import COLOR_INDEX

from .calendario import lunedi_settimana
from .copertura import Motore
from .modelli import COLORE_TIPO
from .operazioni import Operazioni
from .rotazione import (MESI, TIPO_COLORE, GRIGIO, colore_bgr, colore_giorno, meseinizio, RIGHE_PER_MESE)

BGR_VUOTA = colore_bgr(GRIGIO)
BGR_C_RIP = colore_bgr(TIPO_COLORE["C_RIP"])
TIPO_DA_BGR = {colore_bgr(rgb): tipo for tipo, rgb in TIPO_COLORE.items()}
BIANCO_BGR = 16777215
DESCRIZIONE = {"CONG_FEST": "Cong./Fest.", "ASS_MAL": "Ass./Mal.", "104": "104", "CORSI": "Corsi", "SIND": "Sind.",
               "C_RIP": "C. Rip.", "RL": "RL", "MIS": "MIS", "RU": "RU"}
ASSENZE = ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND")
MANUALI = ("RL", "MIS", "RU", "C_RIP")


@dataclass
class Cambio:
    riga: int
    col: int
    data: date
    pos: int
    nome: str
    tipo: str            # "COLORE" o "NOTA"
    vecchio: str
    nuovo: str
    col_nuovo: int = 0
    testo_nuovo: str = ""
    stato: str = ""      # APPLICA / CONFLITTO / MANUALE / MANTENUTA / SALTATA
    motivo: str = ""


class ErroreImport(Exception):
    pass


# ------------------------------------------------------------------ colori
def _tema_rgb(wb):
    """Colori del tema (indice di Excel -> RRGGBB)."""
    xml = getattr(wb, "loaded_theme", None)
    if not xml:
        return {}
    if isinstance(xml, bytes):
        xml = xml.decode("utf-8")
    nomi = ["lt1", "dk1", "lt2", "dk2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"]
    out = {}
    for i, n in enumerate(nomi):
        m = re.search(r"<a:%s>.*?(?:srgbClr val=\"([0-9A-Fa-f]{6})\"|sysClr[^>]*lastClr=\"([0-9A-Fa-f]{6})\")" % n, xml, re.S)
        if m:
            out[i] = (m.group(1) or m.group(2)).upper()
    return out


def _con_tinta(rgb, tint):
    if not tint:
        return rgb
    r, g, b = (int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = l * (1 + tint) if tint < 0 else l * (1 - tint) + tint
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), s)
    return "%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def colore_cella(cella, tema):
    """Colore di riempimento come numero BGR (come Interior.Color); bianco se non c'e' riempimento."""
    f = cella.fill
    if f is None or f.fill_type != "solid":
        return BIANCO_BGR
    fg = f.fgColor
    rgb = None
    if fg.type == "rgb" and isinstance(fg.rgb, str):
        rgb = fg.rgb[-6:]
    elif fg.type == "indexed":
        try:
            rgb = COLOR_INDEX[fg.indexed][-6:]
        except (IndexError, TypeError):
            rgb = None
    elif fg.type == "theme":
        base = tema.get(fg.theme)
        rgb = _con_tinta(base, fg.tint) if base else None
    if not rgb:
        return BIANCO_BGR
    return colore_bgr(rgb.upper())


def _norm(testo):
    return (testo or "").replace("\r\n", "\n").replace("\r", "\n").strip()


# ------------------------------------------------------------------ analisi
def analizza(arch, percorso, anno_iso, sett1, sett2):
    """Restituisce (cambi, n_fuori_anno, anno_file). Solleva ErroreImport se il file non e' valido."""
    if sett1 < 1 or sett2 > 53 or sett2 < sett1 or sett2 - sett1 > 8:
        raise ErroreImport("Intervallo di settimane non valido (massimo 9 settimane per volta).")
    wb = openpyxl.load_workbook(percorso)
    anno = 0
    for n in wb.sheetnames:
        if n.isdigit():
            anno = int(n)
    if anno == 0:
        raise ErroreImport("Il file scelto non contiene un foglio anno valido.")
    if "_base" not in wb.sheetnames or "_note" not in wb.sheetnames:
        raise ErroreImport("Il file scelto non è un'esportazione valida per l'anno %d: mancano il foglio dell'anno o la copia di partenza." % anno)
    if arch.cella(date(anno, 12, 31), 1) is None:
        raise ErroreImport("L'anno %d non esiste nell'archivio." % anno)
    exp, base, note_sh = wb[str(anno)], wb["_base"], wb["_note"]
    mi = meseinizio(anno)
    for mese in range(mi, 13):
        rb = 3 + (mese - mi) * RIGHE_PER_MESE
        atteso = "%s %d" % (MESI[mese - 1].upper(), anno)
        if str(exp.cell(rb, 1).value or "") != atteso:
            raise ErroreImport("La struttura del file esportato non coincide con l'archivio (mese %d). Importazione annullata." % mese)
    tema = _tema_rgb(wb)
    mot = Motore(arch)
    note_base = {}
    r = 1
    while note_sh.cell(r, 1).value is not None:
        note_base[(note_sh.cell(r, 1).value, note_sh.cell(r, 2).value)] = _norm(note_sh.cell(r, 3).value)
        r += 1
    note_exp = {(c.row, c.column): _norm(c.comment.text) for row in exp.iter_rows() for c in row if c.comment}
    note_main = {}
    for (d, pos), t in arch.note_celle(anno).items():
        note_main[(3 + (d.month - mi) * RIGHE_PER_MESE + 2 + pos, 3 + d.day)] = _norm(t)

    cambi, n_fuori = [], 0
    for w in range(sett1, sett2 + 1):
        lun = lunedi_settimana(anno_iso, w)
        for g in range(7):
            d = lun + timedelta(days=g)
            if d.year != anno:
                n_fuori += 1
                continue
            rb = 3 + (d.month - mi) * RIGHE_PER_MESE
            col = 3 + d.day
            idx_p = []
            for pos in range(1, 15):
                r = rb + 2 + pos
                vuota = mot.chi_in_servizio(pos, d) == ""
                cel = arch.cella(d, pos)
                tipo_main = cel.tipo if cel else ""
                col_main = (colore_bgr(TIPO_COLORE[tipo_main]) if tipo_main
                            else BGR_VUOTA if vuota else colore_bgr(colore_giorno(d)))
                if col_main == BGR_VUOTA:
                    continue
                nome = mot.chi_in_servizio(pos, d)
                v_base = base.cell(r, col).value
                if v_base is not None:
                    col_base = int(v_base)
                    col_exp = colore_cella(exp.cell(r, col), tema)
                    if col_exp != col_main:
                        t_v, t_n, t_m = TIPO_DA_BGR.get(col_base, ""), TIPO_DA_BGR.get(col_exp, ""), tipo_main
                        c = Cambio(r, col, d, pos, nome, "COLORE", DESCRIZIONE.get(t_m, "(nessuno)"),
                                   DESCRIZIONE.get(t_n, "(nessuno)"), col_nuovo=col_exp)
                        diag = cel.diag if cel else ""
                        conosciuto = col_exp in TIPO_DA_BGR or col_exp in (
                            BIANCO_BGR, colore_bgr("C6EFCE"), colore_bgr("FF6C5D"), BGR_VUOTA)
                        if col_exp != col_base and col_main != col_base:
                            c.stato, c.motivo = "CONFLITTO", "il file principale è stato modificato dopo l'esportazione"
                        elif diag:
                            c.stato, c.motivo = "MANUALE", "corso sopra un rientro: da gestire a mano"
                        elif t_v in MANUALI or t_n in MANUALI or t_m in MANUALI:
                            c.stato, c.motivo = "MANUALE", "RL, MIS, RU e cambi riposo non riconoscibili vanno gestiti a mano"
                        elif t_n in ASSENZE and (cel.valore if cel else "") == "R":
                            c.stato, c.motivo = "SALTATA", "assenza su un riposo"
                        elif col_exp == col_base:
                            c.stato, c.motivo = "MANTENUTA", "modificata solo nel principale: resta com'è"
                        elif not conosciuto:
                            c.stato, c.motivo = "SALTATA", "colore non riconosciuto"
                        else:
                            c.stato = "APPLICA"
                        cambi.append(c)
                        if col_exp == BGR_C_RIP and c.stato == "MANUALE" and len(idx_p) < 14:
                            idx_p.append(len(cambi) - 1)
                key = (r, col)
                nb, ne, nm = note_base.get(key, ""), note_exp.get(key, ""), note_main.get(key, "")
                if ne != nm:
                    c = Cambio(r, col, d, pos, nome, "NOTA", nm, ne, testo_nuovo=ne)
                    if ne == nb:
                        c.stato, c.motivo = "MANTENUTA", "nota modificata solo nel principale: resta com'è"
                    elif nm != nb:
                        c.stato, c.motivo = "CONFLITTO", "la nota è stata modificata anche nel file principale"
                    else:
                        c.stato = "APPLICA"
                    cambi.append(c)
            if len(idx_p) == 2:
                _abbina_cambio_riposo(arch, anno, cambi, idx_p[0], idx_p[1])
    return cambi, n_fuori, anno


def _abbina_cambio_riposo(arch, anno, cambi, i1, i2):
    """Cambio riposo personale: due celle magenta nello stesso giorno, una turno e una riposo."""
    a, b = cambi[i1], cambi[i2]
    if a.data != b.data or a.stato != "MANUALE" or b.stato != "MANUALE":
        return
    if a.vecchio != "(nessuno)" or b.vecchio != "(nessuno)":
        return
    v1 = arch.cella(a.data, a.pos).valore
    v2 = arch.cella(b.data, b.pos).valore
    if v1 == "R" and v2 not in ("R", ""):
        riposo, turno_c = a, b
    elif v2 == "R" and v1 not in ("R", ""):
        riposo, turno_c = b, a
    else:
        return
    turno = arch.cella(turno_c.data, turno_c.pos).valore
    op = Operazioni(arch)
    if op.assegnazione_esistente(anno, riposo.pos, riposo.data):
        return
    if op.turno_gia_coperto(anno, riposo.data, turno):
        return
    for c in (a, b):
        c.stato, c.motivo, c.nuovo = "APPLICA", "cambio riposo personale", "C. Rip. (personale)"
    riposo.testo_nuovo = turno


def riepilogo(cambi):
    r = {"APPLICA": 0, "CONFLITTO": 0, "MANUALE": 0, "MANTENUTA": 0, "SALTATA": 0}
    for c in cambi:
        r[c.stato] = r.get(c.stato, 0) + 1
    return r


# ------------------------------------------------------------------ applicazione
def applica(arch, cambi, anno, nome_file, adesso=None):
    """Applica i cambiamenti APPLICA e scrive il log. Tutto o niente: se qualcosa va storto non resta niente a meta'."""
    adesso = adesso or datetime.now().replace(second=0, microsecond=0)
    n_colori = n_note = 0
    try:
        for c in cambi:
            if c.stato != "APPLICA":
                continue
            if c.tipo == "COLORE":
                tipo = TIPO_DA_BGR.get(c.col_nuovo, "")
                arch.imposta_cella(c.data, c.pos, tipo, "")
                n_colori += 1
                if c.col_nuovo == BGR_C_RIP and c.testo_nuovo:
                    op = Operazioni(arch)
                    if not op.assegnazione_esistente(anno, c.pos, c.data):
                        arch.aggiungi_assegnazione(anno, c.pos, c.data, c.testo_nuovo, "C_RIP")
            else:
                arch.imposta_nota(c.data, c.pos, c.testo_nuovo)
                n_note += 1
            arch.con.execute("INSERT INTO log_import VALUES(?,?,?,?,?,?,?,?,?)",
                             (adesso.strftime("%Y-%m-%d %H:%M"), nome_file, anno, c.data.isoformat(), c.pos,
                              c.nome, c.tipo, c.vecchio, c.nuovo))
        arch.salva()
    except Exception:
        arch.annulla()
        arch.ricarica()
        raise
    return n_colori, n_note
