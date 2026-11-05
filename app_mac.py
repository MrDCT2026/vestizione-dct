"""Vestizione DCT come app: finestra propria (pywebview) oppure, se non disponibile, il browser."""
import os
import sys
import threading
import time
import webbrowser


def _log():
    """Nell'app senza Terminale scrive i messaggi in ~/VestizioneDCT/app.log."""
    cartella = os.path.join(os.path.expanduser("~"), "VestizioneDCT")
    os.makedirs(cartella, exist_ok=True)
    f = open(os.path.join(cartella, "app.log"), "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = f
    print("\n--- avvio", time.strftime("%d/%m/%Y %H:%M:%S"))


def main():
    if getattr(sys, "frozen", False) or sys.stdout is None:
        _log()
    from dct.app.server import prepara
    r = prepara()
    if r is None:
        print("Nessuna porta libera.")
        return
    server, porta, cartella = r
    url = "http://127.0.0.1:%d" % porta
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Server su", url, "- dati in", cartella)

    finestra = "--browser" not in sys.argv
    if finestra:
        try:
            import webview
            try:
                webview.settings["ALLOW_DOWNLOADS"] = True
            except Exception:
                pass
            webview.create_window("Vestizione servizio DCT", url, width=1440, height=900, min_size=(1000, 650))
            webview.start()
            print("Finestra chiusa.")
            server.shutdown()
            return
        except Exception as e:
            print("Finestra propria non disponibile (%s): uso il browser." % e)
    webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
