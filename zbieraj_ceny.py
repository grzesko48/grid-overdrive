#!/usr/bin/env python3
"""Zbiera ceny i dostępność ze wszystkich sklepów — deterministycznie, bez udziału modelu.

Dlaczego to istnieje: dotychczasowa Routine pobierała 50 cen narzędziem WebFetch, czyli
rękami modelu. Model bywa niesystematyczny i pokrycie spadało do 7-22 z 50, a commit
wyglądał identycznie przy 7 i przy 49 zebranych cenach. Zwykły skrypt albo pobierze stronę,
albo zgłosi błąd — nie ma trzeciej możliwości. Dzięki temu pokrycie przestaje być losowe,
a przy okazji obejmuje sekcję PC, której automat nie ruszał w ogóle.

Czyta pozycje wprost z szablonu (jedyne źródło prawdy), niczego nie zapisuje.
Wynik idzie do JSON-a, który dopiero drugi skrypt nanosi na dane.
"""
import argparse, json, os, re, sys, threading, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

BAZA = os.path.dirname(os.path.abspath(__file__))
SZABLON = os.path.join(BAZA, "monitors_1700_template.html")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")

# ---------------------------------------------------------------- czytanie danych

def _pole(seg, nazwa, cudz):
    m = re.search(nazwa + r":\{([^}]*)\}", seg)
    if not m:
        return {}
    tresc = m.group(1)
    if cudz == "'":
        pary = re.findall(r"(\w+):'([^']*)'", tresc) or re.findall(r"(\w+):(\d+)", tresc)
    else:
        pary = re.findall(r'(\w+):"([^"]*)"', tresc) or re.findall(r"(\w+):(\d+)", tresc)
    return dict(pary)


def wczytaj(sz):
    """Zwraca liste pozycji. Monitory maja pola w apostrofach, PC w cudzyslowach.

    Wpis konczy sie tam, gdzie zaczyna sie nastepny. Wczesniej czytalismy stale okno
    3000 znakow i krotki wpis „pozyczal" pola od sasiada — zestaw bez zadnej oferty
    MediaMarkt dostawal w ten sposob cudze soldout:["mediamarkt"]. Sciezka zapisu byla
    bezpieczna (granice() liczy ja poprawnie), ale odczyt klamal.
    """
    wzory = [("monitor", r"\{img:'(\d\d_[^']+)', name:'([^']+)'", "'"),
             ("pc", r'\{img:"(p[^"]*)", name:"([^"]*)"', '"')]
    trafienia = []
    for rodzaj, wzor, cudz in wzory:
        for m in re.finditer(wzor, sz):
            trafienia.append((m.start(), rodzaj, m.group(1), m.group(2), cudz))
    trafienia.sort()

    poz = []
    for i, (start, rodzaj, img, nazwa, cudz) in enumerate(trafienia):
        stop = trafienia[i + 1][0] if i + 1 < len(trafienia) else len(sz)
        seg = sz[start:stop]
        mc = re.search(r"(?<![A-Za-z])price:(\d+)", seg)
        if not mc:
            continue
        mp = re.search(r"prices:\{([^}]*)\}", seg)
        ceny = {k: int(v) for k, v in re.findall(r"(\w+):(\d+)", mp.group(1))} if mp else {}
        sold = re.search(r"soldout:\[([^\]]*)\]", seg)
        pb = re.search(r"priceBare:(\d+)", seg)
        poz.append({
            "rodzaj": rodzaj, "img": img, "name": nazwa,
            "price": int(mc.group(1)),
            "priceBare": int(pb.group(1)) if pb else None,
            "prices": ceny, "urls": _pole(seg, "urls", cudz),
            "soldout": re.findall(r"['\"](\w+)['\"]", sold.group(1)) if sold else [],
            "ukryty": bool(re.search(r"(?<![A-Za-z])ukryty:1", seg)),
        })
    return poz


# ---------------------------------------------------------------- pobieranie

class Tempo:
    """Minimalny odstęp między zapytaniami do tego samego hosta. Hard-PC przy sześciu
    równoległych wątkach odrzucał 52 z 219 zapytań kodem 429 — sklep nie jest wolniejszy,
    tylko pilnuje tempa. Dławimy per host, żeby nie spowalniać pozostałych sklepów."""
    def __init__(self, odstep=0.6):
        self.odstep, self.ostatnie, self.zamek = odstep, {}, threading.Lock()

    def czekaj(self, host):
        with self.zamek:
            t = time.time()
            nast = self.ostatnie.get(host, 0) + self.odstep
            self.ostatnie[host] = max(t, nast)
            spij = nast - t
        if spij > 0:
            time.sleep(spij)


TEMPO = Tempo()


