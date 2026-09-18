#!/usr/bin/env python3
"""Porównuje katalog sklepu z naszymi danymi: co zniknęło, co doszło.

Automat cenowy potrafi wyłącznie nadpisać cenę istniejącego wpisu. Nie doda zestawu,
którego nie ma, i nie usunie wycofanego — dlatego we wrześniowym przeglądzie ręcznym
wyszło 118 zestawów, o których strona nie miała pojęcia. Ten skrypt zamyka tę lukę.

Świadomie NIE dopisuje nowych zestawów automatycznie: wpis wymaga specyfikacji,
zdjęcia i ocen liczonych wobec całego zbioru. Automat ma zgłosić kandydatów, a nie
wpuścić na stronę pozycję bez danych.
"""
import json, os, re, sys, time, urllib.error, urllib.request

BAZA = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")
SZABLON_URL = "https://sklep.hard-pc.pl/k530,zestawy-komputery-hard-pc{}.html"
# Widełki NABORU nowych kandydatów, nie zakres istniejącego zestawienia. To rozróżnienie
# jest istotne: zestawy wybrano kiedyś przy 5000-9000 zł bez systemu, ale ceny poszły w górę
# (181 podwyżek i zero obniżek we wrześniowym przeglądzie) i dziś zbiór sięga 10 098 zł bez
# systemu. Nabór zostaje przy pierwotnym kryterium — inaczej podwyżki same poszerzałyby
# zestawienie w nieskończoność. Zmiana tych liczb to decyzja właściciela, nie skutek uboczny.
ZAKRES = (5000, 9000)

KARTA = re.compile(
    r'<h2><a href="(p(\d+),[^"]+\.html)"[^>]*>([^<]+)</a></h2>.*?'
    r'<span id="cena_\2_0"><span class="default">([\d\s ,.]+)\s*zł</span>', re.S)

sys.path.insert(0, BAZA)
from zbieraj_ceny import wczytaj, TEMPO                             # noqa: E402


def pobierz(url):
    TEMPO.czekaj("sklep.hard-pc.pl")
    r = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(r, timeout=30).read().decode("utf-8", "replace")


def katalog():
    produkty, strona = {}, 1
    while strona <= 40:
        try:
            s = pobierz(SZABLON_URL.format("" if strona == 1 else f",{strona}"))
        except urllib.error.HTTPError as e:
            print(f"  strona {strona}: HTTP {e.code} — przerywam", file=sys.stderr)
            break
        trafienia = KARTA.findall(s)
        nowe = 0
        for sciezka, pid, nazwa, cena in trafienia:
            if pid in produkty:
                continue
            produkty[pid] = {"id": pid, "nazwa": re.sub(r"\s+", " ", nazwa).strip(),
                             "cena": round(float(re.sub(r"[^\d,]", "", cena).replace(",", "."))),
                             "url": "https://sklep.hard-pc.pl/" + sciezka}
            nowe += 1
        print(f"  strona {strona}: {len(trafienia)} kart, {nowe} nowych "
              f"(razem {len(produkty)})", file=sys.stderr)
        if not trafienia or nowe == 0:
            break
        strona += 1
    return produkty


def main():
    sz = open(os.path.join(BAZA, "monitors_1700_template.html"), encoding="utf-8").read()
    poz = wczytaj(sz)

    nasze = {}
    for p in poz:
        u = p["urls"].get("hardpc", "")
        m = re.search(r"/p(\d+),", u)
        if m:
            nasze.setdefault(m.group(1), []).append(p)

    print("pobieram katalog Hard-PC…", file=sys.stderr)
    kat = katalog()
    print(f"katalog: {len(kat)} zestawów  |  u nas: {len(nasze)} identyfikatorów",
          file=sys.stderr)

    zniknely = [{"id": i, "nazwa": w[0]["name"], "wpisow": len(w)}
                for i, w in sorted(nasze.items()) if i not in kat]

    kandydaci = []
    for i, k in sorted(kat.items()):
        if i in nasze:
            continue
        if not (ZAKRES[0] <= k["cena"] <= ZAKRES[1]):
            continue
        gora = k["nazwa"].upper()
        if "DDR4" in gora:                      # zestawienie jest wyłącznie DDR5
            continue
        if not re.search(r"\b(RTX|GTX|RX|ARC)\b", gora):
            # zestaw bez karty graficznej albo w ogóle nie komputer (bywa płyta
            # z zasilaczem) — to nie jest pozycja do porównywarki sprzętu do gier
            continue
        kandydaci.append(k)

    raport = {"katalog_pozycji": len(kat), "nasze_identyfikatory": len(nasze),
              "zniknely": zniknely, "nowi_kandydaci": kandydaci}
    json.dump(raport, open(os.path.join(BAZA, "raport_katalogu.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\nZNIKNĘŁY z katalogu: {len(zniknely)}")
    for z in zniknely[:12]:
        print(f"   [{z['id']}] {z['nazwa'][:76]}" +
              (f"  (+{z['wpisow']-1} wariantów)" if z["wpisow"] > 1 else ""))
    print(f"\nNOWI KANDYDACI ({ZAKRES[0]}–{ZAKRES[1]} zł, DDR5): {len(kandydaci)}")
    for k in kandydaci[:12]:
        print(f"   {k['cena']:5d} zł  {k['nazwa'][:74]}")
    print("\n→ raport_katalogu.json  (nic nie dopisano do danych — to wymaga "
          "specyfikacji, zdjęcia i przeliczenia ocen)")


if __name__ == "__main__":
    main()
