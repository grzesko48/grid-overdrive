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
from fractions import Fraction
import ocena_pc

BAZA = os.path.dirname(os.path.abspath(__file__))
SZABLON = os.path.join(BAZA, "monitors_1700_template.html")

PROGI = {
    # (najlepszy = 100 pkt, najgorszy = 0 pkt) w jednostce podstawy
    "monitor": {"podstawa": "zł/Hz", "najlepszy": 3.00, "najgorszy": 12.00},
    "pc":      {"podstawa": "zł/pkt wydajności", "najlepszy": 70.0, "najgorszy": 140.0},
}

# PROGI DŁUGOWIECZNOŚCI SĄ BEZWZGLĘDNE, NIE MIN-MAX — to jest CAŁA ISTOTA naprawy w
# tym etapie i dokładnie ta sama usterka, którą wyżej usunięto z „value". Do dziś
# `longevity` w szablonie liczono (ręcznie, poza tym skryptem) wzorem
# round(1 + (longevityYears − min) / (max − min) × 99), gdzie min i max to NAJMNIEJSZA
# i NAJWIĘKSZA wartość longevityYears w DZISIEJSZEJ bazie (1,22 i 3,78) — nie stałe.
# Skutek: dolną kotwicę trzymała JEDNA pozycja (Ryzen 5 7500F, RTX 5050 8GB), a jej
# zniknięcie ze sklepu przeliczałoby longevity u 337 z 347 pozostałych zestawów i
# ultra u 332 z 347 — bez żadnej zmiany w sprzęcie ani cenie. Progi poniżej są STAŁE
# (wybór, nie pomiar z bazy, patrz PAKIET-NAPRAWCZY-2.md/ETAP 3): dodanie albo
# usunięcie dowolnego produktu nie rusza już oceny NIKOGO innego.
DLUGOWIECZNOSC_MIN_LAT = 1.2
DLUGOWIECZNOSC_MAX_LAT = 3.8

# Wzory zbiorcze — sprawdzone, odtwarzają dzisiejsze wartości co do wpisu.
WZORY = {
    "monitor": {"overall": (("image", .30), ("value", .30), ("perf", .25), ("features", .15))},
    "pc": {"overall": (("components", .28), ("value", .32), ("perf", .27), ("features", .13)),
           "ultra":   (("perf", .35), ("longevity", .28), ("value", .20),
                       ("components", .10), ("features", .07))},
}


def ocena_wartosci(x, rodzaj):
    """Im taniej za jednostkę, tym wyżej. Liniowo między progami, przycięte do 0–100."""
    p = PROGI[rodzaj]
    u = (p["najgorszy"] - x) / (p["najgorszy"] - p["najlepszy"])
    return int(round(max(0.0, min(1.0, u)) * 100))


def ocena_dlugowiecznosci(lata_tekst):
    """Im więcej lat, tym wyżej. Liniowo między progami BEZWZGLĘDNYMI (patrz stałe
    DLUGOWIECZNOSC_*), przycięcie do [0, 1] OBOWIĄZKOWE — automat dokłada nowe zestawy
    co kilka dni i wartość spoza dzisiejszych widełek nie może wyjść poza skalę 1–100.
    Skala wynikowa to 1–100 (nie 0–100 jak `value`) — zgodnie z dotychczasowym wzorem
    w szablonie. `lata_tekst` to surowy tekst z regeksa (np. "1.55"): liczymy na
    ułamkach dokładnych (Fraction) tą samą regułą „połowa do parzystej" co sumy ważone
    niżej, więc konwersja przez string→float nigdy nie wnosi błędu reprezentacji."""
    lata = Fraction(lata_tekst)
    dol, gora = Fraction(str(DLUGOWIECZNOSC_MIN_LAT)), Fraction(str(DLUGOWIECZNOSC_MAX_LAT))
    u = (lata - dol) / (gora - dol)
    u = max(Fraction(0), min(Fraction(1), u))
    return int(round(1 + u * 99))


