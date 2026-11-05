"""Esegue tutte le prove: python3 prove.py VESTIZIONE_DCT_15.xlsm"""
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
r = subprocess.run([sys.executable, "confronta.py", f, "44", "45", "46", "47"], capture_output=True, text=True)
print(r.stdout.strip())
sys.exit(0 if ok else 1)
