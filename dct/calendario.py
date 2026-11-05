from datetime import date, timedelta


def pasqua(anno):
    a = anno % 19
    b = anno // 100
    c = anno % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    p = h + l - 7 * m + 114
    return date(anno, p // 31, p % 31 + 1)


_FESTE = {(1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15), (11, 1), (12, 8), (12, 25), (12, 26)}


def is_festivo(d):
    return (d.month, d.day) in _FESTE or d == pasqua(d.year) + timedelta(days=1)


def modalita(d):
    if is_festivo(d):
        return "Domenica"
    w = d.weekday()
    return "Sabato" if w == 5 else "Domenica" if w == 6 else "Feriale"


def lunedi_settimana(anno, nn):
    q = date(anno, 1, 4)
    return q - timedelta(days=q.weekday()) + timedelta(days=7 * (nn - 1))


def numero_iso(d):
    return d.isocalendar()[1]


def anno_iso(d):
    return d.isocalendar()[0]


def primo_feriale_dopo_festivo(d):
    """Primo giorno feriale (lun-ven, non festivo) dopo una domenica o un festivo."""
    if is_festivo(d) or d.weekday() > 4:
        return False
    p = d - timedelta(days=1)
    return p.weekday() == 6 or is_festivo(p)
