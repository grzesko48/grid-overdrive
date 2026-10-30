#!/usr/bin/env python3
"""Adapter sklepu GoblinPC (goblinpc.pl): ręcznie składane komputery gamingowe.

Zakres: tylko komputery (sklep nie sprzedaje monitorów: menu to gotowe zestawy, konfigurator
i dobór pod grę), więc lista_monitorow() zwraca [] bez żadnego żądania.

Strona to aplikacja Next.js, ale serwer oddaje gotowy HTML, więc czytamy go jak zwykłą stronę:
- cena, dostępność, zdjęcie: dane strukturalne ld+json (cena zestawu w konfiguracji DOMYŚLNEJ,
  tej samej, którą opisują kafelki „Pod maską"); availability „MadeToOrder" to normalny stan
  tego sklepu (zestaw powstaje po zamówieniu, wysyłka 7–14 dni roboczych), nie brak towaru;
- cpu, karta (z pamięcią w nawiasie), RAM, dysk, zasilacz, obudowa, system: kafelki sekcji
  „Pod maską" (etykieta, nazwa, opis). DDR5 musi wynikać z kafelka RAM; DDR4 gdziekolwiek =
  odrzucenie. Certyfikat zasilacza stoi w opisie kafelka, nie w jego nazwie;
- konfigurator („Dopasuj zestaw": Moc, RAM, Dysk): czytamy tylko nazwy opcji i opcję standardową
  i sprawdzamy, czy standardowy RAM i dysk zgadzają się z kafelkami. DOPŁAT NIE PODAJEMY:
  HTML ich nie zawiera (liczy je JavaScript), a cena zestawu nie jest sumą cen składników
  z osadzonych danych (Goblin: 8800 zł na stronie wobec 8834 zł z sumy) — wyliczenie byłoby
  zgadywaniem, więc `opcje` jest puste, a nazwy opcji idą do `opcje_bez_ceny`.

Pobieranie sieciowe wykonuje WOŁAJĄCY (`pobierz` z zbieraj_ceny); tu są funkcje czyste.
Wspólne narzędzia (tekst, ld+json, robots) pochodzą z zrodla/plugnplay.py.
"""
import html as htmllib
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
from zrodla.plugnplay import _tekst, _zlote, _ld_json, robots_dozwolony, dysk, pierwsze_dozwolone_zdjecie

SKLEP = "goblinpc"
LOKALNIE = False
SKLEP_UWAGI = (
    "komputery: lista /komputery to jedna strona bez paginacji (dziś 9 zestawów: Utopiec 6310 zł … "
    "Hydra 21270 zł; strona deklaruje ich liczbę, a adapter ją sprawdza); wstępny przesiew po cenie "
    "kafelka 5000–10000 zł (cena_od/cena_do=None go wyłączają). Cena zestawu jest ceną konfiguracji "
    "DOMYŚLNEJ (np. Utopiec = START + 16 GB RAM + 512 GB; Goblin = STANDARD + 32 GB + 1 TB) i "
    "zawiera Windows 11 (kafelek „System” — zainstalowany; brak opcji bez systemu). Pole 'model' = "
    "nazwa zestawu (Utopiec, Goblin…). Konfigurator (Moc/RAM/Dysk) zmienia CPU, GPU, RAM i dysk, "
    "ale dopłat nie ma w HTML-u (liczy je JS) — adapter ich nie wylicza: 'opcje' jest puste, nazwy "
    "opcji w 'opcje_bez_ceny'. Strona NIE podaje: EAN, producenta i modelu RAM/dysku/zasilacza "
    "(„markowy zasilacz”, „Goodram, Lexar…”), częstotliwości RAM; certyfikat zasilacza tylko w opisie. "
    "Monitorów sklep nie sprzedaje, więc lista_monitorow() zwraca []."
)

HOST = "goblinpc.pl"
LISTA_PC = "https://goblinpc.pl/komputery"
CENA_LISTY_OD, CENA_LISTY_DO = 5000, 10000      # wstępny przesiew po cenie kafelka [zł]; None = bez przesiewu
MAKS_ADRESOW = 100
CENA_OD, CENA_DO = 500, 100000

# Kopia reguł z https://goblinpc.pl/robots.txt (30.10.2026), User-agent: *.
ROBOTS_REGULY = (
    ("Allow", "/"), ("Disallow", "/admin"), ("Disallow", "/admin/"), ("Disallow", "/checkout"),
    ("Disallow", "/checkout/"), ("Disallow", "/api/"), ("Disallow", "/zamowienia"),
)
DOSTEPNE = ("InStock", "MadeToOrder")           # availability uznawane za „da się kupić"


def dozwolony(url):
    return robots_dozwolony(url, HOST, ROBOTS_REGULY)


