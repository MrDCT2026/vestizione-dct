"""Avvia Vestizione DCT: python3 avvia.py [--rete] [--porta 8765] [--cartella PERCORSO]"""
import argparse
from dct.app.server import avvia

p = argparse.ArgumentParser()
p.add_argument("--rete", action="store_true", help="consente l'accesso dall'iPad sulla stessa rete Wi-Fi")
p.add_argument("--porta", type=int, default=8765)
p.add_argument("--cartella", default=None, help="dove tenere archivio e copie di sicurezza")
p.add_argument("--senza-browser", action="store_true")
a = p.parse_args()
avvia(a.cartella, a.porta, a.rete, not a.senza_browser)
