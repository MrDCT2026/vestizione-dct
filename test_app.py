"""Prove del programma locale: avvia il server su una cartella temporanea e prova le richieste."""
import json, os, sys, tempfile, threading, urllib.error, urllib.request
from datetime import date
from http.server import HTTPServer
from dct.app import server as sv

XLSM = sys.argv[1]
OK = KO = 0


def check(nome, cond, extra=""):
    global OK, KO
    if cond:
        OK += 1
    else:
        KO += 1
        print("  FALLITO:", nome, extra)


P = sv.Programma(tempfile.mkdtemp(), oggi=date(2026, 10, 23))
sv.Gestore.P = P
srv = sv.Server(("127.0.0.1", 0), sv.Gestore)
base = "http://127.0.0.1:%d" % srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def get(u):
    with urllib.request.urlopen(base + u) as r:
        return r.read(), r.headers


def j(u, corpo=None):
    rich = urllib.request.Request(base + u, data=None if corpo is None else (corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()))
    try:
        with urllib.request.urlopen(rich) as r:
            return json.loads(r.read()), 200
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


check("pagina", b"Vestizione" in get("/")[0])
# connessione aperta e non usata (come fa WebKit): le altre richieste non devono bloccarsi
import socket, time
_ferma = socket.create_connection(srv.server_address)
_t = time.time()
try:
    ok_ = b"aperto" in urllib.request.urlopen(base + "/api/stato", timeout=5).read()
except Exception:
    ok_ = False
check("connessione inutilizzata non blocca le pagine", ok_ and time.time() - _t < 2)
_ferma.close()
# invio iniziato e non finito (es. file interrotto): le altre richieste non devono aspettare
_ferma = socket.create_connection(srv.server_address)
_ferma.sendall(b"POST /api/import/analizza?anno=2026&da=45&a=45 HTTP/1.1\r\nHost: x\r\nContent-Length: 400000\r\n\r\n0123")
time.sleep(0.2)
_t = time.time()
try:
    ok_ = b"aperto" in urllib.request.urlopen(base + "/api/stato", timeout=5).read()
except Exception:
    ok_ = False
check("invio interrotto non blocca le pagine", ok_ and time.time() - _t < 2)
_ferma.close()
check("statici", b"function" in get("/app.js")[0] and b"cal" in get("/stile.css")[0])
try:
    urllib.request.urlopen(base + "/..%2f..%2fetc/passwd")
    check("percorso fuori", False)
except urllib.error.HTTPError as e:
    check("percorso fuori", e.code == 404)
s, _ = j("/api/stato")
check("senza archivio", s["aperto"] is False)
e, c = j("/api/anno?anno=2026&mese=10")
check("senza archivio: errore chiaro", c == 400 and "importa" in e["errore"].lower())

s, _ = j("/api/importa", open(XLSM, "rb").read())
check("importato", s["aperto"] and s["mesi"][0] == [2026, 10] and "graduatoria" not in s)
a, _ = j("/api/anno?anno=2026&mese=10")
check("anno: 31 giorni, 14 righe", len(a["giorni"]) == 31 and len(a["righe"]) == 14)
check("anno: DCT per giorno", len(a["dct"]) == 31 and a["dct"][0]["soglia"] == 8)
check("anno: colori", a["giorni"][2]["fill"] == "C6EFCE" and a["giorni"][3]["fill"] == "FF6C5D")
cella = a["righe"][0]["celle"][27]
r, _ = j("/api/tasto", {"tasto": "ASS_MAL", "celle": [["2026-10-28", 1]]})
check("tasto", r["ok"] and r["colorate"] == 1)
a2, _ = j("/api/anno?anno=2026&mese=10")
check("cella colorata", a2["righe"][0]["celle"][27]["fill"] == "FFC0C0" and a2["dct"][27]["n"] == a["dct"][27]["n"] - 1)
r, _ = j("/api/tasto", {"tasto": "ASS_MAL", "celle": [["2026-10-28", 1]]})
a3, _ = j("/api/anno?anno=2026&mese=10")
check("ripristinata", r["ripristinate"] == 1 and a3["righe"][0]["celle"][27] == cella)
r, c = j("/api/tasto", {"tasto": "SIND", "celle": [["2026-10-28", 1], ["2026-10-28", 2]]})
check("rifiuto: una cella alla volta", r["ok"] is False)
st, _ = j("/api/stato")
check("salvataggio registrato", st["salvato"] is not None)
check("copie di sicurezza", len([f for f in os.listdir(os.path.join(P.cartella, "backup")) if f.startswith("archivio_")]) >= 2)

