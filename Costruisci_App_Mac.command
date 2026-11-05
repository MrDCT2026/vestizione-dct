#!/bin/bash
# Costruisce l'app "Vestizione DCT" (finestra propria, doppio clic) sul tuo Mac.
# Serve Python 3 solo per costruirla; l'app costruita non lo richiede.
cd "$(dirname "$0")"
set -e
echo "1/5 Preparo l'ambiente..."
python3 -m venv .costruzione
source .costruzione/bin/activate
pip install --quiet --upgrade pip
pip install --quiet openpyxl lxml pywebview pyinstaller
echo "2/5 Preparo l'icona..."
rm -rf icona.iconset icona.icns
mkdir icona.iconset
for s in 16 32 128 256 512; do
  sips -z $s $s icona.png --out icona.iconset/icon_${s}x${s}.png > /dev/null
  d=$((s*2)); sips -z $d $d icona.png --out icona.iconset/icon_${s}x${s}@2x.png > /dev/null
done
iconutil -c icns icona.iconset -o icona.icns
echo "3/5 Costruisco l'app (qualche minuto)..."
rm -rf build dist
pyinstaller --noconfirm --clean --windowed --name "Vestizione DCT" \
  --icon icona.icns --osx-bundle-identifier it.brunoroli.vestizionedct \
  --add-data "dct/app/static:dct/app/static" \
  --add-data "modello:modello" \
  --collect-submodules dct --collect-all webview \
  app_mac.py > costruzione.log 2>&1 || { echo "ERRORE: guarda costruzione.log"; exit 1; }
echo "4/5 Preparo la cartella finale..."
rm -rf App_Vestizione_DCT
mkdir App_Vestizione_DCT
cp -R "dist/Vestizione DCT.app" App_Vestizione_DCT/
xattr -cr App_Vestizione_DCT 2>/dev/null || true
echo "5/5 Fatto."
echo "L'app e' in App_Vestizione_DCT: trascina 'Vestizione DCT' in Applicazioni."
echo "Prima volta: clic destro > Apri. I dati restano in ~/VestizioneDCT (messaggi in app.log)."
