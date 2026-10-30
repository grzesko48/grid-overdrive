#!/usr/bin/env python3
"""Adapter sklepu x-kom (www.x-kom.pl): monitory QHD 26–28" 240–500 Hz i gotowe komputery DDR5.

x-kom odpowiada tylko z komputera właściciela (z chmury daje 403), więc LOKALNIE = True. Gdy
sklep odmawia (kod ≠ 200 albo błąd sieci), listy zwracają [] i nic się nie wywraca; strona listy
z kodem 200, ale bez listy produktów (zmiana układu, ekran blokady), to BrakDanych z opisem.

Skąd bierzemy dane (nic nie jest zgadywane; brak pola = BrakDanych):
- LISTY: strona kategorii zawiera w stanie aplikacji (JSON) uporządkowaną listę produktów
  `listingContainer` i dla każdego krótkie podsumowanie cech (`featureSummary`: przekątna,
  rozdzielczość, matryca, Hz — dla komputerów karta, procesor, RAM w GB, system, dysk) razem
  z ceną i dostępnością. Przesiew po liście odrzuca tylko to, co karta NA PEWNO by odrzuciła
  (jawna sprzeczność); pozycja bez podsumowania (sklep czasem nie dołącza go do wszystkich
  kafelków) przechodzi i o jej losie decyduje karta;
- KARTY: dane strukturalne ld+json (nazwa, kod producenta, cena, zdjęcie) oraz pełna
  specyfikacja ze stanu strony (obiekt produktu → `features`: klucz → wartości). Cena z ld+json
  (bieżąca, także promocyjna — tę samą czyta zbieraj_ceny) musi być ceną regularną albo
  promocyjną ze stanu strony, inaczej odrzucenie;
  Klucze addytywne kart (gdy produkt objęty promocją z kodem): `cena_bez_kodu` (cena regularna bez kodu),
  `kod_rabatowy` (kod promocyjny), `kod_do` (termin ważności promocji);
- dostępność: ld+json (jeśli ją podaje) ORAZ `availabilityStatus` ze stanu strony; wycofany
  produkt (np. status „Unavailable") = BrakDanych, nie wpis z flagą;
- komputery: x-kom sprzedaje każdą wersję systemu jako OSOBNĄ kartę (brak systemu / Windows 11
  Home / Pro). Karta opisuje jedną konfigurację; dopłaty do innych wersji systemu bierzemy z
  grupy „System operacyjny" (alternativeProducts) jako różnicę cen kart i opisujemy w `opcje`.

Pobieranie sieciowe wykonuje WOŁAJĄCY (funkcja `pobierz` z zbieraj_ceny); ten plik zawiera
funkcje czyste: adres + html → dane. Robots.txt x-kom (30.10.2026) dla `*` zakazuje m.in.
/konto, /koszyk, /zamowienie, /p//*; trzymamy jego kopię (ROBOTS_REGULY) i nie prosimy o żaden
adres, który by ją łamał.

UWAGA do decyzji właściciela: robots.txt x-kom zawiera wpis „User-agent: mozilla/5" z
„Disallow: /" (obok wielu wpisów dla starych przeglądarek i narzędzi). urllib.robotparser
dopasowuje agentów po pierwszym członie nazwy („mozilla”), więc ani UA zbieraj_ceny, ani
„Mozilla/5.0 (compatible; GridOverdriveBot)” tego wpisu nie dostają i obowiązuje grupa „*”
(zakazy tylko dla koszyka, konta itp.). Dosłowne dopasowanie po fragmencie napisu dałoby inny
wynik — interpretacja jest sporna, a adapter działa wyłącznie lokalnie, na komputerze właściciela.
"""
import html as htmllib
import json
import math
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

SKLEP = "xkom"
LOKALNIE = True
SKLEP_UWAGI = (
    "monitory: kategoria Monitory + filtr WQHD (90/stronę), przesiew po podsumowaniu cech z listy "
    "(rozdzielczość, Hz, przekątna); komputery: kategoria Desktopy + „Dla graczy” + typ RAM DDR5 "
    "(UDIMM, DIMM, DDR5; zapis z przecinkiem gubi drugą wartość, więc trzy przebiegi), przesiew po "
    "karcie, procesorze i cenie z uwzględnieniem min(cena, cena_promocyjna) oraz zwijaniem wariantów "
    "systemu do jednej karty na konfigurację sprzętową. Karty: specyfikacja ze stanu strony. Sklep nie "
    "podaje EAN ani sprzedawcy zewnętrznego (sprzedawca = None). Hz: bierzemy natywne (bez OC), OC tylko w nazwie "
    "matrycy. Promocje z kodem: klucze addytywne cena_bez_kodu, kod_rabatowy, kod_do. "
    "System: każda wersja to osobna karta; `opcje` = dopłata do innych wersji systemu. "
    "Z chmury 403 → listy puste."
)

HOST = "www.x-kom.pl"
ADRES = "https://" + HOST
LISTA_MONITOROW = (ADRES + "/g-6/c/15-monitory.html?per_page=90"
                   "&f100098-rozdzielczosc-ekranu=1045868-2560-x-1440-wqhd")
SCIEZKA_MONITOROW = "/g-6/c/15-monitory"
# Filtr „Typ pamięci RAM" przyjmuje jedną wartość naraz (przecinek odrzuca drugą), a DDR5 jest
# opisany trzema wartościami. UDIMM i DIMM to prawie wszystkie komputery; „DDR5" ma kilka pozycji.
# SO-DIMM (laptopy, mini-PC) i R-DIMM (stacje robocze) pomijamy świadomie.
TYPY_RAM_DDR5 = ("1178996-udimm-ddr5", "1178991-dimm-ddr5", "1179012-ddr5")
LISTY_PC = tuple(ADRES + "/g-2/c/1708-desktopy.html?per_page=90"
                 "&f100934-przeznaczenie-produktu=1135938-dla-graczy&f102486-typ-pamieci-ram=" + t
                 for t in TYPY_RAM_DDR5)
