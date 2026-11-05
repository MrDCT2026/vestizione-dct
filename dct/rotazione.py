"""Esportazione della Rotazione_AAAA.xlsm per i colleghi.
Il file si costruisce partendo da un modello (una Rotazione gia' esistente): si riscrivono solo i dati
(foglio dell'anno, _base, _note, note), lasciando intatti macro, pulsanti e tema.
2026 Bruno Roli"""
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape
from lxml import etree

from .calendario import is_festivo, numero_iso
from .copertura import Motore
from .modelli import COLORE_TIPO

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
N = {"m": NS}
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
TIPO_COLORE = {v: k for k, v in COLORE_TIPO.items()}
BIANCO, SABATO, FESTA, GRIGIO, NERO, GIALLO = "FFFFFF", "C6EFCE", "FF6C5D", "E6E6E6", "000000", "FFFF00"
RIGHE_PER_MESE = 19
NUM_RIGHE_FOGLIO = 500
NUM_COLONNE_BASE = 35


def col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def meseinizio(anno):
    return 10 if anno == 2026 else 1


def giorni_mese(anno, mese):
    return (date(anno + (mese == 12), mese % 12 + 1, 1) - date(anno, mese, 1)).days


# ------------------------------------------------------------------ stili
class Stili:
    """Aggiunge a styles.xml (del modello) i caratteri, i riempimenti, i bordi e gli stili che servono."""

    def __init__(self, xml):
        self.root = etree.fromstring(xml)
        self.fonts = self.root.find("m:fonts", N)
        self.fills = self.root.find("m:fills", N)
        self.borders = self.root.find("m:borders", N)
        self.xfs = self.root.find("m:cellXfs", N)
        self._c = {}
        f0 = self.fonts[0]
        self._nome = f0.find("m:name", N).get("val")
        self._fam = f0.find("m:family", N).get("val")
        sc = f0.find("m:scheme", N)
        self._scheme = sc.get("val") if sc is not None else None

    def xf_semplice(self, num_fmt=0, a_capo=False):
        """Indice di uno stile "semplice" (carattere, riempimento e bordo 0) con il formato numerico dato
        o con il testo a capo: lo cerca nel modello, altrimenti lo aggiunge.
        Serve per _base (data di esportazione) e _note, senza dipendere dalla numerazione del modello."""
        for i, x in enumerate(self.xfs):
            if (x.get("numFmtId", "0") == str(num_fmt) and x.get("fontId", "0") == "0" and x.get("fillId", "0") == "0"
                    and x.get("borderId", "0") == "0" and x.get("xfId", "0") == "0"):
                al = x.find("m:alignment", N)
                wrap = al is not None and al.get("wrapText") == "1"
                altro = al is not None and any(k != "wrapText" for k in al.attrib)
                if wrap == a_capo and not altro:
                    return i
        e = etree.Element("{%s}xf" % NS, numFmtId=str(num_fmt), fontId="0", fillId="0", borderId="0", xfId="0")
        if num_fmt:
            e.set("applyNumberFormat", "1")
        if a_capo:
            e.set("applyAlignment", "1")
            etree.SubElement(e, "{%s}alignment" % NS).set("wrapText", "1")
        return self._agg(self.xfs, e, ("semplice", num_fmt, a_capo))

    def _agg(self, parent, el, chiave):
        k = (parent.tag, chiave)
        if k in self._c:
            return self._c[k]
        parent.append(el)
        parent.set("count", str(len(parent)))
        self._c[k] = len(parent) - 1
        return self._c[k]

    def font(self, b=False, i=False, sz=11, rgb=None):
        e = etree.Element("{%s}font" % NS)
        if b:
            etree.SubElement(e, "{%s}b" % NS)
        if i:
            etree.SubElement(e, "{%s}i" % NS)
        etree.SubElement(e, "{%s}sz" % NS).set("val", str(sz))
        c = etree.SubElement(e, "{%s}color" % NS)
        if rgb:
            c.set("rgb", "FF" + rgb)
        else:
            c.set("theme", "1")
        etree.SubElement(e, "{%s}name" % NS).set("val", self._nome)
        etree.SubElement(e, "{%s}family" % NS).set("val", self._fam)
        if self._scheme:
            etree.SubElement(e, "{%s}scheme" % NS).set("val", self._scheme)
        return self._agg(self.fonts, e, (b, i, sz, rgb))

    def fill(self, rgb):
        if rgb is None:
            return 0
        e = etree.Element("{%s}fill" % NS)
        p = etree.SubElement(e, "{%s}patternFill" % NS)
        p.set("patternType", "solid")
        etree.SubElement(p, "{%s}fgColor" % NS).set("rgb", "FF" + rgb)
        etree.SubElement(p, "{%s}bgColor" % NS).set("indexed", "64")
        return self._agg(self.fills, e, rgb)

    def border(self, l=None, r=None, t=None, b=None, diag=None):
        """l,r,t,b: None/'thin'/'medium'; diag: colore RGB della diagonale (spessa) oppure None."""
        e = etree.Element("{%s}border" % NS)
        if diag:
            e.set("diagonalDown", "1")
        for nome, stile in (("left", l), ("right", r), ("top", t), ("bottom", b)):
            x = etree.SubElement(e, "{%s}%s" % (NS, nome))
            if stile:
                x.set("style", stile)
                etree.SubElement(x, "{%s}color" % NS).set("rgb", "FF000000")
        d = etree.SubElement(e, "{%s}diagonal" % NS)
        if diag:
            d.set("style", "thick")
            etree.SubElement(d, "{%s}color" % NS).set("rgb", "FF" + diag)
        return self._agg(self.borders, e, (l, r, t, b, diag))

    def xf(self, font, fill, border, h="center", v="center", wrap=False):
        k = ("xf", font, fill, border, h, v, wrap)
        if k in self._c:
            return self._c[k]
        e = etree.Element("{%s}xf" % NS)
        for a, val in (("numFmtId", "0"), ("fontId", str(font)), ("fillId", str(fill)),
                       ("borderId", str(border)), ("xfId", "0"), ("applyFont", "1"),
                       ("applyFill", "1"), ("applyBorder", "1"), ("applyAlignment", "1")):
            e.set(a, val)
        al = etree.SubElement(e, "{%s}alignment" % NS)
        if h:
            al.set("horizontal", h)
        if v:
            al.set("vertical", v)
        if wrap:
            al.set("wrapText", "1")
        self.xfs.append(e)
        self.xfs.set("count", str(len(self.xfs)))
        self._c[k] = len(self.xfs) - 1
        return self._c[k]

    def tobytes(self):
        return etree.tostring(self.root, xml_declaration=True, encoding="UTF-8", standalone=True)