# ------------------------------------------------------------------ lista
def kafelki(s):
    """Kafelki zestawów z /komputery: [{nazwa, cena, adres}] w kolejności ze strony."""
    znaczniki = [m for m in re.finditer(r"<a\b[^>]*class=\"[^\"]*zestaw-kafel__nazwa[^\"]*\"[^>]*>", s)]
    wynik = []
    for i, m in enumerate(znaczniki):
        koniec = znaczniki[i + 1].start() if i + 1 < len(znaczniki) else len(s)
        h = re.search(r'href="(/product/[^"#?]+)"', m.group(0))
        if not h:
            continue
        nazwa = _tekst(s[m.end():s.find("</a>", m.end())])
        c = re.search(r'class="[^"]*zestaw-kafel__cena[^"]*"[^>]*>(.*?)</p>', s[m.end():koniec], re.S)
        wynik.append({"nazwa": nazwa, "cena": _zlote(c.group(1)) if c else None,
                      "adres": urllib.parse.urljoin("https://" + HOST, h.group(1))})
    return wynik


def _deklarowana_liczba(s):
    """„Nasze zestawy 9 zestawów" → 9; None, gdy strona tego nie podaje."""
    plaski = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b.*?</\1>", "", s, flags=re.S | re.I))
    m = re.search(r"Nasze zestawy\s+(\d+)\s+zestaw", re.sub(r"\s+", " ", htmllib.unescape(plaski)))
    return int(m.group(1)) if m else None


def lista_pc(pobierz, maks_stron=6, cena_od=CENA_LISTY_OD, cena_do=CENA_LISTY_DO, uwagi=None):
    """Adresy kart zestawów. Lista jest jedną stroną (maks_stron nie ma tu znaczenia).
    BrakDanych: brak 200 (z wyjątkiem 403, który zwraca [] i dopisuje uwagę), brak kafelków
    albo liczba kafelków ≠ liczbie deklarowanej na stronie (zmiana układu lub paginacja —
    wolimy hałas niż ciche zgubienie zestawów)."""
    if not dozwolony(LISTA_PC):
        raise BrakDanych(f"lista GoblinPC: adres zabroniony przez robots.txt: {LISTA_PC}")
    kod, s = pobierz(LISTA_PC)
    if kod != 200:
        if kod == 403:
            if uwagi is not None:
                uwagi.append(f"HTTP 403: {LISTA_PC}")
            return []
        raise BrakDanych(f"lista GoblinPC: HTTP {kod}")
    kafle = kafelki(s)
    if not kafle:
        raise BrakDanych("lista GoblinPC: niedostępne kafelki zestawów — zmienił się układ strony "
                         "(adapter do poprawy)")
    deklarowana = _deklarowana_liczba(s)
    if deklarowana is not None and deklarowana != len(kafle):
        raise BrakDanych(f"lista GoblinPC: strona deklaruje {deklarowana} zestawów, odczytano {len(kafle)} "
                         f"— zmiana układu albo paginacja (adapter do poprawy)")
    adresy = []
    for k in kafle:
        if k["adres"] in adresy or not dozwolony(k["adres"]):
            continue
        if k["cena"] is not None and ((cena_od is not None and k["cena"] < cena_od)
                                      or (cena_do is not None and k["cena"] > cena_do)):
            continue
        adresy.append(k["adres"])
    return adresy[:MAKS_ADRESOW]


def lista_monitorow(pobierz, maks_stron=6, uwagi=None):
    """GoblinPC nie sprzedaje monitorów. Bez żadnego żądania."""
    return []


def odczytaj_monitor(url, html):
    raise BrakDanych("GoblinPC nie sprzedaje monitorów")


# ------------------------------------------------------------------ karta zestawu
def kafle_specyfikacji(s):
    """Sekcja „Pod maską": {etykieta: {nazwa, tag, opis}}. BrakDanych, gdy sekcji nie ma."""
    etykiety = list(re.finditer(r'<span class="sp-tile-label">(.*?)</span>', s, re.S))
    if not etykiety:
        raise BrakDanych("niedostępna sekcja „Pod maską” (kafelki specyfikacji) — to nie zestaw albo "
                         "zmienił się układ (adapter do poprawy)")
    wynik = {}
    for i, m in enumerate(etykiety):
        koniec = etykiety[i + 1].start() if i + 1 < len(etykiety) else m.end() + 3000
        seg = s[m.end():koniec]
        nazwa = re.search(r'<span class="sp-tile-name">(.*?)</span>', seg, re.S)
        tag = re.search(r'<span class="sp-tile-tag">(.*?)</span>', seg, re.S)
        opis = re.search(r'<p class="sp-tile-desc">(.*?)</p>', seg, re.S)
        wynik.setdefault(_tekst(m.group(1)), {
            "nazwa": _tekst(nazwa.group(1)) if nazwa else "",
            "tag": _tekst(tag.group(1)) if tag else "",
            "opis": _tekst(opis.group(1)) if opis else ""})
    return wynik


