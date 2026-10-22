#!/usr/bin/env python3
"""Test nowe_pc.py na zapisanych stronach Hard-PC (bez sieci).

Najmocniejszy test: zestaw zbudowany OD ZERA ze strony produktu musi mieć te same oceny,
tekst i pola co ten sam zestaw, który jest już na stronie (dopisany ręcznie/starym kodem).
Kod wyjścia 0 = zaliczony."""
import os, re, sys
BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import nowe_pc as n
import ocena_pc
from ocena_pc import BrakDanych
import zbieraj_ceny as z

F = lambda nazwa: open(os.path.join(BAZA, "tests_fixtures", nazwa), encoding="utf-8").read()
bledy = []
def ok(warunek, opis):
    if not warunek:
        bledy.append(opis)

# --- tytuł
t = n.rozbierz_tytul("Zestaw | Ryzen 5 9500F, RTX 5060 8GB, 16GB DDR5, 500GB SSD, 650W, Hunter 2")
ok(t["cpu"] == "Ryzen 5 9500F" and t["gpu"] == "RTX 5060 8GB" and t["ram"] == "16GB DDR5"
   and t["dysk"] == "500GB SSD" and t["psu"] == "650W" and t["obudowa"] == ["Hunter 2"], f"tytuł: {t}")
t2 = n.rozbierz_tytul("Zestaw | Ryzen 5 9500F, RTX 5060 Ti 16GB, 32GB DDR5, 750W, Signum 300 ARGB")
ok(t2["dysk"] is None and t2["psu"] == "750W", f"tytuł bez dysku: {t2}")
for zly in ("Laptop Dream Machines Ryzen 7", "Zestaw | Ryzen 5 9500F, 650W, Hunter 2"):
    try:
        n.rozbierz_tytul(zly); ok(False, f"powinien odrzucić: {zly}")
    except BrakDanych:
        pass

# --- zestaw już obecny na stronie: nowy kod daje TO SAMO
sz = open(n.SZABLON, encoding="utf-8").read()
istn = {p["name"]: p for p in z.wczytaj(sz)}
def pole(seg, nazwa):
    m = re.search(rf'(?<![A-Za-z]){nazwa}:"([^"]*)"', seg); return m.group(1) if m else None
url = "https://sklep.hard-pc.pl/p22785,zestaw-ryzen-5-9500f-rtx-5060-8gb-16gb-ddr5-500gb-ssd-650w-hunter-2.html"
s = F("hardpc_pelna_p22785.html")
wpisy = n.zloz_wpisy(url, s, None, set(), "pcimg_test")
ok(len(wpisy) == 2, f"oczekiwano bazy i wariantu 32GB, jest {len(wpisy)}")
for w in wpisy:
    tw = istn.get(w["name"])
    ok(tw is not None, f"brak na stronie zestawu o nazwie {w['name'][:50]}")
    if not tw:
        continue
    seg = sz[tw["start"]: tw["start"] + 4000]
    sc = {a: int(b) for a, b in re.findall(r"(\w+):(\d+)", re.search(r"scores:\{([^}]*)\}", seg).group(1))}
    ok(w["scores"] == sc, f"{w['name'][-30:]}: oceny {w['scores']} ≠ strona {sc}")
    for k in ("cpu", "gpu", "ram", "storage", "psu", "os"):
        ok(w[k] == pole(seg, k), f"{w['name'][-30:]}: {k}: {w[k]!r} ≠ {pole(seg, k)!r}")
    ok(w["price"] == tw["price"] and w["priceBare"] == tw["priceBare"],
       f"{w['name'][-30:]}: cena {w['price']}/{w['priceBare']} ≠ {tw['price']}/{tw['priceBare']}")
    ok(w["pros"] == re.findall(r'"((?:[^"\\]|\\.)*)"', re.search(r"pros:\[(.*?)\]", seg, re.S).group(1)),
       f"{w['name'][-30:]}: zalety różnią się od tych na stronie")
    ok(w["cons"] == re.findall(r'"((?:[^"\\]|\\.)*)"', re.search(r"cons:\[(.*?)\]", seg, re.S).group(1)),
       f"{w['name'][-30:]}: wady różnią się od tych na stronie")

# --- brak licencji Windows na stronie → pominięcie, nie zgadywanie
url2 = "https://sklep.hard-pc.pl/p26430,zestaw-intel-ultra-225f-rtx-5060-ti-8gb-16gb-ddr5-650w-signum-300-argb.html"
try:
    n.zloz_wpisy(url2, F("hardpc_bez_windows_p26430.html"), None, set(), "k")
    ok(False, "strona bez licencji Windows powinna zostać pominięta")
except BrakDanych as x:
    ok("Windows" in str(x), f"zły powód pominięcia: {x}")

# --- dysk: BRAK w specyfikacji
spec3 = n.specyfikacja(F("hardpc_bez_dysku_p26383.html"))
ok(n.dysk_znormalizowany(spec3, None) == "SSD: brak (potwierdzone przez sklep)", "dysk BRAK")
spec1 = n.specyfikacja(F("hardpc_bez_windows_p26430.html"))
ok(n.dysk_znormalizowany(spec1, None) == "1TB SSD", f"dysk z tabeli: {n.dysk_znormalizowany(spec1, None)}")
ok(n.gpu_kanoniczna("RTX 5060 Ti", spec1) == "NVIDIA GeForce RTX 5060 Ti 8GB",
   "pamięć karty ze specyfikacji, gdy tytuł jej nie podaje")
try:
    n.gpu_kanoniczna("RTX 5060 Ti 16GB", spec1); ok(False, "sprzeczność pamięci tytuł/specyfikacja powinna odrzucić")
except BrakDanych:
    pass

# --- serializacja: wpis wczytuje się z powrotem tym samym parserem co cały serwis
js = n.wpis_js(wpisy[1])
mini = "var PDATA = [\n    " + js + "\n  ];"
odczyt = z.wczytaj(mini)
ok(len(odczyt) == 1 and odczyt[0]["price"] == wpisy[1]["price"] and odczyt[0]["prices"] == {"hardpc": wpisy[1]["priceBare"]},
   f"wpis nie wraca z serializacji: {odczyt}")
ok(js.count("{") == js.count("}") and js.count("[") == js.count("]"), "nawiasy w wpisie się nie domykają")

if bledy:
    print("TEST NIE PRZESZEDŁ"); [print("  ", b) for b in bledy]; sys.exit(1)
print("TEST ZALICZONY: zestaw zbudowany od zera = zestaw na stronie (oceny, pola, teksty, ceny)")
