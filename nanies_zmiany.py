#!/usr/bin/env python3
"""Nanosi zebrane ceny i dostępność na szablon. Czyta zebrane_ceny.json, nic nie pobiera.

Rozdzielenie pobierania od zapisu jest celowe: pobieranie bywa zawodne (blokady, limity
tempa), a zapis musi być przewidywalny i odwracalny. Dzięki temu da się obejrzeć, co
automat ZAMIERZA zrobić (--na-sucho), zanim cokolwiek tknie dane.

Czego pilnuje:
  * dopłata za system jest stała per wpis (price - priceBare: 519 zł u Hard-PC, ale też
    800/500/300 i 0) — odtwarzamy różnicę, nie zakładamy stawki;
  * 68 wariantów „custom" wskazuje ten sam adres co zestaw bazowy, więc pobrana cena to
    cena BAZY — wariantowi doliczamy jego własną różnicę (koszt pamięci);
  * zmiana powyżej progu nie jest nanoszona automatycznie, tylko zgłaszana do przejrzenia
    (bot już raz wziął cenę z kodem rabatowym zamiast regularnej — commit f576fac);
  * pole `store` NIE jest przepinane samo z siebie, bo to zmienia ranking — sprzeczności
    trafiają do raportu jako decyzja dla człowieka.
"""
import argparse, datetime, json, os, re, subprocess, sys

BAZA = os.path.dirname(os.path.abspath(__file__))
SZABLON = os.path.join(BAZA, "monitors_1700_template.html")
PROG_ZMIANY = 0.40          # udział, powyżej którego zmiana idzie do przejrzenia

sys.path.insert(0, BAZA)
from zbieraj_ceny import wczytaj                                    # noqa: E402


def znaczniki(nazwa):
    """Człony nazwy, które identyfikują model: zawierają cyfrę i mają co najmniej 3 znaki
    (9500F, 5060, 7800X3D, Q27G4ZR). Człony opisowe („Zestaw", „Monitor") pomijamy."""
    nazwa = re.sub(r"\(custom:[^)]*\)", " ", nazwa)
    return {t.upper() for t in re.findall(r"[A-Za-z0-9]{3,}", nazwa)
            if any(c.isdigit() for c in t)}


def ta_sama_rzecz(nasza, ze_strony, prog=0.5):
    """Czy adres nadal prowadzi do tego samego produktu. Brak nazwy ze strony nie
    blokuje zapisu (część sklepów jej nie podaje) — blokuje dopiero rozjazd członów."""
    if not ze_strony:
        return True
    a = znaczniki(nasza)
    if not a:
        return True
    b = znaczniki(ze_strony)

    def pasuje(t):
        # Sklepy zapisują ten sam SKU różnie: „LS27FG602EUXEN" u nas, „S27FG602EUX" na
        # stronie. Zawieranie się członów łapie takie warianty, a nadal odrzuca produkt
        # zupełnie inny, bo wymaga wspólnego rdzenia co najmniej pięcioznakowego.
        return any(t == x or (len(t) >= 5 and t in x) or (len(x) >= 5 and x in t)
                   for x in b)

    return sum(1 for t in a if pasuje(t)) / len(a) >= prog


def granice(sz):
    """Początek każdego wpisu DATA[]/PDATA[] — wpis kończy się tam, gdzie zaczyna następny."""
    p = [m.start() for m in re.finditer(r"\{img:'\d\d_[^']+', name:'", sz)]
    p += [m.start() for m in re.finditer(r'\{img:"p[^"]*", name:"', sz)]
    return sorted(p)


def podmien(seg, pole, wartosc):
    nowy, n = re.subn(r"(?<![A-Za-z])" + pole + r":\d+", f"{pole}:{wartosc}", seg, count=1)
    return nowy, n


def podmien_cene_sklepu(seg, sklep, wartosc):
    m = re.search(r"prices:\{([^}]*)\}", seg)
    if not m:
        return seg, 0
    tresc, n = re.subn(r"\b" + sklep + r":\d+", f"{sklep}:{wartosc}", m.group(1), count=1)
    if not n:
        return seg, 0
    return seg[:m.start(1)] + tresc + seg[m.end(1):], 1


