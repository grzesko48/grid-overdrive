#!/usr/bin/env python3
"""Adapter sklepu PlugNPlay (plugnplay.sklep.pl): gotowe komputery stacjonarne.

Zakres: tylko komputery. Sklep ma też kategorię „Monitor", ale zlecenie obejmuje wyłącznie PC,
więc lista_monitorow() zwraca [] bez żadnego żądania (patrz SKLEP_UWAGI).

Skąd bierzemy dane (nic nie jest zgadywane; brak pola = BrakDanych):
- cena i dostępność: dane strukturalne ld+json strony produktu (cena wariantu DOMYŚLNEGO);
- cpu, karta, RAM, dysk, zasilacz, obudowa: blok „DOKŁADNA SPECYFIKACJA" z opisu. TYTUŁY I SLUGI
  PLUGNPLAY BYWAJĄ MYLĄCO OGÓLNE („Komputer RTX 5060 Ti / AMD AM5 / 32GB DDR5 / 1TB"), więc
  służą wyłącznie do wykrycia sprzeczności (DDR4 w tytule przy DDR5 w specyfikacji = odrzucenie);
- procesor: w opisie stoi „wybrany wyżej", czyli wartość wybiera konfigurator — bierzemy opcję
  grupy „Procesor" bez dopłaty (= konfiguracja domyślna, na której liczona jest cena ze strony;
  NIE zawsze pierwszą: na stronach DDR4 pierwsza opcja ma „-150 zł");
- pamięć karty: z opisu („RTX 5070 12GB"), a gdy opis jej nie podaje — z opcji bez dopłaty grupy
  „Wersja karty (ilość VRAM)"; gdy opis i konfigurator się różnią, odrzucamy. Brak obu
  = tabela ocena_pc.JEDNA_PAMIEC_GB (modele istniejące w jednej wersji), inaczej BrakDanych;
- DDR5: tylko gdy potwierdza go specyfikacja (linia RAM albo własność „Platforma").

Pobieranie sieciowe wykonuje WOŁAJĄCY (funkcja `pobierz` z zbieraj_ceny); ten plik zawiera
funkcje czyste: adres + html → dane. Robots.txt PlugNPlay prosi o Crawl-delay 1 s (stosuje go
zbieraj_ceny.REGULAMIN); tu dodatkowo trzymamy zapisaną kopię reguł Disallow i nie prosimy o
żaden adres, który by je łamał.
"""
import html as htmllib
import json
import os
import re
import sys
import urllib.parse

BAZA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BAZA not in sys.path:
    sys.path.insert(0, BAZA)
import ocena_pc
from ocena_pc import BrakDanych
import nowe_pc

SKLEP = "plugnplay"
LOKALNIE = False
SKLEP_UWAGI = (
    "komputery: lista /kategoria-produktu/komputery (8 kafelków na stronę, ok. 17 stron; kolejne strony "
    "przez <link rel=next>, pełny przegląd idzie za rel=next do końca z twardym sufitem MAKS_STRON_TWARDO=40). "
    "Filtr „Platforma (DDR5)” jest po stronie JS, więc DDR5 odsiewamy po tytule kafelka (tylko jawne DDR4) "
    "i dopiero po specyfikacji karty; wstępnie tniemy też po cenie kafelka 5000–10000 zł (Windows jest w cenie, "
    "więc cena kafelka = cena bazowa) — to oszczędność żądań, cena_od/cena_do=None ją wyłączają. Karta produktu to "
    "konfigurator: cena i specyfikacja dotyczą wariantu domyślnego (opcje bez dopłaty: Procesor, Wersja "
    "karty VRAM, Gwarancja), dopłaty pozostałych opcji są w polu 'opcje' (klucz „Grupa: opcja”). "
    "Strona NIE podaje: EAN, symbolu producenta, słowa NVMe (jest „SSD M.2”), licencji Windows wprost "
    "(jest „zainstalowany i skonfigurowany system Windows 11” i brak opcji bez systemu). "
    "Monitory: sklep MA kategorię /pl/c/Monitor/48 (m.in. QHD OLED 240+ Hz), ale karta monitora "
    "nie ma tabeli parametrów (dodatkowe właściwości ld+json additionalProperty są puste, a parametry "
    "przekątnej, matrycy i Hz są tylko w prozie producenta), więc lista_monitorow() zwraca [] "
    "z powodu braku danych strukturalnych zamiast zgadywania."
)