SCIEZKA_PC = "/g-2/c/1708-desktopy"

MAKS_STRON_TWARDO = 20      # sufit niezależny od argumentu wołającego [stron listy]
MAKS_ADRESOW = 400          # sufit wyniku jednej listy [adresów kart]

HZ_OD, HZ_DO = 240, 500
DIAG_OD, DIAG_DO = 26.0, 28.0
CENA_MONITORA_OD, CENA_MONITORA_DO = 500, 6000        # jak nowe_monitory: poza tym to błąd odczytu
CENA_PC_OD, CENA_PC_DO = 500, 100000                  # j.w. dla karty komputera
# Przesiew listy komputerów po cenie [zł]: te same progi co nowe_pc (decyzja właściciela 21.10.2026).
# Cena karty ≥ ceny bez systemu, więc cena < 5000 nie da zestawu ≥ 5000 bez systemu, a cena > 10000
# nie zmieści się pod sufitem z Windowsem — przesiew odrzuca tylko to, co na pewno odpadnie.
CENA_LISTY_PC_OD = nowe_pc.CENA_OD_BEZ_SYSTEMU
CENA_LISTY_PC_DO = nowe_pc.SUFIT_Z_WINDOWS

MARKI = {"asus": "ASUS", "msi": "MSI", "aoc": "AOC", "lg": "LG", "hp": "HP", "dell": "Dell",
         "acer": "Acer", "benq": "BenQ", "aorus": "AORUS"}

# Kopia reguł z https://www.x-kom.pl/robots.txt (30.10.2026), User-agent: *. Pominięty pierwszy
# wiersz „Disallow:" (pusty = brak zakazu): w parserach „pierwsza reguła wygrywa" unieważniałby
# resztę. Wzorce jak w standardzie (* i $), wygrywa najdłuższy pasujący.
ROBOTS_REGULY = (
    ("Disallow", "/src/"), ("Allow", "/src/templates/default/img/"), ("Allow", "/src/banners/"),
    ("Disallow", "/dane-do-zamowien"), ("Disallow", "/konto"), ("Disallow", "/koszyk"),
    ("Disallow", "/listy"), ("Disallow", "/logowanie/"), ("Disallow", "/opinie"),
    ("Disallow", "/przypomnienie-hasla"), ("Disallow", "/ustawienia-konta"),
    ("Disallow", "/zamowienia"), ("Disallow", "/zamowienie"), ("Disallow", "/zmiana-hasla"),
    ("Disallow", "/basket.php"), ("Disallow", "/gen/"), ("Disallow", "/files/"),
    ("Disallow", "/file/"), ("Disallow", "/http*"), ("Disallow", "/www.*"), ("Disallow", "/p//*"),
    ("Disallow", "/p/index.php*"), ("Disallow", "/lp/intel_ssd/*"), ("Disallow", "/www*"),
    ("Disallow", "/xkom*"),
)

_DEKODER = json.JSONDecoder()


# ------------------------------------------------------------------ drobne narzędzia
def dozwolony(url):
    """Czy robots.txt (kopia w ROBOTS_REGULY) pozwala pobrać ten adres."""
    p = urllib.parse.urlparse(url)
    if p.netloc and p.netloc != HOST:
        return False
    sciezka = (p.path or "/") + (("?" + p.query) if p.query else "")
    najlepsza_dl, wolno = -1, True
    for rodzaj, wzorzec in ROBOTS_REGULY:
        rx = "^" + re.escape(wzorzec).replace(r"\*", ".*").replace(r"\$", "$")
        if re.match(rx, sciezka) and len(wzorzec) > najlepsza_dl:
            najlepsza_dl, wolno = len(wzorzec), (rodzaj == "Allow")
    return wolno


def _tekst(x):
    """Tekst bez twardych spacji, ™/® i podwójnych odstępów."""
    t = htmllib.unescape(str(x)).replace("\xa0", " ").replace("™", "").replace("®", "")
    return re.sub(r"\s+", " ", t).strip()


def _zl(x):
    """Cena w pełnych złotych albo None. Liczba skończona i dodatnia, inaczej None (nigdy NaN/inf)."""
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, (int, float)):
        v = float(x)
    elif isinstance(x, str):
        try:
            v = float(x.replace("\xa0", "").replace(" ", "").replace(",", "."))
        except ValueError:
            return None
    else:
        return None
    return int(round(v)) if math.isfinite(v) and v > 0 else None


def _liczba(txt):
    m = re.search(r"\d+(?:[.,]\d+)?", txt or "")
    return float(m.group(0).replace(",", ".")) if m else None


def _jsonld(s):
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', s, re.S):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:
            continue
        for o in (d if isinstance(d, list) else [d]):
            if isinstance(o, dict):
                yield o


def _encja(s, pid, pierwsze_klucze):
    """Obiekt stanu strony zapisany pod kluczem `"<pid>":{"<pierwszy klucz>"…`. None, gdy brak.
    Pierwszy klucz odróżnia pełny obiekt produktu od krótkich wpisów o tym samym identyfikatorze
    (np. {"courierAvailabilityText":…})."""
    for klucz in pierwsze_klucze:
        znacznik = f'"{pid}":{{"{klucz}"'
        i = s.find(znacznik)
        if i >= 0:
            try:
                obiekt, _ = _DEKODER.raw_decode(s, i + len(f'"{pid}":'))
            except ValueError:
                continue
            if isinstance(obiekt, dict):
                return obiekt
    return None


def _id_z_adresu(url):
    m = re.search(r"/p/(\d+)-", urllib.parse.urlparse(url).path)
    if not m:
        raise BrakDanych(f"adres nie jest kartą produktu x-kom (brak /p/<id>-): {url!r}")
    return m.group(1)