def konfigurator(s):
    """„Dopasuj zestaw": {etykieta: {opcje: [...], standardowa: str | None}} (Moc, RAM, Dysk)."""
    wiersze = list(re.finditer(r'<span class="qsm-label">(.*?)</span>', s, re.S))
    wynik = {}
    for i, m in enumerate(wiersze):
        koniec = wiersze[i + 1].start() if i + 1 < len(wiersze) else m.end() + 6000
        seg = s[m.end():koniec]
        punkty = re.findall(r'<button\b[^>]*class="([^"]*qsm-tick[^"]*)"[^>]*>(.*?)</button>', seg, re.S)
        opcje = [_tekst(t) for _, t in punkty]
        std = [_tekst(t) for c, t in punkty if "qsm-tick--std" in c.split()]
        if opcje:
            wynik[_tekst(m.group(1))] = {"opcje": opcje, "standardowa": std[0] if len(std) == 1 else None}
    return wynik


def _cpu(nazwa):
    """„Ryzen 5 8400f" → „Ryzen 5 8400F" (strona pisze modele małą literą)."""
    cpu = " ".join(t.upper() if re.search(r"\d", t) and re.search(r"[a-z]", t) else t
                   for t in re.sub(r"\s+", " ", nazwa).strip().split())
    ocena_pc.klasa_cpu(cpu)
    return cpu