HOST = "plugnplay.sklep.pl"
LISTA_PC = "https://plugnplay.sklep.pl/kategoria-produktu/komputery"
CENA_LISTY_OD, CENA_LISTY_DO = 5000, 10000      # wstępny przesiew po cenie kafelka [zł]; None = bez przesiewu
# MAKS_STRON_TWARDO: twardy sufit liczby stron listy PC (niezależny od argumentu wołającego).
# Argument maks_stron traktujemy jako dolną granicę, nie górną — lista_pc przechodzi
# wszystkie strony za rel=next / do pustej strony aż do twardego sufitu MAKS_STRON_TWARDO=40.
MAKS_STRON_TWARDO = 40
MAKS_ADRESOW = 400
CENA_OD, CENA_DO = 500, 100000                  # poza tym zakresem to błąd odczytu, nie komputer

# Kopia reguł z https://plugnplay.sklep.pl/robots.txt (30.10.2026), User-agent: *. Wzorce jak w
# standardzie (* i $), wygrywa najdłuższy pasujący. Crawl-delay 1 s stosuje zbieraj_ceny.REGULAMIN.
ROBOTS_REGULY = (
    ("Disallow", "/application"), ("Disallow", "/environment"),
    ("Allow", "/environment/cache/images"), ("Disallow", "/libraries"),
    ("Disallow", "/*/fav/add"), ("Disallow", "/*/p/comment/add"),
    ("Disallow", "/*/p/mail/recommend"), ("Disallow", "/*/p/q"),
    ("Disallow", "/*/reg"), ("Disallow", "/*/login"), ("Disallow", "/*/basket"),
    ("Disallow", "/*/searchquery"),
)

ETYKIETY_SPEC = ("Karta graficzna", "Procesor", "Chłodzenie", "Płyta główna", "RAM RGB", "RAM",
                 "Dysk SSD M.2", "Dysk SSD", "Dysk", "Zasilacz", "Obudowa")


# ------------------------------------------------------------------ drobne narzędzia
def robots_dozwolony(url, host, reguly):
    """Czy kopia reguł robots.txt (lista ("Allow"|"Disallow", wzorzec)) pozwala pobrać adres.
    Wzorce jak w standardzie: * oznacza dowolny ciąg, $ koniec; wygrywa najdłuższy pasujący."""
    p = urllib.parse.urlparse(url)
    if p.netloc and p.netloc != host:
        return False
    sciezka = (p.path or "/") + (("?" + p.query) if p.query else "")
    najlepsza_dl, wolno = -1, True
    for rodzaj, wzorzec in reguly:
        rx = "^" + re.escape(wzorzec).replace(r"\*", ".*").replace(r"\$", "$")
        if re.match(rx, sciezka) and len(wzorzec) > najlepsza_dl:
            najlepsza_dl, wolno = len(wzorzec), (rodzaj == "Allow")
    return wolno


def dozwolony(url):
    return robots_dozwolony(url, HOST, ROBOTS_REGULY)


def pierwsze_dozwolone_zdjecie(kandydaci, baza, host, reguly):
    """Pierwszy adres zdjęcia, którego pobranie nie łamie robots.txt sklepu (adresy na cudzych
    domenach, np. CDN, nie podlegają jego regułom). Adresy względne rozwijamy względem `baza`.
    BrakDanych, gdy żaden nie przechodzi — wołający pobiera zdjęcie, więc nie podamy mu zakazanego."""
    adresy = [urllib.parse.urljoin(baza, htmllib.unescape(c)) for c in kandydaci if isinstance(c, str) and c]
    for a in adresy:
        if urllib.parse.urlparse(a).netloc != host or robots_dozwolony(a, host, reguly):
            return a
    raise BrakDanych(f"brak zdjęcia do pobrania zgodnie z robots.txt (adresów: {len(adresy)}, "
                     f"{'wszystkie zabronione' if adresy else 'strona nie podaje żadnego'})")


