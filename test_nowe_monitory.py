#!/usr/bin/env python3
"""Test kontrolny nowe_monitory.py na zapisanych stronach produktów (bez sieci).

Sprawdza to, co przy dopisywaniu monitorów może zepsuć stronę po cichu:
  1. dane z karty produktu → wpis (przekątna, Hz, matryca, cena, zdjęcie, nazwa),
  2. odrzucenia: za duża przekątna, brak w sprzedaży, nazwa-opis zamiast modelu,
  3. rozpoznanie duplikatu (ten sam model pod inną nazwą, wariant z inną końcówką to NIE duplikat),
  4. wpis wstawiony do szablonu daje się wczytać przez zbieraj_ceny.wczytaj (a więc dostaje
     ceny z automatu) i nie zmienia liczby ani treści pozostałych wpisów,
  5. oceny: tylko perf i value — bez overall/image/features (brak zgadywania).
"""
import json, os, re, sys

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import nowe_monitory as nm
import zbieraj_ceny as z
from ocena_pc import BrakDanych

F = os.path.join(BAZA, "tests_fixtures")
bledy = []


def czytaj(n):
    return open(os.path.join(F, n + ".html"), encoding="utf-8").read()


def oczekuj(warunek, opis):
    if not warunek:
        bledy.append(opis)
        print("  BŁĄD:", opis)


# 1. poprawna karta
u = "https://www.morele.net/monitor-asus-rog-strix-woled-xg27aqdmgr-90lm0cc0-b01171-15625114/"
d = nm.odczytaj(u, czytaj("morele_asus_xg27aqdmgr"))
oczekuj(d["nazwa"] == "ASUS ROG Strix WOLED XG27AQDMGR", f"nazwa: {d['nazwa']!r}")
oczekuj(d["hz"] == 240 and d["diag"] == 26.5, f"hz/diag: {d['hz']} {d['diag']}")
oczekuj((d["panelName"], d["panel"]) == ("OLED (WOLED)", "oled"), f"matryca: {d['panelName']}")
oczekuj(isinstance(d["cena"], int) and 500 <= d["cena"] <= 6000, f"cena: {d['cena']}")
oczekuj(d["zdjecie"].startswith("http"), f"zdjęcie: {d['zdjecie']!r}")

e = nm.wpis(d, nm.klucz_zdjecia(63, d["nazwa"]))
oczekuj(set(e["scores"]) == {"perf", "value"}, f"oceny nowego monitora: {sorted(e['scores'])}")
oczekuj(e["scores"]["perf"] == 60, f"perf 240 Hz = 60, jest {e['scores']['perf']}")
oczekuj(e["diag"] == '26,5"', f"zapis przekątnej: {e['diag']}")
oczekuj(e["img"] == "63_asus_rog_strix_woled_xg27a", f"klucz zdjęcia: {e['img']}")

# 2. odrzucenia
for plik, adres, fragment in [
    ("morele_samsung_32", "https://www.morele.net/monitor-samsung-odyssey-g6-ls32bg650euxen-10399420/", "przekątna"),
]:
    try:
        nm.odczytaj(adres, czytaj(plik)); oczekuj(False, f"{plik}: powinno być odrzucone")
    except BrakDanych as x:
        oczekuj(fragment in str(x), f"{plik}: powód {x}")

# nazwa-opis (sklep wkleił specyfikację do tytułu) → marka + model, nie cały opis
g = nm.odczytaj("https://www.morele.net/gigabyte-g27q3/", czytaj("morele_gigabyte_g27q3"))
oczekuj(len(g["nazwa"]) <= 40 and '"' not in g["nazwa"], f"nazwa-opis nie została skrócona: {g['nazwa']!r}")

# 3. duplikaty
katalog = ["MSI MAG 272QP QD-OLED X24", "Gigabyte GO27Q24", "Philips Evnia 27M2N8500/00",
           "Samsung Odyssey G6 LS27BG650EUXEN"]
oczekuj(nm.juz_jest("MSI MAG 272QP QD-OLED X24", katalog, set(), "https://www.morele.net/x-15790413/"),
        "ten sam model nie został rozpoznany jako duplikat")
oczekuj(nm.juz_jest("Gigabyte GO27Q24A", katalog, set(), "https://www.morele.net/y-1/") is None,
        "wariant GO27Q24A błędnie uznany za duplikat GO27Q24")
oczekuj(nm.juz_jest("MSI MAG 272QP QD-OLED X28", katalog, set(), "https://www.morele.net/z-2/") is None,
        "wariant X28 błędnie uznany za duplikat X24")
oczekuj(nm.juz_jest("Philips Evnia 27M2N8500", katalog, set(), "https://www.morele.net/w-3/"),
        "model bez końcówki /00 nie został rozpoznany")
oczekuj(nm.juz_jest("Cokolwiek 99X", [], {"15790413"}, "https://www.morele.net/a-15790413/"),
        "adres Morele z katalogu nie został rozpoznany")

# 4. wstawienie do szablonu (wpis testowy o nazwie, której w danych nie ma — automat mógł już
# dopisać prawdziwy monitor z fixtury)
d = dict(d, nazwa="Testowy ZZ9999 QD", url="https://www.morele.net/monitor-testowy-zz9999-99999999/")
e = nm.wpis(d, nm.klucz_zdjecia(999, d["nazwa"]))
u = d["url"]
sz = open(os.path.join(BAZA, "monitors_1700_template.html"), encoding="utf-8").read()
przed = z.wczytaj(sz)
nowy = nm.wstaw(sz, [e])
po = z.wczytaj(nowy)
oczekuj(len(po) == len(przed) + 1, f"liczba wpisów {len(przed)} → {len(po)}, miało być +1")
oczekuj([p["name"] for p in po if p["name"] != d["nazwa"]] == [p["name"] for p in przed], "zmieniła się kolejność/treść wcześniejszych wpisów")
nowe = [p for p in po if p["name"] == d["nazwa"]]
oczekuj(len(nowe) == 1 and nowe[0]["rodzaj"] == "monitor", "nowy wpis nie jest czytany jako monitor")
if nowe:
    oczekuj(nowe[0]["urls"].get("morele") == u, f"adres Morele nowego wpisu: {nowe[0]['urls']}")
oczekuj(nowy.index("name:'" + d["nazwa"] + "'") < nowy.index("var PDATA"),
        "wpis wylądował poza tablicą monitorów")
# składnia JS: nawiasy i cudzysłowy wpisu
w = nm.wpis_js(e)
oczekuj(w.count("{") == w.count("}") and w.count("[") == w.count("]"), "niezbilansowane nawiasy we wpisie JS")

print("\nTEST ZALICZONY" if not bledy else f"\nTEST NIEZALICZONY: {len(bledy)} błędów")
sys.exit(1 if bledy else 0)
