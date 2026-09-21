#!/usr/bin/env python3
"""Etap 3A pakietu naprawczego 3 — jednorazowa normalizacja "1000GB SSD" -> "1TB SSD".

Dlaczego istnieje: martwy skrypt `recheck/aktualizuj_pc.py` (17.09) liczył
storage_quality() tak, że "N TB" konwertował na N*1024 GB, ale "N GB" brał
dosłownie — więc "1000GB" (1000 < próg 1024) wpadało w niższy koszyk niż
"1TB" (1024 >= próg), mimo że to fizycznie ta sama pojemność dysku.
`pc_audit/build_all_pcs.py` NIE ma tej usterki — sprawdzone osobno.

Ten skrypt jest jednorazowy: nie wywołuje żadnego z martwych generatorów,
tylko patchuje monitors_1700_template.html bezpośrednio, dokładnie tak jak
robi to przelicz_oceny.py (segmentacja po granicach wpisów PDATA/DATA,
podmiana pól regexem wewnątrz jednego segmentu).

Zakres zmiany (świadomie wąski, zgodnie z PAKIET-NAPRAWCZY-3.md/ETAP 3A):
  - pole storage: "1000GB SSD" -> "1TB SSD" (fizycznie ta sama pojemność)
  - pole scores.components: +4, przycięte do 100 (min(100, components+4))
Pole `name` (tytuł karty) NIE jest tu ruszane celowo: `porownaj_rankingi.py`
paruje wpisy między commitami po dokładnym tekście `name` - zmiana nazwy
wyrzuciłaby te 13 wpisów z porównania "przed/po" zamiast pokazać ich
faktyczną zmianę oceny.
"""
import re

PLIK = "monitors_1700_template.html"


def main():
    src = open(PLIK, encoding="utf-8").read()
    i = src.index("var PDATA")
    koniec_bloku = i + re.search(r"\n\s*\];", src[i:]).start()
    przed = src[:i]
    blok = src[i:koniec_bloku]
    po = src[koniec_bloku:]

    poz = [m.start() for m in re.finditer(r"\{img:", blok)]
    prefiks = blok[:poz[0]]
    segs = []
    for k, s in enumerate(poz):
        stop = poz[k + 1] if k + 1 < len(poz) else len(blok)
        segs.append(blok[s:stop])

    zmienione = []
    for idx, seg in enumerate(segs):
        if 'storage:"1000GB SSD"' not in seg:
            continue

        sc = re.search(r"scores:\{([^}]*)\}", seg)
        if not sc:
            raise SystemExit(f"idx={idx}: brak scores{{}} — zatrzymuję się, nie zgaduję")
        scores_tresc = sc.group(1)
        m = re.search(r"\bcomponents:(\d+)", scores_tresc)
        if not m:
            raise SystemExit(f"idx={idx}: brak pola components — zatrzymuję się")
        stary = int(m.group(1))
        nowy = min(100, stary + 4)
        nowa_tresc = re.sub(r"\bcomponents:\d+", f"components:{nowy}", scores_tresc, count=1)
        seg = seg[:sc.start(1)] + nowa_tresc + seg[sc.end(1):]

        seg = seg.replace('storage:"1000GB SSD"', 'storage:"1TB SSD"', 1)

        nazwa = re.search(r'name:"([^"]*)"', seg).group(1)
        zmienione.append({"idx": idx, "nazwa": nazwa, "components_przed": stary, "components_po": nowy})
        segs[idx] = seg

    nowy_blok = prefiks + "".join(segs)
    wynik = przed + nowy_blok + po

    # test blokujacy: po zmianie zero wpisow ze storage=="1000GB SSD"
    if 'storage:"1000GB SSD"' in wynik:
        raise SystemExit("TEST NIE PRZESZEDL: po zmianie nadal istnieje storage==\"1000GB SSD\" — nie zapisuje")

    open(PLIK, "w", encoding="utf-8").write(wynik)

    print(f"zmienionych wpisow: {len(zmienione)}")
    for z in zmienione:
        znak = "bez zmiany (juz na suficie 100)" if z["components_po"] == z["components_przed"] else "+4"
        print(f"  idx={z['idx']:3d}  components {z['components_przed']:3d} -> {z['components_po']:3d}  ({znak})"
              f"  {z['nazwa']}")


if __name__ == "__main__":
    main()
