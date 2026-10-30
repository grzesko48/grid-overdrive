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
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor

BAZA = os.path.dirname(os.path.abspath(__file__))
SZABLON = os.path.join(BAZA, "monitors_1700_template.html")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")

# Sam User-Agent nie wystarcza: z tego komputera x-kom oddaje komplet 57/57, a z maszyny
# w chmurze odrzucil wszystkie 57 zapytan. Roznica jest w adresie IP, ale zanim uznamy
# sklep za niedostepny, warto wygladac jak zwykla przegladarka — brak naglowkow Accept
# i Sec-Fetch-* to najtansza do usuniecia przyczyna takiego odsiewu.
NAGLOWKI = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}

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


class _Pusty:
    @staticmethod
    def group(_): return ""


_P = _Pusty()


def wczytaj(sz):
    """Zwraca liste pozycji. Monitory maja pola w apostrofach, PC w cudzyslowach.

    Wpis konczy sie tam, gdzie zaczyna sie nastepny. Wczesniej czytalismy stale okno
    3000 znakow i krotki wpis „pozyczal" pola od sasiada — zestaw bez zadnej oferty
    MediaMarkt dostawal w ten sposob cudze soldout:["mediamarkt"]. Sciezka zapisu byla
    bezpieczna (granice() liczy ja poprawnie), ale odczyt klamal.
    """
    wzory = [("monitor", r"\{img:'(\d{2,}_[^']+)', name:'([^']+)'", "'"),
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
            # `start` to jedyny klucz, który jednoznacznie wskazuje wpis. Klucz zdjęcia (`img`)
            # NIE jest unikalny: jedna obudowa to jedno zdjęcie, więc 290 z 360 zestawów dzieli
            # go z innym wpisem. Słownik po `img` oddawał każdemu segmentowi dane OSTATNIEGO
            # wpisu z tą obudową — i tak cena jednego zestawu trafiła do wszystkich Hunter 2.
            "start": start,
            "rodzaj": rodzaj, "img": img, "name": nazwa,
            "price": int(mc.group(1)),
            "priceBare": int(pb.group(1)) if pb else None,
            "prices": ceny, "urls": _pole(seg, "urls", cudz),
            "soldout": re.findall(r"['\"](\w+)['\"]", sold.group(1)) if sold else [],
            # Pola specyfikacji czytamy z segmentu TEGO wpisu. Szukanie ich po kluczu
            # zdjecia jest pulapka: 290 z 360 zestawow dzieli klucz z innym wpisem
            # (jeden obsluguje 62 pozycje), wiec find() po img zwraca cudze dane.
            "ram": (re.search(r'ram:"([^"]*)"', seg) or re.search(r"ram:'([^']*)'", seg) or _P).group(1) if re.search(r"ram:['\"]", seg) else "",
            "gpu": (re.search(r'gpu:"([^"]*)"', seg) or _P).group(1) if re.search(r'gpu:"', seg) else "",
            "ukryty": bool(re.search(r"(?<![A-Za-z])ukryty:1", seg)),
        })
    return poz


# ---------------------------------------------------------------- pobieranie

class Tempo:
    """Minimalny odstęp między zapytaniami do tego samego hosta, dobierany w biegu.

    Stały odstęp nie wystarcza: te same 0,6 s daje komplet 219/219 z tego komputera,
    a z maszyny w chmurze Hard-PC odrzucił 57 zapytań kodem 429 (pokrycie 88% → 75%).
    Limit zależy od tego, skąd pytamy, więc nie da się go zgadnąć z góry — zamiast
    zgadywać, po każdym 429 podwajamy odstęp DLA TEGO HOSTA i zostawiamy go już
    spowolnionego do końca przebiegu. Pozostałe sklepy chodzą pełnym tempem."""
    # Sufit 2 s, nie wiecej: Hard-PC ma 219 adresow, wiec 3 s dawaloby 11 minut zbierania,
    # a Bash w Routine ma twardy limit 10 minut. Lepiej stracic kilka adresow niz caly przebieg.
    def __init__(self, odstep=0.6, sufit=2.0):
        self.bazowy, self.sufit = odstep, sufit
        self.odstepy, self.ostatnie = {}, {}
        self.zamek = threading.Lock()

    def czekaj(self, host):
        with self.zamek:
            odstep = self.odstepy.get(host, self.bazowy)
            t = time.time()
            nast = self.ostatnie.get(host, 0) + odstep
            self.ostatnie[host] = max(t, nast)
            spij = nast - t
        if spij > 0:
            time.sleep(spij)

    def ustaw_minimum(self, host, sekundy):
        """Tempo wymuszone przez robots.txt sklepu — nigdy nie schodzimy poniżej."""
        with self.zamek:
            self.odstepy[host] = max(self.odstepy.get(host, self.bazowy), sekundy)

    def spowolnij(self, host):
        """Sklep powiedział „za szybko". Zwalniamy trwale, zamiast tylko ponawiać —
        samo ponowienie trafia w ten sam limit, bo reszta wątków dalej wali pełnym tempem."""
        with self.zamek:
            stary = self.odstepy.get(host, self.bazowy)
            nowy = min(stary * 2, self.sufit)
            self.odstepy[host] = nowy
            return stary, nowy


