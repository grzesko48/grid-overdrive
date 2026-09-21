#!/usr/bin/env python3
"""Etap 3B pakietu naprawczego 3 — pieciu wpisow z "brak danych" o dysku.

Jednorazowy skrypt. Wartosci ponizej sa wynikiem WLASNEGO pobrania surowego
HTML kazdej z 5 stron Hard-PC.pl (curl + User-Agent przegladarki, regex na
polu "Dysk SSD:" w tabeli specyfikacji) i reczengo porownania z premisa
PAKIET-NAPRAWCZY-3.md, ETAP 3B — NIE jest to bezposrednie przepisanie tabeli
z pakietu. Dla idx 292 wlasna kontrola dala INNY wynik niz zalecenie pakietu
(patrz komentarz przy tym wpisie) — zgloszone w raporcie, nie zgadywane.

Zasada z pakietu: components rusza sie TYLKO gdy w bazie istnieje realny
blizniak (ten sam cpu+gpu+ram+psu) z potwierdzona klasa dysku. W przeciwnym
razie zostaje bez zmian.
"""
import re

PLIK = "monitors_1700_template.html"

# idx -> (nowy_storage, nowy_components_lub_None, dopisany_cons_lub_None)
ZMIANY = {
    # Wlasne pobranie (curl, UA przegladarki) https://sklep.hard-pc.pl/p26430,...
    # potwierdzilo: "Dysk SSD Sandisk Green SN3000 1 TB M.2 PCIe Gen4 NVMe".
    # Blizniak (ten sam cpu+gpu+ram+psu) z potwierdzonym "1TB SSD" NIE istnieje
    # w bazie -> components zostaje bez zmian (81), zgodnie z zasada pakietu.
    60: {
        "storage_z": "SSD (pojemność brak w danych producenta)",
        "storage_na": "1TB SSD",
        "components_na": None,
        "dopisz_cons": None,
    },
    # Wlasne pobranie https://sklep.hard-pc.pl/p26383,... potwierdzilo wprost:
    # "Dysk SSD BRAK" — ten zestaw naprawde nie ma nosnika. components bez
    # zmian (nie mamy formuly, patrz Pakiet 2/Etap 5); dopisujemy uczciwa
    # wzmianke do cons[], ktorej dotad brakowalo.
    194: {
        "storage_z": "SSD (pojemność brak w danych producenta)",
        "storage_na": "SSD: brak (potwierdzone przez sklep)",
        "components_na": None,
        "dopisz_cons": "Brak dysku SSD w zestawie (potwierdzone przez sklep) — trzeba dokupić go osobno.",
    },
    # Wlasne pobranie https://sklep.hard-pc.pl/p26399,... potwierdzilo wprost:
    # "Dysk SSD BRAK" — jak wyzej.
    275: {
        "storage_z": "SSD (pojemność brak w danych producenta)",
        "storage_na": "SSD: brak (potwierdzone przez sklep)",
        "components_na": None,
        "dopisz_cons": "Brak dysku SSD w zestawie (potwierdzone przez sklep) — trzeba dokupić go osobno.",
    },
    # Wlasne pobranie https://sklep.hard-pc.pl/p22421,... potwierdzilo:
    # "Dysk SSD Patriot 1TB Viper P400 Lite". Blizniak (ten sam
    # cpu+gpu+ram+psu) istnieje: idx 276, storage "1TB SSD", components=100
    # -> przypisujemy te sama wartosc, bez rekonstrukcji formuly.
    280: {
        "storage_z": "SSD (pojemność brak w danych producenta)",
        "storage_na": "1TB SSD",
        "components_na": 100,
        "dopisz_cons": None,
    },
    # UWAGA — ROZBIEZNOSC Z PAKIETEM, rozstrzygnieta wlasna kontrola:
    # Pakiet twierdzil, ze urls.hardpc tego wpisu wskazuje na INNY produkt
    # (rzekomo p20880, Ryzen 5 7500F+RTX 5060 8GB+850W) i kazal podmienic URL
    # na p20836 (2TB SSD, 850W, 9849 zl). Wlasne pobranie OBU stron pokazalo:
    #   - urls.hardpc w naszych danych to w rzeczywistosci p26222, NIE p20880
    #     -- tytul strony p26222 to doslownie "Ryzen 7 7800X3D, RTX 5070 12GB,
    #     32GB DDR5, 750W, Hunter 3" (identyczne cpu/gpu/ram/psu jak w danych),
    #     a cena na tej stronie to 8 729 zl == nasze priceBare co do zlotowki.
    #     Ten URL jest wiec juz PRAWIDLOWY, nie zamieniamy go.
    #   - p20836 (URL rekomendowany przez pakiet) to w rzeczywistosci WARIANT
    #     850W/2TB SSD za 9 849 zl -- INNY produkt niz nasz wpis (750W,
    #     priceBare 8729 zl). Podmiana urls.hardpc na p20836 wprowadzilaby
    #     dokladnie ten sam blad, ktory pakiet mial naprawic (URL niezgodny
    #     ze specyfikacja wpisu).
    #   - Prawdziwa strona p26222 (ta juz podpieta w danych) mowi wprost:
    #     "Dysk SSD BRAK" -- czyli realny problem tego wpisu jest identyczny
    #     jak przy idx 194/275 (brak nosnika), nie zla pojemnosc/zly URL.
    # Traktujemy wiec ten wpis jak 194/275: storage + cons, URL i ceny BEZ
    # zmian. Pelny opis w raporcie kierownika.
    292: {
        "storage_z": "SSD (pojemność brak w danych producenta)",
        "storage_na": "SSD: brak (potwierdzone przez sklep)",
        "components_na": None,
        "dopisz_cons": "Brak dysku SSD w zestawie (potwierdzone przez sklep) — trzeba dokupić go osobno.",
    },
}


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

    raport = []
    for idx, zm in sorted(ZMIANY.items()):
        seg = segs[idx]
        nazwa = re.search(r'name:"([^"]*)"', seg).group(1)

        pole_storage = f'storage:"{zm["storage_z"]}"'
        if pole_storage not in seg:
            raise SystemExit(f"idx={idx}: nie znaleziono storage={zm['storage_z']!r} — zatrzymuję się")
        seg = seg.replace(pole_storage, f'storage:"{zm["storage_na"]}"', 1)

        stary_comp = int(re.search(r"components:(\d+)", seg).group(1))
        nowy_comp = zm["components_na"] if zm["components_na"] is not None else stary_comp
        if nowy_comp != stary_comp:
            sc = re.search(r"scores:\{([^}]*)\}", seg)
            tresc = re.sub(r"\bcomponents:\d+", f"components:{nowy_comp}", sc.group(1), count=1)
            seg = seg[:sc.start(1)] + tresc + seg[sc.end(1):]

        if zm["dopisz_cons"]:
            m = re.search(r"cons:\[(.*?)\]", seg)
            if not m:
                raise SystemExit(f"idx={idx}: brak pola cons[] — zatrzymuję się")
            if zm["dopisz_cons"] in m.group(1):
                pass  # juz jest, nic nie rob
            else:
                nowa_tresc = m.group(1) + f',"{zm["dopisz_cons"]}"'
                seg = seg[:m.start(1)] + nowa_tresc + seg[m.end(1):]

        segs[idx] = seg
        raport.append({
            "idx": idx, "nazwa": nazwa,
            "storage": f'{zm["storage_z"]!r} -> {zm["storage_na"]!r}',
            "components": f"{stary_comp} -> {nowy_comp}" + ("" if nowy_comp != stary_comp else " (bez zmian)"),
            "cons_dopisany": zm["dopisz_cons"],
        })

    nowy_blok = prefiks + "".join(segs)
    wynik = przed + nowy_blok + po
    open(PLIK, "w", encoding="utf-8").write(wynik)

    for r in raport:
        print(f"idx={r['idx']:3d}  {r['nazwa']}")
        print(f"    storage: {r['storage']}")
        print(f"    components: {r['components']}")
        if r["cons_dopisany"]:
            print(f"    cons += {r['cons_dopisany']!r}")


if __name__ == "__main__":
    main()