def _oferta(ld):
    of = ld.get("offers")
    of = of[0] if isinstance(of, list) and of else of
    return of if isinstance(of, dict) else {}


def _karta(url, s):
    """(ld+json produktu, obiekt produktu ze stanu strony, cechy) albo BrakDanych. Pilnuje, żeby
    strona opisywała produkt z adresu (sklep potrafi przekierować na inny)."""
    if not isinstance(s, str) or not s:
        raise BrakDanych("strona niedostępna: pusta strona produktu")
    pid = _id_z_adresu(url)
    ld = next((o for o in _jsonld(s) if o.get("@type") == "Product"), None)
    if ld is None:
        raise BrakDanych("strona niedostępna: strona bez danych produktu (JSON-LD Product)")
    ld_id = ld.get("productID") or ld.get("sku")
    if not ld_id:
        raise BrakDanych("strona niedostępna: brak productID/sku w danych JSON-LD")
    if str(ld_id) != pid:
        raise BrakDanych(f"strona niedostępna: strona opisuje produkt {ld_id}, a adres wskazuje {pid}")
    encja = _encja(s, pid, ("isFetching",))
    if not encja or not isinstance(encja.get("features"), list):
        raise BrakDanych("strona niedostępna: strona bez specyfikacji produktu w stanie aplikacji — zmienił się układ")
    cechy = {}
    for f in encja["features"]:
        if isinstance(f, dict) and f.get("key"):
            cechy[_tekst(f["key"])] = [_tekst(v.get("name")) for v in f.get("values") or []
                                       if isinstance(v, dict) and v.get("name")]
    return ld, encja, cechy


def _dostepnosc(ld, encja):
    """Towar musi być nowy (NewCondition, nie outlet) i w sprzedaży wg ld+json i stanu strony."""
    of = _oferta(ld)
    cond = str(of.get("itemCondition", "") or ld.get("itemCondition", ""))
    if cond and not cond.endswith("NewCondition"):
        raise BrakDanych(f"towar nie jest nowy (itemCondition={cond.rsplit('/', 1)[-1]})")
    if encja.get("isOutlet"):
        raise BrakDanych("towar z outletu (isOutlet=True)")
    dost = str(of.get("availability", ""))
    if dost and not dost.endswith("InStock"):
        raise BrakDanych(f"nie ma w sprzedaży (availability={dost.rsplit('/', 1)[-1]})")
    status = encja.get("availabilityStatus")
    if status != "Available":
        raise BrakDanych(f"nie ma w sprzedaży (availabilityStatus={status!r})")


def _cena(ld, encja, od, do):
    cena = _zl(_oferta(ld).get("price"))
    if not cena:
        raise BrakDanych("brak ceny")
    # Cena z ld+json to cena bieżąca (tę samą czyta zbieraj_ceny.z_jsonld). W stanie strony leży
    # cena regularna (`price`, `priceInfo.price`) i, w trakcie akcji, promocyjna
    # (`promotionInfo.discountedPrice`); cena z ld+json musi być jedną z nich.
    stan = {_zl(encja.get("price")), _zl((encja.get("priceInfo") or {}).get("price")),
            _zl((encja.get("promotionInfo") or {}).get("discountedPrice"))} - {None}
    if stan and cena not in stan:
        raise BrakDanych(f"strona niedostępna: ceny na stronie się różnią: ld+json {cena} zł, stan strony {sorted(stan)} zł")
    if not (od <= cena <= do):
        raise BrakDanych(f"cena {cena} zł poza wiarygodnym zakresem {od}–{do} zł")
    return cena


def _promo_info(ld, encja, cena):
    """(cena_bez_kodu, kod_rabatowy, kod_do) z danych promocji karty albo (None, None, None)."""
    prom = encja.get("promotionInfo") or {}
    kod = prom.get("code")
    kod_do = prom.get("promotionEndDate")
    of = _oferta(ld)
    pspec = of.get("priceSpecification") or []
    if isinstance(pspec, dict):
        pspec = [pspec]
    cena_lp = next((_zl(p.get("price")) for p in pspec
                    if isinstance(p, dict) and str(p.get("priceType", "")).endswith("ListPrice")), None)
    cena_bk = cena_lp or _zl((encja.get("priceInfo") or {}).get("price"))
    if kod or (cena_bk and cena_bk != cena):
        return cena_bk, kod, kod_do
    return None, None, None


def _zdjecie(ld):
    img = ld.get("image")
    img = img[0] if isinstance(img, list) and img else img
    if isinstance(img, dict):
        img = img.get("url")
    if not isinstance(img, str) or not img.startswith("http"):
        raise BrakDanych("brak zdjęcia na stronie produktu")
    # szablon adresu zdjęcia: {SEO} to dowolny napis, pusty działa (sprawdzone na cdn.x-kom.pl)
    return htmllib.unescape(img).replace("{SEO}", "")


def _jedna_wartosc(wartosci, nazwa_pola):
    if not wartosci:
        raise BrakDanych(f"brak pola „{nazwa_pola}”")
    if len(wartosci) > 1:
        raise BrakDanych(f"pole „{nazwa_pola}” ma kilka wartości {wartosci} — niejednoznaczne")
    return wartosci[0]


def _jedna(cechy, klucz):
    return _jedna_wartosc(cechy.get(klucz), klucz)


def _podsumowanie(encja):
    """featureSummary z listy ('Klucz: a, b') → {klucz: [wartości]}; None, gdy kafelek go nie ma."""
    ps = encja.get("featureSummary")
    if not isinstance(ps, list):
        return None
    wynik = {}
    for p in ps:
        if isinstance(p, str) and ":" in p:
            k, v = p.split(":", 1)
            # wartości rozdziela przecinek Z ODSTĘPEM; przecinek dziesiętny („26,5”") odstępu nie ma
            wynik[_tekst(k)] = [_tekst(x) for x in re.split(r",\s+", v.strip()) if _tekst(x)]
    return wynik