def dokladny_klucz_gpu(surowa):
    """Zwraca dokładny klucz z ocena_pc.KLASA_GPU albo None.
    Usuwa markę (NVIDIA GeForce, AMD Radeon, Intel), pamięć VRAM i nawiasy/odstępy."""
    t = re.sub(r"\b\d{1,2}\s*GB\b", "", surowa or "", flags=re.I)
    t = re.sub(r"\b(nvidia\s+geforce|geforce|amd\s+radeon|radeon|intel)\b", "", t, flags=re.I)
    t = re.sub(r"[()]", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t if t in ocena_pc.KLASA_GPU else None


def _gpu(nazwa):
    """„RTX 5050 (8GB)" → „NVIDIA GeForce RTX 5050 8GB". Pamięć stoi w nawiasie na stronie."""
    if not re.search(r"\d{1,2}\s*GB", nazwa, re.I):
        raise BrakDanych(f"kafelek karty nie podaje pamięci: {nazwa!r}")
    if re.search(r"\b(SUPER|GRE|XTX)\b", nazwa, re.I):
        raise BrakDanych(f"karta z nieobsługiwanym przyrostkiem: {nazwa!r}")
    gpu = nowe_pc.gpu_kanoniczna(nazwa, {})
    if re.search(r"\bTi\b", nazwa, re.I) and not re.search(r"\bTi\b", gpu, re.I):
        raise BrakDanych(f"utracony przyrostek Ti przy kanonizacji karty: {nazwa!r}")
    if re.search(r"\bXT\b", nazwa, re.I) and not re.search(r"\bXT\b", gpu, re.I):
        raise BrakDanych(f"utracony przyrostek XT przy kanonizacji karty: {nazwa!r}")
    klucz_gpu = dokladny_klucz_gpu(gpu)
    if not klucz_gpu:
        raise BrakDanych(f"karta spoza słownika klas: {gpu!r} (model {nazwa!r} nie ma dokładnego dopasowania w KLASA_GPU)")
    ocena_pc.klasa_gpu(gpu)
    return gpu


def _ram(k, platforma):
    tekst = f"{k['nazwa']} {k['opis']} {platforma['nazwa'] if platforma else ''} {platforma['opis'] if platforma else ''}"
    if re.search(r"DDR4", tekst, re.I):
        raise BrakDanych(f"pamięć DDR4 w specyfikacji: {k['nazwa']!r}")
    if not re.search(r"DDR5", f"{k['nazwa']} {k['opis']}", re.I):
        raise BrakDanych(f"kafelek RAM nie potwierdza DDR5: {k['nazwa']!r}")
    m = re.search(r"(\d+)\s*GB", k["nazwa"], re.I)
    if not m:
        raise BrakDanych(f"brak pojemności RAM w {k['nazwa']!r}")
    return f"{int(m.group(1))}GB DDR5"


def _zasilacz(k):
    m = re.match(r"^(\d{3,4})\s*W\b", k["nazwa"], re.I)
    if not m:
        raise BrakDanych(f"brak mocy zasilacza w {k['nazwa']!r}")
    c = re.search(r"80\s*\+\s*(White|Bronze|Silver|Gold|Platinum|Titanium)", k["opis"], re.I)
    return f"{m.group(1)}W" + (f" 80+ {c.group(1).capitalize()}" if c else "")


def _system(k):
    """Kafelek „System": Windows 11 zainstalowany, w jedynej cenie zestawu. Brak kafelka = nie wiemy."""
    if not k or not re.search(r"windows", k["nazwa"], re.I):
        return {"w_cenie": None, "doplata": None, "nazwa": None}
    return {"w_cenie": True, "doplata": 0, "nazwa": k["nazwa"]}


def odczytaj_pc(url, html):
    """Karta zestawu → słownik konfiguracji domyślnej (klucze jak w kontrakcie adapterów).
    BrakDanych, gdy czegokolwiek brakuje, jest niejednoznaczne albo nie pasuje do zakresu."""
    ld = _ld_json(html)
    produkt = next((o for o in ld if o.get("@type") == "Product"), None)
    if produkt is None:
        raise BrakDanych("niedostępne dane produktu (ld+json Product) — zmienił się układ strony")
    of = produkt.get("offers")
    of = of[0] if isinstance(of, list) and of else of
    if not isinstance(of, dict) or of.get("price") in (None, ""):
        raise BrakDanych("brak ceny w danych strukturalnych strony")
    cena = _zlote(of["price"])
    if not cena or not (CENA_OD <= cena <= CENA_DO):
        raise BrakDanych(f"cena {of['price']!r} poza wiarygodnym zakresem {CENA_OD}–{CENA_DO} zł")
    dostepnosc = str(of.get("availability", "")).rsplit("/", 1)[-1]
    if not dostepnosc:
        raise BrakDanych("strona nie podaje dostępności")
    if dostepnosc not in DOSTEPNE:
        raise BrakDanych(f"nie ma w sprzedaży (availability = {dostepnosc})")
    model = _tekst(produkt.get("name", ""))
    if not model:
        raise BrakDanych("brak nazwy zestawu")

    k = kafle_specyfikacji(html)
    dyski = [e for e in k if e.startswith("Dysk")]
    if len(dyski) > 1:
        raise BrakDanych(f"więcej niż jedna etykieta dysku w sekcji „Pod maską” ({dyski}) — niejednoznaczna konfiguracja")
    brak = [e for e in ("Karta graficzna", "Procesor", "Pamięć RAM", "Dysk SSD", "Zasilacz") if e not in k]
    if brak:
        raise BrakDanych(f"w sekcji „Pod maską” nie ma pól: {', '.join(brak)}")
    cpu, gpu = _cpu(k["Procesor"]["nazwa"]), _gpu(k["Karta graficzna"]["nazwa"])
    ram = _ram(k["Pamięć RAM"], k.get("Płyta główna"))
    nosnik = dysk("Dysk SSD", k["Dysk SSD"]["nazwa"])
    psu = _zasilacz(k["Zasilacz"])

    kf = konfigurator(html)
    for etykieta, kafelek in (("RAM", k["Pamięć RAM"]["nazwa"]), ("Dysk", k["Dysk SSD"]["nazwa"])):
        std = (kf.get(etykieta) or {}).get("standardowa")
        if std and not re.sub(r"\s+", "", kafelek).lower().startswith(re.sub(r"\s+", "", std).lower()):
            raise BrakDanych(f"konfiguracja standardowa ({etykieta}: {std}) różni się od kafelka "
                             f"specyfikacji ({kafelek!r}) — niejednoznaczny wariant domyślny")

    kandydaci = list(produkt["image"] if isinstance(produkt.get("image"), list) else [produkt.get("image")])
    kandydaci += re.findall(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
    # część zdjęć leży pod /api/blob/..., a robots.txt zakazuje /api/ — takiego adresu nie podajemy
    img = pierwsze_dozwolone_zdjecie(kandydaci, "https://" + HOST + "/", HOST, ROBOTS_REGULY)
    sp = of.get("seller")
    sprzedawca = sp.get("name") if isinstance(sp, dict) else None
    obudowa = (k.get("Obudowa") or {}).get("nazwa") or None
    return {
        "nazwa": f"{model} (GoblinPC)", "model": model, "url": url,
        "cpu": cpu, "gpu": gpu, "ram": ram, "storage": nosnik, "psu": psu, "obudowa": obudowa,
        "cena_bazowa": cena, "system": _system(k.get("System")), "dostepny": True,
        "sprzedawca": sprzedawca if sprzedawca and "goblin" not in sprzedawca.lower() else None,
        "zdjecie": img, "ean": None,
        "opcje": {}, "opcje_bez_ceny": {e: v["opcje"] for e, v in kf.items()},
        "domyslne": {e: v["standardowa"] for e, v in kf.items() if v["standardowa"]},
        "vram_zrodlo": "opis",
    }
