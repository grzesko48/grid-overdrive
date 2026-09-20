#!/usr/bin/env python3
"""Przyrzad pomiarowy pakietu naprawczego 2.

Zrzuca stan wszystkich skladnikow oceny i liczy bramki odbioru z PAKIET-NAPRAWCZY-2.md.
Nie zmienia niczego. Uruchamiany przed i po kazdym etapie.

Sumy wazone liczymy na ULAMKACH DOKLADNYCH. Na floatach 61.5 wychodzi jako
61.4999... i round() zaokragla w dol sam z siebie, maskujac niezgodnosc.
"""
import json, os, re, sys
from fractions import Fraction as F

PLIK = "monitors_1700_template.html"
WAGI = (("perf", F(35, 100)), ("longevity", F(28, 100)), ("value", F(20, 100)),
        ("components", F(10, 100)), ("features", F(7, 100)))


def wczytaj(plik=PLIK):
    src = open(plik, encoding="utf-8").read()
    i = src.index("var PDATA")
    blok = src[i: i + re.search(r"\n\s*\];", src[i:]).start()]
    poz = [m.start() for m in re.finditer(r"\{img:", blok)]
    out = []
    for k, s in enumerate(poz):
        seg = blok[s: poz[k + 1] if k + 1 < len(poz) else len(blok)]
        if re.search(r"(?<![A-Za-z])ukryty:1", seg):
            continue
        sc = re.search(r"scores:\{([^}]*)\}", seg)
        nm = re.search(r'name:"([^"]*)', seg)
        ly = re.search(r"longevityYears:([\d.]+)", seg)
        ce = re.search(r"(?<![A-Za-z])price:(\d+)", seg)
        if not (sc and nm):
            continue
        out.append({
            "nazwa": nm.group(1),
            "lata": float(ly.group(1)) if ly else None,
            "cena": int(ce.group(1)) if ce else None,
            **{k2: int(v) for k2, v in re.findall(r"(\w+):(\d+)", sc.group(1))},
        })
    return out


def odch(xs):
    s = sum(xs) / len(xs)
    return (sum((x - s) ** 2 for x in xs) / len(xs)) ** 0.5