# ------------------------------------------------------------------ wspólne: przejście list
def pozycje_listy(s):
    """Strona kategorii → lista słowników {id, url, nazwa, cena, dostepny, cechy, alternativeGroupId}.
    `cechy` to podsumowanie z kafelka albo None. `cena` uwzględnia min(cena_regularna, cena_promocyjna).
    BrakDanych, gdy strony nie da się odczytać jako lista."""
    if not isinstance(s, str):
        raise BrakDanych("strona niedostępna: lista x-kom: pusta odpowiedź")
    m = re.search(r'"listingContainer":(\[[^\]]*\])', s)
    if not m:
        raise BrakDanych("strona niedostępna: lista x-kom: brak listy produktów w stanie strony — zmienił się układ "
                         "albo to ekran blokady (adapter do poprawy)")
    try:
        wpisy = json.loads(m.group(1))
    except ValueError:
        raise BrakDanych("strona niedostępna: lista x-kom: nieczytelna lista produktów")
    poz, widziane = [], set()
    for w in wpisy:
        pid = str(w.get("id", "")) if isinstance(w, dict) else ""
        if not re.fullmatch(r"\d+", pid) or pid in widziane:
            continue
        widziane.add(pid)
        e = _encja(s, pid, ("featureSummary", "availabilityStatus"))
        link = urllib.parse.urlparse(e.get("productLink", "")).path if e else ""
        if not re.match(r"/p/%s-" % pid, link):
            continue                                  # brak adresu karty — nie ma czego pobrać
        status = e.get("availabilityStatus")
        regularna = _zl(e.get("price"))
        promocyjna = _zl((e.get("promotionInfo") or {}).get("discountedPrice"))
        ceny = [c for c in (regularna, promocyjna) if c is not None]
        cena = min(ceny) if ceny else None
        poz.append({"id": pid, "url": ADRES + link,
                    "nazwa": _tekst(e.get("fullName") or e.get("descriptiveProductName") or ""),
                    "cena": cena,
                    "dostepny": None if status is None else status == "Available",
                    "cechy": _podsumowanie(e),
                    "alternativeGroupId": e.get("alternativeGroupId") if e else None})
    return poz


def _nastepna_strona(s, sciezka):
    """Adres z <link rel="next"> tej samej kategorii albo None."""
    for m in re.finditer(r"<link\b[^>]*>", s):
        znacznik = m.group(0)
        h = re.search(r'\bhref="([^"]+)"', znacznik)
        if not h or not re.search(r'\brel="next"', znacznik):
            continue
        nast = urllib.parse.urljoin(ADRES + "/", htmllib.unescape(h.group(1)))
        p = urllib.parse.urlparse(nast)
        if p.netloc == HOST and p.path.startswith(sciezka):
            return nast
    return None


def _zwijaj_warianty_pc(kandydaci):
    """Zwija warianty systemu tego samego komputera z listy.
    Klucz konfiguracji: (alternativeGroupId, Procesor, Grafika, Pamięć RAM, Dysk).
    Zostawia kartę z Windows 11 Home, a Pro i Brak systemu pomija, gdy w grupie jest Home.
    Brak systemu zostawia tylko wtedy, gdy Home nie ma."""
    grupy = {}
    pojedyncze = []
    for p in kandydaci:
        c = p.get("cechy")
        if not c:
            pojedyncze.append(p["url"])
            continue
        alt_id = p.get("alternativeGroupId")
        k = (alt_id,
             tuple(c.get("Procesor") or []),
             tuple(c.get("Grafika") or []),
             tuple(c.get("Pamięć RAM") or []),
             tuple(c.get("Dysk") or []))
        grupy.setdefault(k, []).append(p)
    wynik = set(pojedyncze)
    for k, lista in grupy.items():
        home = next((p for p in lista if any(re.search(r"Windows 11 Home\b", s, re.I)
                                             for s in (p.get("cechy") or {}).get("System") or [])), None)
        if home:
            wynik.add(home["url"])
        else:
            bez_sys = next((p for p in lista if any(re.search(r"brak\b", s, re.I)
                                                    for s in (p.get("cechy") or {}).get("System") or [])), None)
            if bez_sys:
                wynik.add(bez_sys["url"])
            else:
                wynik.add(lista[0]["url"])
    return wynik


def _przejdz(adresy_startowe, sciezka, pobierz, maks_stron, powod_odrzucenia, zwijaj=None):
    """Przechodzi kolejne strony każdej listy startowej (najwyżej `maks_stron` na listę).
    Błąd pobrania (403 z chmury, brak sieci) kończy daną listę bez wyjątku."""
    maks_stron = max(1, min(int(maks_stron), MAKS_STRON_TWARDO))
    kandydaci, wynik_prosty, obejrzane, odwiedzone = [], set(), set(), set()
    for start in adresy_startowe:
        url = start
        for _ in range(maks_stron):
            if url is None or url in odwiedzone or not dozwolony(url):
                break
            odwiedzone.add(url)
            kod, s = pobierz(url)
            if kod != 200 or not s:
                break
            nowych = 0                       # pozycje, których nie widzieliśmy na wcześniejszych stronach
            for p in pozycje_listy(s):
                if p["url"] in obejrzane or not dozwolony(p["url"]):
                    continue
                obejrzane.add(p["url"])
                nowych += 1
                if powod_odrzucenia(p) is None:
                    if zwijaj:
                        kandydaci.append(p)
                    else:
                        wynik_prosty.add(p["url"])
            liczba_zebranych = len(kandydaci) if zwijaj else len(wynik_prosty)
            if nowych == 0 or liczba_zebranych >= MAKS_ADRESOW:
                break
            url = _nastepna_strona(s, sciezka)
    wynik = zwijaj(kandydaci) if zwijaj else wynik_prosty
    return sorted(wynik)[:MAKS_ADRESOW]


