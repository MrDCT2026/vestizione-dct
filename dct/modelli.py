from dataclasses import dataclass, field
from datetime import date, time
from typing import Optional

# colori delle celle: valori Long del VBA (BGR) convertiti in RGB esadecimale
# valori VBA Long (BGR) -> tipo, convertiti in RGB
def _bgr(n):
    r, g, b = n & 255, (n >> 8) & 255, (n >> 16) & 255
    return "%02X%02X%02X" % (r, g, b)

COLORE_TIPO = {
    _bgr(65535): "CONG_FEST",   # 65535
    _bgr(12632319): "ASS_MAL",
    _bgr(39423): "104",
    _bgr(32768): "CORSI",
    _bgr(12611584): "SIND",
    _bgr(16711935): "C_RIP",
    _bgr(15773696): "RL",
    _bgr(16751052): "MIS",
    _bgr(13395609): "RU",
}
COLORE_VUOTA = _bgr(15132390)

ASSENZE = ("CONG_FEST", "ASS_MAL", "104", "CORSI", "SIND")


@dataclass
class Cella:
    valore: str = ""
    tipo: str = ""
    diag: str = ""   # se non vuoto: corso sopra un rientro; contiene il tipo sottostante (MIS o C_RIP)


@dataclass
class Persona:
    pos: int
    nome: str
    gruppo: str
    inizio: date
    fine: date  # date.max se aperta


@dataclass
class CellaGiorno:
    data: date
    pos: int
    nome: str
    valore: str
    tipo: str
    diag: str = ""


@dataclass
class Riga:
    codice: str
    nome: str = ""
    nota: str = ""
    scoperto: bool = False
    escludi_grad: bool = False


@dataclass
class Assente:
    nome: str
    motivazione: str
    is_riposo: bool = False


@dataclass
class GiornoCoperto:
    data: date
    modalita: str
    turni: list = field(default_factory=list)
    sussidiari: list = field(default_factory=list)
    assenti: list = field(default_factory=list)


@dataclass
class Assegnazione:
    anno: int
    pos: int
    data: date
    turno: str
    tipo: str


@dataclass
class Config:
    turni: dict          # codice -> {'Feriale':(i,f), 'Sabato':..., 'Domenica':...}
    disponibilita: dict  # modalita -> [codici ordinati]
    sussidiari: dict     # chiave -> [(codice, inizio, fine)] ordinati per priorita
    motivazioni: dict    # tipo -> [codici]
