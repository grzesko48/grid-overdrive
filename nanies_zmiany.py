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


def znaczniki_adresu(url):
    """Człony modelu z samego adresu (slug), bez numerycznych identyfikatorów sklepu."""
    slug = re.sub(r"\.(html?|bhtml)$", "", (url or "").rstrip("/").rsplit("/", 1)[-1])
    return {t for t in znaczniki(slug.replace("-", " ")) if not t.isdigit()}


def ta_sama_rzecz(nasza, ze_strony, prog=0.5, url=None):
    """Czy adres nadal prowadzi do tego samego produktu. Brak nazwy ze strony nie
    blokuje zapisu (część sklepów jej nie podaje) — blokuje dopiero rozjazd członów.

    Nasza nazwa bywa potoczna („Samsung Odyssey OLED G60SD"), a sklep podaje symbol
    producenta („…G6 OLED (LS27DG602SUXEN)") — ten sam monitor, zero wspólnych członów,
    więc strażnik blokował jego cenę przy KAŻDYM przebiegu przez miesiąc. Adres, pod
    którym zestaw dodano, też identyfikuje model; gdyby sklep przepisał identyfikator na
    inny SKU, zmieniłby się tytuł strony i ten test nadal by go odrzucił."""
    if not ze_strony:
        return True
    b = znaczniki(ze_strony)
    if url:
        z_adresu = znaczniki_adresu(url)
        if z_adresu and _pokrycie(z_adresu, b) >= prog:
            return True
    a = znaczniki(nasza)
    if not a:
        return True

    return _pokrycie(a, b) >= prog


def _pokrycie(a, b):
    """Jaka część członów z `a` ma odpowiednik w `b`."""
    def pasuje(t):
        # Sklepy zapisują ten sam SKU różnie: „LS27FG602EUXEN" u nas, „S27FG602EUX" na
        # stronie. Zawieranie się członów łapie takie warianty, a nadal odrzuca produkt
        # zupełnie inny, bo wymaga wspólnego rdzenia co najmniej pięcioznakowego.
        return any(t == x or (len(t) >= 5 and t in x) or (len(x) >= 5 and x in t)
                   for x in b)

    return sum(1 for t in a if pasuje(t)) / len(a) if a else 0


def granice(sz):
    """Początek każdego wpisu DATA[]/PDATA[] — wpis kończy się tam, gdzie zaczyna następny."""
    p = [m.start() for m in re.finditer(r"\{img:'\d{2,}_[^']+', name:'", sz)]
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


def doplata_ram(adresy, sklep, url):
    """Aktualna dopłata sklepu za rozbudowę do 32GB (z konfiguratora strony produktu) albo
    None, gdy dziś jej nie znamy. 66 wariantów „32GB RAM" trzymało dopłatę z dnia dodania
    (+899 zł) przez miesiąc, gdy sklep żądał już +1199 zł — wszystkie były o 300 zł za tanie."""
    w = adresy.get(f"{sklep}|{url}")
    if not w or w.get("stan") != "ok":
        return None
    return next((v for k, v in (w.get("opcje") or {}).items() if re.match(r"^32\s*GB", k)), None)


def odswiez_doplate_wariantu(seg, d):
    """Przepisuje dopłatę tam, gdzie jest zapisana jako tekst: pole, etykieta i zaleta."""
    nowy = re.sub(r"ramUpgradeCost:\d+", f"ramUpgradeCost:{d}", seg, count=1)
    nowy = re.sub(r'(customLabel:"\+ RAM 32GB \(\+)\d+( zł\)")', rf"\g<1>{d}\g<2>", nowy, count=1)
    nowy = re.sub(r"(RAM podniesiony do 32GB za dopłatą )\d+( zł)", rf"\g<1>{d}\g<2>", nowy, count=1)
    return nowy, nowy != seg


def ustaw_flage(seg, pole, wlacz):
    """Dopisuje albo zdejmuje flage typu `ukryty:1`. Zdejmowanie jest tak samo wazne jak
    dopisywanie: pozycja ma wrocic na strone sama, gdy towar wroci do sprzedazy."""
    m = re.search(r",\s*" + pole + r":1", seg)
    if not wlacz:
        return (seg[:m.start()] + seg[m.end():], 1) if m else (seg, 0)
    if m:
        return seg, 0
    k = re.search(r"(?<![A-Za-z])price:\d+", seg)
    if not k:
        return seg, 0
    return seg[:k.end()] + f", {pole}:1" + seg[k.end():], 1


