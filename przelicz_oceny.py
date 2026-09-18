#!/usr/bin/env python3
"""Liczy składnik „opłacalność" jawnym wzorem i przelicza oceny zbiorcze.

Dlaczego istnieje: audyt z 18 września 2026 wykazał, że `value` nigdy nie było liczone
deklarowaną formułą — oceny przypisano ręcznie. Sumy ważone (`overall`, `ultra`) okazały
się za to uczciwe: odtwarzają się co do jednego wpisu (56/56 monitorów, 353/353 zestawów).
Wystarczy więc policzyć `value` i przeliczyć sumy z już sprawdzonych wzorów.

PROGI SĄ BEZWZGLĘDNE, NIE MIN-MAX. To świadoma zmiana konstrukcji. Przy min-max ocena
mówi „ten sprzęt wypada tak wobec tych, które akurat dziś są w bazie" — usunięcie jednej
skrajnej pozycji przesuwało 358 z 359 ocen długowieczności. Przy progach zamrożonych
ocena znaczy to samo w każdym przebiegu, a dodanie produktu nie rusza nikogo.

Progi poniżej to WYBÓR, nie pomiar. Zmienia się je świadomie, tutaj, z wpisem w commicie.
Dobrane tak, żeby dzisiejszy rynek mieścił się z zapasem po obu stronach:
  monitory  3,12–10,69 zł/Hz  (mediana 6,11)  → widełki 3,00–12,00
  zestawy  78,4–129,2 zł/pkt  (mediana 101,3) → widełki 70,0–140,0
"""
import argparse, json, os, re, subprocess, sys

BAZA = os.path.dirname(os.path.abspath(__file__))
SZABLON = os.path.join(BAZA, "monitors_1700_template.html")

PROGI = {
    # (najlepszy = 100 pkt, najgorszy = 0 pkt) w jednostce podstawy
    "monitor": {"podstawa": "zł/Hz", "najlepszy": 3.00, "najgorszy": 12.00},
    "pc":      {"podstawa": "zł/pkt wydajności", "najlepszy": 70.0, "najgorszy": 140.0},
}

# Wzory zbiorcze — sprawdzone, odtwarzają dzisiejsze wartości co do wpisu.
WZORY = {
    "monitor": {"overall": (("image", .30), ("value", .30), ("perf", .25), ("features", .15))},
    "pc": {"overall": (("components", .28), ("value", .32), ("perf", .27), ("features", .13)),
           "ultra":   (("perf", .28), ("longevity", .30), ("value", .22),
                       ("components", .12), ("features", .08))},
}


def ocena_wartosci(x, rodzaj):
    """Im taniej za jednostkę, tym wyżej. Liniowo między progami, przycięte do 0–100."""
    p = PROGI[rodzaj]
    u = (p["najgorszy"] - x) / (p["najgorszy"] - p["najlepszy"])
    return int(round(max(0.0, min(1.0, u)) * 100))