w, _ = j("/api/settimana?anno=2026&nn=43")
check("settimana", w["dal"] == "2026-10-19" and len(w["blocchi"]) == 7 and w["blocchi"][0]["righe"][0]["cod"] == "603")
check("settimana_di", j("/api/settimana_di?data=2026-10-25")[0] == {"anno": 2026, "nn": 43})
r, c = j("/api/settimana?anno=2025&nn=10")
check("settimana fuori calendario", c == 400)
t, _ = j("/api/rl_turni?data=2026-10-24&pos=1")
check("rl_turni", "turni" in t and t["riposo"] is True)

f, h = get("/api/esporta/settimana?anno=2026&nn=43")
check("esporta settimana", f[:2] == b"PK" and "Settimana_43_2026.xlsx" in h["Content-Disposition"])
f, h = get("/api/esporta/rotazione?anno=2026")
check("esporta rotazione", f[:2] == b"PK" and "Rotazione_2026.xlsm" in h["Content-Disposition"])

# cambi riposo
turno_cell = next(i for i, r in enumerate(a["righe"]) if r["celle"][12]["v"] not in ("", "R") and not r["celle"][12]["vuota"] and not r["celle"][12]["t"])
rr, _ = j("/api/cambio_servizio", {"data": "2026-10-13", "pos": turno_cell + 1})
check("cambio servizio: turno -> RU", rr["ok"] and j("/api/anno?anno=2026&mese=10")[0]["righe"][turno_cell]["celle"][12]["t"] == "RU")
rr, _ = j("/api/cancella", {"data": "2026-10-13", "pos": turno_cell + 1})
check("RU cancellato", rr["ok"])
rip = next(i for i, r in enumerate(a["righe"]) if r["celle"][12]["v"] == "R" and not r["celle"][12]["vuota"] and not r["celle"][12]["t"])
rr, _ = j("/api/cambio_servizio", {"data": "2026-10-13", "pos": rip + 1, "turno": "FOR"})
cf = j("/api/anno?anno=2026&mese=10")[0]["righe"][rip]["celle"][12]
check("cambio servizio FOR: corso con diagonale lavanda", rr["ok"] and cf["t"] == "CORSI" and cf["diag"] == "MIS" and cf["dfill"].upper() == "CC99FF", (rr, cf))
w42, _ = j("/api/settimana?anno=2026&nn=42")
check("cambio servizio FOR: nella settimana \"MIS (Corso)\"", "MIS (Corso)" in json.dumps(w42))
rr, _ = j("/api/tasto", {"tasto": "CORSI", "celle": [["2026-10-13", rip + 1]]})
rr, _ = j("/api/cancella", {"data": "2026-10-13", "pos": rip + 1})
check("FOR tolto (prima corso, poi C)", rr["ok"] and not j("/api/anno?anno=2026&mese=10")[0]["righe"][rip]["celle"][12]["t"])
rr, _ = j("/api/cambio_personale", {"data": "2026-10-13", "pos1": turno_cell + 1, "pos2": rip + 1})
check("cambio personale", rr["ok"] and j("/api/anno?anno=2026&mese=10")[0]["righe"][rip]["celle"][12]["t"] == "C_RIP", rr)
rr, _ = j("/api/cancella", {"data": "2026-10-13", "pos": rip + 1})
check("cambio personale cancellato (coppia)", rr["ok"] and j("/api/anno?anno=2026&mese=10")[0]["righe"][turno_cell]["celle"][12]["t"] == "")
j("/api/nota", {"data": "2026-10-28", "pos": 3, "testo": "prova"})
check("nota", j("/api/anno?anno=2026&mese=10")[0]["righe"][2]["celle"][27]["nota"] == "prova")
j("/api/nota", {"data": "2026-10-28", "pos": 3, "testo": ""})
check("nota tolta", j("/api/anno?anno=2026&mese=10")[0]["righe"][2]["celle"][27]["nota"] == "")
# personale
pers, _ = j("/api/personale")
check("personale: 14 posizioni", len(pers["elenco"]) == 14 and pers["elenco"][0]["nome"] == "Pischetola" and pers["elenco"][3]["nome"] == "")
check("personale: graduatoria", len(pers["graduatoria"]) == 8 and pers["programmati"][0]["nome"] == "Baietti")
r, _ = j("/api/personale/uscita", {"pos": 8, "data": "2026-12-15"})
r2, c2 = j("/api/personale/uscita", {"pos": 8, "data": "2026-10-01"})
check("uscita", r["ok"] and c2 == 400 and "passato" in r2["errore"])
r, c = j("/api/personale/ingresso", {"pos": 4, "nome": "Famà", "data": "2027-01-11"})
check("ingresso di chi e' gia' programmato rifiutato", c == 400)
r, _ = j("/api/personale/ingresso", {"pos": 4, "nome": "Alinari M.", "data": "2027-01-11"})
pers, _ = j("/api/personale")
check("ingresso da graduatoria", r["ok"] and "Alinari M." not in pers["graduatoria"] and any(p["tipo"] == "ingresso" and p["nome"] == "Alinari M." for p in pers["programmati"]))
r, _ = j("/api/personale/annulla_ingresso", {"pos": 4, "data": "2027-01-11"})
r, _ = j("/api/personale/annulla_uscita", {"pos": 8})
r, _ = j("/api/personale/aggiungi", {"nome": "Rossi", "posto": 1})
check("graduatoria aggiungi", j("/api/personale")[0]["graduatoria"][0] == "Rossi")
j("/api/personale/togli", {"nome": "Rossi"})
# anagrafica
an_, _ = j("/api/anagrafica?data=2026-10-24")
check("anagrafica letta", len(an_["turni"]) == 9 and "Feriale" in an_["sussidiari"] and "Feriale" in an_["disponibilita"])
orari = {"Feriale": ["04:55", "11:33"], "Sabato": ["05:07", "11:45"], "Domenica": ["05:07", "11:45"]}
w0, _ = j("/api/settimana?anno=2026&nn=45")
r, _ = j("/api/anagrafica/turno", {"codice": "603", "orari": orari, "dal": "2026-11-02"})
check("anagrafica: orari turno", r["ok"] and j("/api/anagrafica?data=2026-11-02")[0]["turni"][0]["orari"]["Feriale"] == ["04:55", "11:33"]
      and j("/api/anagrafica?data=2026-11-01")[0]["turni"][0]["orari"]["Feriale"] == ["04:50", "11:28"])
