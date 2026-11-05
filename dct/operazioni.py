"""Operazioni sul calendario annuale (tasti colorati, RL, cambi riposo, cancellazioni).
Porting delle regole di Modulo1 (v11). Ogni operazione restituisce un Esito e non scrive nulla se rifiutata.
2026 Bruno Roli"""
from dataclasses import dataclass, field
from datetime import date
from .modelli import ASSENZE
from .copertura import Motore

ASSENZE_TASTO = ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND")
SCOPERTO_TIPI = ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND", "C_RIP", "RU")
MULTI = ("CONG_FEST", "ASS_MAL")
TURNO_CORSO = "CORSO"   # turno registrato per il rientro solo per un corso ('FOR')
SOLO_TURNO = ASSENZE_TASTO


@dataclass
class Esito:
    ok: bool
    msg: str = ""
    colorate: int = 0
    ripristinate: int = 0
    saltate: int = 0
    motivi: list = field(default_factory=list)
    chiede_cancellazione: str = ""   # "RL" / "MIS": la cella ha gia' un rientro, la schermata propone di cancellarlo


def no(msg):
    return Esito(False, msg)


class Operazioni:
    def __init__(self, archivio):
        self.a = archivio
        self.m = Motore(archivio)

    # ---------- letture di appoggio
    def cella(self, d, pos):
        return self.a.cella(d, pos)

    def vuota(self, d, pos):
        return self.m.chi_in_servizio(pos, d).strip() == ""

    def val(self, d, pos):
        c = self.cella(d, pos)
        return c.valore if c else ""

    def tipo(self, d, pos):
        c = self.cella(d, pos)
        return c.tipo if c else ""

    def diag(self, d, pos):
        c = self.cella(d, pos)
        return c.diag if c else ""

    def turno_valido(self, codice, d):
        from .calendario import modalita
        return codice in self.m.turni_principali(modalita(d), d)

    def turno_scoperto(self, codice, d):
        for p in range(1, 15):
            if self.val(d, p) == codice:
                if self.vuota(d, p):
                    return True
                return self.tipo(d, p) in SCOPERTO_TIPI
        return True

    def assegnazione_esistente(self, anno, pos, d):
        return any(x.anno == anno and x.pos == pos and x.data == d for x in self.a.assegnazioni)

    def turno_gia_coperto(self, anno, d, turno):
        return any(x.anno == anno and x.data == d and x.turno == turno for x in self.a.assegnazioni)

    def _valida_data(self, d):
        # solo i giorni presenti nel calendario (come "colonna fuori mese" del VBA)
        return self.cella(d, 1) is not None

    # ============================================================
    # TASTI ASSENZA (Cong./Fest., Ass./Mal., 104, Corsi, Sind.)
    # celle = lista di (data, pos)
    # ============================================================
    def applica_tasto(self, tasto, celle):
        if tasto not in ASSENZE_TASTO:
            return no("Tasto non valido.")
        if tasto not in MULTI and len(celle) > 1:
            return no("Questo tasto funziona solo su una cella alla volta.\nSeleziona una singola cella.")
        e = Esito(True)
        piano = []
        for d, pos in celle:
            if not self._valida_data(d):
                e.saltate += 1
                self._motivo(e, "colonna fuori dal mese")
                continue
            if self.vuota(d, pos):
                e.saltate += 1
                self._motivo(e, "posizione vuota (nessun dipendente in servizio)")
                continue
            valore = self.val(d, pos)
            riposo = (valore == "R")
            tipo = self.tipo(d, pos)
            diag = self.diag(d, pos)
            corso_su_rientro = False
            if tasto == "CORSI" and riposo and (tipo in ("MIS", "C_RIP") or diag):
                corso_su_rientro = True
            if tasto in SOLO_TURNO and riposo and not corso_su_rientro:
                e.saltate += 1
                self._motivo(e, "riposo (tasto applicabile solo ai turni)")
                continue
            if tipo == "C_RIP" and not riposo:
                e.saltate += 1
                self._motivo(e, "cella con cambio riposo (chi esce): cancella prima il cambio riposo")
                continue
            if tipo == tasto:                       # secondo click: ripristina
                nuovo_tipo = diag if diag else ""
                piano.append((d, pos, nuovo_tipo, ""))
                e.ripristinate += 1
            else:
                piano.append((d, pos, tasto, tipo if corso_su_rientro else ""))
                e.colorate += 1
        for d, pos, t, dg in piano:
            self.a.imposta_cella(d, pos, t, dg)
        self.a.salva()
        return e

    @staticmethod
    def _motivo(e, testo):
        if testo not in e.motivi:
            e.motivi.append(testo)

    # ============================================================
    # RL
    # ============================================================
    def rl(self, d, pos, turno=None):
        """Assegna un RL sul riposo (d,pos) per coprire `turno`. Se la cella ha gia' un RL o MIS
        restituisce chiede_cancellazione; la cancellazione si fa con cancella()."""
        if self.diag(d, pos):
            return no("Questa cella ha un corso sopra un rientro in servizio.\nTogli prima il corso con il tasto Corsi.")
        t = self.tipo(d, pos)
        if t in ("RL", "MIS"):
            return Esito(False, "", chiede_cancellazione=t)
        if self.vuota(d, pos):
            return no("Posizione vuota: nessun dipendente in servizio.")
        if self.val(d, pos) != "R":
            return no("L'RL si applica solo sui riposi (R).")
        return self._rientro(d, pos, turno, "RL")

    def _rientro(self, d, pos, turno, tipo):
        if not turno:
            return no("Operazione annullata.")
        if not self._valida_data(d):
            return no("Data non valida.")
        if not self.turno_valido(turno, d):
            return no("Turno non valido per la modalità di questo giorno.")
        if not self.turno_scoperto(turno, d):
            return no("Il turno %s non è scoperto in questa data." % turno)
        if self.assegnazione_esistente(d.year, pos, d):
            return no("Esiste già un'assegnazione per questa persona in questa data.")
        if self.turno_gia_coperto(d.year, d, turno):
            return no("Questo turno è già coperto da un RL/MIS.")
        self.a.imposta_cella(d, pos, tipo, "")
        self.a.aggiungi_assegnazione(d.year, pos, d, turno, tipo)
        self.a.salva()
        return Esito(True)

    # ============================================================
    # CAMBIO RIPOSO DI SERVIZIO (S): riposo -> MIS (rientro), turno -> RU (uscita a riposo)
    # turno 'FOR': rientro solo per un corso (MIS senza turno, con il corso sopra)
    # ============================================================
    def cambio_riposo_servizio(self, d, pos, turno=None):
        e = self._controlli_c_rip(d, pos)
        if e:
            return e
        if self.vuota(d, pos):
            return no("Posizione vuota: nessun dipendente in servizio.")
        t = self.tipo(d, pos)
        if t in ASSENZE_TASTO:
            return no("Questa cella ha gia' un'assenza (corso, congedo, ecc.).\nToglila prima con il tasto relativo.")
        if t in ("RL", "MIS"):
            return Esito(False, "", chiede_cancellazione=t)
        if t in ("C_RIP", "RU"):
            return no("Questa cella ha già un cambio riposo. Cancellalo prima con 'C'.")
        valore = self.val(d, pos)
        if valore == "":
            return no("Cella vuota: niente da cambiare.")
        if valore == "R":
            if (turno or "").strip().upper() == "FOR":
                return self._rientro_per_corso(d, pos)
            return self._rientro(d, pos, turno, "MIS")
        self.a.imposta_cella(d, pos, "RU", "")
        self.a.salva()
        return Esito(True)

    def _rientro_per_corso(self, d, pos):
        """'FOR' (formazione): il collega rientra solo per un corso, senza turno da coprire (Excel v13b).
        Registro: MIS con turno "CORSO"; cella: corso (verde) con la diagonale del MIS.
        Nessun controllo di turno valido/scoperto/gia' coperto. Per toglierlo: prima il corso (tasto Corsi), poi 'C'."""
        if not self._valida_data(d):
            return no("Data non valida.")
        if self.assegnazione_esistente(d.year, pos, d):
            return no("Esiste già un'assegnazione per questa persona in questa data.")
        self.a.imposta_cella(d, pos, "CORSI", "MIS")
        self.a.aggiungi_assegnazione(d.year, pos, d, TURNO_CORSO, "MIS")
        self.a.salva()
        return Esito(True)

    def _controlli_c_rip(self, d, pos):
        if self.diag(d, pos):
            return no("Questa cella ha un corso sopra un rientro in servizio.\nTogli prima il corso con il tasto Corsi.")
        if self.vuota(d, pos) and self.tipo(d, pos) not in ("C_RIP", "MIS", "RL", "RU"):
            return no("Posizione vuota: nessun dipendente in servizio.")
        return None

    # ============================================================
    # CAMBIO RIPOSO PERSONALE (P): scambio tra un turno e un riposo nella stessa giornata
    # ============================================================
    def cambio_riposo_personale(self, d, pos1, pos2):
        e = self._controlli_c_rip(d, pos1)
        if e:
            return e
        if self.vuota(d, pos1):
            return no("Posizione vuota: nessun dipendente in servizio.")
        t1 = self.tipo(d, pos1)
        if t1 in ASSENZE_TASTO:
            return no("Questa cella ha gia' un'assenza (corso, congedo, ecc.).\nToglila prima con il tasto relativo.")
        if t1 != "":
            return no("Questa cella ha gia' un colore (cambio riposo, RL, MIS, ecc.). Cancellalo prima.")
        # seconda cella
        if pos2 == pos1 or self.tipo(d, pos2) != "":
            return no("Cella non valida. Operazione annullata.")
        v1, v2 = self.val(d, pos1), self.val(d, pos2)
        turno1 = v1 not in ("", "R")
        turno2 = v2 not in ("", "R")
        if turno1 == turno2:
            return no("Cella non valida. Operazione annullata.")
        if self.vuota(d, pos2):
            return no("Posizione vuota: nessun dipendente in servizio.")
        if turno1:
            pos_turno, pos_rient = pos1, pos2
        else:
            pos_turno, pos_rient = pos2, pos1
        codice = self.val(d, pos_turno)
        if self.assegnazione_esistente(d.year, pos_rient, d):
            return no("Esiste già un'assegnazione per questa persona in questa data.")
        if self.turno_gia_coperto(d.year, d, codice):
            return no("Questo turno è già coperto da un RL/MIS/C_RIP.")
        self.a.imposta_cella(d, pos1, "C_RIP", "")
        self.a.imposta_cella(d, pos2, "C_RIP", "")
        self.a.aggiungi_assegnazione(d.year, pos_rient, d, codice, "C_RIP")
        self.a.salva()
        return Esito(True)

    # ============================================================
    # CANCELLAZIONE (MIS, RU, RL singoli; C_RIP a coppia)
    # ============================================================
    def cancella(self, d, pos):
        if self.diag(d, pos):
            return no("Questa cella ha un corso sopra un rientro in servizio.\nTogli prima il corso con il tasto Corsi.")
        t = self.tipo(d, pos)
        if t in ("MIS", "RU", "RL"):
            self.a.imposta_cella(d, pos, "", "")
            if t in ("MIS", "RL"):
                self.a.rimuovi_assegnazione(d.year, pos, d)
            self.a.salva()
            return Esito(True, "Cambio riposo cancellato.")
        if t != "C_RIP":
            return no("Nessun cambio riposo da cancellare in questa cella.")
        partner = self._partner_registro(d, pos)
        if partner is None:
            partner = self._altra_c_rip(d, pos)
        elif self.diag(d, partner):
            return no("Il collega che rientra ha un corso sopra il cambio riposo.\n"
                      "Togli prima il corso con il tasto Corsi, poi cancella il cambio riposo.")
        pos_rient = 0
        if self.val(d, pos) == "R":
            pos_rient = pos
        elif partner is not None and self.val(d, partner) == "R":
            pos_rient = partner
        if pos_rient > 0:
            self.a.rimuovi_assegnazione(d.year, pos_rient, d)
        self.a.imposta_cella(d, pos, "", "")
        if partner is not None:
            self.a.imposta_cella(d, partner, "", "")
        self.a.salva()
        return Esito(True, "Cambio riposo cancellato.")

    def _partner_registro(self, d, pos):
        val = self.val(d, pos)
        for x in self.a.assegnazioni:
            if x.anno == d.year and x.tipo == "C_RIP" and x.data == d:
                if val == "R":
                    if x.pos == pos:
                        for p in range(1, 15):
                            if self.val(d, p) == x.turno and self.tipo(d, p) == "C_RIP":
                                return p
                        return None
                else:
                    if x.turno == val:
                        return x.pos
        return None

    def _altra_c_rip(self, d, pos):
        trovate = [p for p in range(1, 15) if p != pos and self.tipo(d, p) == "C_RIP"]
        return trovate[0] if len(trovate) == 1 else None