def ustaw_soldout(seg, sklepy, cudz):
    """Dopisuje/zdejmuje soldout:[...]. Zdjęcie jest równie ważne jak dopisanie —
    inaczej plakietka „chwilowo niedostępne" wisiałaby po powrocie towaru."""
    m = re.search(r",\s*soldout:\[[^\]]*\]", seg)
    if not sklepy:
        return (seg[:m.start()] + seg[m.end():], 1) if m else (seg, 0)
    lista = ",".join(f"{cudz}{s}{cudz}" for s in sorted(sklepy))
    nowy = f", soldout:[{lista}]"
    if m:
        return (seg, 0) if m.group(0).strip() == nowy.strip() else \
               (seg[:m.start()] + nowy + seg[m.end():], 1)
    k = re.search(r"(?<![A-Za-z])price:\d+", seg)
    if not k:
        return seg, 0
    return seg[:k.end()] + nowy + seg[k.end():], 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zebrane", default=os.path.join(BAZA, "zebrane_ceny.json"))
    ap.add_argument("--na-sucho", action="store_true", help="pokaż zmiany, nie zapisuj")
    ap.add_argument("--data", default=None, help='np. "18 września 2026"')
    ap.add_argument("--prog", type=float, default=PROG_ZMIANY)
    a = ap.parse_args()

    zeb = json.load(open(a.zebrane, encoding="utf-8"))
    adresy = zeb["adresy"]
    w_nazwa = {k: v.get("nazwa", "") for k, v in adresy.items()}
    sz = open(SZABLON, encoding="utf-8").read()
    poz = wczytaj(sz)
    wg_img = {p["img"]: p for p in poz}

    # bazy dla wariantów custom: ten sam adres Hard-PC, nazwa bez „(custom:"
    baza_dla = {}
    grupy = {}
    for p in poz:
        for sklep, u in p["urls"].items():
            grupy.setdefault(u, []).append(p)
    for u, lista in grupy.items():
        bazy = [x for x in lista if "(custom:" not in x["name"]]
        if len(bazy) == 1:
            for x in lista:
                if x is not bazy[0]:
                    baza_dla[x["img"]] = bazy[0]

    zmiany, do_przejrzenia, dostepnosc, bez_bazy, inny_produkt = [], [], [], [], []

    for p in poz:
        nowe_ceny, niedostepne = {}, set()
        for sklep, u in p["urls"].items():
            w = adresy.get(f"{sklep}|{u}")
            if not w:
                continue
            if w["stan"] == "wycofany":
                niedostepne.add(sklep)
                continue
            if w["stan"] != "ok":
                continue
            if w.get("niedostepny"):
                niedostepne.add(sklep)
            nowe_ceny[sklep] = w["cena"]
        p["_nowe"], p["_niedostepne"] = nowe_ceny, niedostepne

    nowy_dok, koniec_poprz = [], 0
    punkty = granice(sz)
    for i, start in enumerate(punkty):
        stop = punkty[i + 1] if i + 1 < len(punkty) else len(sz)
        nowy_dok.append(sz[koniec_poprz:start])
        seg = sz[start:stop]
        koniec_poprz = stop

        img = re.search(r"\{img:['\"]([^'\"]+)['\"]", seg).group(1)
        p = wg_img.get(img)
        if not p:
            nowy_dok.append(seg)
            continue
        cudz = "'" if p["rodzaj"] == "monitor" else '"'

        for sklep, nowa in sorted(p["_nowe"].items()):
            stara = p["prices"].get(sklep)
            # wariant custom: pobrana cena dotyczy zestawu bazowego
            if "(custom:" in p["name"]:
                b = baza_dla.get(img)
                if b is None or p["priceBare"] is None or b["priceBare"] is None:
                    # Pobrana cena dotyczy zestawu BAZOWEGO. Bez jednoznacznej bazy nie
                    # da się policzyć dopłaty za pamięć, a zapisanie ceny bazy zaniżyłoby
                    # wariant o kilkaset złotych — po cichu. Lepiej zostawić starą cenę.
                    bez_bazy.append(p["name"])
                    continue
                nowa = nowa + (p["priceBare"] - b["priceBare"])
            if not ta_sama_rzecz(p["name"], w_nazwa.get(f"{sklep}|{p['urls'][sklep]}", "")):
                inny_produkt.append({"nazwa": p["name"], "sklep": sklep,
                                     "na_stronie": w_nazwa.get(f"{sklep}|{p['urls'][sklep]}", "")})
                continue
            if stara is None or nowa == stara:
                continue
            if nowa <= 0 or abs(nowa - stara) / stara > a.prog:
                do_przejrzenia.append({"nazwa": p["name"], "sklep": sklep,
                                       "stara": stara, "nowa": nowa,
                                       "zmiana_proc": round((nowa - stara) / stara * 100)})
                continue
            seg, n = podmien_cene_sklepu(seg, sklep, nowa)
            if not n:
                continue
            wpis = {"nazwa": p["name"], "rodzaj": p["rodzaj"], "sklep": sklep,
                    "stara": stara, "nowa": nowa, "roznica": nowa - stara}
            # nagłówek wpisu jedzie za sklepem źródłowym
            if p["prices"] and stara == p["price"] - (0 if p["rodzaj"] == "monitor"
                                                      else (p["price"] - (p["priceBare"] or p["price"]))):
                pass
            if p["rodzaj"] == "pc" and p["priceBare"] == stara:
                doplata = p["price"] - p["priceBare"]
                seg, _ = podmien(seg, "priceBare", nowa)
                seg, _ = podmien(seg, "price", nowa + doplata)
                wpis["naglowek"] = nowa + doplata
            elif p["rodzaj"] == "monitor" and p["price"] == stara:
                seg, _ = podmien(seg, "price", nowa)
                wpis["naglowek"] = nowa
            zmiany.append(wpis)

        stare_sold = set(p["soldout"])
        if p["_niedostepne"] != stare_sold and (p["_nowe"] or p["_niedostepne"]):
            seg, n = ustaw_soldout(seg, p["_niedostepne"], cudz)
            if n:
                dostepnosc.append({"nazwa": p["name"], "bylo": sorted(stare_sold),
                                   "jest": sorted(p["_niedostepne"])})
        nowy_dok.append(seg)
    nowy_dok.append(sz[koniec_poprz:])
    wynik = "".join(nowy_dok)

    if a.data:
        wynik = re.sub(r"var PRICE_CHECK_LABEL = '[^']*';",
                       f"var PRICE_CHECK_LABEL = '{a.data}';", wynik)

    licz = zeb.get("pobrano", {})
    raport = {
        "data": a.data or datetime.date.today().isoformat(),
        "pobrano": licz,
        "pokrycie_proc": round(licz.get("ok", 0) / max(1, sum(licz.values())) * 100),
        "zmian_cen": len(zmiany),
        "do_przejrzenia": do_przejrzenia,
        "zmiany_dostepnosci": dostepnosc,
        "warianty_bez_bazy": bez_bazy,
        "inny_produkt_pod_adresem": inny_produkt,
        "zmiany": zmiany,
    }

    print(f"pokrycie   : {licz.get('ok',0)}/{sum(licz.values())} ({raport['pokrycie_proc']}%)")
    print(f"zmian cen  : {len(zmiany)}   (monitory "
          f"{sum(1 for z in zmiany if z['rodzaj']=='monitor')}, PC "
          f"{sum(1 for z in zmiany if z['rodzaj']=='pc')})")
    print(f"dostępność : {len(dostepnosc)} zmian")
    print(f"do przejrzenia (powyżej {int(a.prog*100)}%): {len(do_przejrzenia)}")
    if bez_bazy:
        print(f"warianty bez zestawu bazowego (pominięte): {len(bez_bazy)}")
    if inny_produkt:
        print(f"adres prowadzi do innego produktu (pominięte): {len(inny_produkt)}")
        for x in inny_produkt[:6]:
            print(f"   nasza: {x['nazwa'][:52]}")
            print(f"   strona: {x['na_stronie'][:52]}")

    if a.na_sucho:
        print("\n--na-sucho: nic nie zapisano")
        for z in zmiany[:15]:
            print(f"   {z['roznica']:+6d} zł  {z['sklep']:11s} {z['nazwa'][:58]}")
        for z in do_przejrzenia[:10]:
            print(f"   [?] {z['zmiana_proc']:+4d}%  {z['sklep']:11s} {z['nazwa'][:52]} "
                  f"{z['stara']}→{z['nowa']}")
        for z in dostepnosc[:10]:
            print(f"   [d] {z['nazwa'][:52]}  {z['bylo']} → {z['jest']}")
        return

    open(SZABLON, "w", encoding="utf-8").write(wynik)
    json.dump(raport, open(os.path.join(BAZA, "raport_rano.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    dziennik = []
    plik = os.path.join(BAZA, "coverage_log.json")
    if os.path.exists(plik):
        dziennik = json.load(open(plik, encoding="utf-8"))
    dziennik.append({k: raport[k] for k in ("data", "pobrano", "pokrycie_proc",
                                            "zmian_cen")})
    json.dump(dziennik, open(plik, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nszablon zapisany; przebudowuję stronę")
    subprocess.run([sys.executable, os.path.join(BAZA, "build_merged.py")], check=True)


if __name__ == "__main__":
    main()