righe = list(reversed(an_["sussidiari"]["Feriale"]))
r, _ = j("/api/anagrafica/sussidiari", {"chiave": "Feriale", "righe": righe, "dal": "2026-11-09"})
check("anagrafica: sussidiari", r["ok"] and [x["codice"] for x in j("/api/anagrafica?data=2026-11-09")[0]["sussidiari"]["Feriale"]] == [x["codice"] for x in righe])
r, c = j("/api/anagrafica/sussidiari", {"chiave": "Feriale", "righe": righe, "dal": "2026-10-01"})
check("anagrafica: passato rifiutato", c == 400)
r, c = j("/api/anagrafica/turno", {"codice": "603", "orari": {"Feriale": ["99:00", "11:33"]}, "dal": "2026-12-01"})
check("anagrafica: orario errato", c == 400)
r, c = j("/api/anagrafica/turno", {"codice": "603", "orari": orari})
check("anagrafica: manca la data", c == 400)
pr = j("/api/anagrafica?data=2026-10-24")[0]["programmate"]
check("anagrafica: programmate", pr == ["2026-11-02", "2026-11-09"])
r, _ = j("/api/anagrafica/elimina", {"dal": "2026-11-09"})
check("anagrafica: elimina", j("/api/anagrafica?data=2026-10-24")[0]["programmate"] == ["2026-11-02"])
# importazione settimane (file dei colleghi)
import io, openpyxl
from openpyxl.styles import PatternFill
rot, _ = get("/api/esporta/rotazione?anno=2026")
wbc = openpyxl.load_workbook(io.BytesIO(rot), keep_vba=True)
wsc = wbc["2026"]
# cella di dicembre ancora senza colore e con turno, in un giorno senza assegnazioni
from dct.operazioni import Operazioni as _Op
_op = _Op(P.arch)
_occ = {x.data for x in P.arch.assegnazioni}
gg, pp = next((g, q) for g in range(1, 32) for q in range(1, 15)
              if date(2026, 12, g) not in _occ and _op.tipo(date(2026, 12, g), q) == ""
              and not _op.vuota(date(2026, 12, g), q) and _op.val(date(2026, 12, g), q) != "R")
