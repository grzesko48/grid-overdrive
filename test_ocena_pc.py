#!/usr/bin/env python3
"""Test: ocena_pc.py odtwarza oceny zestawów PC zapisane w szablonie.

Wzory były kiedyś liczbami wpisanymi w szablonie. Ten test pilnuje, że kod, który je teraz
liczy, daje TO SAMO co strona — z wyjątkiem jawnie wymienionych poprawek (WYJATKI).
Kod wyjścia 0 = zaliczony."""
import os, re, sys
BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import ocena_pc as o
from zbieraj_ceny import wczytaj

# Świadome różnice względem wartości zapisanych 21.10.2026, każda z uzasadnieniem w ocena_pc.py
WYJATKI = {
    "klasa procesora 225F/270K (pisownia bez cyfry)": lambda e: re.search(r"\b(225F|270K)\b", e["cpu"], re.I)
        and not re.search(r"ultra\s*[579]", e["cpu"], re.I),
    "zestaw bez dysku: kara jak za HDD": lambda e: "brak" in e["storage"].lower(),
}
BRAK_DANYCH_OK = ("NVIDIA GeForce RTX 5060 Ti",)     # karta bez podanej pamięci: dwie wersje

sz = open(os.path.join(BAZA, "monitors_1700_template.html"), encoding="utf-8").read()
i = sz.index("var PDATA")
blok = sz[i: i + re.search(r"\n\s*\];", sz[i:]).start()]
starty = [m.start() for m in re.finditer(r'\{img:"p', blok)]
zgodne = {k: 0 for k in ("perf", "components", "features", "longevityYears")}
wyjatki, brak, rozbieznosci = [], [], []
n = 0
for k, s in enumerate(starty):
    seg = blok[s: starty[k + 1] if k + 1 < len(starty) else len(blok)]
    def f(nazwa):
        m = re.search(rf'(?<![A-Za-z]){nazwa}:"([^"]*)"', seg)
        return m.group(1) if m else ""
    e = {"name": f("name"), "cpu": f("cpu"), "gpu": f("gpu"), "ram": f("ram"),
         "storage": f("storage"), "psu": f("psu"), "os": f("os")}
    sc = {a: int(b) for a, b in re.findall(r"(\w+):(\d+)", re.search(r"scores:\{([^}]*)\}", seg).group(1))}
    ly = float(re.search(r"longevityYears:([\d.]+)", seg).group(1))
    nsklepow = len(re.findall(r"\w+:\d+", re.search(r"prices:\{([^}]*)\}", seg).group(1)))
    n += 1
    try:
        wynik = o.oceny(e["cpu"], e["gpu"], e["ram"], e["storage"], e["psu"], e["os"], nsklepow)
    except o.BrakDanych:
        brak.append(e["gpu"]); continue
    stare = {"perf": sc["perf"], "components": sc["components"],
             "features": sc["features"], "longevityYears": ly}
    wyjatek = next((nazwa for nazwa, test in WYJATKI.items() if test(e)), None)
    for pole in zgodne:
        if abs(wynik[pole] - stare[pole]) < 0.005:
            zgodne[pole] += 1
        elif wyjatek:
            wyjatki.append((wyjatek, pole))
        else:
            rozbieznosci.append(f"{e['name'][:55]} {pole}: kod {wynik[pole]}, szablon {stare[pole]}")
print(f"wpisów PC: {n}; zgodne: {zgodne}")
print(f"różnice WYJAŚNIONE jawnym wyjątkiem: {len(wyjatki)}; karty bez pamięci (BrakDanych): {len(brak)}")
bledy = []
if rozbieznosci:
    bledy += ["NIEWYJAŚNIONE rozbieżności:"] + rozbieznosci[:15]
if any(g not in BRAK_DANYCH_OK for g in brak):
    bledy.append(f"BrakDanych dla nieoczekiwanej karty: {set(brak) - set(BRAK_DANYCH_OK)}")
# testy brzegowe: brak danych to wyjątek, nie wartość domyślna
for nazwa, wywolanie in (("nieznana karta", lambda: o.klasa_gpu("NVIDIA GeForce RTX 9999")),
                         ("RTX 5060 Ti bez pamięci", lambda: o.pamiec_gpu_gb("NVIDIA GeForce RTX 5060 Ti")),
                         ("nieznany procesor", lambda: o.klasa_cpu("Pentium 4"))):
    try:
        wywolanie(); bledy.append(f"{nazwa}: powinien być BrakDanych")
    except o.BrakDanych:
        pass
assert o.podzespoly("Ryzen 5 7500F", "16GB DDR5", "1000GB SSD") == o.podzespoly("Ryzen 5 7500F", "16GB DDR5", "1TB SSD")
if bledy:
    print("TEST NIE PRZESZEDŁ"); [print("  ", b) for b in bledy]; sys.exit(1)
print("TEST ZALICZONY")