# ------------------------------------------------------------------ monitory
def czestotliwosci(wartosci):
    """(natywne, oc) z wartości pola Hz, np. ['260 Hz - OC', '240 Hz'] → (240, 260).
    Natywne = wartość bez adnotacji OC; oc = najwyższa z adnotacją OC albo None.
    BrakDanych, gdy nie ma żadnej wartości natywnej albo gdy jest ich kilka (niejednoznaczne)."""
    nat, oc = [], []
    for w in wartosci or []:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*Hz", w, re.I)
        if not m:
            raise BrakDanych(f"nieczytelna częstotliwość odświeżania: {w!r}")
        hz = int(float(m.group(1).replace(",", ".")))
        (oc if re.search(r"\bOC\b|overclock|podkręc", w, re.I) else nat).append(hz)
    if not nat:
        raise BrakDanych(f"brak natywnej częstotliwości odświeżania (same wartości OC): {wartosci}")
    if len(nat) > 1:
        raise BrakDanych("kilka natywnych wartości Hz — niejednoznaczne")
    return nat[0], (max(oc) if oc else None)


def matryca(rodzaj, typ_ekranu, dodatkowe, oc):
    """(panelName, panel) z pola „Rodzaj matrycy”, np. 'LED, Fast IPS'. Typ spoza listy = pominięcie,
    nie zgadywanie. Nazwy jak w istniejącej bazie (IPS / Rapid IPS / OLED (WOLED) / QD-OLED / VA…)."""
    t = _tekst(rodzaj)
    t = re.sub(r"^(LED|LCD)\s*,\s*", "", t, flags=re.I)
    u = t.upper()
    if u == "QD-OLED":
        nazwa, klucz = "QD-OLED", "qdoled"
    elif (m := re.fullmatch(r"WOLED(?: (\d)\. GENERACJI)?", u)):
        nazwa, klucz = "OLED (WOLED" + (f", {m.group(1)}. generacji" if m.group(1) else "") + ")", "oled"
    elif u == "OLED":
        nazwa, klucz = "OLED", "oled"
    elif u in ("TANDEM OLED", "TANDEM WOLED"):
        nazwa, klucz = "OLED (Tandem)", "oled"
    elif re.fullmatch(r"(FAST |RAPID |NANO |SS |SUPER SPEED )?IPS( BLACK)?", u):
        nazwa, klucz = t, "ips"
    elif re.fullmatch(r"(FAST |RAPID )?VA", u):
        nazwa, klucz = t, "va"
    else:
        raise BrakDanych(f"typ matrycy „{t or 'brak'}” spoza zakresu (IPS/VA/OLED/QD-OLED)")
    if _tekst(typ_ekranu).lower().startswith("zakrzyw"):
        promien = next((m.group(1) for d in dodatkowe or []
                        if (m := re.search(r"\b(\d{3,4}R)\b", d))), None)
        nazwa += ", zakrzywiony" + (f" {promien}" if promien else "")
    if oc:
        nazwa += f" ({oc} Hz OC)"
    return nazwa, klucz


def _nazwa_monitora(ld, encja):
    """Nazwa „Marka Model” jak w bazie. x-kom podaje ją w tej formie (np. „Gigabyte GO27Q24A”);
    nazwę-opis (cudzysłów, >60 znaków) zastępujemy marką i kodem producenta, a gdy ich nie ma, odrzucamy."""
    n = _tekst(ld.get("name") or encja.get("fullName") or "")
    n = re.sub(r"^Monitor\s+", "", n, flags=re.I)
    if not n:
        raise BrakDanych("brak nazwy")
    if '"' in n or len(n) > 60 or re.search(r"pikseli|aspect ratio", n, re.I):
        marka = ld.get("brand")
        marka = _tekst(marka.get("name") if isinstance(marka, dict) else marka or "")
        model = _tekst(ld.get("mpn") or encja.get("producerCode") or "")
        if not marka or len(model) < 4 or len(model) > 30:
            raise BrakDanych(f"tytuł karty nie jest nazwą modelu: {n[:50]!r}")
        n = f"{marka} {model}"
    n = n.replace("'", "’")
    w = n.split(" ", 1)
    if w[0].lower() in MARKI:
        n = MARKI[w[0].lower()] + (" " + w[1] if len(w) > 1 else "")
    return n


def _kod_modelu(ld, encja):
    """Symbol producenta (np. LS27BG650EUXEN) albo None, gdy strona go nie podaje w czytelnej formie."""
    for k in (ld.get("mpn"), encja.get("producerCode")):
        k = _tekst(k or "")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/\- ]{3,39}", k) and re.search(r"\d", k):
            return k
    return None