TEMPO = Tempo()


class Regulamin:
    """robots.txt każdego sklepu — czytamy go i stosujemy, zamiast zakładać, że wolno nam
    wszystko.

    Dwie rzeczy z niego bierzemy. Disallow: sklepy zamykają koszyki, konta i panele
    administracyjne; stron produktowych żaden z nich nie zamyka, ale sprawdzamy to przy
    każdym adresie, zamiast ufać jednorazowemu przeglądowi. Crawl-delay: PlugNPlay prosi
    o sekundę przerwy, a my pytaliśmy co 0,6 s — czyli szybciej, niż sklep sobie życzy.
    Prośba o wolniejsze tempo jest wiążąca tak samo jak zakaz.

    Gdy robots.txt jest niedostępny, zakładamy zgodę na strony produktowe — to jest
    zachowanie zgodne ze standardem, bo brak pliku oznacza brak ograniczeń."""

    def __init__(self):
        self.reguly, self.zamek = {}, threading.Lock()

    def _wczytaj(self, host):
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = urllib.request.Request(f"https://{host}/robots.txt", headers=NAGLOWKI)
            with urllib.request.urlopen(r, timeout=20) as o:
                rp.parse(o.read().decode("utf-8", "replace").splitlines())
        except Exception:
            rp.parse([])                     # brak pliku = brak ograniczen
        opoznienie = None
        try:
            opoznienie = rp.crawl_delay(UA)
        except Exception:
            pass
        if opoznienie:
            TEMPO.ustaw_minimum(host, float(opoznienie))
            print(f"  {host}: robots.txt prosi o {opoznienie}s przerwy — stosuję",
                  file=sys.stderr)
        return rp

    def wolno(self, url):
        host = urllib.parse.urlparse(url).netloc
        with self.zamek:
            if host not in self.reguly:
                self.reguly[host] = self._wczytaj(host)
            rp = self.reguly[host]
        try:
            return rp.can_fetch(UA, url)
        except Exception:
            return True


REGULAMIN = Regulamin()


def pobierz(url, prob=4):
    host = urllib.parse.urlparse(url).netloc
    ostatni = None
    for n in range(prob):
        TEMPO.czekaj(host)
        try:
            r = urllib.request.Request(url, headers=NAGLOWKI)
            with urllib.request.urlopen(r, timeout=30) as o:
                return o.status, o.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and n < prob - 1:
                stary, nowy = TEMPO.spowolnij(host)
                if nowy != stary:
                    print(f"  {host}: limit tempa — zwalniam {stary:.1f}s → {nowy:.1f}s",
                          file=sys.stderr)
                time.sleep(2 * (n + 1))
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
        for o in oferty_tablicowe(s) or []:
            c = _liczba(o.get("price")) if isinstance(o, dict) and "name" not in o else None
            if c:
                return c, str(o.get("availability", ""))
        return None, ""
    # grupa `[\d.,]+` zjada też przecinek JSON-a po liczbie: „7549.99," nie jest liczbą
    # i każda cena z groszami (.99) kończyła się jako „brak_ceny" — NITROPC na MediaMarkt.
    cena = _liczba(m.group(1).strip(".,"))
    blok = s[m.start():m.start() + 600]
    dost = re.search(r'"availability"\s*:\s*"([^"]+)"', blok)
    return cena, dost.group(1) if dost else ""