class Stringhe:
    def __init__(self):
        self.lista, self.idx, self.conteggio = [], {}, 0

    def id(self, s):
        self.conteggio += 1
        if s not in self.idx:
            self.idx[s] = len(self.lista)
            self.lista.append(s)
        return self.idx[s]

    def xml(self):
        out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="%s" count="%d" uniqueCount="%d">'
               % (NS, self.conteggio, len(self.lista))]
        for s in self.lista:
            out.append('<si><t xml:space="preserve">%s</t></si>' % escape(s))
        out.append("</sst>")
        return "".join(out).encode("utf-8")


# ------------------------------------------------------------------ dati del foglio
def in_servizio(c, vuota):
    """Valore di una cella per il conteggio DCT IN SERVIZIO (come ValoreInServizio del VBA)."""
    if vuota and c.tipo == "":
        return 0
    if c.valore == "":
        return 0
    t = c.tipo
    if t in ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND", "RU"):
        return 0
    if t == "C_RIP":
        return 1 if c.valore == "R" else 0
    if t in ("RL", "MIS"):
        return 1
    return 0 if c.valore == "R" else 1


def soglia(d):
    if is_festivo(d):
        return 6
    w = d.isoweekday()
    return 7 if w == 6 else 6 if w == 7 else 8


def colore_giorno(d):
    if is_festivo(d):
        return FESTA
    w = d.isoweekday()
    return SABATO if w == 6 else FESTA if w == 7 else BIANCO


def etichetta_posizione(motore, pos, anno, mese):
    et, ultima = [], None
    for g in range(1, giorni_mese(anno, mese) + 1):
        chi = motore.chi_in_servizio(pos, date(anno, mese, g))
        if chi != ultima:
            et.append(chi)
            ultima = chi
    return "/".join(et) if et else ""


def valore_cella(v):
    """Le sigle di soli numeri (601...) sono numeri nel foglio, come in Excel."""
    return int(v) if re.fullmatch(r"\d+", v) else v