def odczytaj_monitor(url, html):
    """Dane z karty monitora → słownik o kluczach jak nowe_monitory.odczytaj (+ kod_modelu).
    Klucze addytywne przy promocji z kodem: cena_bez_kodu, kod_rabatowy, kod_do.
    BrakDanych, gdy czegokolwiek brakuje albo nie pasuje (przekątna, rozdzielczość, Hz, matryca,
    cena, dostępność). EAN karta nie podaje, więc klucza `ean` nie ma."""
    ld, encja, cechy = _karta(url, html)
    _dostepnosc(ld, encja)
    nazwa = _nazwa_monitora(ld, encja)
    diag = _liczba(_jedna(cechy, "Przekątna ekranu"))
    if diag is None:
        raise BrakDanych("brak przekątnej")
    if not (DIAG_OD <= diag <= DIAG_DO):
        raise BrakDanych(f"przekątna {diag:g}\" poza zakresem {DIAG_OD:g}–{DIAG_DO:g}\"")
    rozdz = _jedna(cechy, "Rozdzielczość ekranu")
    if not re.match(r"2560\s*x\s*1440\b", rozdz, re.I):
        raise BrakDanych(f"rozdzielczość „{rozdz}” (wymagane 2560 x 1440)")
    hz, oc = czestotliwosci(cechy.get("Częstotliwość odświeżania ekranu"))
    if oc is None:
        opis = (encja.get("productDescription") or "") + " " + html
        wzorzec_oc = re.compile(
            rf"(?:{hz}\s*Hz[^.]{{0,40}}(?:podkręc|\bOC\b|overclock)|(?:podkręc|\bOC\b|overclock)[^.]{{0,40}}{hz}\s*Hz)",
            re.I
        )
        if wzorzec_oc.search(opis):
            raise BrakDanych("Hz z podkręcenia (OC) bez wartości natywnej")
    if not (HZ_OD <= hz <= HZ_DO):
        raise BrakDanych(f"{hz} Hz poza zakresem {HZ_OD}–{HZ_DO} Hz")
    nazwa_matrycy, klucz_matrycy = matryca(_jedna(cechy, "Rodzaj matrycy"),
                                           (cechy.get("Typ ekranu") or [""])[0],
                                           cechy.get("Dodatkowe informacje"), oc)
    cena = _cena(ld, encja, CENA_MONITORA_OD, CENA_MONITORA_DO)
    cena_bez_kodu, kod_rabatowy, kod_do = _promo_info(ld, encja, cena)
    wynik = {"nazwa": nazwa, "url": url, "hz": hz, "diag": diag, "panelName": nazwa_matrycy,
             "panel": klucz_matrycy, "cena": cena, "zdjecie": _zdjecie(ld),
             "kod_modelu": _kod_modelu(ld, encja)}
    if cena_bez_kodu is not None:
        wynik["cena_bez_kodu"] = cena_bez_kodu
    if kod_rabatowy is not None:
        wynik["kod_rabatowy"] = kod_rabatowy
    if kod_do is not None:
        wynik["kod_do"] = kod_do
    return wynik


def powod_odrzucenia_monitora(p):
    """Przesiew pozycji listy (słownik z pozycje_listy): None = pobierz kartę, tekst = powód
    odrzucenia. Odrzuca tylko jawne sprzeczności z wymaganiami; brak pola nie odrzuca."""
    if p["dostepny"] is False:
        return "niedostępny"
    c = p["cechy"]
    if c is None:
        # kafelek bez podsumowania: zostają monitory z grupy 27" (26,5"–28,4"), reszta o innej przekątnej
        return None if "monitor-led-27-265-284" in p["url"] else "bez podsumowania i spoza grupy 27\""
    if "Rozdzielczość ekranu" in c:
        if len(c["Rozdzielczość ekranu"]) != 1:
            return "kilka rozdzielczości (tryb dwuekranowy) — niejednoznaczne Hz"
        if not re.match(r"2560\s*x\s*1440\b", c["Rozdzielczość ekranu"][0], re.I):
            return f"rozdzielczość {c['Rozdzielczość ekranu'][0]}"
    if "Częstotliwość odświeżania ekranu" in c:
        try:
            hz, _ = czestotliwosci(c["Częstotliwość odświeżania ekranu"])
        except BrakDanych as x:
            return str(x)
        if not (HZ_OD <= hz <= HZ_DO):
            return f"{hz} Hz"
    if "Przekątna" in c and c["Przekątna"]:
        d = _liczba(c["Przekątna"][0])
        if d is not None and not (DIAG_OD <= d <= DIAG_DO):
            return f"przekątna {d:g}\""
    return None


def lista_monitorow(pobierz, maks_stron=6):
    """Adresy kart monitorów QHD 26–28" 240–500 Hz z kategorii Monitory (filtr WQHD, 90 na stronę).
    `pobierz(url)` → (kod, html). Kod ≠ 200 (np. 403 z chmury) = [], bez wyjątku."""
    return _przejdz([LISTA_MONITOROW], SCIEZKA_MONITOROW, pobierz, maks_stron,
                    powod_odrzucenia_monitora)


# ------------------------------------------------------------------ komputery
def _cpu(wartosc):
    """„AMD Ryzen™ 5 8400F (6 rdzeni, …)” → „AMD Ryzen 5 8400F” (tekst dla ocena_pc.klasa_cpu)."""
    return _tekst(re.sub(r"\(.*?\)", " ", wartosc))


def _gpu_dyskretny(wartosci):
    """Jedyna karta dyskretna RTX/RX z listy wartości (zintegrowane pomijamy) jako tekst z
    kanonicznym zapisem sufiksu (RTX 5070Ti → RTX 5070 Ti), żeby klasa karty nie spadała po cichu."""
    trafienia = set()
    for w in wartosci:
        txt = _tekst(w)
        m = re.search(r"\b(RTX|RX)\s*(\d{4})\s*(Ti|XT)?\b", txt, re.I)
        if m:
            nxt = re.match(r"\s*([A-Za-z]+)", txt[m.end():])
            if nxt and nxt.group(1).upper() in ("SUPER", "GRE", "D", "LAPTOP"):
                raise BrakDanych(f"nieobsługiwany wariant karty {m.group(0)} {nxt.group(1)}")
            rodzina = m.group(1).lower()
            numer = m.group(2)
            suf = (m.group(3) or "").lower()
            if suf in ("ti", "xt"):
                klucz = f"{rodzina} {numer} {suf}"
                if klucz not in ocena_pc.KLASA_GPU:
                    raise BrakDanych(f"karta {klucz} spoza słownika klas ocena_pc")
            sufiks = {"ti": " Ti", "xt": " XT"}.get(suf, "")
            marka = "AMD Radeon RX" if rodzina == "rx" else "NVIDIA GeForce RTX"
            trafienia.add(f"{marka} {numer}{sufiks}")
    if not trafienia:
        raise BrakDanych(f"brak karty dyskretnej RTX/RX: {wartosci}")
    if len(trafienia) > 1:
        raise BrakDanych(f"kilka kart dyskretnych {sorted(trafienia)} — niejednoznaczne")
    return trafienia.pop()