def pobierz(url, prob=4):
    host = urllib.parse.urlparse(url).netloc
    ostatni = None
    for n in range(prob):
        TEMPO.czekaj(host)
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA,
                                                     "Accept-Language": "pl-PL,pl;q=0.9"})
            with urllib.request.urlopen(r, timeout=30) as o:
                return o.status, o.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and n < prob - 1:
                time.sleep(3 * (n + 1))          # ograniczenie tempa — czekamy i wracamy
                continue
            return e.code, ""
        except Exception as e:                      # timeout, DNS, reset
            ostatni = type(e).__name__
            time.sleep(1.5 * (n + 1))
    return None, ostatni or "blad"


def _liczba(x):
    if x is None:
        return None
    s = str(x).strip().replace(" ", "").replace(" ", "")
    s = s.replace(",", ".")
    s = re.sub(r"\.(?=\d{3}\b)", "", s)             # 1.299 -> 1299
    try:
        w = float(s)
    except ValueError:
        return None
    return int(round(w)) if 1 <= w <= 100000 else None


def z_jsonld(s):
    """Cena + dostępność z pierwszego obiektu z 'offers'. Tak podają x-kom, Morele,
    Hard-PC, GoblinPC, PlugNPlay i MediaMarkt."""
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', s, re.S):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:
            continue
        stos = d if isinstance(d, list) else [d]
        if isinstance(d, dict) and "@graph" in d:
            stos = d["@graph"]
        for o in stos:
            if not isinstance(o, dict) or "offers" not in o:
                continue
            of = o["offers"]
            of = of[0] if isinstance(of, list) and of else of
            if not isinstance(of, dict):
                continue
            c = _liczba(of.get("price") or of.get("lowPrice"))
            if c:
                return c, str(of.get("availability", ""))
    return None, ""


def z_ceneo(s, url):
    """Ceneo: oferty poszczególnych sklepów siedzą w atrybutach data-*.
    KONIECZNIE filtrujemy po data-ProductId — bez tego łapaliśmy oferty innych
    produktów ze strony (wychodziło „449 zł" przy monitorze za 880 zł)."""
    pid = re.search(r"/(\d+)", url)
    pid = pid.group(1) if pid else None
    naj = None
    for m in re.finditer(r'<[^>]*data-productid="(\d+)"[^>]*>', s, re.I):
        blok = s[m.start():m.start() + 4000]
        if pid and m.group(1) != pid:
            continue
        c = re.search(r'data-price="([\d.,]+)"', blok, re.I)
        if c:
            w = _liczba(c.group(1))
            if w and (naj is None or w < naj):
                naj = w
    return naj, ""


def z_mediamarkt(s):
    """MediaMarkt nie wystawia oferty produktu w zwykłym bloku ld+json — siedzi ona
    w osadzonym stanie strony. Oferta produktu jest OBIEKTEM ("offers":{...}), a oferty
    dodatkowe (ubezpieczenia, „Ochrona od awarii") leżą w TABLICY i mają pole "name".
    Ten rozróżnik jest jedynym pewnym — bez niego łapaliśmy 23 zł za ubezpieczenie."""
    m = re.search(r'"offers"\s*:\s*\{(?:(?!"name")[^{}])*?"price"\s*:\s*"?([\d.,]+)', s)
    if not m:
        return None, ""
    cena = _liczba(m.group(1))
    blok = s[m.start():m.start() + 600]
    dost = re.search(r'"availability"\s*:\s*"([^"]+)"', blok)
    return cena, dost.group(1) if dost else ""


def wyciagnij(sklep, url, s):
    if "ceneo.pl" in url:
        return z_ceneo(s, url)
    if "mediamarkt.pl" in url:
        return z_mediamarkt(s)
    return z_jsonld(s)


def nazwa_ze_strony(s):
    """Nazwa produktu widniejąca na stronie. Służy do sprawdzenia, czy adres nadal
    prowadzi do TEGO SAMEGO produktu: sklepy potrafią przypisać identyfikator ponownie
    do innego SKU, a wtedy pobralibyśmy cudzą cenę i nikt by tego nie zauważył."""
    for wz in (r"<h1[^>]*>(.*?)</h1>",
               r'"name"\s*:\s*"([^"]{5,160})"',
               r"<title[^>]*>(.*?)</title>"):
        m = re.search(wz, s, re.S)
        if m:
            t = re.sub(r"<[^>]+>", " ", m.group(1))
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) > 4:
                return t[:160]
    return ""


NIEDOSTEPNE = ("OutOfStock", "SoldOut", "Discontinued", "BackOrder")
SLOWA_BRAKU = ("niedostępny", "Niedostępny", "wycofan", "Produkt niedostępny",
               "chwilowo niedostępny", "brak w magazynie")


