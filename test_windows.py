"""Prove dell'avvio Windows (girano anche su Mac/Linux).

  python test_windows.py                      prova app_windows.py con questo Python
  python test_windows.py COMANDO [ARGOMENTI]  prova un avvio gia' costruito, es.:
      python test_windows.py dist\\Vestizione_DCT_App\\VestizioneDCT.exe
      python test_windows.py SD\\Vestizione_DCT_Portatile\\python\\python.exe SD\\Vestizione_DCT_Portatile\\programma\\app_windows.py
Il programma viene avviato con --senza-apertura su una cartella dati di prova, poi si controllano le pagine.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

QUI = os.path.dirname(os.path.abspath(__file__))
OK = KO = 0


def check(nome, cond, extra=""):
    global OK, KO
    if cond:
        OK += 1
    else:
        KO += 1
        print("  FALLITO:", nome, extra)


def leggi(url, timeout=2):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read()


def aspetta(url, secondi=60):
    fine = time.time() + secondi
    while time.time() < fine:
        try:
            return json.loads(leggi(url + "/api/stato")[1].decode("utf-8"))
        except Exception:
            time.sleep(0.5)
    return None


# 1. dove finiscono i dati (senza lettere di unita')
sys.path.insert(0, QUI)
import app_windows as aw

t = tempfile.mkdtemp()
sd = os.path.join(t, "SD con spazi è")
for d in ("Vestizione_DCT_App", os.path.join("Vestizione_DCT_Portatile", "programma")):
    os.makedirs(os.path.join(sd, d))
originale = aw.cartella_programma
aw.cartella_programma = lambda: os.path.join(sd, "Vestizione_DCT_App")
check("app: dati accanto al programma", aw.cartella_dati_predefinita() == os.path.join(sd, "Dati_VestizioneDCT"), aw.cartella_dati_predefinita())
aw.cartella_programma = lambda: os.path.join(sd, "Vestizione_DCT_Portatile", "programma")
check("portatile: stessi dati dell'app", aw.cartella_dati_predefinita() == os.path.join(sd, "Dati_VestizioneDCT"), aw.cartella_dati_predefinita())
os.makedirs(os.path.join(t, "Dati_VestizioneDCT"))                     # un'altra cartella dati piu' in alto non conta
check("dati altrove ignorati", aw.cartella_dati_predefinita() == os.path.join(sd, "Dati_VestizioneDCT"))
aw.cartella_programma = originale

# 2. avvio vero
comando = sys.argv[1:] or [sys.executable, os.path.join(QUI, "app_windows.py")]
dati = os.path.join(t, "Dati prova àèì")
porta = 8790
args = comando + ["--senza-apertura", "--cartella", dati, "--porta", str(porta)]
pr = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
try:
    url = "http://127.0.0.1:%d" % porta
    s = aspetta(url)
    check("si avvia", s is not None)
    if s:
        check("e' Vestizione DCT", s.get("programma") == "Vestizione DCT")
        check("usa la cartella indicata", os.path.normcase(s.get("cartella", "")) == os.path.normcase(os.path.abspath(dati)), s.get("cartella"))
        check("senza archivio all'inizio", s.get("aperto") is False)
        c, html = leggi(url + "/")
        check("pagina principale", c == 200 and b"Vestizione" in html and b"v0.24" in html)
        c, js = leggi(url + "/app.js") if b'src="app.js"' in html else leggi(url + "/static/app.js")
        check("script della pagina", c == 200 and len(js) > 1000)
        check("cartella backup creata", os.path.isdir(os.path.join(dati, "backup")))
        # seconda apertura sugli stessi dati: non parte un secondo server
        t0 = time.time()
        r2 = subprocess.run(comando + ["--senza-apertura", "--cartella", dati, "--porta", str(porta)], capture_output=True, timeout=60)
        check("seconda apertura riusa la prima", r2.returncode == 0 and time.time() - t0 < 30)
        try:
            leggi("http://127.0.0.1:%d/api/stato" % (porta + 1), timeout=1)
            check("nessun secondo server", False)
        except Exception:
            check("nessun secondo server", True)
finally:
    pr.terminate()
    try:
        out = pr.communicate(timeout=10)[0]
    except Exception:
        pr.kill()
        out = pr.communicate()[0]
    if KO:
        print((out or b"").decode("utf-8", "replace"))
        log = os.path.join(dati, "app.log")
        if os.path.exists(log):
            print(open(log, encoding="utf-8").read())
shutil.rmtree(t, ignore_errors=True)
print("   prove riuscite: %d, fallite: %d" % (OK, KO))
sys.exit(1 if KO else 0)