def oferty_tablicowe(s):
    """MediaMarkt, gdy towaru nie sprzedaje sam, pokazuje ofertę zewnętrznego sprzedawcy
    z marketplace jako TABLICĘ `"offers":[{"price":2811,"seller":{"name":"Deluxury"}}]`.
    Wcześniej parser znał tylko formę obiektu, więc 22 z 34 adresów MediaMarkt co przebieg
    kończyło się „brak_ceny", a strona miesiącami pokazywała ceny sprzed kilku tygodni
    (do 25% niższe od bieżących). Ubezpieczenia i dodatki w tej samej tablicy mają pole
    `name` — ofertę towaru rozpoznajemy po jego braku, jak w z_mediamarkt()."""
    i = s.find('"offers":[')
    if i < 0:
        return None
    i += len('"offers":') 
    gl = 0
    for j in range(i, min(len(s), i + 20000)):
        if s[j] == "[":
            gl += 1
        elif s[j] == "]":
            gl -= 1
            if gl == 0:
                try:
                    return json.loads(s[i:j + 1])
                except Exception:
                    return None
    return None


def sprzedawca_mediamarkt(s):
    """Nazwa zewnętrznego sprzedawcy, gdy oferta pochodzi z marketplace; None, gdy
    towar sprzedaje MediaMarkt sam (forma obiektu) albo gdy nie umiemy tego ustalić."""
    if re.search(r'"offers"\s*:\s*\{', s):
        return None
    for o in oferty_tablicowe(s) or []:
        if isinstance(o, dict) and "name" not in o and _liczba(o.get("price")):
            sp = o.get("seller")
            return sp.get("name") if isinstance(sp, dict) else None
    return None


# ---------------------------------------------------------------- promocje deklarowane przez sklep
# Rozpoznanie 30.10.2026 (workflow „rozpoznanie-promocji-sklepow"): x-kom, Morele i Hard-PC podają na stronie
# przecenionego produktu „najniższą cenę z 30 dni przed obniżką" (dyrektywa Omnibus). To jedyna wiarygodna cena
# odniesienia — „cena przekreślona" (old) bywa zawyżona. Morele dodatkowo pokazuje cenę „z kodem" (kampania
# Black Weeks): cena w JSON-LD to cena Z KODEM, a „cena bez kodu" jest osobno. Czytamy tylko to, co jest na
# stronie głównego produktu; brak pola = brak promocji (nie zero rabatu).
def _zl(txt):
    """„1 569,00 zł" → 1569 (zaokrąglone do pełnych złotych)."""
    if txt is None:
        return None
    s = re.sub(r"[^\d,.]", "", txt.replace("\xa0", " "))
    s = s.replace(",", ".")
    try:
        return int(round(float(s))) if s else None
    except ValueError:
        return None


def promo_ze_strony(sklep, url, s):
    """→ {"omn": najniższa cena z 30 dni | None, "bk": cena bez kodu | None, "kod": kod rabatowy | None}
    albo None, gdy strona nie deklaruje żadnej obniżki."""
    omn = bk = kod = None
    if sklep == "morele":
        m = re.search(r'data-testid="product-regular-price"[^>]*>\s*([\d\s\xa0.,]+?)\s*z', s)
        bk = _zl(m.group(1)) if m else None
        m = re.search(r'data-testid="product-lowest-price"[^>]*>\s*([\d\s\xa0.,]+?)\s*z', s)
        omn = _zl(m.group(1)) if m else None
        m = re.search(r'data-testid="product-discount-code"[^>]*>([^<]+)<', s)
        kod = m.group(1).strip() if m else None
    elif sklep == "xkom":
        m = re.search(r'Najniższa cena z 30 dni przed obniżką: <span[^>]*>([\d\s\xa0,]+)\s*zł', s)
        omn = _zl(m.group(1)) if m else None
        if omn is None:
            m = re.search(r'"minPriceInfo":\{"minPrice":(\d+(?:\.\d+)?)', s)
            omn = _zl(m.group(1)) if m else None
        m = re.search(r'<meta property="product:original_price:amount" content="([\d.]+)"', s)
        bk = _zl(m.group(1)) if m else None
    elif sklep == "hardpc":
        # promocja realna tylko, gdy jest odznaka -N% ORAZ Omnibus (sam „old" nie wystarcza — bywa zawyżony)
        if re.search(r'<p class="discount-a">Promocja <span>-\d+%</span></p>', s):
            m = re.search(r'<hr class="omnibus-price">\s*<span>Najniższa cena z 30 dni przed obniżką: ([^<]+)</span>', s)
            omn = _zl(m.group(1)) if m else None
    if omn is None and bk is None and kod is None:
        return None
    return {"omn": omn, "bk": bk, "kod": kod}


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


