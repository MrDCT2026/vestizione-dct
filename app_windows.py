"""Vestizione DCT per Windows (anche da scheda SD o chiavetta).

Due modi di partire, stesso programma:
  - app (VestizioneDCT.exe, costruita con PyInstaller): finestra propria (Edge WebView2);
  - portatile (Avvia_Vestizione_DCT.bat): Python ufficiale + questo file, si apre in Edge.

I dati stanno nella cartella Dati_VestizioneDCT accanto alla cartella del programma
(sulla scheda SD: nella scheda stessa), senza lettere di unita' fisse.
Si puo' indicare un'altra cartella con --cartella PERCORSO.

Opzioni: --browser (niente finestra propria)  --senza-apertura (solo server, per le prove)
         --cartella PERCORSO  --porta 8765
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

NOME_DATI = "Dati_VestizioneDCT"
PORTA = 8765


def cartella_programma():
    """Cartella che contiene il programma (quella dell'exe, oppure quella con avvia/app_windows.py)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def cartella_dati_predefinita():
    """Dati_VestizioneDCT nella cartella che contiene le cartelle del programma (la "radice"):
    App:       <radice>\\Vestizione_DCT_App\\VestizioneDCT.exe               -> <radice>\\Dati_VestizioneDCT
    Portatile: <radice>\\Vestizione_DCT_Portatile\\programma\\app_windows.py -> <radice>\\Dati_VestizioneDCT
    La radice puo' essere la scheda SD o una qualsiasi cartella: i dati seguono il programma."""
    qui = cartella_programma()
    radice = os.path.dirname(qui)
    if os.path.basename(qui).lower() == "programma":          # versione portatile: programma\ dentro Vestizione_DCT_Portatile\
        radice = os.path.dirname(radice)
    return os.path.join(radice, NOME_DATI)


def _log(cartella):
    """Senza finestra di comando (app) i messaggi vanno in app.log nella cartella dati."""
    f = open(os.path.join(cartella, "app.log"), "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = f
    print("\n--- avvio", time.strftime("%d/%m/%Y %H:%M:%S"))


def gia_aperto(cartella, porta=PORTA):
    """Se Vestizione DCT e' gia' in funzione sugli stessi dati, ne restituisce l'indirizzo."""
    voluta = os.path.normcase(os.path.abspath(cartella))
    for p in range(porta, porta + 20):
        url = "http://127.0.0.1:%d" % p
        try:
            with urllib.request.urlopen(url + "/api/stato", timeout=0.4) as r:
                s = json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
        if s.get("programma") == "Vestizione DCT" and os.path.normcase(s.get("cartella", "")) == voluta:
            return url
    return None


def apri_in_edge(url):
    """Apre l'indirizzo in Edge come finestra senza schede; se non riesce, nel browser predefinito."""
    if os.name == "nt":
        try:
            subprocess.Popen('start "" msedge --app=%s' % url, shell=True)
            return
        except Exception as e:
            print("Edge non disponibile (%s): uso il browser predefinito." % e)
    webbrowser.open(url)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--cartella", default=None)
    p.add_argument("--porta", type=int, default=PORTA)
    p.add_argument("--browser", action="store_true")
    p.add_argument("--senza-apertura", action="store_true")
    a = p.parse_args(argv)

    cartella = os.path.abspath(a.cartella or cartella_dati_predefinita())
    os.makedirs(cartella, exist_ok=True)
    if sys.stdout is None or getattr(sys, "frozen", False):
        _log(cartella)

    url = gia_aperto(cartella, a.porta)
    if url:
        print("Gia' aperto su", url, ": lo riapro.")
        if not a.senza_apertura:
            apri_in_edge(url)
        return 0

    from dct.app.server import prepara
    r = prepara(cartella, a.porta)
    if r is None:
        print("Nessuna porta libera.")
        return 1
    server, porta, cartella = r
    url = "http://127.0.0.1:%d" % porta
    print("Vestizione DCT in funzione:", url)
    print("Dati in:", cartella)

    if a.senza_apertura:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0

    if not a.browser:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            import webview
            try:
                webview.settings["ALLOW_DOWNLOADS"] = True
            except Exception:
                pass
            webview.create_window("Vestizione servizio DCT", url, width=1440, height=900, min_size=(1000, 650))
            # i file della finestra (WebView2) restano nella cartella dati, non nel profilo dell'utente
            try:
                webview.start(private_mode=True, storage_path=os.path.join(cartella, "finestra"))
            except TypeError:
                webview.start()
            print("Finestra chiusa.")
            server.shutdown()
            return 0
        except Exception as e:
            print("Finestra propria non disponibile (%s): uso Edge." % e)
        apri_in_edge(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    # versione portatile: il programma resta acceso finche' e' aperta la finestra nera
    print()
    print("Il programma si apre in Edge. Se hai chiuso Edge, fai di nuovo doppio clic su Avvia.")
    print("PER CHIUDERE IL PROGRAMMA: chiudi questa finestra (dopo aver finito di lavorare).")
    apri_in_edge(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