def ustaw_sprzedawcow(seg, nowi, cudz):
    """Zapisuje `sprzedawcy:{mediamarkt:'Deluxury'}` — kto naprawdę sprzedaje towar, gdy
    sklep jest tylko pośrednikiem (marketplace). `nowi` to PEŁNY słownik po przebiegu:
    sklep, którego dziś nie udało się sprawdzić, zachowuje poprzedni wpis (wywołujący
    scala to z tym, co już jest). Pusty słownik zdejmuje pole."""
    m = re.search(r",\s*sprzedawcy:\{[^}]*\}", seg)
    if not nowi:
        return (seg[:m.start()] + seg[m.end():], 1) if m else (seg, 0)
    czesci = ",".join(f"{k}:{cudz}{v}{cudz}" for k, v in sorted(nowi.items()))
    nowy = f", sprzedawcy:{{{czesci}}}"
    if m:
        return (seg, 0) if m.group(0).strip() == nowy.strip() else \
               (seg[:m.start()] + nowy + seg[m.end():], 1)
    k = re.search(r"(?<![A-Za-z])price:\d+", seg)
    if not k:
        return seg, 0
    return seg[:k.end()] + nowy + seg[k.end():], 1


def czysty_sprzedawca(nazwa):
    """Nazwa sprzedawcy trafia do kodu strony — przepuszczamy tylko znaki bezpieczne."""
    return re.sub(r"[^0-9A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ .&-]", "", nazwa or "").strip()[:40]


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