def granice(sz):
    t = [(m.start(), "monitor") for m in re.finditer(r"\{img:'\d{2,}_[^']+', name:'", sz)]
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
    kontrola_dlugowiecznosc = []
    bez_kodu, zmiany_lat = [], []

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
            # Moc, podzespoły i kompletność liczy teraz KOD (ocena_pc.py), a nie liczby
            # wpisane w szablonie. Zestaw, którego nie da się policzyć (karta bez podanej
            # pamięci, nieznany procesor), zostaje przy zapisanych wartościach i trafia
            # do raportu — brak danych nie zamienia się w wartość domyślną.
            spec_pc = None
            def pole(n, seg=seg):
                m = re.search(rf'(?<![A-Za-z]){n}:"([^"]*)"', seg)
                return m.group(1) if m else ""
            mp = re.search(r"prices:\{([^}]*)\}", seg)
            nsk = len(re.findall(r"\w+:\d+", mp.group(1))) if mp else 0
            try:
                spec_pc = ocena_pc.oceny(pole("cpu"), pole("gpu"), pole("ram"), pole("storage"),
                                         pole("psu"), pole("os"), nsk)
            except ocena_pc.BrakDanych as x:
                bez_kodu.append(f"{nazwa}: {x}")
            perf_nowy = spec_pc["perf"] if spec_pc else s.get("perf")
            if not perf_nowy:
                bledy.append(f"{nazwa}: perf = 0 lub brak — nie liczę opłacalności")
                nowy.append(seg); continue
            podstawa = cena / perf_nowy

        nowe = dict(s)          # s = wartości ZAPISANE; różnice liczymy względem nich
        if rodzaj == "pc" and spec_pc:
            nowe.update({k: spec_pc[k] for k in ("perf", "components", "features")})
        nowe["value"] = ocena_wartosci(podstawa, rodzaj)

        # `longevity` MUSI się policzyć PRZED sumami ważonymi niżej — inaczej `ultra`
        # sumowałby jeszcze starą (min-maxową) wartość ze scores szablonu, a cały etap
        # 3 sprowadzałby się do przeliczenia samego pola bez wpływu na resztę.
        lata_tekst = None
        if rodzaj == "pc":
            if spec_pc:
                seg_lat = re.sub(r"longevityYears:[\d.]+",
                                 f"longevityYears:{spec_pc['longevityYears']}", seg, count=1)
                if seg_lat != seg:
                    zmiany_lat.append(nazwa)
                    seg = seg_lat
            ly = re.search(r"longevityYears:([\d.]+)", seg)
            if not ly:
                bledy.append(f"{nazwa}: brak pola longevityYears — nie liczę longevity")
            else:
                lata_tekst = ly.group(1)
                nowe["longevity"] = ocena_dlugowiecznosci(lata_tekst)

        for pole, skl in WZORY[rodzaj].items():
            if all(k in nowe for k, _ in skl):
                # Zaokrąglenie „połowa do parzystej" (round-half-to-even) liczone na
                # ułamkach dokładnych (Fraction), nie na floatach. Suma ważona, która
                # matematycznie wynosi dokładnie X,5, na floatach bywa X,4999999... i
                # round() ucina ją w dół SAM Z SIEBIE — przypadkiem błędu reprezentacji,
                # a nie jawną regułą. Fraction(str(w)) bierze dokładną wartość dziesiętną
                # wagi (0.30 -> 3/10, nie jej binarne przybliżenie), więc suma jest
                # dokładna i round(suma) rozstrzyga remis „,5" zawsze tą samą, jawną
                # regułą parzystości.
                suma = sum(Fraction(nowe[k]) * Fraction(str(w)) for k, w in skl)
                nowe[pole] = int(round(suma))

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
            if lata_tekst is not None:
                kontrola_dlugowiecznosc.append((Fraction(lata_tekst), nowe["longevity"], nazwa))
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

    # TEST BLOKUJĄCY (etap 3, wzorowany na powyższym): zestaw o WIĘKSZEJ liczbie lat
    # longevityYears nie może mieć NIŻSZEJ oceny longevity. Formuła jest liniowa więc
    # inwersja matematycznie nie powinna wystąpić — to siatka bezpieczeństwa na wypadek
    # błędu w kodzie (zły znak, zamieniona kolejność progów), nie na wynik pomiaru.
    n = 0
    for i in range(len(kontrola_dlugowiecznosc)):
        for j in range(len(kontrola_dlugowiecznosc)):
            if (kontrola_dlugowiecznosc[i][0] > kontrola_dlugowiecznosc[j][0]
                    and kontrola_dlugowiecznosc[i][1] < kontrola_dlugowiecznosc[j][1]):
                n += 1
    inwersje["longevity"] = n

    if bez_kodu:
        print(f"pozycje, których kod nie umie ocenić (zostają przy zapisanych wartościach): {len(bez_kodu)}")
        for x in bez_kodu[:6]:
            print("   ", x[:120])
    if zmiany_lat:
        print(f"zmienione lata długowieczności: {len(zmiany_lat)}")
    print(f"pozycji przeliczonych : {len(zmiany)}")
    for r in ("monitor", "pc"):
        z = [x for x in zmiany if x["rodzaj"] == r]
        print(f"   {r:8s}: {len(z)} zmian  |  par sprzecznych po przeliczeniu: {inwersje[r]}")
    print(f"   {'longevity':8s}: par sprzecznych po przeliczeniu: {inwersje['longevity']} "
          f"(na {len(kontrola_dlugowiecznosc)} pozycjach)")
    if bledy:
        print(f"pozycje bez podstawy (pominięte): {len(bledy)}")
        for b in bledy[:5]:
            print("   ", b)

    if any(inwersje.values()):
        print("\nTEST NIE PRZESZEDŁ — nie zapisuję. Para sprzeczna oznacza, że wzór nie działa.")
        sys.exit(1)

    if a.na_sucho:
        print("\n--na-sucho: nic nie zapisano. Największe zmiany:")
        # Podgląd pokazuje KAŻDE zmienione pole, nie tylko „value". Zmiana reguły
        # zaokrąglenia rusza sumy ważone (ultra, overall), a wtedy wpis nie ma wcale
        # pola „value" — wcześniejsza wersja wywracała się tu na None.
        def rozpietosc(z):
            return max((abs(n - s) for s, n in z["zmiany"].values()), default=0)

        for z in sorted(zmiany, key=lambda z: -rozpietosc(z))[:12]:
            opis = "  ".join(f"{k} {s}→{n}" for k, (s, n) in sorted(z["zmiany"].items()))
            print(f"   {z['podstawa']:7.2f}  {opis}  {z['nazwa'][:52]}")
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
