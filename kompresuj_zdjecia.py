#!/usr/bin/env python3
"""Zmniejsza zdjęcia w images/*.json (WebP do 400 px, jakość 62), żeby baza mogła rosnąć.

Dlaczego: artefakt w aplikacji ma twardy limit 16 MB, a prawie cały rozmiar strony to zdjęcia
(base64). Parametry są te same co przy dopisywaniu nowych produktów (zdjecie_obraz.py).
Skrypt jest idempotentny: przepisuje zdjęcie tylko wtedy, gdy wynik jest o >10% mniejszy.
Pliki spoza JPEG/WebP (SVG) zostają nietknięte.
"""
import base64, io, json, os

from zdjecie_obraz import JAKOSC, MAX_PX, pil_image

BAZA = os.path.dirname(os.path.abspath(__file__))


def zakoduj(im):
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        tlo = pil_image().new("RGB", im.size, (255, 255, 255))
        tlo.paste(im, mask=im.split()[-1])
        im = tlo
    im = im.convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    b = io.BytesIO()
    im.save(b, "WEBP", quality=JAKOSC, method=6)
    return b.getvalue()


def main():
    Image = pil_image()
    suma0 = suma1 = 0
    for nazwa in ("monitors.json", "pcs.json"):
        sciezka = os.path.join(BAZA, "images", nazwa)
        d = json.load(open(sciezka, encoding="utf-8"))
        zmienione = bledy = 0
        for k, v in d.items():
            glowa, b64 = v.split(",", 1)
            surowe = base64.b64decode(b64)
            suma0 += len(surowe)
            if "jpeg" in glowa or "webp" in glowa:
                try:
                    nowe = zakoduj(Image.open(io.BytesIO(surowe)))
                except Exception:
                    nowe, bledy = None, bledy + 1
                if nowe is not None and len(nowe) < 0.9 * len(surowe):
                    d[k] = "data:image/webp;base64," + base64.b64encode(nowe).decode()
                    surowe = nowe
                    zmienione += 1
            suma1 += len(surowe)
        open(sciezka, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
        print(f"{nazwa}: przepisano {zmienione} z {len(d)} zdjęć, błędów dekodowania {bledy}")
    print(f"razem {suma0/1e6:.2f} MB → {suma1/1e6:.2f} MB")


if __name__ == "__main__":
    main()
