#!/usr/bin/env python3
"""Bramki rankingu (bez sieci): sprawdzają to, co ranking obiecuje, na danych z szablonu.

Dlaczego istnieją (audyt rankingu 22.10.2026): liczby były poprawne arytmetycznie, ale nic nie
pilnowało RZECZY, które psują ranking po cichu — tego samego produktu wpisanego dwa razy,
zestawu bez dysku na #3, 16 GB RAM na szczycie, wag w kodzie JS rozjechanych z Pythonem.

  1. monitory: overall / perf / value odtwarzają się ze wzorów; brak duplikatów produktu
     (wspólny adres sklepu), nazwy unikalne;
  2. PC: Ultra i ocena ogólna = suma ważona − kary rankingowe (16 GB RAM, brak dysku);
     16 GB nie wchodzi do TOP 10, zestaw bez dysku nie wchodzi do TOP 50, a najlepszy 16 GB
     jest poniżej najlepszego 32 GB;
  3. kod JS (kary i wagi) daje to samo co Python na wszystkich zestawach;
  4. żadna karta w danych nie ma klasy poza skalą mocy (przycięcie do 100 zakłamałoby wynik).
"""
import json, os, re, subprocess, sys
from fractions import Fraction

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import ocena_pc
import przelicz_oceny as po

sz = open(os.path.join(BAZA, "monitors_1700_template.html"), encoding="utf-8").read()
bledy = []


def oczekuj(w, opis):
    if not w:
        bledy.append(opis)
        print("  BŁĄD:", opis)


def zaokr(x):                       # połowa do parzystej na ułamkach dokładnych (jak przelicz_oceny)
    return int(round(Fraction(x)))


def suma(wagi, s):
    return sum(Fraction(s[k]) * Fraction(str(w)) for k, w in wagi)


# ------------------------------------------------------------------ wczytanie danych
punkty = po.granice(sz)
mon, pc = [], []
for i, (st, rod) in enumerate(punkty):
    stop = punkty[i + 1][0] if i + 1 < len(punkty) else len(sz)
    seg = sz[st:stop]
    sc = re.search(r"scores:\{([^}]*)\}", seg)
    if not sc:
        continue
    s = {k: int(v) for k, v in re.findall(r"(\w+):(\d+)", sc.group(1))}
    d = {"name": re.search(r"name:['\"]([^'\"]*)", seg).group(1), "s": s,
         "price": int(re.search(r"(?<![A-Za-z])price:(\d+)", seg).group(1)),
         "ukryty": bool(re.search(r"(?<![A-Za-z])ukryty:1", seg)), "seg": seg}
    if rod == "monitor":
        d["hz"] = int(re.search(r"hz:(\d+)", seg).group(1))
        mon.append(d)
    else:
        for f in ("cpu", "gpu", "ram", "storage"):
            m = re.search(rf'(?<![A-Za-z]){f}:"([^"]*)"', seg)
            d[f] = m.group(1) if m else ""
        pc.append(d)

# ------------------------------------------------------------------ 1. monitory
print(f"monitory: {len(mon)} wpisów")
nazwy = [d["name"] for d in mon]
oczekuj(len(nazwy) == len(set(nazwy)), "nazwy monitorów nie są unikalne")
wagi_m = po.WZORY["monitor"]["overall"]
for d in mon:
    s = d["s"]
    perf_oczek = max(60, min(100, zaokr(Fraction(60) + Fraction(d["hz"] - 240, 260) * 40)))
    oczekuj(s["perf"] == perf_oczek, f"{d['name']}: perf {s['perf']} ≠ f(Hz={d['hz']}) = {perf_oczek}")
    oczekuj(s["value"] == po.ocena_wartosci(d["price"] / d["hz"], "monitor"),
            f"{d['name']}: value {s['value']} ≠ policzone z ceny {d['price']} zł i {d['hz']} Hz")
    if "overall" in s:
        oczekuj(s["overall"] == zaokr(suma(wagi_m, s)), f"{d['name']}: overall {s['overall']} ≠ suma ważona")
    else:
        oczekuj("image" not in s and "features" not in s,
                f"{d['name']}: ma image/features, ale nie ma overall (niedokończona ocena)")

# duplikat produktu = wspólny adres sklepu (x-kom /p/ID, Morele -ID/, MediaMarkt -ID.html)
ident = {}
for d in mon:
    urls = re.search(r"urls:\{([^}]*)\}", d["seg"])
    for u in re.findall(r"'(https?://[^']+)'", urls.group(1) if urls else ""):
        m = re.search(r"x-kom\.pl/p/(\d+)", u) or re.search(r"morele\.net/.*-(\d{6,9})/?$", u) \
            or re.search(r"mediamarkt\.pl/.*-(\d{6,9})\.html", u)
        if m:
            ident.setdefault(m.group(0), set()).add(d["name"])
dup = {k: v for k, v in ident.items() if len(v) > 1}
oczekuj(not dup, f"ten sam produkt sklepu w kilku wpisach monitorów: {dup}")