def _vram_gb(wartosci):
    """Pamięć własna karty w GB z pola „Wielkość pamięci karty graficznej” ('8192 MB GDDR7 (pamięć własna)')."""
    if not wartosci:
        raise BrakDanych("brak pola „Wielkość pamięci karty graficznej”")
    kand = []
    for w in wartosci:
        if re.search(r"współdziel|zintegrow|shared", w, re.I):
            continue
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(MB|GB)", w, re.I)
        if m:
            v = float(m.group(1).replace(",", "."))
            kand.append(v / 1024 if m.group(2).upper() == "MB" else v)
    if len(kand) != 1:
        raise BrakDanych(f"nie umiem ustalić pamięci karty z {wartosci}")
    if abs(kand[0] - round(kand[0])) > 0.01 or not (1 <= kand[0] <= 99):
        raise BrakDanych(f"pamięć karty {kand[0]:g} GB nie jest pełną liczbą GB")
    return int(round(kand[0]))


def _ram(wartosci):
    """'32 GB (UDIMM DDR5, 6000MHz)' → '32GB DDR5 6000MHz'. Wyłącznie DDR5; standard musi być podany."""
    w = _jedna_wartosc(wartosci, "Pamięć RAM")
    m = re.match(r"^(\d+)\s*GB\b(.*)$", w, re.I)
    if not m:
        raise BrakDanych(f"nieczytelna pamięć RAM: {w!r}")
    t = re.search(r"DDR\s?(\d)", m.group(2), re.I)
    if not t:
        raise BrakDanych(f"sklep nie podaje standardu pamięci (DDR4/DDR5): {w!r}")
    if t.group(1) != "5":
        raise BrakDanych(f"pamięć nie jest DDR5: {w!r}")
    mhz = re.search(r"(\d{3,5})\s*MHz", m.group(2), re.I)
    return f"{int(m.group(1))}GB DDR5" + (f" {mhz.group(1)}MHz" if mhz else "")


def _dysk(wartosci):
    """'1000 GB SSD M.2 PCIe' → '1TB SSD'. Zapis prosty, bez NVMe/M.2 (jak nowe_pc.dysk_znormalizowany:
    ten sam dysk zapisany raz tak, raz inaczej dostawał inną ocenę). Brak dysku potwierdzony przez
    sklep → zapis zrozumiały dla ocena_pc; kilka dysków albo nieznany rodzaj = BrakDanych."""
    w = _jedna_wartosc(wartosci, "Dysk")
    if re.search(r"\bbrak\b", w, re.I):
        return "SSD: brak (potwierdzone przez sklep)"
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(TB|GB)", w, re.I)
    if not m:
        raise BrakDanych(f"dysk bez pojemności: {w!r}")
    ssd, hdd = re.search(r"\bSSD\b", w, re.I), re.search(r"\bHDD\b", w, re.I)
    if ssd and hdd:
        raise BrakDanych(f"kilka dysków w jednym polu: {w!r}")
    if not (ssd or hdd):
        raise BrakDanych(f"nieznany rodzaj dysku (ani SSD, ani HDD): {w!r}")
    gb = float(m.group(1).replace(",", ".")) * (1000 if m.group(2).upper() == "TB" else 1)
    if not math.isfinite(gb) or gb <= 0:
        raise BrakDanych(f"pojemność dysku nieczytelna: {w!r}")
    gb = int(round(gb))
    pojemnosc = f"{gb // 1000}TB" if gb >= 1000 and gb % 1000 == 0 else f"{gb}GB"
    return f"{pojemnosc} {'SSD' if ssd else 'HDD'}"


def _zasilacz(cechy):
    """'850 W' + '80 Plus Gold' → '850W 80 Plus Gold'; bez certyfikatu samo '650W'."""
    m = re.search(r"(\d{3,4})\s*W\b", _jedna(cechy, "Zasilacz"))
    if not m:
        raise BrakDanych("brak mocy zasilacza")
    moc = f"{m.group(1)}W"
    spr = cechy.get("Sprawność zasilacza")
    if spr:
        s = _jedna(cechy, "Sprawność zasilacza")
        if re.match(r"80\s*Plus\b", s, re.I):
            return f"{moc} {s}"
    return moc


def _system(cechy, encja, cena):
    """(system, opcje, adresy_opcji). system = {w_cenie, doplata, nazwa} z pola „System operacyjny”;
    w_cenie = True tylko dla ^Microsoft Windows 1[01]; inny system → w_cenie = None.
    `doplata` (tylko dla karty BEZ systemu) = o ile droższa jest karta tej samej konfiguracji z
    Windows 11 Home (grupa „System operacyjny” w alternativeProducts). opcje: etykieta → dopłata [zł]
    względem tej karty, tylko dodatnie (to są dopłaty); adresy_opcji: etykieta → adres tamtej karty."""
    sys_pole = cechy.get("System operacyjny")
    if not sys_pole:
        return {"w_cenie": None, "doplata": None, "nazwa": None}, {}, {}
    nazwa = _jedna(cechy, "System operacyjny")
    brak = bool(re.match(r"brak\b", nazwa, re.I))
    if brak:
        w_cenie = False
    elif re.match(r"^Microsoft Windows 1[01]\b", nazwa, re.I):
        w_cenie = True
    else:
        w_cenie = None
    pid = str(encja.get("id", ""))
    opcje, adresy = {}, {}
    for grupa in encja.get("alternativeProducts") or []:
        if not isinstance(grupa, dict) or grupa.get("name") != "System operacyjny":
            continue
        for alt in grupa.get("alternativeSpecifications") or []:
            if not isinstance(alt, dict) or str(alt.get("productId", "")) == pid:
                continue
            if alt.get("grayedOutOption"):
                continue
            etykieta = _tekst(alt.get("label") or "")
            alt_prom = alt.get("promotionInfo") or {}
            cena_alt = _zl(alt_prom.get("discountedPrice")) or _zl((alt.get("priceInfo") or {}).get("price"))
            if not etykieta or cena_alt is None or cena_alt <= cena:
                continue
            opcje[etykieta] = cena_alt - cena
            adr = [w.get("url") for w in alt.get("webUrls") or []
                   if isinstance(w, dict) and str(w.get("productId", "")) == str(alt.get("productId"))]
            if len(adr) == 1 and isinstance(adr[0], str):
                adresy[etykieta] = adr[0]
    doplata = None
    if brak:
        doplata = next((d for k, d in opcje.items() if re.match(r"Microsoft Windows 11 Home\b", k)), None)
    return {"w_cenie": w_cenie, "doplata": doplata, "nazwa": nazwa}, opcje, adresy