# ------------------------------------------------------------------ foglio dell'anno
def costruisci_foglio(arch, anno, st, ss):
    mot = Motore(arch)
    celle = {}      # (riga, col) -> (stile, valore)
    merge = []
    righe_ht = {1: 21.9, 2: 21.9}
    mi = meseinizio(anno)

    F = lambda **k: st.font(**k)
    f_norm, f_b11, f_b14, f_b9 = F(), F(b=True), F(b=True, sz=14), F(b=True, sz=9)
    f_10, f_b12 = F(sz=10), F(b=True, sz=12)
    f_i10, f_bi10, f_bi10g = F(i=True, sz=10, rgb=NERO), F(b=True, i=True, sz=10), F(b=True, i=True, sz=10, rgb=GIALLO)
    f_bi10n = F(b=True, i=True, sz=10, rgb=NERO)
    nero_fill = st.fill(NERO)

    def put(r, c, stile, val=None):
        celle[(r, c)] = (stile, val)

    for i, mese in enumerate(range(mi, 13)):
        b = 3 + i * RIGHE_PER_MESE
        ng = giorni_mese(anno, mese)
        L = 3 + ng                      # ultima colonna dei giorni
        # titolo
        for c in range(1, L + 1):
            bd = st.border(l="medium" if c == 1 else "thin", r="medium" if c == L else "thin", t="medium", b="thin")
            put(b, c, st.xf(f_b14, 0, bd, h="center", v=None),
                (MESI[mese - 1].upper() + " " + str(anno)) if c == 1 else None)
        merge.append("A%d:%s%d" % (b, col(L), b))
        righe_ht[b] = 18
        # settimane
        for c in range(1, L + 1):
            bd = st.border(l="medium" if c == 1 else "thin", r="medium" if c == L else "thin", t="thin", b="thin")
            put(b + 1, c, st.xf(f_b11, st.fill(BIANCO), bd), "Settimane" if c == 1 else None)
        merge.append("A%d:C%d" % (b + 1, b + 1))
        d0, fine = date(anno, mese, 1), date(anno, mese, ng)
        d = d0
        while d <= fine:
            lun = d - timedelta(days=d.weekday())
            dom = lun + timedelta(days=6)
            ib, fb = max(lun, d0), min(dom, fine)
            c1, c2 = 3 + ib.day, 3 + fb.day
            celle[(b + 1, c1)] = (celle[(b + 1, c1)][0], numero_iso(ib))
            if c2 > c1:
                merge.append("%s%d:%s%d" % (col(c1), b + 1, col(c2), b + 1))
            d = fb + timedelta(days=1)
        righe_ht[b + 1] = 18
        # intestazione giorni
        for c, testo in ((1, "Pos"), (2, "Nome"), (3, "Gr.")):
            bd = st.border(l="medium" if c == 1 else "thin", r="thin", t="thin", b="thin")
            put(b + 2, c, st.xf(f_b11, 0, bd), testo)
        for g in range(1, ng + 1):
            dd = date(anno, mese, g)
            c = 3 + g
            bd = st.border(l="thin", r="medium" if c == L else "thin", t="thin", b="thin")
            put(b + 2, c, st.xf(f_b9, st.fill(colore_giorno(dd)), bd, wrap=True),
                GIORNI[dd.weekday()] + "\n" + str(g))
        righe_ht[b + 2] = 38.1
        # posizioni
        conteggi = [0] * (ng + 1)
        for pos in range(1, 15):
            r = b + 2 + pos
            ultima_pos = (pos == 14)
            vuota_mese = any(mot.chi_in_servizio(pos, date(anno, mese, g)) == "" for g in range(1, ng + 1))
            gf = st.fill(GRIGIO) if vuota_mese else 0
            bb = None if ultima_pos else "thin"
            put(r, 1, st.xf(f_norm, gf, st.border("medium", "thin", "thin", bb)), pos)
            put(r, 2, st.xf(f_b11, gf, st.border("thin", "thin", "thin", bb), h="left"),
                etichetta_posizione(mot, pos, anno, mese) or None)
            put(r, 3, st.xf(f_norm, gf, st.border("thin", "thin", "thin", bb)), mot.gruppo(pos))
            for g in range(1, ng + 1):
                dd = date(anno, mese, g)
                c = 3 + g
                cel = arch.cella(dd, pos)
                vuota = mot.chi_in_servizio(pos, dd) == ""
                if cel and cel.tipo:
                    rgb = TIPO_COLORE[cel.tipo]
                elif vuota:
                    rgb = GRIGIO
                else:
                    rgb = colore_giorno(dd)
                diag = TIPO_COLORE.get(cel.diag) if (cel and cel.diag) else None
                val = cel.valore if cel else ""
                bd = st.border("thin", "medium" if c == L else "thin", "thin", bb, diag)
                put(r, c, st.xf(f_b12 if val == "R" else f_10, st.fill(rgb), bd), valore_cella(val) if val else None)
                if cel:
                    conteggi[g] += in_servizio(cel, vuota)
            righe_ht[r] = 18
        # DCT in servizio
        r = b + 17
        put(r, 1, st.xf(f_bi10, 0, st.border("medium", "thin", "medium", "medium")), "DCT IN SERVIZIO")
        put(r, 2, st.xf(f_bi10, 0, st.border("thin", "thin", "medium", "medium")))
        put(r, 3, st.xf(f_bi10, 0, st.border("thin", "thin", "medium", "medium")))
        merge.append("A%d:C%d" % (r, r))
        mancanti = 0
        for g in range(1, ng + 1):
            dd = date(anno, mese, g)
            c = 3 + g
            n, s = conteggi[g], soglia(dd)
            bd = st.border("thin", None if c == L else "thin", "medium", "medium")
            if n < s:
                put(r, c, st.xf(f_bi10g, nero_fill, bd), n)
                mancanti += s - n
            else:
                put(r, c, st.xf(f_i10, st.fill(colore_giorno(dd)), bd), n)
        bd = st.border("medium", "medium", "medium", "medium")
        if mancanti > 0:
            put(r, L + 1, st.xf(f_bi10g, nero_fill, bd), mancanti)
        else:
            put(r, L + 1, st.xf(f_bi10n, st.fill(BIANCO), bd), 0)
        for rr in (b + 17, b + 18):
            righe_ht[rr] = 18

    # ---- xml delle righe
    righe = {}
    for (r, c), (s, v) in celle.items():
        righe.setdefault(r, {})[c] = (s, v)
    out = []
    for r in range(1, NUM_RIGHE_FOGLIO + 1):
        ht = righe_ht.get(r, 18)
        attr = ' ht="%s" customHeight="1"' % ht
        if r not in righe:
            out.append('<row r="%d"%s/>' % (r, attr))
            continue
        cs = []
        for c in sorted(righe[r]):
            s, v = righe[r][c]
            ref = "%s%d" % (col(c), r)
            if v is None:
                cs.append('<c r="%s" s="%d"/>' % (ref, s))
            elif isinstance(v, (int, float)):
                cs.append('<c r="%s" s="%d"><v>%s</v></c>' % (ref, s, v))
            else:
                cs.append('<c r="%s" s="%d" t="s"><v>%d</v></c>' % (ref, s, ss.id(v)))
        out.append('<row r="%d"%s>%s</row>' % (r, attr, "".join(cs)))
    return "".join(out), merge, celle