# ------------------------------------------------------------------ 2. PC
print(f"PC: {len(pc)} wpisów")
widoczne = [d for d in pc if not d["ukryty"]]
wagi_o, wagi_u = po.WZORY["pc"]["overall"], po.WZORY["pc"]["ultra"]
rozjazdy = 0
for d in pc:
    try:
        kara = ocena_pc.kary_rankingu(d["ram"], d["storage"])
    except ocena_pc.BrakDanych:
        continue
    d["kara"] = kara
    for pole, wagi in (("overall", wagi_o), ("ultra", wagi_u)):
        oczek = max(0, zaokr(suma(wagi, d["s"])) - kara)
        if d["s"][pole] != oczek:
            rozjazdy += 1
            oczekuj(False, f"{d['name'][:60]}: {pole} {d['s'][pole]} ≠ suma ważona − kara = {oczek}")
oczekuj(rozjazdy == 0, "oceny PC rozjechane z wzorem i karami")


def gb(d):
    return int(re.search(r"(\d+)\s*GB", d["ram"]).group(1))


def bez_dysku(d):
    return ocena_pc.bez_ssd(d["storage"])


top = sorted(widoczne, key=lambda d: (-d["s"]["ultra"], d["price"], d["name"]))
oczekuj(not any(gb(d) < 32 for d in top[:10]), "w TOP 10 Ultra jest zestaw z RAM poniżej 32 GB")
oczekuj(not any(bez_dysku(d) for d in top[:50]), "w TOP 50 Ultra jest zestaw bez dysku")
najl16 = max((d["s"]["ultra"] for d in widoczne if gb(d) < 32), default=0)
najl32 = max((d["s"]["ultra"] for d in widoczne if gb(d) >= 32), default=0)
oczekuj(najl16 < najl32, f"najlepszy 16 GB ({najl16}) nie jest poniżej najlepszego 32 GB ({najl32})")
oczekuj(ocena_pc.jakosc_ram("64GB DDR5") == ocena_pc.jakosc_ram("32GB DDR5"),
        "powyżej 32 GB RAM nie może dawać więcej punktów (32 GB = optimum)")

# ------------------------------------------------------------------ 3. JS zgodny z Pythonem
def wytnij(znacznik):
    m = re.search(r"/\*%s_START\*/(.*?)/\*%s_END\*/" % (znacznik, znacznik), sz, re.S)
    oczekuj(bool(m), f"brak znaczników {znacznik} w szablonie")
    return m.group(1) if m else ""


js_kary, js_wagi_pc, js_wagi_mon = wytnij("KARY"), wytnij("WAGI_PC"), wytnij("WAGI_MON")
dane_js = [{"ram": d["ram"], "storage": d["storage"]} for d in pc]
skrypt = (js_kary + js_wagi_pc + js_wagi_mon +
          "const D=%s; console.log(JSON.stringify({kary:D.map(pcKaraSuma),pc:PC_WAGI_ULTRA,mon:MON_WAGI,"
          "stale:[PC_KARA_RAM,PC_KARA_BRAK_DYSKU,PC_RAM_OPTIMUM_GB]}));" % json.dumps(dane_js))
try:
    wyj = subprocess.run(["node", "-e", skrypt], capture_output=True, text=True, timeout=60)
    if wyj.returncode != 0:
        oczekuj(False, f"node nie uruchomił fragmentu JS: {wyj.stderr[:300]}")
    else:
        r = json.loads(wyj.stdout)
        py_kary = []
        for d in pc:
            try:
                py_kary.append(ocena_pc.kary_rankingu(d["ram"], d["storage"]))
            except ocena_pc.BrakDanych:
                py_kary.append(None)
        roznice = [(pc[i]["name"][:50], r["kary"][i], p) for i, p in enumerate(py_kary)
                   if p is not None and r["kary"][i] != p]
        oczekuj(not roznice, f"kary w JS ≠ kary w Pythonie dla {len(roznice)} zestawów, np. {roznice[:2]}")
        oczekuj(r["stale"] == [ocena_pc.KARA_RAM_PONIZEJ_32GB, ocena_pc.KARA_BRAK_DYSKU, 32],
                f"stałe kar w JS {r['stale']} ≠ Python")
        oczekuj({k: Fraction(str(v)) for k, v in r["pc"].items()} == {k: Fraction(str(v)) for k, v in wagi_u},
                "wagi Ultra w JS ≠ WZORY['pc']['ultra']")
        oczekuj({k: Fraction(str(v)) for k, v in r["mon"].items()} == {k: Fraction(str(v)) for k, v in wagi_m},
                "wagi monitorów w JS ≠ WZORY['monitor']")
except FileNotFoundError:
    print("  (node niedostępny — pominięto porównanie JS z Pythonem)")

# ------------------------------------------------------------------ 4. skala mocy
poza = []
for d in pc:
    try:
        k = ocena_pc.klasa_gpu(d["gpu"])
    except ocena_pc.BrakDanych:
        continue
    if k > 7:
        poza.append((d["name"][:50], k))
oczekuj(not poza, f"karta spoza skali mocy (klasa > 7) — przycięcie do 100 zafałszuje ranking: {poza[:3]}")

print("\nTEST ZALICZONY: ranking spełnia swoje reguły" if not bledy else f"\nTEST NIEZALICZONY: {len(bledy)} błędów")
sys.exit(1 if bledy else 0)