# `32GB (+899,00 zl)` w <option> konfiguratora sklepu. Czytamy to przy okazji, bo strona
# produktu i tak jest pobierana dla ceny — dodatkowe zapytanie kosztowaloby tyle samo, co
# zadne. Bierzemy TYLKO opcje z jawna kwota: „32GB" bez ceny znaczy, ze sklep jej nie podal,
# a nie ze rozszerzenie jest za darmo.
OPCJA_KONF = re.compile(
    r"<option[^>]*>\s*([^<(]{1,40}?)\s*\(\+\s*([\d\s \u00a0,.]+)\s*z[\u0142l]\s*\)", re.I)


def opcje_konfiguratora(s):
    """Co jeszcze sklep pozwala dolozyc do tego zestawu i za ile."""
    out = {}
    for nazwa, kwota in OPCJA_KONF.findall(s):
        w = _liczba(kwota)
        if w:
            out[re.sub(r"\s+", " ", nazwa).strip()] = w
    return out


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
    pusta = bool(re.search(r'"offers"\s*:\s*\[\s*\]', s))
    return ('"offers"' not in s or pusta) and any(w in s for w in SLOWA_BRAKU)

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
                       "zablokowane": 0, "robots": 0, "blad": 0}

    def zadanie(klucz):
        sklep, u = klucz
        if not REGULAMIN.wolno(u):
            return klucz, {"stan": "robots", "kod": None}
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
        wynik = {"stan": "ok", "cena": cena, "nazwa": nazwa_ze_strony(s),
                 "sprzedawca": sprzedawca_mediamarkt(s) if "mediamarkt.pl" in u else None,
                 "niedostepny": any(x in dost for x in NIEDOSTEPNE),
                 "dostepnosc": dost.split("/")[-1]}
        opcje = opcje_konfiguratora(s)
        if opcje:
            wynik["opcje"] = opcje
        try:
            pr = promo_ze_strony(sklep, u, s)
        except Exception:
            pr = None                                   # błąd odczytu promocji nigdy nie psuje ceny
        if pr:
            wynik["promo"] = pr
        return klucz, wynik

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.watki) as ex:
        for i, (klucz, w) in enumerate(ex.map(zadanie, lista), 1):
            wyniki[f"{klucz[0]}|{klucz[1]}"] = w
            licz[w["stan"]] = licz.get(w["stan"], 0) + 1
            if i % 50 == 0 or i == len(lista):
                print(f"  {i}/{len(lista)}  ok={licz['ok']} wycofane={licz['wycofany']} "
                      f"brak_ceny={licz['brak_ceny']} robots={licz['robots']} "
                      f"blad={licz['blad']} "
                      f"({time.time()-t0:.0f}s)", file=sys.stderr)

    json.dump({"pobrano": licz, "adresy": wyniki,
               "adres_do_pozycji": {f"{k[0]}|{k[1]}": v for k, v in adresy.items()}},
              open(a.wyjscie, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    wg_sklepu = {}
    for klucz, w in wyniki.items():
        wg_sklepu.setdefault(klucz.split("|")[0], {}).setdefault(w["stan"], 0)
        wg_sklepu[klucz.split("|")[0]][w["stan"]] += 1
    kody = {}
    for klucz, w in wyniki.items():
        if w["stan"] == "blad":
            s = klucz.split("|")[0]
            kody.setdefault(s, {}).setdefault(str(w.get("kod")), 0)
            kody[s][str(w.get("kod"))] += 1
    print("\nwedług sklepu:", file=sys.stderr)
    for s in sorted(wg_sklepu, key=lambda x: -wg_sklepu[x].get("ok", 0)):
        d = wg_sklepu[s]
        print(f"   {s:12s} ok={d.get('ok',0):4d} wycofane={d.get('wycofany',0):3d} "
              f"brak_ceny={d.get('brak_ceny',0):3d} blad={d.get('blad',0):3d}"
              f"   {kody.get(s, '') or ''}", file=sys.stderr)

    razem = sum(licz.values())
    print(f"\nPOKRYCIE: {licz['ok']}/{razem} adresów "
          f"({round(licz['ok']/razem*100) if razem else 0}%)  → {a.wyjscie}", file=sys.stderr)


if __name__ == "__main__":
    main()