def colore_bgr(rgb):
    return int(rgb[4:6], 16) * 65536 + int(rgb[2:4], 16) * 256 + int(rgb[0:2], 16)


# ------------------------------------------------------------------ commenti (note sulle celle)
def commenti_xml(note):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<comments xmlns="%s"><authors><author>Autore</author></authors><commentList>' % NS]
    for ref, testo in note:
        out.append('<comment ref="%s" authorId="0" shapeId="0"><text><r><rPr><sz val="9"/><color indexed="81"/>'
                   '<rFont val="Tahoma"/><family val="2"/></rPr><t xml:space="preserve">%s</t></r></text></comment>'
                   % (ref, escape(testo)))
    out.append("</commentList></comments>")
    return "".join(out).encode("utf-8")


def primo_id_note(drawing_xml, idmap=7):
    """Primo numero di forma per le note (VML) senza sovrapporsi ai pulsanti del foglio (drawing1.xml).
    Excel numera note e pulsanti dello stesso foglio nello stesso blocco (idmap*1024): le note devono stare
    dopo i pulsanti, altrimenti all'apertura Excel toglie pulsanti e note ("Forma disegno", "Commenti").
    Come nel file salvato da Excel v15: pulsanti 2..9, note da 7195."""
    ids = [int(x) for x in re.findall(rb'cNvPr id="(\d+)"', drawing_xml or b"")]
    return idmap * 1024 + max([26] + ids) + 1