def odczytaj_pc(url, html):
    """Dane z karty komputera → słownik. Cena i specyfikacja dotyczą konfiguracji, którą opisuje
    karta (x-kom: jedna wersja systemu = jedna karta). Klucze addytywne przy promocji z kodem:
    cena_bez_kodu, kod_rabatowy, kod_do. BrakDanych, gdy czegokolwiek brakuje:
    procesor lub karta spoza słownika ocena_pc, pamięć inna niż DDR5, brak dysku/ceny/zasilacza,
    produkt niedostępny lub brak dopłaty do Windows przy karcie bez systemu. Klucze: nazwa, url,
    cpu, gpu, ram, storage, psu, cena_bazowa, system, dostepny (zawsze True — niedostępne odrzucamy),
    sprzedawca (None: karta nie podaje sprzedawcy zewnętrznego), zdjecie, opcje, opcje_adresy.
    EAN karta nie podaje, więc klucza `ean` nie ma."""
    ld, encja, cechy = _karta(url, html)
    _dostepnosc(ld, encja)
    nazwa = _tekst(ld.get("name") or encja.get("fullName") or "")
    if not nazwa:
        raise BrakDanych("brak nazwy")
    cena = _cena(ld, encja, CENA_PC_OD, CENA_PC_DO)
    cpu = _cpu(_jedna(cechy, "Procesor"))
    gpu = nowe_pc.gpu_kanoniczna(_gpu_dyskretny(cechy.get("Karta graficzna") or []),
                                 {"Pamięć karty graficznej": f"{_vram_gb(cechy.get('Wielkość pamięci karty graficznej'))} GB"})
    ram = _ram(cechy.get("Pamięć RAM"))
    dysk = _dysk(cechy.get("Dysk"))
    psu = _zasilacz(cechy)
    ocena_pc.klasa_cpu(cpu)             # procesor lub karta spoza słownika = pominięcie (BrakDanych)
    ocena_pc.klasa_gpu(gpu)
    ocena_pc.oceny(cpu, gpu, ram, dysk, psu, "Windows 11 Home", 1)    # nic nie może rzucić później
    system, opcje, adresy = _system(cechy, encja, cena)
    if system["w_cenie"] is None:
        raise BrakDanych(f"system operacyjny „{system['nazwa']}” nie jest wspieranym systemem Windows")
    if system["w_cenie"] is False and system["doplata"] is None:
        raise BrakDanych("karta bez systemu: brak dopłaty do Windows 11 Home — nieweryfikowalne względem progu 10 000 zł")
    cena_bez_kodu, kod_rabatowy, kod_do = _promo_info(ld, encja, cena)
    wynik = {"nazwa": nazwa, "url": url, "cpu": cpu, "gpu": gpu, "ram": ram, "storage": dysk,
             "psu": psu, "cena_bazowa": cena, "system": system, "dostepny": True,
             "sprzedawca": None, "zdjecie": _zdjecie(ld), "opcje": opcje, "opcje_adresy": adresy}
    if cena_bez_kodu is not None:
        wynik["cena_bez_kodu"] = cena_bez_kodu
    if kod_rabatowy is not None:
        wynik["kod_rabatowy"] = kod_rabatowy
    if kod_do is not None:
        wynik["kod_do"] = kod_do
    return wynik


def powod_odrzucenia_pc(p, cena_od=CENA_LISTY_PC_OD, cena_do=CENA_LISTY_PC_DO):
    """Przesiew pozycji listy komputerów: None = pobierz kartę, tekst = powód. Karta i procesor
    muszą mieć klasę w słowniku ocena_pc (ta sama kontrola padłaby po pobraniu karty), cena w
    przedziale; DDR5 zapewnia już filtr listy. Brak pola nie odrzuca."""
    if p["dostepny"] is False:
        return "niedostępny"
    if p["cena"] is not None and ((cena_od is not None and p["cena"] < cena_od)
                                  or (cena_do is not None and p["cena"] > cena_do)):
        return f"cena {p['cena']} zł poza przedziałem"
    c = p["cechy"]
    if c is None:
        return None
    try:
        if "Grafika" in c:
            ocena_pc.klasa_gpu(_gpu_dyskretny(c["Grafika"]))
        if "Procesor" in c:
            ocena_pc.klasa_cpu(_cpu(_jedna(c, "Procesor")))
    except BrakDanych as x:
        return str(x)
    return None


def lista_pc(pobierz, maks_stron=6, cena_od=CENA_LISTY_PC_OD, cena_do=CENA_LISTY_PC_DO):
    """Adresy kart gotowych komputerów „Dla graczy” z pamięcią DDR5 (trzy przebiegi po typach RAM,
    najwyżej `maks_stron` stron każdy), po przesiewie z powod_odrzucenia_pc i zwinięciu wariantów
    systemu do jednej karty na konfigurację sprzętową (preferowane Windows 11 Home).
    `cena_od`/`cena_do` = None wyłącza przesiew po cenie. Kod ≠ 200 (np. 403 z chmury) = [], bez wyjątku."""
    return _przejdz(LISTY_PC, SCIEZKA_PC, pobierz, maks_stron,
                    lambda p: powod_odrzucenia_pc(p, cena_od, cena_do),
                    zwijaj=_zwijaj_warianty_pc)