def kontrola_zgodnosci(poz, wynik, adresy, odrzucone, baza_dla):
    """BRAMKA: cena zapisana na stronie musi być ceną, którą sklep faktycznie podał.

    Przez miesiąc 175 z 217 zestawów Hard-PC miało na żywej stronie cudzą cenę (mediana
    błędu 1700 zł), a żaden test tego nie widział: strażnik 40% porównywał dwie liczby
    z TEGO SAMEGO błędnego wpisu. Ta kontrola porównuje wynik z zewnętrznym faktem —
    odpowiedzią sklepu — osobno dla każdego wpisu. Wariant custom ma zachować swoją
    dopłatę względem zestawu bazowego. Rozbieżność przerywa przebieg PRZED zapisem."""
    nowe = wczytaj(wynik)
    if len(nowe) != len(poz):
        return [f"liczba wpisów zmieniła się: {len(poz)} → {len(nowe)}"]
    idx = {id(p): i for i, p in enumerate(poz)}
    bledy = []
    for i, (st, nw) in enumerate(zip(poz, nowe)):
        if st["name"] != nw["name"]:
            bledy.append(f"kolejność wpisów się zmieniła przy: {st['name'][:50]}")
            continue
        baza = baza_dla.get(st["start"])
        for sklep, cena in nw["prices"].items():
            u = nw["urls"].get(sklep)
            w = adresy.get(f"{sklep}|{u}")
            if (st["name"], sklep) in odrzucone:
                if cena != st["prices"].get(sklep):
                    bledy.append(f"{st['name'][:50]} [{sklep}]: zmieniono mimo odrzucenia")
                continue
            if not w or w["stan"] != "ok":
                if cena != st["prices"].get(sklep):
                    bledy.append(f"{st['name'][:50]} [{sklep}]: zmieniono bez odpowiedzi sklepu")
                continue
            if baza is None:
                if cena != w["cena"] and cena != st["prices"].get(sklep):
                    bledy.append(f"{st['name'][:50]} [{sklep}]: zapisano {cena}, sklep podał {w['cena']}")
            else:
                nb = nowe[idx[id(baza)]]
                d_opcji = doplata_ram(adresy, sklep, u)
                stara_dopl = (d_opcji if d_opcji is not None
                              else st["prices"].get(sklep, 0) - baza["prices"].get(sklep, 0))
                if cena - nb["prices"].get(sklep, 0) != stara_dopl:
                    bledy.append(f"{st['name'][:50]} [{sklep}]: dopłata wariantu się zmieniła")
    return bledy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zebrane", default=os.path.join(BAZA, "zebrane_ceny.json"))
    ap.add_argument("--na-sucho", action="store_true", help="pokaż zmiany, nie zapisuj")
    ap.add_argument("--data", default=None, help='np. "18 września 2026"')
    ap.add_argument("--dzis", action="store_true",
                    help="policz dzisiejszą datę po polsku. Robi to skrypt, a nie prompt "
                         "Routine — poprzednia wersja generowała nazwy miesięcy bez "
                         "polskich znaków i na stronę trafiało „18 wrzesnia 2026”.")
    ap.add_argument("--prog", type=float, default=PROG_ZMIANY)
    a = ap.parse_args()

    if a.dzis and not a.data:
        MIESIACE = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
                    "lipca", "sierpnia", "września", "października", "listopada",
                    "grudnia"]
        d = datetime.date.today()
        a.data = f"{d.day} {MIESIACE[d.month - 1]} {d.year}"
        print(f"data: {a.data}")

    zeb = json.load(open(a.zebrane, encoding="utf-8"))
    adresy = zeb["adresy"]
    w_nazwa = {k: v.get("nazwa", "") for k, v in adresy.items()}
    sz = open(SZABLON, encoding="utf-8").read()
    poz = wczytaj(sz)
    # Wpis wskazujemy POŁOŻENIEM w pliku, nigdy kluczem zdjęcia (patrz komentarz w wczytaj()).
    wg_start = {p["start"]: p for p in poz}

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
                    baza_dla[x["start"]] = bazy[0]

    zmiany, do_przejrzenia, dostepnosc, bez_bazy, inny_produkt = [], [], [], [], []
    sprzedawcy_zmiany, doplaty_ram = [], []
    ukryte, przywrocone, doplaty_os, pros_cen_zsynchronizowane = [], [], [], []

    # Cena systemu przestaje byc zamrozona stala. Byla nia i sie zestarzala: sklep podniosl
    # Windows 11 Home z 519 na 539 zl, a my przy 286 zestawach doliczalismy staria kwote,
    # wiec cena z systemem byla zanizona o 20 zl przy kazdym z nich. Konfigurator podaje te
    # kwote wprost, a strone produktu i tak pobieramy dla ceny — wiec bierzemy ja stamtad.
    def cena_systemu(p):
        for sklep, u in p["urls"].items():
            w = adresy.get(f"{sklep}|{u}") or {}
            for nazwa, kwota in (w.get("opcje") or {}).items():
                if "Windows 11 Home" in nazwa:
                    return kwota
        return None

    for p in poz:
        nowe_ceny, niedostepne = {}, set()
        for sklep, u in p["urls"].items():
            w = adresy.get(f"{sklep}|{u}")
            if not w:
                continue
            # Flagujemy wylacznie sklepy, ktore maja u nas cene. Adres bez ceny nie tworzy
            # wiersza na karcie, wiec flaga dla niego to smiec w danych.
            ma_cene = sklep in p["prices"]
            if w["stan"] == "wycofany":
                if ma_cene:
                    niedostepne.add(sklep)
                continue
            if w["stan"] != "ok":
                continue
            if w.get("niedostepny") and ma_cene:
                niedostepne.add(sklep)
            nowe_ceny[sklep] = w["cena"]
        p["_nowe"], p["_niedostepne"] = nowe_ceny, niedostepne
        # sprzedawca zewnętrzny: dla każdego sklepu, który dziś odpowiedział ceną, wiemy
        # na pewno — albo jest nazwa (marketplace), albo None (sprzedaje sam sklep)
        p["_sprzedawcy"] = {}
        for sklep, u in p["urls"].items():
            w = adresy.get(f"{sklep}|{u}")
            if w and w["stan"] == "ok" and sklep in p["prices"]:
                p["_sprzedawcy"][sklep] = czysty_sprzedawca(w.get("sprzedawca")) or None
        # Ukrywamy dopiero wtedy, gdy KAZDY sklep z cena jest potwierdzenie martwy.
        # Sklep, ktorego nie udalo sie sprawdzic (403, blokada), nie trafia do
        # `niedostepne`, wiec sam z siebie nigdy nie skasuje pozycji ze strony —
        # niewiedza nie moze udawac wiedzy.
        p["_ukryty"] = bool(p["prices"]) and all(s in niedostepne for s in p["prices"])

    nowy_dok, koniec_poprz = [], 0
    punkty = granice(sz)
    for i, start in enumerate(punkty):
        stop = punkty[i + 1] if i + 1 < len(punkty) else len(sz)
        nowy_dok.append(sz[koniec_poprz:start])
        seg = sz[start:stop]
        koniec_poprz = stop

        img = re.search(r"\{img:['\"]([^'\"]+)['\"]", seg).group(1)
        p = wg_start.get(start)
        if not p:
            nowy_dok.append(seg)
            continue
        cudz = "'" if p["rodzaj"] == "monitor" else '"'

        for sklep, nowa in sorted(p["_nowe"].items()):
            stara = p["prices"].get(sklep)
            # wariant custom: pobrana cena dotyczy zestawu bazowego
            if "(custom:" in p["name"]:
                b = baza_dla.get(p["start"])
                if b is None or p["priceBare"] is None or b["priceBare"] is None:
                    # Pobrana cena dotyczy zestawu BAZOWEGO. Bez jednoznacznej bazy nie
                    # da się policzyć dopłaty za pamięć, a zapisanie ceny bazy zaniżyłoby
                    # wariant o kilkaset złotych — po cichu. Lepiej zostawić starą cenę.
                    bez_bazy.append(p["name"])
                    continue
                d_opcji = doplata_ram(adresy, sklep, p["urls"][sklep])
                nowa = nowa + (d_opcji if d_opcji is not None
                               else p["priceBare"] - b["priceBare"])
                p["_doplata_ram"] = d_opcji
            if not ta_sama_rzecz(p["name"], w_nazwa.get(f"{sklep}|{p['urls'][sklep]}", ""),
                                 url=p["urls"][sklep]):
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

        if p["_sprzedawcy"]:
            ms = re.search(r"sprzedawcy:\{([^}]*)\}", seg)
            obecni = dict(re.findall(r"(\w+):['\"]([^'\"]*)['\"]", ms.group(1))) if ms else {}
            for sklep, kto in p["_sprzedawcy"].items():
                if kto:
                    obecni[sklep] = kto
                else:
                    obecni.pop(sklep, None)
            seg, n = ustaw_sprzedawcow(seg, obecni, cudz)
            if n:
                sprzedawcy_zmiany.append({"nazwa": p["name"], "sprzedawcy": obecni})
        if p.get("_doplata_ram") is not None and "(custom:" in p["name"]:
            seg, zm_d = odswiez_doplate_wariantu(seg, p["_doplata_ram"])
            if zm_d:
                doplaty_ram.append({"nazwa": p["name"], "doplata": p["_doplata_ram"]})
        stare_sold = set(p["soldout"])
        if p["_niedostepne"] != stare_sold and (p["_nowe"] or p["_niedostepne"]):
            seg, n = ustaw_soldout(seg, p["_niedostepne"], cudz)
            if n:
                dostepnosc.append({"nazwa": p["name"], "bylo": sorted(stare_sold),
                                   "jest": sorted(p["_niedostepne"])})
        # dopłata za system — tylko tam, gdzie zestaw jest sprzedawany bez niego
        if p["rodzaj"] == "pc" and p["priceBare"] is not None:
            nowa_os = cena_systemu(p)
            stara_os = p["price"] - p["priceBare"]
            if nowa_os and stara_os > 0 and nowa_os != stara_os:
                mb = re.search(r"(?<![A-Za-z])priceBare:(\d+)", seg)
                bare = int(mb.group(1)) if mb else p["priceBare"]
                seg, n = podmien(seg, "price", bare + nowa_os)
                if n:
                    doplaty_os.append({"nazwa": p["name"], "stara": stara_os,
                                       "nowa": nowa_os, "cena": bare + nowa_os})

        bylo_ukryte = bool(re.search(r",\s*ukryty:1", seg))
        if p.get("_ukryty") != bylo_ukryte:
            seg, n = ustaw_flage(seg, "ukryty", p.get("_ukryty"))
            if n:
                (ukryte if p["_ukryty"] else przywrocone).append(
                    {"nazwa": p["name"], "rodzaj": p["rodzaj"],
                     "sklepy": sorted(p["prices"])})

        # Pakiet naprawczy 3, 2.2: cena w price/priceBare zmienia się wyżej, ale
        # pros[] cytuje ją osobno w zdaniu "Spełnia kryteria zestawienia: ...,
        # w cenie X zł" — bez tego kroku X zamarza na starej dopłacie za Windows
        # (519 zł) na zawsze, bo nic innego tego tekstu nie dotyka (błąd znaleziony
        # 21.09 na 5 wpisach Hard-PC). Odtwarzamy X z AKTUALNEGO price w segmencie
        # (po wszystkich podmianach wyżej), więc naprawa działa też wtedy, gdy
        # cena w ogóle się dziś nie zmieniła — a wcześniej po prostu się rozjechała.
        if p["rodzaj"] == "pc":
            mprice = re.search(r"(?<![A-Za-z])price:(\d+)", seg)
            if mprice:
                stara_fraza = re.search(r"w cenie (\d+) zł", seg)
                seg, n = re.subn(r"w cenie \d+ zł", f"w cenie {mprice.group(1)} zł", seg)
                if n and stara_fraza and stara_fraza.group(1) != mprice.group(1):
                    pros_cen_zsynchronizowane.append({"nazwa": p["name"],
                        "bylo": stara_fraza.group(1), "jest": mprice.group(1)})
            # Ta sama usterka w notatce o systemie: „Cena bazowa (bez systemu): 5049 zl" stała
            # przy priceBare 5549 (notatka zamarzła przy pierwszym zapisie). Pole nie jest
            # pokazywane przy zwykłych zestawach, ale czyta je karta zestawu z nieznanym
            # systemem — a dane, które sobie przeczą, nie mają prawa leżeć w pliku.
            mb = re.search(r"(?<![A-Za-z])priceBare:(\d+)", seg)
            if mb:
                seg = re.sub(r"(Cena bazowa \(bez systemu\): )\d+( zl)", rf"\g<1>{mb.group(1)}\g<2>", seg, count=1)
        nowy_dok.append(seg)
    nowy_dok.append(sz[koniec_poprz:])
    wynik = "".join(nowy_dok)

    if a.data:
        wynik = re.sub(r"var PRICE_CHECK_LABEL = '[^']*';",
                       f"var PRICE_CHECK_LABEL = '{a.data}';", wynik)

    # Kiedy KAŻDY sklep był ostatnio naprawdę sprawdzony. Strona pokazuje to przy cenach
    # sklepów, które odrzucają automat: x-kom, Media Expert i RTV stały na cenach z 18.09,
    # a ogólna data „ostatnia weryfikacja" sugerowała, że wszystkie są świeże. Sklep
    # uznajemy za sprawdzony dziś, gdy co najmniej połowa jego adresów dała odpowiedź
    # (cena albo potwierdzone wycofanie); mniej to nie weryfikacja, tylko trafienie.
    wg_sklepu = {}
    for klucz, w in adresy.items():
        sk = klucz.split("|")[0]
        d = wg_sklepu.setdefault(sk, [0, 0])
        d[1] += 1
        d[0] += w["stan"] in ("ok", "wycofany")
    iso = datetime.date.today().isoformat()
    ms = re.search(r"var SHOP_VERIFIED = (\{[^;]*\});", wynik)
    weryf = json.loads(ms.group(1)) if ms else {}
    for sk, (ok_, wszystkie) in wg_sklepu.items():
        if wszystkie and ok_ / wszystkie >= 0.5:
            weryf[sk] = iso
    if ms:
        wynik = (wynik[:ms.start()] + "var SHOP_VERIFIED = " +
                 json.dumps(weryf, sort_keys=True) + ";" + wynik[ms.end():])
    wynik = re.sub(r"var PRICE_CHECK_ISO = '[^']*';", f"var PRICE_CHECK_ISO = '{iso}';", wynik)

    odrzucone = ({(x["nazwa"], x["sklep"]) for x in do_przejrzenia} |
                 {(x["nazwa"], x["sklep"]) for x in inny_produkt} |
                 {(n, s) for n in bez_bazy for s in ("hardpc", "goblinpc", "plugnplay",
                                                    "morele", "xkom", "mediamarkt")})
    niezgodne = kontrola_zgodnosci(poz, wynik, adresy, odrzucone, baza_dla)
    if niezgodne:
        print(f"\nBRAMKA ZGODNOŚCI NIE PRZESZŁA — {len(niezgodne)} wpisów ma cenę inną niż podał sklep:")
        for x in niezgodne[:15]:
            print("   ", x)
        print("nic nie zapisano; strona NIE zostanie opublikowana.")
        sys.exit(2)
    print("bramka zgodności: każda zapisana cena zgadza się z odpowiedzią sklepu")

    licz = zeb.get("pobrano", {})
    raport = {
        "data": a.data or datetime.date.today().isoformat(),
        "pobrano": licz,
        "pokrycie_proc": round(licz.get("ok", 0) / max(1, sum(licz.values())) * 100),
        "zmian_cen": len(zmiany),
        "do_przejrzenia": do_przejrzenia,
        "zmiany_dostepnosci": dostepnosc,
        "doplaty_systemu": doplaty_os,
        "ukryte": ukryte,
        "przywrocone": przywrocone,
        "warianty_bez_bazy": bez_bazy,
        "inny_produkt_pod_adresem": inny_produkt,
        "zmiany": zmiany,
        "pros_cen_zsynchronizowane": pros_cen_zsynchronizowane,
        "zmiany_sprzedawcow": sprzedawcy_zmiany,
        "doplaty_ram_wariantow": doplaty_ram,
        "wg_sklepu": {k: {"ok": v[0], "adresow": v[1]} for k, v in sorted(wg_sklepu.items())},
    }

    print(f"pokrycie   : {licz.get('ok',0)}/{sum(licz.values())} ({raport['pokrycie_proc']}%)")
    print(f"zmian cen  : {len(zmiany)}   (monitory "
          f"{sum(1 for z in zmiany if z['rodzaj']=='monitor')}, PC "
          f"{sum(1 for z in zmiany if z['rodzaj']=='pc')})")
    print(f"dostępność : {len(dostepnosc)} zmian")
    if pros_cen_zsynchronizowane:
        print(f"pros[] 'w cenie X zł' zsynchronizowane z price: {len(pros_cen_zsynchronizowane)}"
              f" (Pakiet 3, 2.2 — inaczej ten tekst zamarza na starej dopłacie za system)")
        for s in pros_cen_zsynchronizowane[:10]:
            print(f"   {s['bylo']} zł → {s['jest']} zł  {s['nazwa'][:58]}")
    if doplaty_os:
        k = {}
        for d in doplaty_os:
            k[(d["stara"], d["nowa"])] = k.get((d["stara"], d["nowa"]), 0) + 1
        print(f"dopłata za system: {len(doplaty_os)} zmian  " +
              "  ".join(f"{a}→{b} zł ×{n}" for (a, b), n in k.items()))
    print(f"ukryte     : {len(ukryte)} (brak jakiejkolwiek kupowalnej oferty)")
    for u in ukryte:
        print(f"   − [{u['rodzaj']}] {u['nazwa'][:62]}  sklepy: {', '.join(u['sklepy'])}")
    print(f"przywrócone: {len(przywrocone)}")
    for u in przywrocone:
        print(f"   + [{u['rodzaj']}] {u['nazwa'][:62]}")
    print(f"do przejrzenia (powyżej {int(a.prog*100)}%): {len(do_przejrzenia)}")
    if bez_bazy:
        print(f"warianty bez zestawu bazowego (pominięte): {len(bez_bazy)}")
    if doplaty_ram:
        print(f"dopłata za RAM w wariantach custom odświeżona z konfiguratora: {len(doplaty_ram)} "
              f"(teraz +{sorted({d['doplata'] for d in doplaty_ram})} zł)")
    if sprzedawcy_zmiany:
        print(f"sprzedawcy zewnętrzni (marketplace): {len(sprzedawcy_zmiany)} zmian")
    stare = [k for k, v in sorted(weryf.items()) if v < iso]
    if stare:
        print("sklepy bez dzisiejszej weryfikacji: " +
              ", ".join(f"{k} (ostatnio {weryf[k]})" for k in stare))
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
                                            "zmian_cen", "wg_sklepu")})
    json.dump(dziennik, open(plik, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # Oceny MUSZA isc za cenami. Dotad automat zmienial ceny i nie ruszal ocen, wiec
    # skladnik „oplacalnosc" (zalezny od ceny) rozjezdzal sie z kazdym przebiegiem:
    # przeliczenie na cenach sprzed dziewieciu dni przesuwalo 298 z 324 zestawow, srednio
    # o 6 miejsc. Skrypt konczy sie bledem, gdy test par sprzecznych nie przejdzie —
    # check=True przerywa wtedy caly przebieg i strona NIE zostaje opublikowana.
    print("\nhistoria cen i promocje")
    r_hist = subprocess.run([sys.executable, os.path.join(BAZA, "historia_cen.py")])
    if r_hist.returncode != 0:
        print("UWAGA: historia_cen.py zakończył się błędem (ceny zapisane normalnie, promocje niezaktualizowane)")
    print("\nszablon zapisany; przeliczam oceny")
    subprocess.run([sys.executable, os.path.join(BAZA, "przelicz_oceny.py"),
                    "--bez-przebudowy"], check=True)
    print("\nprzebudowuję stronę")
    subprocess.run([sys.executable, os.path.join(BAZA, "build_merged.py")], check=True)


if __name__ == "__main__":
    main()