def vml_xml(note_pos, primo_id=7195):
    head = ('<xml xmlns:v="urn:schemas-microsoft-com:vml"\n xmlns:o="urn:schemas-microsoft-com:office:office"\n'
            ' xmlns:x="urn:schemas-microsoft-com:office:excel">\n <o:shapelayout v:ext="edit">\n'
            '  <o:idmap v:ext="edit" data="7"/>\n </o:shapelayout><v:shapetype id="_x0000_t202" coordsize="21600,21600" o:spt="202"\n'
            '  path="m,l,21600r21600,l21600,xe">\n  <v:stroke joinstyle="miter"/>\n'
            '  <v:path gradientshapeok="t" o:connecttype="rect"/>\n </v:shapetype>')
    out = [head]
    for k, (riga0, col0) in enumerate(note_pos):
        out.append(
            '<v:shape id="_x0000_s%d" type="#_x0000_t202" style=\'position:absolute;\n'
            '  margin-left:100pt;margin-top:100pt;width:124.2pt;height:60pt;z-index:%d;\n'
            '  visibility:hidden;mso-wrap-style:square\' fillcolor="#ffffe1" o:insetmode="auto">\n'
            '  <v:fill color2="#ffffe1"/>\n  <v:shadow color="black" obscured="t"/>\n  <v:path o:connecttype="none"/>\n'
            '  <v:textbox style=\'mso-direction-alt:auto;mso-fit-shape-to-text:t\'>\n   <div style=\'text-align:left\'></div>\n  </v:textbox>\n'
            '  <x:ClientData ObjectType="Note">\n   <x:MoveWithCells/>\n   <x:SizeWithCells/>\n   <x:Anchor>\n'
            '    %d, 14, %d, 14, %d, 16, %d, 23</x:Anchor>\n   <x:AutoFill>False</x:AutoFill>\n'
            '   <x:Row>%d</x:Row>\n   <x:Column>%d</x:Column>\n  </x:ClientData>\n </v:shape>'
            % (primo_id + k, k + 1, col0 + 1, max(riga0 - 1, 0), col0 + 5, riga0 + 1, riga0, col0))
    out.append("</xml>")
    return "".join(out).encode("utf-8")


