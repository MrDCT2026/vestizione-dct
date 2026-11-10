"""Esegue tutte le prove: python3 prove.py VESTIZIONE_DCT_15.xlsm [VESTIZIONE_DCT_19.xlsm]
Il primo file (v15) contiene gli scenari delle prove di funzionamento; il secondo, se c'e', serve per il confronto
con la macro su tutte le settimane che contiene (v19: 46-52, con 08/12, 13/12 e Natale)."""
import subprocess, sys
f = sys.argv[1]
ok = True
for script in ("test_generatore.py", "test_operazioni.py", "test_importa.py", "test_anagrafica.py", "test_settimana.py", "test_personale.py", "test_app.py"):
    r = subprocess.run([sys.executable, script, f], capture_output=True, text=True)
    print("%-22s %s" % (script, "OK" if r.returncode == 0 else "FALLITO"))
    print("   " + (r.stdout.strip().splitlines() or [""])[-1])
    if r.returncode:
        ok = False
        print(r.stdout, r.stderr)
# confronto con la macro: con un secondo file (es. VESTIZIONE_DCT_19.xlsm) tutte le settimane che contiene,
# altrimenti le settimane 43-45 del primo
if len(sys.argv) > 2:
    import openpyxl
    fm = sys.argv[2]
    _wb = openpyxl.load_workbook(fm, read_only=True, keep_vba=True)
    _sett = sorted({int(n.split("_")[2]) for n in _wb.sheetnames if n.startswith("Settimana_") and n.count("_") == 2})
    _wb.close()
else:
    fm, _sett = f, [43, 44, 45]
r = subprocess.run([sys.executable, "confronta.py", fm] + [str(n) for n in _sett], capture_output=True, text=True)
print(r.stdout.strip())
if r.returncode != 0 or "UGUALE" not in r.stdout or "diversi" in r.stdout:
    ok = False
    print("confronto con la macro FALLITO", r.stderr[-2000:])
sys.exit(0 if ok else 1)