r0, c0 = 3 + (12 - 10) * 19 + 2 + pp, 3 + gg        # dicembre, posizione pp, giorno gg
vecchio = wsc.cell(r0, c0).fill.fgColor.rgb
wsc.cell(r0, c0).fill = PatternFill("solid", fgColor="FFFFFF00")
buf = io.BytesIO(); wbc.save(buf)
rich = urllib.request.Request(base + "/api/import/analizza?anno=2026&da=%d&a=%d&nome=coll.xlsm" % ((date(2026, 12, gg).isocalendar()[1],) * 2), data=buf.getvalue())
with urllib.request.urlopen(rich) as rr:
    an_ = json.loads(rr.read())
check("import: anteprima", an_["riepilogo"]["APPLICA"] == 1 and an_["righe"][0]["data"] == "2026-12-%02d" % gg and an_["righe"][0]["nuovo"] == "Cong./Fest.", an_["riepilogo"])
r, _ = j("/api/import/applica", {})
check("import: applicato", r["ok"] and r["colori"] == 1)
check("import: cella cambiata", j("/api/anno?anno=2026&mese=12")[0]["righe"][pp - 1]["celle"][gg - 1]["t"] == "CONG_FEST")
r, c = j("/api/import/applica", {})
check("import: niente da applicare", c == 400)
rich = urllib.request.Request(base + "/api/import/analizza?anno=2026&da=49&a=49", data=b"non e' un file excel")
try:
    urllib.request.urlopen(rich); check("import: file non valido", False)
except urllib.error.HTTPError as e:
    check("import: file non valido", e.code == 400)
r, c = j("/api/import/analizza?anno=2026&da=5&a=1", b"x")
check("import: intervallo errato", c == 400)
# RL
rl_, _ = j("/api/rl?anno=2026")
_rl = sorted((x for x in P.arch.assegnazioni if x.tipo == "RL" and x.data.year == 2026), key=lambda x: (x.data, x.pos))
check("rl: elenco", _rl and rl_["totale"] == len(_rl) and rl_["righe"][0]["data"] == _rl[0].data.isoformat()
      and rl_["righe"][0]["nome"] == P.mot.chi_in_servizio(_rl[0].pos, _rl[0].data) and rl_["righe"][0]["turno"] == _rl[0].turno, (rl_["totale"], len(_rl)))
check("rl: riepilogo", sum(x["n"] for x in rl_["mesi"]) == len(_rl) and rl_["mesi"][0]["mese"] == _rl[0].data.month
      and sum(x["n"] for x in rl_["colleghi"]) == len(_rl))
f, h = get("/api/esporta/rl?anno=2026")
wbr = openpyxl.load_workbook(io.BytesIO(f))
check("rl: esporta", f[:2] == b"PK" and wbr.active.title == "RL_2026" and wbr.active["C4"].value == rl_["righe"][0]["nome"])
# note della settimana
n44 = len(j("/api/settimana?anno=2026&nn=44")[0]["note"])
j("/api/nota", {"data": "2026-10-28", "pos": 3, "testo": "Autore:\nCambio con il collega"})
w44, _ = j("/api/settimana?anno=2026&nn=44")
check("settimana: note", len(w44["note"]) == n44 + 1 and any(x["giorno"] == "mer 28/10" and x["testo"] == "Cambio con il collega" for x in w44["note"])
      and "regole" not in w44, w44["note"])
j("/api/nota", {"data": "2026-10-28", "pos": 3, "testo": ""})
check("pagina regole tolta", j("/api/regole")[1] == 400)
# nuova importazione con l'archivio aperto (su Windows un file aperto non si puo' sostituire)
s, _ = j("/api/importa", open(XLSM, "rb").read())
check("reimportazione con archivio aperto", s.get("aperto") and any(f.startswith("prima_importazione_") for f in os.listdir(os.path.join(P.cartella, "backup"))), s)
check("stato: programma e cartella", s.get("programma") == "Vestizione DCT" and s.get("cartella") == os.path.abspath(P.cartella))
print("   prove riuscite: %d, fallite: %d" % (OK, KO))
sys.exit(1 if KO else 0)