def bramki(w):
    r = {"pozycji": len(w)}

    # G2 — czy suma wazona odtwarza opublikowana ocene (ulamki dokladne)
    nieodtworzone = []
    for e in w:
        if not all(k in e for k, _ in WAGI):
            continue
        s = sum(F(e[k]) * wg for k, wg in WAGI)
        # round-half-to-even, jawnie
        d, m = divmod(s, 1)
        oczek = int(d) + (1 if m > F(1, 2) or (m == F(1, 2) and int(d) % 2) else 0)
        if e.get("ultra") != oczek:
            nieodtworzone.append({"nazwa": e["nazwa"], "opublikowano": e.get("ultra"),
                                  "suma": str(s), "reguła_parzysta": oczek})
    r["G2_nieodtworzone"] = nieodtworzone
    r["G2"] = f"{len(w) - len(nieodtworzone)}/{len(w)}"

    # G3 — stabilnosc: czy usuniecie jednej skrajnej pozycji rusza oceny innym
    lata = [e["lata"] for e in w if e["lata"] is not None]
    if lata:
        lo, hi = min(lata), max(lata)
        wzor = sum(1 for e in w if e["lata"] is not None
                   and e["longevity"] == round(1 + (e["lata"] - lo) / (hi - lo) * 99))
        r["min_max_na_zywej_bazie"] = f"{wzor}/{len(lata)}"
        # Druga hipoteza: progi BEZWZGLEDNE. Roznica miedzy tymi dwoma wierszami jest
        # calym sensem etapu 3 — przy min-maxie kotwice wyznacza dzisiejsza baza,
        # przy progach sa stale i dodanie produktu nie rusza nikogo innego.
        PROG_LO, PROG_HI = 1.2, 3.8
        bez = sum(1 for e in w if e["lata"] is not None and e["longevity"] ==
                  round(1 + max(0.0, min(1.0, (e["lata"] - PROG_LO) / (PROG_HI - PROG_LO))) * 99))
        r["progi_bezwzgledne"] = f"{bez}/{len(lata)}"
        r["kotwica_dolna"] = {"lata": lo, "trzyma_pozycji": sum(1 for x in lata if x == lo)}
        # G3 liczymy REGULA, KTORA DANE FAKTYCZNIE SPELNIAJA — nie zalozona z gory.
        # Wersja poprzednia zakladala min-max i po naprawie pokazywalaby 337/347 na
        # bazie, ktora jest juz stabilna. Bramka, ktora klamie o stanie po naprawie,
        # jest tą samą klasą usterki, którą ten pakiet usuwa.
        reszta = [e for e in w if e["lata"] != lo]
        lo2 = min(e["lata"] for e in reszta)
        if bez == len(lata):
            regula, opis = (lambda x, a2, b2: round(
                1 + max(0.0, min(1.0, (x - PROG_LO) / (PROG_HI - PROG_LO))) * 99)), "progi bezwzgledne"
        elif wzor == len(lata):
            regula, opis = (lambda x, a2, b2: round(1 + (x - a2) / (b2 - a2) * 99)), "min-max na zywej bazie"
        else:
            regula, opis = None, "nierozpoznana"
        if regula:
            ruch = sum(1 for e in reszta if regula(e["lata"], lo2, hi) != e["longevity"])
            r["G3_rusza_longevity"] = f"{ruch}/{len(reszta)}"
        else:
            r["G3_rusza_longevity"] = "nie do policzenia — reguła nierozpoznana"
        r["G3_regula"] = opis

    # G5 — efektywna liczba skladnikow
    sd = {k: odch([e[k] for e in w if k in e]) for k, _ in WAGI}
    wpl = {k: sd[k] * float(wg) for k, wg in WAGI}
    suma = sum(wpl.values())
    udz = {k: v / suma for k, v in wpl.items()}
    r["odchylenia"] = {k: round(v, 2) for k, v in sd.items()}
    r["udzial_sd_razy_waga"] = {k: round(v * 100, 1) for k, v in udz.items()}
    r["G5_efektywna_sd_razy_waga"] = round(1 / sum(p * p for p in udz.values()), 2)

    # Ta sama wielkosc na drugiej podstawie. Udzial w wariancji jest jedyna miara
    # sumujaca sie do 100% przy skorelowanych skladnikach i daje inny obraz -- 2,07
    # zamiast 2,89. Bramka bez nazwanej podstawy jest pusta.
    sr = {k: sum(e[k] for e in w) / len(w) for k, _ in WAGI}
    kow = lambda a, b: sum((e[a] - sr[a]) * (e[b] - sr[b]) for e in w) / len(w)
    fw = {k: float(g) for k, g in WAGI}
    cal = sum(fw[a] * fw[b] * kow(a, b) for a, _ in WAGI for b, _ in WAGI)
    udz_war = {k: sum(fw[k] * fw[b] * kow(k, b) for b, _ in WAGI) / cal for k, _ in WAGI}
    r["udzial_w_wariancji"] = {k: round(v * 100, 1) for k, v in udz_war.items()}
    r["G5_efektywna_wariancja"] = round(1 / sum(p * p for p in udz_war.values()), 2)

    # remisy
    u = [e["ultra"] for e in w if "ultra" in e]
    r["roznych_wartosci_ultra"] = len(set(u))
    r["par_z_remisem_pct"] = round(
        sum(u.count(x) * (u.count(x) - 1) for x in set(u)) / (len(u) * (len(u) - 1)) * 100, 1)

    # martwe skladniki
    r["moda"] = {}
    for k, _ in WAGI:
        xs = [e[k] for e in w if k in e]
        m = max(set(xs), key=xs.count)
        r["moda"][k] = {"wartosc": m, "pozycji": xs.count(m),
                        "pct": round(xs.count(m) / len(xs) * 100, 1)}
    return r


if __name__ == "__main__":
    # raport-bazowy.json jest baza odniesienia i NIE WOLNO go nadpisac przypadkiem —
    # inaczej kazdy kolejny pomiar porownuje sie sam ze soba i zawsze wychodzi "bez zmian".
    zrodlo = sys.argv[1] if len(sys.argv) > 1 else PLIK
    cel = sys.argv[2] if len(sys.argv) > 2 else "raport-biezacy.json"
    if cel == "raport-bazowy.json" and os.path.exists(cel):
        sys.exit("raport-bazowy.json juz istnieje — nie nadpisuje bazy odniesienia. "
                 "Podaj inna nazwe celu albo usun plik swiadomie.")
    w = wczytaj(zrodlo)
    b = bramki(w)
    json.dump({"bramki": b, "pozycje": w}, open(cel, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(b, ensure_ascii=False, indent=1))
    print(f"\nzapisano {cel} ({len(w)} pozycji)")
