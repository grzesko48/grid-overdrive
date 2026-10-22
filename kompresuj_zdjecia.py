#!/usr/bin/env python3
"""Zmniejsza zdjęcia w images/*.json (JPEG do 480 px, jakość 74, progresywny), żeby baza mogła rosnąć.

Dlaczego: artefakt w aplikacji ma twardy limit 16 MB, a prawie cały rozmiar strony to zdjęcia
(base64). Przy 520 px / jakość 80 mieściło się jeszcze ok. 15 nowych produktów; po kompresji
kilkadziesiąt razy więcej, więc automat może dopisywać nowe pozycje miesiącami.
Skrypt jest idempotentny: przepisuje zdjęcie tylko wtedy, gdy wynik jest o >10% mniejszy.
Pliki spoza JPEG (SVG, WebP) zostają nietknięte.
"""
import base64, io, json, os, sys
from PIL import Image

BAZA = os.path.dirname(os.path.abspath(__file__))
MAX_PX, JAKOSC = 480, 74


def zakoduj(im):
    im = im.convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=JAKOSC, optimize=True, progressive=True)
    return b.getvalue()


def main():
    suma0 = suma1 = 0
    for nazwa in ("monitors.json", "pcs.json"):
        sciezka = os.path.join(BAZA, "images", nazwa)
        d = json.load(open(sciezka, encoding="utf-8"))
        zmienione = 0
        for k, v in d.items():
            glowa, b64 = v.split(",", 1)
            surowe = base64.b64decode(b64)
            suma0 += len(surowe)
            if "jpeg" in glowa:
                try:
                    nowe = zakoduj(Image.open(io.BytesIO(surowe)))
                except Exception:
                    nowe = None
                if nowe is not None and len(nowe) < 0.9 * len(surowe):
                    d[k] = glowa + "," + base64.b64encode(nowe).decode()
                    surowe = nowe
                    zmienione += 1
            suma1 += len(surowe)
        open(sciezka, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
        print(f"{nazwa}: przepisano {zmienione} z {len(d)} zdjęć")
    print(f"razem {suma0/1e6:.2f} MB → {suma1/1e6:.2f} MB")


if __name__ == "__main__":
    main()
