"""Calcolo della copertura di un giorno: porting fedele di modCopertura.bas (v11)."""
from datetime import date, timedelta
from .modelli import *
from .calendario import modalita as get_modalita, is_festivo, primo_feriale_dopo_festivo

ASSENTI_COPERTURA = ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND", "RU")
MAX_TURNI_FESTIVI = 7                            # domenica e festivi: 6 principali + 630
# chi esce per primo quando i presenti sono piu' di 7 (601 in fondo, confermato il 09/11/2026);
# si salta l'ultimo della coda (a Natale il Dd5), che copre il turno piu' tardi
ORDINE_ECCEDENTI = ("Dd5", "Dd2", "Dd8", "607V", "601")


class Motore:
    def __init__(self, archivio):
        self.a = archivio

    # ---------- persone / celle
    def chi_in_servizio(self, pos, d):
        for p in self.a.persone:
            if p.pos == pos and p.nome and p.inizio <= d <= p.fine:
                return p.nome
        return ""

    def gruppo(self, pos):
        for p in self.a.persone:
            if p.pos == pos:
                return p.gruppo
        return ""

    def dati_giorno(self, d):
        out = {}
        for pos in range(1, 15):
            c = self.a.cella(d, pos)
            nome = self.chi_in_servizio(pos, d)
            if c is None:
                out[pos] = CellaGiorno(d, pos, nome, "", "", False)
            else:
                out[pos] = CellaGiorno(d, pos, nome, c.valore, c.tipo, c.diag)
        return out

    # ---------- lunedi caso A
    def is_lunedi_caso_a(self, d):
        if not primo_feriale_dopo_festivo(d):
            return False
        prec = d - timedelta(days=1)
        n = 0
        for pos in range(1, 15):
            if self.chi_in_servizio(pos, prec).strip() == "":
                continue
            c = self.a.cella(prec, pos)
            val = c.valore if c else ""
            tipo = c.tipo if c else ""
            if val != "" and val != "R":
                if tipo in ASSENTI_COPERTURA:
                    pass
                else:
                    n += 1
            elif val == "R" and tipo in ("C_RIP", "MIS"):
                n += 1
        return n <= 6

    # ---------- configurazione per modalita'
    def turni_principali(self, mod, d):
        nat = self.a.natale_alla(d)
        if nat:
            return [c for c, _i, _f in nat["TURNO"]]
        if mod == "Feriale":
            if self.is_lunedi_caso_a(d):
                return ["627", "603", "605", "601", "604", "608", "606", "602", "610"]
            return ["603", "605", "601", "604", "608", "606", "602", "610"]
        if mod == "Sabato":
            return ["603", "605", "604", "608", "606", "602", "610"]
        if mod == "Domenica":
            return ["603", "605", "604", "608", "602", "610"]
        return []

    def sussidiari_cfg(self, mod, d):
        nat = self.a.natale_alla(d)
        if nat:
            return [c for c, _i, _f in nat["SUSS"]]
        if mod == "Feriale":
            if primo_feriale_dopo_festivo(d):
                chiave = "Lun_CasoA" if self.is_lunedi_caso_a(d) else "Lun_CasoB"
            else:
                chiave = "Feriale"
        else:
            chiave = mod
        return [x[0] for x in self.a.config_alla(d).sussidiari.get(chiave, [])]

    def orario_suss(self, codice, mod, d):
        nat = self.a.natale_alla(d)
        for c, i, _f in (nat["SUSS"] if nat else self.a.config_alla(d).sussidiari.get(mod, [])):
            if c == codice:
                return i
        return ""

    def orario_turno(self, codice, mod, d):
        nat = self.a.natale_alla(d)
        if nat:
            return next((i for c, i, _f in nat["TURNO"] if c == codice), "")
        t = self.a.config_alla(d).turni.get(codice)
        return t[mod][0] if t else ""

    def coda_disp(self, mod, d):
        nat = self.a.natale_alla(d)
        if nat:
            return [c for c, _i, _f in nat["DISP"]]
        return list(self.a.config_alla(d).disponibilita.get(mod, []))

    def max_turni_festivi(self, d):
        """Domenica e festivi: 7 turni coperti; a Natale il parametro TurniCoperti (8)."""
        nat = self.a.natale_alla(d)
        return int(nat["PARAM"].get("TurniCoperti", MAX_TURNI_FESTIVI)) if nat else MAX_TURNI_FESTIVI

    # ---------- funzione principale
    def calcola_giorno(self, d):
        mod = get_modalita(d)
        g = GiornoCoperto(d, mod)
        dati = self.dati_giorno(d)
        elenco = self.turni_principali(mod, d)
        g.turni = [Riga(c) for c in elenco]
        self._assegna_titolari(g, dati)
        self._applica_assegnazioni(g, d, dati)
        presenti = self._conta_presenti(dati)
        if mod == "Feriale" and self.is_lunedi_caso_a(d) and presenti <= 8:
            for t in g.turni:
                if t.codice == "603":
                    t.escludi_grad = True
                    break
        nsuss = max(0, presenti - len(g.turni))
        cfg = self.sussidiari_cfg(mod, d)
        nsuss = min(nsuss, len(cfg))
        max_fest = self.max_turni_festivi(d)
        if mod == "Domenica":       # domenica e festivi: al massimo 7 turni coperti (6 principali + 630), Natale 8
            nsuss = min(nsuss, max(0, max_fest - len(g.turni)))
        g.sussidiari = [Riga(cfg[i]) for i in range(nsuss)]
        disp = self._raccogli_disponibilita(dati, mod, d)
        eccedenti = []
        if mod == "Domenica" and presenti > max_fest:
            # gli eccedenti escono dalla copertura e vanno tra gli assenti con FU (festivo) o CU (domenica):
            # si scelgono tra i disponibili presenti nell'ordine Dd5, Dd2, Dd8, 607V (09/11/2026, VBA v17)
            resto = presenti - max_fest
            ultimo = self.coda_disp(mod, d)[-1:]       # l'ultimo della coda non va mai tra gli eccedenti (v18b)
            for cod in ORDINE_ECCEDENTI:
                if resto == 0:
                    break
                if cod in ultimo:
                    continue
                for j, x in enumerate(disp):
                    if x[1] == cod:
                        eccedenti.append(disp.pop(j))
                        resto -= 1
                        break
        grad = self._costruisci_graduatoria(g, mod, d)
        self._copri(g, grad, disp, self.coda_disp(mod, d))
        for s in g.sussidiari:
            if s.nome == "":
                s.nome = "Scoperto"
                s.scoperto = True
        # sussidiari mostrati in ordine di orario di inizio (06/11/2026), come i turni principali
        g.sussidiari.sort(key=lambda r: self.orario_suss(r.codice, mod, d) or "99:99")
        self._raccogli_assenti(g, dati, d)
        for x in eccedenti:
            g.assenti.append(Assente(x[2], "CU" if d.weekday() == 6 else "FU"))
        g.presenti = presenti
        return g

    # ---------- passi
    def _assegna_titolari(self, g, dati):
        for t in g.turni:
            pos = 0
            for p in range(1, 15):
                if dati[p].valore == t.codice:
                    pos = p
                    break
            if pos == 0:
                t.nome, t.scoperto = "Scoperto", True
                continue
            c = dati[pos]
            tipo = c.tipo
            if tipo in ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND", "C_RIP", "RU"):
                t.nome, t.scoperto = "Scoperto", True
            elif tipo in ("RL", "MIS"):
                t.nome, t.nota, t.scoperto = c.nome, tipo, False
            else:
                if c.nome == "":
                    t.nome, t.scoperto = "Scoperto", True
                else:
                    t.nome, t.scoperto = c.nome, False

    def _assegnazioni_del_giorno(self, d):
        return [x for x in self.a.assegnazioni if x.data == d]

    def _applica_assegnazioni(self, g, d, dati):
        for x in self._assegnazioni_del_giorno(d):
            if dati[x.pos].tipo == "CORSI":
                continue
            if x.tipo in ("RL", "MIS"):
                for t in g.turni:
                    if t.codice == x.turno:
                        t.nome, t.nota, t.scoperto = dati[x.pos].nome, x.tipo, False
                        break
            elif x.tipo == "C_RIP":
                for t in g.turni:
                    if t.codice == x.turno:
                        t.nome, t.nota, t.scoperto = dati[x.pos].nome, "C. Rip.", False
                        break

    def _conta_presenti(self, dati):
        n = 0
        for p in range(1, 15):
            c = dati[p]
            if c.nome == "":
                continue
            if c.tipo in ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND", "RU"):
                continue
            if c.valore == "R":
                if c.tipo in ("MIS", "C_RIP", "RL"):
                    n += 1
                continue
            if c.valore == "":
                continue
            if c.tipo == "C_RIP":
                continue
            n += 1
        return n

    def _raccogli_disponibilita(self, dati, mod, d):
        coda = self.coda_disp(mod, d)
        sost = {}
        for x in self._assegnazioni_del_giorno(d):
            if x.tipo == "C_RIP" and x.turno in coda and dati[x.pos].tipo != "CORSI":
                sost.setdefault(x.turno, x.pos)
        out = []
        for codice in coda:
            if codice in sost:
                pr = sost[codice]
                nome = dati[pr].nome
                if nome != "":
                    out.append((pr, codice, nome, "C. Rip."))
                continue
            for p in range(1, 15):
                if dati[p].valore == codice and dati[p].nome != "":
                    tipo = dati[p].tipo
                    if tipo in ASSENTI_COPERTURA or tipo == "C_RIP":
                        pass
                    else:
                        out.append((p, codice, dati[p].nome, ""))
                    break
        return out

    def _costruisci_graduatoria(self, g, mod, d):
        arr = []
        for i, t in enumerate(g.turni):
            if t.scoperto and not t.escludi_grad:
                o = self.orario_turno(t.codice, mod, d) or "99:99"
                arr.append(("P", i, o))
        for i, s in enumerate(g.sussidiari):
            o = self.orario_suss(s.codice, mod, d) or "99:99"
            arr.append(("S", i, o))
        n = len(arr)
        for j in range(n - 1):  # stesso ordinamento a scambi del VBA
            for k in range(j + 1, n):
                if arr[j][2] > arr[k][2]:
                    arr[j], arr[k] = arr[k], arr[j]
        return arr

    def _copri(self, g, grad, disp, coda=()):
        """L'ultimo della coda dei disponibili ("ultimo turno disp.": Dd5 nei feriali e il sabato, 606 la domenica e
        i festivi) copre il turno da coprire che inizia piu' tardi, principale o sussidiario. Gli altri disponibili,
        in ordine di priorita', coprono i turni rimasti in ordine di orario. (606: 26/10 e 09/11/2026; Dd5: 06/11/2026)"""
        usato_g, usato_d = set(), set()
        ultimo_cod = coda[-1] if coda else None
        liberi = list(range(len(grad)))        # principali e sussidiari (dal 09/11/2026 anche per il 606)
        if ultimo_cod and liberi:
            for j, d in enumerate(disp):
                if d[1] == ultimo_cod:
                    self._assegna(g, grad[liberi[-1]], d)   # graduatoria in ordine di orario: l'ultimo inizia piu' tardi
                    usato_g.add(liberi[-1])
                    usato_d.add(j)
                    break
        j = 0
        for k, x in enumerate(grad):
            if k in usato_g:
                continue
            while j < len(disp) and j in usato_d:
                j += 1
            if j >= len(disp):
                break
            self._assegna(g, x, disp[j])
            j += 1

    @staticmethod
    def _assegna(g, voce, d):
        tipo, idx, _ = voce
        _, _, nome, nota = d
        r = g.turni[idx] if tipo == "P" else g.sussidiari[idx]
        r.nome, r.nota, r.scoperto = nome, nota, False

    def _raccogli_assenti(self, g, dati, d):
        out = []
        for p in range(1, 15):
            c = dati[p]
            if c.nome != "" and c.valore == "R" and c.tipo not in ("MIS", "RL", "C_RIP", "CORSI"):
                out.append(Assente(c.nome, "R"))
        for p in range(1, 15):
            c = dati[p]
            if c.nome == "":
                continue
            if c.tipo in ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND"):
                mot = self._motivazione(c.tipo, d)
                if c.tipo == "CORSI" and c.diag in ("MIS", "C_RIP"):   # corso sopra un rientro
                    mot = "%s (%s)" % ("MIS" if c.diag == "MIS" else "C. Rip.", mot or "Corso")
                out.append(Assente(c.nome, mot))
            elif c.tipo == "RU":
                out.append(Assente(c.nome, "RU", True))
            elif c.tipo == "C_RIP" and c.valore != "R":
                out.append(Assente(c.nome, "C. Rip.", True))
        g.assenti = out

    def _motivazione(self, tipo, d):
        m = self.a.config_alla(d).motivazioni.get(tipo, [])
        if tipo == "CONG_FEST":
            cod = "Fest." if is_festivo(d) else "Cong."
            return cod if cod in m else ""
        return m[0] if m else ""
