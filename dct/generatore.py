"""Generazione della rotazione annuale (turni e riposi per gruppo). Porting di Modulo1: IsRiposo / CalcolaTurnoAllaData.
2026 Bruno Roli"""
from datetime import date, timedelta

DATA_RIFERIMENTO = date(2026, 9, 28)   # lunedi' della settimana di partenza dei tipi di riposo
DATA_TURNI = date(2026, 10, 1)         # data a cui si riferiscono i turni iniziali
TURNI_ROTAZIONE = ["601", "602", "Dd2", "603", "604", "605", "Dd5", "606", "607V", "608", "Dd8", "610"]
GRUPPI = ["D", "E", "F", "G", "A", "B", "C", "D", "E", "F", "G", "A", "B", "C"]
TIPO_INIZIALE = {"D": 4, "E": 3, "F": 2, "G": 1, "A": 7, "B": 6, "C": 5}
GIORNI_RIPOSO = {1: (4,), 2: (3,), 3: (2, 7), 4: (1, 7), 5: (6,), 6: (6,), 7: (5, 6, 7)}   # 1 = lunedi'
TURNO_INIZIALE = ["601", "602", "Dd2", "", "603", "604", "605", "Dd5", "606", "607V", "", "608", "Dd8", "610"]
DOPO_RIPOSO_INIZIALE = {4: "603", 11: "608"}


def gruppo_posizione(pos):
    return GRUPPI[pos - 1]


def is_riposo(pos, d):
    settimane = (d - DATA_RIFERIMENTO).days // 7      # settimane intere dal lunedi' di riferimento
    tipo = (TIPO_INIZIALE[GRUPPI[pos - 1]] - 1 + settimane) % 7 + 1
    return d.isoweekday() in GIORNI_RIPOSO[tipo]


def _successivo(turno):
    i = TURNI_ROTAZIONE.index(turno)
    return TURNI_ROTAZIONE[(i + 1) % 12]


def valori_posizione(pos, fine):
    """Valore (turno o 'R') di una posizione per ogni giorno da DATA_TURNI a `fine` compresa."""
    out = {}
    d = DATA_TURNI
    turno = TURNO_INIZIALE[pos - 1]
    if turno == "":
        turno = DOPO_RIPOSO_INIZIALE[pos]
        while is_riposo(pos, d):
            out[d] = "R"
            d += timedelta(days=1)
    while d <= fine:
        if is_riposo(pos, d):
            out[d] = "R"
            if not is_riposo(pos, d + timedelta(days=1)):
                turno = _successivo(turno)
        else:
            out[d] = turno
        d += timedelta(days=1)
    return out


def genera_valori(anno):
    """Dizionario {(data, pos): valore} per l'anno (dal 1 ottobre 2026 per il 2026)."""
    inizio = DATA_TURNI if anno == 2026 else date(anno, 1, 1)
    fine = date(anno, 12, 31)
    res = {}
    for pos in range(1, 15):
        v = valori_posizione(pos, fine)
        d = inizio
        while d <= fine:
            res[(d, pos)] = v[d]
            d += timedelta(days=1)
    return res
