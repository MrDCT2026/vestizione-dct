"""Calcolo della copertura di un giorno: porting fedele di modCopertura.bas (v11)."""
from datetime import date, timedelta
from .modelli import *
from .calendario import modalita as get_modalita, is_festivo, primo_feriale_dopo_festivo

ASSENTI_COPERTURA = ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND", "RU")


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
        if mod == "Feriale":
            if primo_feriale_dopo_festivo(d):
                chiave = "Lun_CasoA" if self.is_lunedi_caso_a(d) else "Lun_CasoB"
            else:
                chiave = "Feriale"
        else:
            chiave = mod
        return [x[0] for x in self.a.config_alla(d).sussidiari.get(chiave, [])]

    def orario_suss(self, codice, mod, d):
        for c, i, _f in self.a.config_alla(d).sussidiari.get(mod, []):
            if c == codice:
                return i
        return ""

    def orario_turno(self, codice, mod, d):
        t = self.a.config_alla(d).turni.get(codice)
        return t[mod][0] if t else ""

    def coda_disp(self, mod, d):
        return list(self.a.config_alla(d).disponibilita.get(mod, []))

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
        g.sussidiari = [Riga(cfg[i]) for i in range(nsuss)]
        disp = self._raccogli_disponibilita(dati, mod, d)
        grad = self._costruisci_graduatoria(g, mod, d)
        self._copri(g, grad, disp)
        for s in g.sussidiari:
            if s.nome == "":
                s.nome = "Scoperto"
                s.scoperto = True
        self._raccogli_assenti(g, dati, d)
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

    def _copri(self, g, grad, disp):
        usato_g, usato_d = set(), set()
        # il 606 (disponibile della domenica e dei festivi) copre il turno principale scoperto piu' tardi
        ultimo = max((k for k, x in enumerate(grad) if x[0] == "P"), default=None)
        if ultimo is not None:
            for j, d in enumerate(disp):
                if d[1] == "606":
                    self._assegna(g, grad[ultimo], d)
                    usato_g.add(ultimo)
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