# ------------------------------------------------------------------ esportazione
def esporta_rotazione(arch, anno, modello, uscita, adesso=None):
    adesso = adesso or datetime.now().replace(second=0, microsecond=0)
    zin = zipfile.ZipFile(modello)
    parti = {n: zin.read(n) for n in zin.namelist()}
    st = Stili(parti["xl/styles.xml"])
    ss = Stringhe()

    righe_xml, merge, celle = costruisci_foglio(arch, anno, st, ss)

    # --- foglio dell'anno: riuso testa e coda del modello
    s1 = parti["xl/worksheets/sheet1.xml"].decode("utf-8")
    testa = s1[: s1.index("<sheetData>")]
    coda = s1[s1.index("</sheetData>") + len("</sheetData>"):]
    testa = re.sub(r'<dimension ref="[^"]*"/>', '<dimension ref="A1:AI%d"/>' % NUM_RIGHE_FOGLIO, testa)
    testa = re.sub(r'<pane [^>]*/>', '<pane ySplit="2" topLeftCell="A3" activePane="bottomLeft" state="frozen"/>', testa)
    testa = re.sub(r'<selection [^>]*/>', '<selection pane="bottomLeft" activeCell="A3" sqref="A3"/>', testa)
    coda = re.sub(r"<mergeCells.*?</mergeCells>",
                  '<mergeCells count="%d">%s</mergeCells>' % (len(merge), "".join('<mergeCell ref="%s"/>' % m for m in merge)),
                  coda, flags=re.S)

    # note sulle celle
    note = arch.note_celle(anno)
    mi = meseinizio(anno)
    elenco = []
    for (d, pos), testo in sorted(note.items(), key=lambda x: (x[0][0], x[0][1])):
        riga = 3 + (d.month - mi) * RIGHE_PER_MESE + 2 + pos
        colonna = 3 + d.day
        elenco.append(("%s%d" % (col(colonna), riga), testo, riga - 1, colonna - 1))
    elenco.sort(key=lambda x: (x[2], x[3]))
    rels1 = parti["xl/worksheets/_rels/sheet1.xml.rels"].decode("utf-8")
    ct = parti["[Content_Types].xml"].decode("utf-8")
    if elenco:
        parti["xl/comments1.xml"] = commenti_xml([(e[0], e[1]) for e in elenco])
        parti["xl/drawings/vmlDrawing1.vml"] = vml_xml([(e[2], e[3]) for e in elenco],
                                                       primo_id_note(parti.get("xl/drawings/drawing1.xml")))
    else:
        coda = coda.replace('<legacyDrawing r:id="rId3"/>', "")
        rels1 = re.sub(r'<Relationship Id="rId3"[^>]*/>', "", rels1)
        rels1 = re.sub(r'<Relationship Id="rId4"[^>]*/>', "", rels1)
        parti.pop("xl/comments1.xml", None)
        parti.pop("xl/drawings/vmlDrawing1.vml", None)
        ct = re.sub(r'<Override PartName="/xl/comments1.xml"[^>]*/>', "", ct)
    parti["xl/worksheets/_rels/sheet1.xml.rels"] = rels1.encode("utf-8")
    parti["[Content_Types].xml"] = ct.encode("utf-8")
    parti["xl/worksheets/sheet1.xml"] = (testa + "<sheetData>" + righe_xml + "</sheetData>" + coda).encode("utf-8")

    # --- _base: colori di partenza (numeri BGR) e dati dell'esportazione
    st_serial = (adesso - datetime(1899, 12, 30)).total_seconds() / 86400
    base = []
    for r in range(1, NUM_RIGHE_FOGLIO + 1):
        cs = []
        for c in range(1, NUM_COLONNE_BASE + 1):
            info = celle.get((r, c))
            rgb = BIANCO
            if info:
                f = st.fills[_fill_id_di_stile(st, info[0])]
                p = f.find("m:patternFill", N)
                fg = p.find("m:fgColor", N) if p is not None else None
                if p is not None and p.get("patternType") == "solid" and fg is not None and fg.get("rgb"):
                    rgb = fg.get("rgb")[2:]
            cs.append('<c r="%s%d"><v>%d</v></c>' % (col(c), r, colore_bgr(rgb)))
        if r == 1:
            cs.append('<c r="AK1" t="s"><v>%d</v></c><c r="AL1"><v>%d</v></c>' % (ss.id("anno"), anno))
        if r == 2:
            cs.append('<c r="AK2" t="s"><v>%d</v></c><c r="AL2" s="%d"><v>%s</v></c>' % (ss.id("esportato"), st.xf_semplice(22), repr(st_serial)))
        base.append('<row r="%d">%s</row>' % (r, "".join(cs)))
    s2 = parti["xl/worksheets/sheet2.xml"].decode("utf-8")
    s2 = s2[: s2.index("<sheetData>")] + "<sheetData>" + "".join(base) + "</sheetData>" + s2[s2.index("</sheetData>") + 12:]
    parti["xl/worksheets/sheet2.xml"] = s2.encode("utf-8")

    # --- _note
    s_nota = st.xf_semplice(0, a_capo=True)
    nr = []
    for k, e in enumerate(elenco, 1):
        nr.append('<row r="%d"><c r="A%d"><v>%d</v></c><c r="B%d"><v>%d</v></c><c r="C%d" s="%d" t="s"><v>%d</v></c></row>'
                  % (k, k, e[2] + 1, k, e[3] + 1, k, s_nota, ss.id(e[1])))
    s3 = parti["xl/worksheets/sheet3.xml"].decode("utf-8")
    s3 = s3[: s3.index("<sheetData>")] + "<sheetData>" + "".join(nr) + "</sheetData>" + s3[s3.index("</sheetData>") + 12:]
    s3 = re.sub(r'<dimension ref="[^"]*"/>', '<dimension ref="A1:C%d"/>' % max(len(elenco), 1), s3)
    parti["xl/worksheets/sheet3.xml"] = s3.encode("utf-8")

    parti["xl/styles.xml"] = st.tobytes()
    parti["xl/sharedStrings.xml"] = ss.xml()
    wbx = parti["xl/workbook.xml"].decode("utf-8")
    wbx = re.sub(r'<sheet name="\d+"', '<sheet name="%d"' % anno, wbx, count=1)
    parti["xl/workbook.xml"] = wbx.encode("utf-8")
    app = parti["docProps/app.xml"].decode("utf-8")
    app = re.sub(r"<vt:lpstr>\d{4}</vt:lpstr>", "<vt:lpstr>%d</vt:lpstr>" % anno, app)
    parti["docProps/app.xml"] = app.encode("utf-8")

    with zipfile.ZipFile(uscita, "w", zipfile.ZIP_DEFLATED) as zout:
        ordine = ["[Content_Types].xml"] + [n for n in parti if n != "[Content_Types].xml"]
        for n in ordine:
            zout.writestr(n, parti[n])
    return uscita


def _fill_id_di_stile(st, idx):
    return int(st.xfs[idx].get("fillId"))