def granice(sz):
    t = [(m.start(), "monitor") for m in re.finditer(r"\{img:'\d\d_[^']+', name:'", sz)]
    t += [(m.start(), "pc") for m in re.finditer(r'\{img:"p[^"]*", name:"', sz)]
    return sorted(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--na-sucho", action="store_true")
    ap.add_argument("--bez-przebudowy", action="store_true",
                    help="zapisz szablon, ale nie buduj strony — buduje wolajacy")
    a = ap.parse_args()

    sz = open(SZABLON, encoding="utf-8").read()
    punkty = granice(sz)
    nowy, koniec, zmiany, bledy = [], 0, [], []
    kontrola = {"monitor": [], "pc": []}

    for i, (start, rodzaj) in enumerate(punkty):
        stop = punkty[i + 1][0] if i + 1 < len(punkty) else len(sz)
        nowy.append(sz[koniec:start])
        seg = sz[start:stop]
        koniec = stop

        sc = re.search(r"scores:\{([^}]*)\}", seg)
        cen = re.search(r"(?<![A-Za-z])price:(\d+)", seg)
        if not (sc and cen):
            nowy.append(seg)
            continue
        s = {k: int(v) for k, v in re.findall(r"(\w+):(\d+)", sc.group(1))}
        cena = int(cen.group(1))
        nazwa = re.search(r"name:['\"]([^'\"]*)", seg).group(1)

        if rodzaj == "monitor":
            hz = re.search(r"hz:(\d+)", seg)
            if not hz:
                bledy.append(f"{nazwa}: brak pola hz — nie liczę opłacalności")
                nowy.append(seg); continue
            podstawa = cena / int(hz.group(1))
        else:
            if not s.get("perf"):
                bledy.append(f"{nazwa}: perf = 0 lub brak — nie liczę opłacalności")
                nowy.append(seg); continue
            podstawa = cena / s["perf"]

        nowe = dict(s)
        nowe["value"] = ocena_wartosci(podstawa, rodzaj)
        for pole, skl in WZORY[rodzaj].items():
            if all(k in nowe for k, _ in skl):
                nowe[pole] = int(round(sum(nowe[k] * w for k, w in skl)))

        roznice = {k: (s[k], nowe[k]) for k in nowe if s.get(k) != nowe[k]}
        if roznice:
            zmiany.append({"nazwa": nazwa, "rodzaj": rodzaj, "podstawa": round(podstawa, 2),
                           "zmiany": roznice})
            tresc = sc.group(1)
            for k, (_, v) in roznice.items():
                tresc = re.sub(r"\b" + k + r":\d+", f"{k}:{v}", tresc, count=1)
            seg = seg[:sc.start(1)] + tresc + seg[sc.end(1):]

        ukryty = bool(re.search(r"(?<![A-Za-z])ukryty:1", seg))
        if not ukryty:
            kontrola[rodzaj].append((podstawa, nowe["value"], nazwa))
        nowy.append(seg)

    nowy.append(sz[koniec:])
    wynik = "".join(nowy)

    # TEST BLOKUJĄCY: tańszy za jednostkę nie może mieć niższej oceny opłacalności.
    # To jest cała usterka, przez którą powstał ten skrypt — sprawdzamy ją mechanicznie
    # przy każdym przebiegu, zamiast ufać, że wzór został użyty.
    inwersje = {}
    for rodzaj, lista in kontrola.items():
        n = 0
        for i in range(len(lista)):
            for j in range(len(lista)):
                if lista[i][0] < lista[j][0] and lista[i][1] < lista[j][1]:
                    n += 1
        inwersje[rodzaj] = n

    print(f"pozycji przeliczonych : {len(zmiany)}")
    for r in ("monitor", "pc"):
        z = [x for x in zmiany if x["rodzaj"] == r]
        print(f"   {r:8s}: {len(z)} zmian  |  par sprzecznych po przeliczeniu: {inwersje[r]}")
    if bledy:
        print(f"pozycje bez podstawy (pominięte): {len(bledy)}")
        for b in bledy[:5]:
            print("   ", b)

    if any(inwersje.values()):
        print("\nTEST NIE PRZESZEDŁ — nie zapisuję. Para sprzeczna oznacza, że wzór nie działa.")
        sys.exit(1)

    if a.na_sucho:
        print("\n--na-sucho: nic nie zapisano. Największe zmiany:")
        naj = sorted(zmiany, key=lambda z: -abs(z["zmiany"].get("value", (0, 0))[1]
                                                - z["zmiany"].get("value", (0, 0))[0]))
        for z in naj[:12]:
            v = z["zmiany"].get("value")
            print(f"   {z['podstawa']:7.2f}  value {v[0]:3d}→{v[1]:3d}  {z['nazwa'][:52]}")
        return

    open(SZABLON, "w", encoding="utf-8").write(wynik)
    json.dump({"progi": PROGI, "przeliczonych": len(zmiany),
               "par_sprzecznych": inwersje, "bez_podstawy": bledy, "zmiany": zmiany},
              open(os.path.join(BAZA, "raport_ocen.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    if a.bez_przebudowy:
        print("\nszablon zapisany (przebudowę wykona wołający)")
        return
    print("\nszablon zapisany; przebudowuję stronę")
    subprocess.run([sys.executable, os.path.join(BAZA, "build_merged.py")], check=True)


if __name__ == "__main__":
    main()