def _tekst(x):
    """Fragment HTML → zwykły tekst: bez znaczników i encji, twarde spacje i odstępy złączone."""
    x = htmllib.unescape(re.sub(r"<[^>]+>", "", x or ""))
    return re.sub(r"\s+", " ", x.replace("\xa0", " ").replace("\u202f", " ")).strip()


def _zlote(txt):
    """„+1 000,00 zł" → 1000; „-100 zł" → -100; brak liczby → None."""
    m = re.search(r"([+-]?)\s*(\d[\d ]*)(?:[.,](\d{1,2}))?", _tekst(str(txt)))
    if not m:
        return None
    w = int(m.group(2).replace(" ", "")) + (int(m.group(3).ljust(2, "0")) / 100 if m.group(3) else 0)
    return int(round(-w if m.group(1) == "-" else w))


def _ld_json(s):
    """Wszystkie obiekty z bloków application/ld+json (także z @graph); błędny blok pomijamy."""
    wynik = []
    for m in re.finditer(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", s, re.S):
        try:
            d = json.loads(m.group(1).strip())
        except ValueError:
            continue
        for o in (d if isinstance(d, list) else [d]):
            if isinstance(o, dict):
                wynik.append(o)
                wynik.extend(x for x in o.get("@graph", []) if isinstance(x, dict))
    return wynik


# ------------------------------------------------------------------ lista z katalogu
def kafelki(s):
    """Kafelki produktów ze strony kategorii: [{id, nazwa, cena, adres}] w kolejności ze strony.
    Kafelek to <product-tile product-id name price …> z linkiem /pl/p/… w środku."""
    znaczniki = list(re.finditer(r"<product-tile\b([^>]*)>", s))
    wynik = []
    for i, m in enumerate(znaczniki):
        koniec = znaczniki[i + 1].start() if i + 1 < len(znaczniki) else len(s)
        atr = {k: htmllib.unescape(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', m.group(1))}
        h = re.search(r'href="(/pl/p/[^"#?]+)"', s[m.end():koniec])
        if not h or not atr.get("name"):
            continue
        wynik.append({"id": atr.get("product-id"), "nazwa": _tekst(atr["name"]), "cena": _zlote(atr.get("price")),
                      "adres": urllib.parse.urljoin("https://" + HOST, h.group(1))})
    return wynik


def nastepna_strona(s, url):
    """Adres z <link rel="next"> tej samej kategorii albo None."""
    for m in re.finditer(r"<link\b[^>]*>", s):
        znacznik = m.group(0)
        h = re.search(r'\bhref="([^"]+)"', znacznik)
        if not h or not re.search(r'\brel="next"', znacznik):
            continue
        nast = urllib.parse.urljoin(url, htmllib.unescape(h.group(1)))
        p = urllib.parse.urlparse(nast)
        if p.netloc == HOST and p.path.startswith("/kategoria-produktu/komputery"):
            return nast
    return None


def _wstepnie_ok(k, cena_od, cena_do):
    """Przesiew kafelka PRZED pobraniem karty. Odrzucamy tylko to, co karta na pewno by odrzuciła:
    jawne DDR4 (bez słowa DDR5) w tytule lub adresie oraz cenę spoza przedziału."""
    tekst = (k["nazwa"] + " " + urllib.parse.unquote(k["adres"])).upper()
    if "DDR4" in tekst and "DDR5" not in tekst:
        return False
    if k["cena"] is not None:
        if cena_od is not None and k["cena"] < cena_od:
            return False
        if cena_do is not None and k["cena"] > cena_do:
            return False
    return True


def lista_pc(pobierz, maks_stron=6, cena_od=CENA_LISTY_OD, cena_do=CENA_LISTY_DO, uwagi=None):
    """Adresy kart gotowych komputerów z kolejnych stron kategorii. `pobierz(url)` → (kod, html).
    Przechodzi WSZYSTKIE strony listy (za rel=next aż do pustej strony lub braku linku rel=next),
    z twardym sufitem MAKS_STRON_TWARDO=40 stron. Argument `maks_stron` jest traktowany jako
    dolna granica liczby stron, nie górna.
    Błąd 403 na pierwszej stronie zwraca [] i dopisuje uwagę; niepowodzenia na stronach >= 2
    są dopisywane do opcjonalnej listy `uwagi` zamiast połykania."""
    sufit = MAKS_STRON_TWARDO
    adresy, widziane, url = [], set(), LISTA_PC
    for nr in range(1, sufit + 1):
        if url in widziane:
            break
        widziane.add(url)
        if not dozwolony(url):
            if nr == 1:
                raise BrakDanych(f"lista PlugNPlay: adres zabroniony przez robots.txt: {url}")
            if uwagi is not None:
                uwagi.append(f"robots.txt zabrania: {url}")
            break
        kod, s = pobierz(url)
        if kod != 200:
            if nr == 1:
                if kod == 403:
                    if uwagi is not None:
                        uwagi.append(f"HTTP 403: {url}")
                    return []
                raise BrakDanych(f"lista PlugNPlay: HTTP {kod}")
            if uwagi is not None:
                uwagi.append(f"HTTP {kod}: {url}")
            break
        kafle = kafelki(s)
        if not kafle:
            if nr == 1:
                raise BrakDanych("lista PlugNPlay: niedostępne kafelki produktów — zmienił się układ strony "
                                 "(adapter do poprawy)")
            break
        for k in kafle:
            if k["adres"] not in adresy and dozwolony(k["adres"]) and _wstepnie_ok(k, cena_od, cena_do):
                adresy.append(k["adres"])
        url = nastepna_strona(s, url)
        if not url:
            break
    return adresy[:MAKS_ADRESOW]


def lista_monitorow(pobierz, maks_stron=6, uwagi=None):
    """Karta monitora nie ma tabeli parametrów (ld+json additionalProperty puste, proza). Bez żadnego żądania."""
    return []


def odczytaj_monitor(url, html):
    raise BrakDanych("PlugNPlay: adapter obsługuje tylko komputery (monitory poza zakresem)")


# ------------------------------------------------------------------ odczyt karty produktu
def specyfikacja(s):
    """Etykieta → wartość z bloku „DOKŁADNA SPECYFIKACJA". BrakDanych, gdy bloku nie ma."""
    m = re.search(r"DOK[ŁL]ADNA\s+SPECYFIKACJA", s, re.I)
    if not m:
        raise BrakDanych("niedostępny blok „DOKŁADNA SPECYFIKACJA” na stronie (to nie zestaw albo "
                         "zmienił się układ — adapter do poprawy)")
    seg = s[m.end():m.end() + 8000]
    ucieta = re.search(r"Jeśli potrzebujesz|</product-description>|<script", seg)
    if ucieta:
        seg = seg[:ucieta.start()]
    seg = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", seg)
    tekst = htmllib.unescape(re.sub(r"<[^>]+>", "", seg)).replace("\xa0", " ").replace("\u202f", " ")
    # zdarza się brak <br> między wierszami („Zasilacz: 650W … Obudowa: KRUX") — dzielimy po znanych etykietach
    tekst = re.sub(r"(?<=\S)[ \t]+(?=(?:%s):)" % "|".join(re.escape(e) for e in ETYKIETY_SPEC), "\n", tekst)
    pola, ostatnia = {}, None
    for linia in (re.sub(r"\s+", " ", l).strip() for l in tekst.split("\n")):
        if not linia:
            continue
        e = re.match(r"^([^:]{2,40}):\s*(.*)$", linia)
        if e:
            ostatnia = e.group(1).strip()
            pola.setdefault(ostatnia, e.group(2).strip())
        elif ostatnia and not pola.get(ostatnia):
            pola[ostatnia] = linia                  # wartość w następnym wierszu niż etykieta
    return pola


def opcje_konfiguratora(s):
    """Grupy opcji konfiguratora: {grupa: [(opcja, dopłata_zł | None), …]} w kolejności ze strony.
    Dopłata jest względem wariantu domyślnego (patrz domyslne()); None = strona jej nie podaje."""
    grupy = {}
    for m in re.finditer(r"<(radio|select)-variant-option\b(.*?)</\1-variant-option>", s, re.S):
        blok = m.group(2)
        nazwa = re.search(r'validation-name-label="([^"]*)"', blok)
        if not nazwa:
            continue
        if m.group(1) == "radio":
            wezly = re.findall(r'<input\b[^>]*type="radio"[^>]*>', blok)
        else:
            wezly = re.findall(r"<h-option\b(?!-)[^>]*>", blok)
        opcje = []
        for w in wezly:
            v = re.search(r'data-user-value="([^"]*)"', w)
            if not v:
                continue
            pm = re.search(r'data-price-modifier="([^"]*)"', w)
            opcje.append((_tekst(v.group(1)), _zlote(pm.group(1)) if pm else None))
        if opcje:
            grupy[_tekst(nazwa.group(1))] = opcje
    return grupy


def domyslne(grupy):
    """{grupa: opcja domyślna}. Domyślna jest JEDYNA opcja bez dopłaty (nie pierwsza: u sklepu
    bywa tak, że pierwsza ma „-150 zł”, a domyślna stoi druga). Zero albo kilka takich opcji =
    nie wiemy, na której konfiguracji liczona jest cena → BrakDanych."""
    wynik = {}
    for g, op in grupy.items():
        bez = [n for n, d in op if d in (None, 0)]
        if len(bez) != 1:
            raise BrakDanych(f"niejednoznaczna konfiguracja domyślna grupy {g!r}: opcji bez dopłaty jest "
                             f"{len(bez)} ({', '.join(bez) or 'brak'})")
        wynik[g] = bez[0]
    return wynik


def cena_i_dostepnosc(ld):
    """(cena zł, availability) z danych strukturalnych. Brak lub niejednoznaczność = BrakDanych."""
    ceny, dost = set(), set()
    for o in ld:
        of = o.get("offers")
        for x in (of if isinstance(of, list) else [of]):
            if not isinstance(x, dict):
                continue
            if x.get("price") not in (None, ""):
                c = _zlote(x["price"])
                if c:
                    ceny.add(c)
            if x.get("availability"):
                dost.add(str(x["availability"]).rsplit("/", 1)[-1])
    if not ceny:
        raise BrakDanych("brak ceny w danych strukturalnych strony")
    if len(ceny) > 1:
        raise BrakDanych(f"niejednoznaczna cena na stronie: {sorted(ceny)}")
    cena = ceny.pop()
    if not (CENA_OD <= cena <= CENA_DO):
        raise BrakDanych(f"cena {cena} zł poza wiarygodnym zakresem {CENA_OD}–{CENA_DO} zł")
    if not dost:
        raise BrakDanych("strona nie podaje dostępności")
    if len(dost) > 1:
        raise BrakDanych(f"niejednoznaczna dostępność na stronie: {sorted(dost)}")
    return cena, dost.pop()


def _platforma(ld):
    for o in ld:
        for p in o.get("additionalProperty", []) if isinstance(o.get("additionalProperty"), list) else []:
            if isinstance(p, dict) and p.get("name") == "Platforma":
                return _tekst(str(p.get("value", "")))
    return ""


def procesor(linia, dom):
    """Procesor wariantu domyślnego. „wybrany wyżej" = domyślna opcja grupy „Procesor"."""
    domyslny = next((v for k, v in dom.items() if k.strip().lower() == "procesor"), None)
    if linia and not re.search(r"wybran", linia, re.I):
        nazwa = lambda t: re.sub(r"\b(amd|intel|procesor)\b|\s+", "", t.lower())
        if domyslny and nazwa(domyslny) not in nazwa(linia) and nazwa(linia) not in nazwa(domyslny):
            raise BrakDanych(f"procesor w opisie ({linia!r}) różni się od domyślnego w konfiguratorze "
                             f"({domyslny!r})")
        cpu = linia
    elif domyslny:
        cpu = domyslny
    else:
        raise BrakDanych("procesor wybierany w konfiguratorze, a strona nie ma grupy „Procesor”")
    cpu = re.sub(r"\s+", " ", cpu).strip()
    ocena_pc.klasa_cpu(cpu)                  # brak reguły klasy = BrakDanych
    return cpu


def dokladny_klucz_gpu(surowa):
    """Zwraca dokładny klucz z ocena_pc.KLASA_GPU albo None.
    Usuwa markę (NVIDIA GeForce, AMD Radeon, Intel), pamięć VRAM i nawiasy/odstępy."""
    t = re.sub(r"\b\d{1,2}\s*GB\b", "", surowa or "", flags=re.I)
    t = re.sub(r"\b(nvidia\s+geforce|geforce|amd\s+radeon|radeon|intel)\b", "", t, flags=re.I)
    t = re.sub(r"[()]", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t if t in ocena_pc.KLASA_GPU else None


def karta(linia, dom):
    """(gpu kanoniczny, źródło pamięci). Pamięć: opis → konfigurator → tabela JEDNA_PAMIEC_GB."""
    linia = _tekst(linia)
    if re.search(r"\b(SUPER|GRE|XTX)\b", linia, re.I):
        raise BrakDanych(f"karta z nieobsługiwanym przyrostkiem w {linia!r}")
    m = re.search(r"(\d{1,2})\s*GB", linia, re.I)
    z_opisu = int(m.group(1)) if m else None
    z_konf = None
    for nazwa, opcja in dom.items():
        if re.search(r"vram|pami[eę]ć karty|wersja karty", nazwa, re.I):
            m2 = re.search(r"(\d{1,2})\s*GB", opcja, re.I)
            z_konf = int(m2.group(1)) if m2 else None
    if z_opisu and z_konf and z_opisu != z_konf:
        raise BrakDanych(f"pamięć karty w opisie ({z_opisu} GB) różni się od domyślnej w konfiguratorze "
                         f"({z_konf} GB): {linia!r}")
    if z_opisu:
        gb, zrodlo = z_opisu, "opis"
    elif z_konf:
        gb, zrodlo = z_konf, "konfigurator"
    else:
        klucz = dokladny_klucz_gpu(linia)
        if not klucz:
            raise BrakDanych(f"karta spoza słownika klas: {linia!r} (brak dokładnego dopasowania w KLASA_GPU)")
        if klucz in ocena_pc.JEDNA_PAMIEC_GB:
            gb, zrodlo = ocena_pc.JEDNA_PAMIEC_GB[klucz], "tabela jednej wersji pamięci"
        else:
            raise BrakDanych(f"brak pamięci karty ({linia!r}): opis jej nie podaje, a konfigurator nie ma "
                             f"wyboru VRAM")
    gpu = nowe_pc.gpu_kanoniczna(linia if z_opisu else f"{linia} {gb}GB", {})
    if re.search(r"\bTi\b", linia, re.I) and not re.search(r"\bTi\b", gpu, re.I):
        raise BrakDanych(f"utracony przyrostek Ti przy kanonizacji karty: {linia!r}")
    if re.search(r"\bXT\b", linia, re.I) and not re.search(r"\bXT\b", gpu, re.I):
        raise BrakDanych(f"utracony przyrostek XT przy kanonizacji karty: {linia!r}")
    klucz_gpu = dokladny_klucz_gpu(gpu)
    if not klucz_gpu:
        raise BrakDanych(f"karta spoza słownika klas: {gpu!r} (brak dokładnego dopasowania w KLASA_GPU)")
    ocena_pc.klasa_gpu(gpu)                  # brak klasy = BrakDanych
    return gpu, zrodlo


def pamiec_ram(linia, platforma, tytul):
    """„32GB DDR5 6000MHz". DDR5 musi wynikać ze specyfikacji; DDR4 gdziekolwiek = odrzucenie."""
    linia = _tekst(linia)
    if re.search(r"DDR4", f"{linia} {platforma} {tytul}", re.I):
        raise BrakDanych(f"pamięć DDR4 (opis RAM {linia!r}, platforma {platforma!r}, tytuł {tytul!r})")
    if not re.search(r"DDR5", f"{linia} {platforma}", re.I):
        raise BrakDanych(f"specyfikacja nie potwierdza DDR5 (RAM {linia!r}, platforma {platforma!r})")
    m = re.match(r"^\s*(\d+)\s*GB", linia, re.I)
    gb = int(m.group(1)) if m else None
    if gb is None:
        m = re.search(r"(\d+)\s*[xX]\s*(\d+)\s*GB", linia)
        gb = int(m.group(1)) * int(m.group(2)) if m else None
    if gb is None:
        m = re.search(r"(\d+)\s*GB", linia, re.I)
        gb = int(m.group(1)) if m else None
    if not gb:
        raise BrakDanych(f"brak pojemności RAM w {linia!r}")
    mhz = re.search(r"(\d{4,5})\s*MH?z", linia, re.I)
    return f"{gb}GB DDR5" + (f" {mhz.group(1)}MHz" if mhz else "")


def dysk(etykieta, linia):
    """„1TB SSD M.2" — zapis wiernie według strony (NVMe tylko, gdy strona to mówi)."""
    linia = _tekst(linia)
    if re.search(r"\bbrak\b", linia, re.I):
        raise BrakDanych(f"brak dysku w zestawie: {linia!r}")
    if "+" in linia:
        raise BrakDanych(f"złożona konfiguracja dysków (+): {linia!r}")
    if re.search(r"\d+\s*[xX]", linia):
        raise BrakDanych(f"wielokrotny dysk ({linia!r}) — niejednoznaczna konfiguracja")
    opis = f"{etykieta} {linia}"
    if re.search(r"\bHDD\b", opis, re.I) and re.search(r"\bSSD\b", opis, re.I):
        raise BrakDanych(f"dysk zawiera jednocześnie SSD i HDD: {opis!r}")
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(TB|GB)", linia, re.I)
    if not m:
        raise BrakDanych(f"dysk bez pojemności: {linia!r}")
    liczba = m.group(1).replace(",", ".")
    liczba = liczba[:-2] if liczba.endswith(".0") else liczba
    if re.search(r"\bSSD\b", opis, re.I):
        typ = "SSD"
    elif re.search(r"\bHDD\b", opis, re.I):
        typ = "HDD"
    else:
        raise BrakDanych(f"nie wiadomo, czy dysk to SSD czy HDD: {etykieta!r} {linia!r}")
    dopisek = " NVMe" if re.search(r"NVMe", opis, re.I) else " M.2" if re.search(r"M\.2", opis, re.I) else ""
    return f"{liczba}{m.group(2).upper()} {typ}{dopisek}"


def zasilacz(linia):
    """„650W 80 Plus Bronze" → tak samo; sama moc, gdy certyfikatu nie ma."""
    linia = _tekst(linia)
    m = re.match(r"^(\d{3,4})\s*W\b\s*(.*)$", linia, re.I)
    if not m:
        raise BrakDanych(f"brak mocy zasilacza w {linia!r}")
    c = re.search(r"80\s*(?:\+|plus)\s*(?:White|Bronze|Silver|Gold|Platinum|Titanium)?", m.group(2), re.I)
    certyfikat = re.sub(r"\s+", " ", c.group(0)).strip() if c else ""
    return f"{m.group(1)}W" + (f" {certyfikat}" if certyfikat else "")


def system(ld, grupy):
    """Informacja o systemie operacyjnym wprost ze strony; nieznana → wartości None."""
    opis = " ".join(_tekst(str(o.get("description"))) for o in ld if o.get("description"))
    m = re.search(r"system\s+(Windows\s*\d+)", opis, re.I)
    if not m:
        return {"w_cenie": None, "doplata": None, "nazwa": None}
    nazwa = re.sub(r"\s+", " ", m.group(1)).replace("Windows1", "Windows 1")
    if any(re.search(r"windows|system operacyjny", g, re.I) for g in grupy):
        return {"w_cenie": None, "doplata": None, "nazwa": nazwa}      # konfigurator ma wybór systemu — nie rozstrzygamy
    return {"w_cenie": True, "doplata": 0, "nazwa": nazwa}


def zdjecie_url(s, ld):
    kandydaci = []
    for m in re.finditer(r"<meta\b[^>]*>", s):
        if re.search(r'property="og:image"', m.group(0)):
            c = re.search(r'content="([^"]+)"', m.group(0))
            if c:
                kandydaci.append(c.group(1))
    for o in ld:
        img = o.get("image")
        kandydaci.extend(img if isinstance(img, list) else [img])
    return pierwsze_dozwolone_zdjecie(kandydaci, "https://" + HOST + "/", HOST, ROBOTS_REGULY)


def _sprzedawca(ld):
    """Nazwa sprzedawcy innego niż sam sklep; None, gdy sprzedaje PlugNPlay."""
    for o in ld:
        akcja = o.get("potentialAction")
        sp = akcja.get("seller") if isinstance(akcja, dict) else None
        nazwa = sp.get("name") if isinstance(sp, dict) else None
        if nazwa and "plugnplay" not in nazwa.lower():
            return nazwa
    return None


def _krotko_gpu(g):
    return re.sub(r"^(NVIDIA GeForce|AMD Radeon)\s+", "", g)


def widoczna_cena_brutto(html):
    """Cena oferty brutto z bloku js__special-offer-price-value w panelu js__product-price-gross."""
    m_gross = re.search(r"<h-tab-panel\b[^>]*\bclass=[\"\x27][^\"]*js__product-price-gross[^\"]*[\"\x27][^>]*>(.*?)</h-tab-panel>", html, re.S)
    blok = m_gross.group(1) if m_gross else html
    m = re.search(r"class=[\"\x27][^\"]*js__special-offer-price-value[^\"]*[\"\x27][^>]*>(.*?)</span>", blok, re.S)
    if not m:
        raise BrakDanych("niedostępna widoczna cena oferty (js__special-offer-price-value) — zmienił się układ strony")
    c = _zlote(m.group(1))
    if c is None:
        raise BrakDanych("niedostępna wartość liczbowej ceny w bloku js__special-offer-price-value")
    return c


def odczytaj_pc(url, html):
    """Karta produktu → słownik wariantu domyślnego (klucze jak w kontrakcie adapterów).
    BrakDanych, gdy czegokolwiek brakuje, jest niejednoznaczne albo nie pasuje do zakresu."""
    ld = _ld_json(html)
    cena, dostepnosc = cena_i_dostepnosc(ld)
    if dostepnosc != "InStock":
        raise BrakDanych(f"nie ma w sprzedaży (availability = {dostepnosc})")
    widoczna = widoczna_cena_brutto(html)
    if widoczna != cena:
        raise BrakDanych(f"rozbieżność ceny: ld+json ({cena} zł) różni się od widocznej ceny oferty ({widoczna} zł)")
    spec = specyfikacja(html)
    grupy = opcje_konfiguratora(html)
    dom = domyslne(grupy)
    brak = [e for e in ("Karta graficzna", "Procesor", "Zasilacz") if not spec.get(e)]
    linia_ram = spec.get("RAM") or spec.get("RAM RGB")
    dyski = [k for k in spec if k.startswith("Dysk")]
    if len(dyski) > 1:
        raise BrakDanych(f"więcej niż jedna etykieta dysku w specyfikacji ({dyski}) — niejednoznaczna konfiguracja")
    etykieta_dysku = dyski[0] if dyski else None
    if not linia_ram:
        brak.append("RAM")
    if not etykieta_dysku:
        brak.append("Dysk")
    if brak:
        raise BrakDanych(f"w specyfikacji nie ma pól: {', '.join(brak)}")

    cpu = procesor(spec["Procesor"], dom)
    gpu, zrodlo_vram = karta(spec["Karta graficzna"], dom)
    tytul = _tekst(next(iter(re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S)), ""))
    ram = pamiec_ram(linia_ram, _platforma(ld), tytul)
    nosnik = dysk(etykieta_dysku, spec[etykieta_dysku])
    psu = zasilacz(spec["Zasilacz"])
    obudowa = spec.get("Obudowa") or None
    czesci = [cpu, _krotko_gpu(gpu), ram.split(" DDR5")[0] + " DDR5", nosnik] + ([obudowa] if obudowa else [])
    opcje = {f"{g}: {n}": (d or 0) for g, op in grupy.items() for n, d in op if n != dom[g]}
    return {
        "nazwa": "PlugNPlay | " + ", ".join(czesci), "url": url,
        "cpu": cpu, "gpu": gpu, "ram": ram, "storage": nosnik, "psu": psu, "obudowa": obudowa,
        "cena_bazowa": cena, "system": system(ld, grupy), "dostepny": True,
        "sprzedawca": _sprzedawca(ld), "zdjecie": zdjecie_url(html, ld), "ean": None,
        "opcje": opcje, "domyslne": dom, "vram_zrodlo": zrodlo_vram,
    }