def zablokowane(url, s):
    """Ceneo po serii zapytań przestaje podawać oferty i zwraca wszystkim adresom tę samą
    ogólną stronę (~20 tys. znaków, zero atrybutów data-ShopUrl). To NIE jest informacja
    o produkcie, tylko o nas — musi trafić do luk w pokryciu, nigdy do danych."""
    return "ceneo.pl" in url and "data-ShopUrl" not in s


def bez_oferty(s):
    """Strona wraca z kodem 200, ale nie ma na niej żadnej oferty — produkt zdjęto ze
    sprzedaży. Odróżniamy to od zwykłego nietrafienia ekstraktora, bo to dwie różne
    informacje: pierwsza jest DANĄ o produkcie, druga LUKĄ w naszym narzędziu.
    Wymagamy obu przesłanek naraz, żeby nie uznać za wycofany produktu, którego cenę
    po prostu nie umiemy odczytać."""
    return '"offers"' not in s and any(w in s for w in SLOWA_BRAKU)

# ---------------------------------------------------------------- przebieg

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rodzaj", choices=["monitor", "pc", "wszystko"], default="wszystko")
    ap.add_argument("--limit", type=int, default=0, help="tylko N adresów — do testów")
    ap.add_argument("--watki", type=int, default=6)
    ap.add_argument("--ceneo", action="store_true",
                    help="dołącz adresy Ceneo (Media Expert, RTV). Domyślnie pomijane: "
                         "Ceneo blokuje seryjne zapytania, a sklepy te i tak dają 403 "
                         "pod własnym adresem — codzienny przebieg tylko ściągałby bana.")
    ap.add_argument("--wyjscie", default=os.path.join(BAZA, "zebrane_ceny.json"))
    a = ap.parse_args()

    sz = open(SZABLON, encoding="utf-8").read()
    poz = wczytaj(sz)
    if a.rodzaj != "wszystko":
        poz = [p for p in poz if p["rodzaj"] == a.rodzaj]

    # jeden adres = jedno pobranie, choćby wskazywało na niego wiele pozycji
    # (68 wariantów custom dzieli adres z zestawem bazowym)
    adresy, pominiete = {}, 0
    for p in poz:
        for sklep, u in p["urls"].items():
            if not u.startswith("http"):
                continue
            if "ceneo.pl" in u and not a.ceneo:
                pominiete += 1
                continue
            adresy.setdefault((sklep, u), []).append(p["img"])
    lista = sorted(adresy)
    if a.limit:
        lista = lista[:a.limit]

    if pominiete:
        print(f"pominięto {pominiete} odwołań do Ceneo (użyj --ceneo, żeby dołączyć)",
              file=sys.stderr)
    print(f"pozycji: {len(poz)}  |  unikalnych adresów: {len(adresy)}"
          f"{f' (pobieram {len(lista)})' if a.limit else ''}", file=sys.stderr)

    wyniki, licz = {}, {"ok": 0, "brak_ceny": 0, "wycofany": 0,
                       "zablokowane": 0, "blad": 0}

    def zadanie(klucz):
        sklep, u = klucz
        kod, s = pobierz(u)
        if kod != 200 or not s:
            return klucz, {"stan": "blad", "kod": kod, "szczegol": s or ""}
        cena, dost = wyciagnij(sklep, u, s)
        if not cena:
            if zablokowane(u, s):
                return klucz, {"stan": "zablokowane", "kod": kod}
            if bez_oferty(s):
                return klucz, {"stan": "wycofany", "kod": kod, "niedostepny": True}
            return klucz, {"stan": "brak_ceny", "kod": kod}
        return klucz, {"stan": "ok", "cena": cena, "nazwa": nazwa_ze_strony(s),
                       "niedostepny": any(x in dost for x in NIEDOSTEPNE),
                       "dostepnosc": dost.split("/")[-1]}

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.watki) as ex:
        for i, (klucz, w) in enumerate(ex.map(zadanie, lista), 1):
            wyniki[f"{klucz[0]}|{klucz[1]}"] = w
            licz[w["stan"]] = licz.get(w["stan"], 0) + 1
            if i % 50 == 0 or i == len(lista):
                print(f"  {i}/{len(lista)}  ok={licz['ok']} wycofane={licz['wycofany']} "
                      f"brak_ceny={licz['brak_ceny']} blad={licz['blad']} "
                      f"({time.time()-t0:.0f}s)", file=sys.stderr)

    json.dump({"pobrano": licz, "adresy": wyniki,
               "adres_do_pozycji": {f"{k[0]}|{k[1]}": v for k, v in adresy.items()}},
              open(a.wyjscie, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    razem = sum(licz.values())
    print(f"\nPOKRYCIE: {licz['ok']}/{razem} adresów "
          f"({round(licz['ok']/razem*100) if razem else 0}%)  → {a.wyjscie}", file=sys.stderr)


if __name__ == "__main__":
    main()
