#!/usr/bin/env python3
"""Adapter Morele.net: gotowe komputery stacjonarne (gaming, DDR5) do naboru nowych pozycji.

Monitory z Morele obsługuje nowe_monitory.py, więc tu lista_monitorow zwraca [] — ten plik
zbiera wyłącznie komputery. Adapter składa się z funkcji czystych (adres + html → dane);
jedyny kontakt z siecią to wstrzyknięty `pobierz` (w produkcji zbieraj_ceny.pobierz, który
pilnuje tempa i ponawia po 429). Kod sam niczego nie pobiera.

ZASADY (te same co w nowe_pc.py: BRAK zamiast zgadywania):
- każde pole pochodzi z karty produktu (JSON-LD „Product” + jego specyfikacja). Brakująca,
  niejednoznaczna albo sprzeczna dana (np. karta w specyfikacji ≠ karta w tytule) to
  BrakDanych — nigdy wartość domyślna;
- cena_bazowa to cena BEZ kodu rabatowego. JSON-LD Morele podaje cenę Z KODEM (kampania
  Black Weeks), więc przy kodzie bierzemy „cenę bez kodu” ze strony;
- JSON-LD ma `seller: Morele.net` także dla ofert marketplace (Artrel, ERROR, Proxima…),
  dlatego sprzedawcę czytamy z bloku „Sprzedaje i wysyła przedsiębiorca” (merchant-name).

Pułapki Morele, które ten kod obsługuje (sprawdzone na żywych stronach 30.10.2026):
- karta ma tablicę JSON-LD: ProductGroup, właściwy Product i atrapy wariantów (Product
  z samym `url`) — bierzemy Product z ofertą i specyfikacją;
- pola dysku „SSD” i „SSD M.2 PCIe” bywają oba wypełnione TĄ SAMĄ pojemnością dla jednego
  dysku (Artrel: 1 TB + 1 TB przy tytule „1TB”) — suma by zdublowała pojemność, więc o liczbie
  dysków rozstrzyga tytuł oferty;
- fasety listy rozjeżdżają się z tytułem (chipset „RTX 4060” przy tytule „RTX 5060”).
"""
import html as htmllib, json, os, re, sys

BAZA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BAZA not in sys.path:
    sys.path.insert(0, BAZA)
import ocena_pc
from ocena_pc import BrakDanych
import zbieraj_ceny as z

SKLEP = "morele"
LOKALNIE = False                       # Morele odpowiada też z chmury (x-kom: tylko z komputera właściciela)
SKLEP_UWAGI = (
    "Kategoria komputery-stacjonarne-672 z filtrami: Typ pamięci RAM = DDR5, Zastosowanie = Gamingowe, "
    "okno cen 4500-10000 zł, a dalej fasety „Chipset graficzny” (tylko modele z ocena_pc.KLASA_GPU), "
    "maks_stron stron na chipset (30 ofert na stronę). Sklep ma ~3500 ofert w tym oknie (marketplace: Artrel, "
    "ERROR, Proxima…), więc jeden przebieg widzi ułamek — parametr strona_od pozwala rotować głębokość. "
    "Monitory: lista_monitorow = [] (obsługuje je nowe_monitory.py). Cena w JSON-LD bywa Z KODEM rabatowym; "
    "cena_bazowa = „cena bez kodu” ze strony. JSON-LD podaje sprzedawcę Morele.net także dla marketplace — "
    "sprzedawca czytany z karty. Brak konfiguratora: system to albo Windows w cenie, albo „Bez systemu”, "
    "dopłata = None. Dysk zapisany jak w nowe_pc („1TB SSD”, bez NVMe), interfejs w polu dysk_typ. "
    "Sklep nie podaje certyfikatu zasilacza (80 Plus), tylko moc."
)

LISTA = ("https://www.morele.net/kategoria/komputery-stacjonarne-672/"
         "{cena_od},{cena_do},,,,,,,0,,,,{filtry}/{strona}/")
FILTR_DDR5 = (33381, 1976356)          # grupa „Typ pamięci RAM” = DDR5
FILTR_GAMING = (43184, 1607461)        # grupa „Zastosowanie” = Gamingowe
# Okno cen listy: nowe_pc przyjmuje zestaw od 5000 zł bez systemu do 10 000 zł z Windowsem, więc
# każda cena na stronie jest ≥ 5000 i ≤ 10 000. Dolna granica ma zapas 500 zł, bo nie wiemy, czy
# filtr sklepu liczy po cenie z kodem rabatowym (a ta bywa niższa od ceny bez kodu).
CENA_LISTY_OD, CENA_LISTY_DO = 4500, 10000
NA_STRONE = 30                         # tyle ofert na stronie listy
STRON_SUFIT = 60                       # sklep sam kończy paginację na 60 stronach (data-max-page)
CENA_PC_OD, CENA_PC_DO = 1500, 60000   # poza tym zakresem to błąd odczytu, nie komputer
BRAK = re.compile(r"^\s*(brak( danych)?|nie dotyczy|n/?d|-)?\s*$", re.I)


# ------------------------------------------------------------------ lista z katalogu
def jsonld(s):
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', s, re.S):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:
            continue
        for o in (d if isinstance(d, list) else [d]):
            if isinstance(o, dict):
                yield o


def adres_produktu(u):
    """Karta komputera Morele: …-<id 6–9 cyfr>/ ; id odróżnia oferty o tym samym tytule."""
    return bool(re.fullmatch(r"https://www\.morele\.net/[a-z0-9-]+-\d{6,9}/", u or ""))


def pozycje_listy(s):
    """[(adres, nazwa, cena|None)] z bloku ItemList strony listy, w kolejności sklepu."""
    wynik = []
    for o in jsonld(s):
        if o.get("@type") != "ItemList":
            continue
        for el in o.get("itemListElement", []):
            it = el.get("item", el)
            adres, nazwa = it.get("url"), it.get("name")
            of = it.get("offers") or {}
            of = of[0] if isinstance(of, list) and of else of
            cena = z._liczba(of.get("price")) if isinstance(of, dict) else None
            if adres_produktu(adres) and nazwa:
                wynik.append((adres, htmllib.unescape(nazwa), cena))
    return wynik


def klucz_chipu(etykieta):
    """„Radeon RX 9060 XT” / „RTX 5060 Ti 16GB” → klucz słownika KLASA_GPU albo None.
    Wymagamy DOKŁADNEGO modelu: „RX 7600 XT” i „RTX 4060 Ti” nie mogą wpaść do klasy
    „rx 7600” / „rtx 4060” tylko dlatego, że to ich początek."""
    t = re.sub(r"\s+\d{1,2}\s*GB$", "", (etykieta or "").strip(), flags=re.I)
    g = ocena_pc.znormalizuj_gpu(t).replace("radeon ", "")
    return g if g in ocena_pc.KLASA_GPU else None


def chipsety_z_listy(s):
    """[(grupa, id, etykieta, liczba_ofert)] — fasety „Chipset graficzny” ze znaną klasą karty
    i niezerową liczbą ofert (liczba dotyczy aktualnie wybranych filtrów)."""
    i = s.find(">Chipset graficzny</legend>")
    if i < 0:
        return []
    blok = s[i:s.find("</fieldset>", i)]
    wynik = []
    for m in re.finditer(r'<input[^>]*?\bid="(\d+)"[^>]*?name="(\d+)"[^>]*?data-label="([^"]*)"'
                         r'[^>]*?data-count="(\d+)"', blok, re.S):
        fid, grupa, etykieta, liczba = m.groups()
        etykieta = htmllib.unescape(etykieta)
        if klucz_chipu(etykieta) and int(liczba) > 0:
            wynik.append((int(grupa), int(fid), etykieta, int(liczba)))
    return wynik


def adres_listy(filtry, strona):
    """Filtry MUSZĄ iść rosnąco po numerze grupy — inna kolejność kończy się przekierowaniem 301
    (dodatkowym żądaniem), a strona poza ostatnią przekierowuje na pierwszą."""
    f = ",".join(f"{g}O{w}" for g, w in sorted(filtry))
    return LISTA.format(cena_od=CENA_LISTY_OD, cena_do=CENA_LISTY_DO, filtry=f, strona=strona)


def lista_pc(pobierz, maks_stron=6, wolno=None, chipsety=None, strona_od=1, uwagi=None):
    """Adresy kart komputerów gaming DDR5 z Morele, bez duplikatów, w kolejności sklepu.

    pobierz(url) → (kod, tekst); wolno(url) → bool (w produkcji zbieraj_ceny.REGULAMIN.wolno);
    chipsety: opcjonalnie tylko te etykiety fasety („RTX 5060 Ti”); strona_od: od której strony
    zacząć w każdym chipsecie (rotacja głębokości); uwagi: lista, do której trafiają
    niepowodzenia pojedynczych stron. Błąd pierwszej strony = BrakDanych (jak lista_morele)."""
    uwagi = [] if uwagi is None else uwagi
    maks_stron = max(1, min(int(maks_stron), STRON_SUFIT))
    strona_od = max(1, int(strona_od))
    bazowe = [FILTR_DDR5, FILTR_GAMING]
    url0 = adres_listy(bazowe, 1)
    if wolno is not None and not wolno(url0):
        raise BrakDanych(f"lista Morele PC: robots.txt zabrania {url0}")
    kod, s = pobierz(url0)
    if kod != 200:
        info = f"HTTP {kod}" + (f" {s}" if kod is None and s else "")
        raise BrakDanych(f"lista Morele PC: {info}")
    if not pozycje_listy(s):
        raise BrakDanych("lista Morele PC: strona niedostępna lub zmieniony układ — brak listy produktów")
    fasety = chipsety_z_listy(s)
    if not fasety:
        raise BrakDanych("lista Morele PC: strona niedostępna lub zmieniony układ — nie znaleziono faset chipsetu")
    if chipsety is not None:
        chciane = {c.strip().lower() for c in chipsety}
        fasety = [f for f in fasety if f[2].lower() in chciane]

    wynik = {}
    for grupa, fid, etykieta, liczba in sorted(fasety, key=lambda f: f[2]):
        widziane = set()
        for strona in range(strona_od, strona_od + maks_stron):
            if (strona - 1) * NA_STRONE >= liczba:
                break                                 # chipset nie ma już tylu ofert
            url = adres_listy(bazowe + [(grupa, fid)], strona)
            if wolno is not None and not wolno(url):
                uwagi.append(f"robots.txt zabrania: {url}")
                break
            kod, s = pobierz(url)
            if kod != 200:
                info = f"HTTP {kod}" + (f" {s}" if kod is None and s else "")
                uwagi.append(f"{info}: {url}")
                break
            nowych = 0
            for adres, nazwa, cena in pozycje_listy(s):
                if adres not in widziane:
                    widziane.add(adres)
                    nowych += 1
                if "DDR4" in nazwa.upper():
                    continue
                if cena is not None and not (CENA_LISTY_OD <= cena <= CENA_LISTY_DO):
                    continue
                wynik.setdefault(adres, None)
            # strona poza ostatnią wraca jako pierwsza (te same oferty) — to koniec chipsetu
            if nowych == 0 or '<link rel="next"' not in s:
                break
    return list(wynik)


def lista_monitorow(pobierz, maks_stron=6):
    """Morele sprzedaje monitory, ale zbiera je nowe_monitory.py (lista_morele)."""
    return []


def odczytaj_monitor(url, html):
    raise BrakDanych("monitory z Morele obsługuje nowe_monitory.py, ten adapter zbiera tylko komputery")


# ------------------------------------------------------------------ odczyt karty produktu
def produkt(s):
    """Product z ofertą i specyfikacją. Pomijamy ProductGroup i atrapy wariantów (same `url`)."""
    for o in jsonld(s):
        if o.get("@type") == "Product" and o.get("offers") and o.get("additionalProperty"):
            return o
    raise BrakDanych("strona niedostępna lub zmieniony układ: bez danych produktu (JSON-LD Product z ofertą i specyfikacją)")


def wlasciwosci(o):
    """Nazwa → wartość z additionalProperty. Ta sama nazwa o dwóch różnych wartościach to
    niejednoznaczność (np. „Moc” w dwóch grupach) — BrakDanych, nie wybór losowego."""
    w = {}
    for p in o.get("additionalProperty", []):
        if not isinstance(p, dict) or not p.get("name"):
            continue
        nazwa, wartosc = str(p["name"]).strip(), htmllib.unescape(str(p.get("value", ""))).strip()
        if nazwa in w and w[nazwa] != wartosc:
            raise BrakDanych(f"specyfikacja podaje pole „{nazwa}” dwa razy z różnymi wartościami")
        w[nazwa] = wartosc
    return w


def pole(w, nazwa):
    v = w.get(nazwa)
    if v is None or BRAK.match(v):
        raise BrakDanych(f"brak pola „{nazwa}” w specyfikacji" + (f" (sklep podaje: {v!r})" if v else ""))
    return v


def norm(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def cena_bez_kodu(url, s, cena_jsonld):
    """(cena_bazowa, kod, promo). Gdy strona pokazuje kod rabatowy, cena w JSON-LD jest ceną
    Z KODEM — cena_bazowa to wtedy „cena bez kodu” ze strony. Bez kodu: cena z JSON-LD."""
    promo = z.promo_ze_strony("morele", url, s)
    if not promo or not promo.get("kod"):
        return cena_jsonld, None, promo
    if not promo.get("bk"):
        raise BrakDanych(f"cena z kodem „{promo['kod']}”, a strona nie podaje ceny bez kodu")
    if promo["bk"] < cena_jsonld:
        raise BrakDanych(f"cena bez kodu ({promo['bk']} zł) niższa od ceny z JSON-LD ({cena_jsonld} zł)")
    return promo["bk"], promo["kod"], promo


def sprzedawca(s):
    """None = sprzedaje sam Morele.net; inaczej nazwa sprzedawcy marketplace."""
    m = re.search(r'data-testid="merchant-name"[^>]*>\s*([^<]+?)\s*<', s)
    if not m:
        raise BrakDanych("strona niedostępna lub zmieniony układ: strona nie podaje sprzedawcy — nie odróżnię Morele od marketplace")
    nazwa = htmllib.unescape(m.group(1)).strip()
    return None if nazwa.lower() == "morele.net" else nazwa


GPU_W_TEKSCIE = re.compile(r"\b(RTX|RX)\s*(\d{4})\s*(Ti|XT)?\b|\bArc\s*([AB]\d{3})\b", re.I)


def ram_ddr5(w, tytul=""):
    typ = pole(w, "Typ pamięci RAM")
    if not re.fullmatch(r"\s*DDR5\s*", typ, re.I):
        raise BrakDanych(f"pamięć nie jest DDR5: {typ!r}")
    if re.search(r"\bDDR4\b", tytul or "", re.I):
        raise BrakDanych(f"pamięć w tytule wskazuje DDR4: {tytul!r}")
    m = re.fullmatch(r"\s*(\d{1,3})\s*GB\s*", pole(w, "Wielkość pamięci RAM"), re.I)
    if not m:
        raise BrakDanych(f"nieczytelna pojemność RAM: {w.get('Wielkość pamięci RAM')!r}")
    spec_gb = int(m.group(1))

    t = tytul or ""
    t = re.sub(r"(?:" + GPU_W_TEKSCIE.pattern + r")(?:\s*\d{1,2}\s*GB)?", " ", t, flags=re.I)
    t = re.sub(r"\b\d+(?:[.,]\d+)?\s*TB\b", " ", t, flags=re.I)
    t = re.sub(r"\b\d+(?:[.,]\d+)?\s*GB(?=\s*(?:M\.2|SSD|NVMe|PCIe|HDD|dysk))\b(?:\s*(?:M\.2|SSD|NVMe|PCIe|HDD|dysk))?", " ", t, flags=re.I)
    ram_tytuly = [int(x) for x in re.findall(r"\b(\d{1,3})\s*GB(?=\s*(?:,|RAM|DDR[45]|\s*/|\s*$))", t, flags=re.I)]
    for rt in ram_tytuly:
        if rt != spec_gb:
            raise BrakDanych(f"pamięć RAM w tytule ({rt} GB) różni się od specyfikacji ({spec_gb} GB)")

    mhz = re.search(r"(\d{3,5})\s*MHz", w.get("Taktowanie", ""), re.I)
    return f"{m.group(1)}GB DDR5" + (f" {mhz.group(1)}MHz" if mhz else "")


def karta_z_tekstu(t):
    """(nazwa kanoniczna, klucz porównawczy) pierwszej karty w tekście albo None."""
    m = GPU_W_TEKSCIE.search(t or "")
    if not m:
        return None
    if m.group(4):
        return f"Intel Arc {m.group(4).upper()}", f"arc{m.group(4).lower()}"
    amd = m.group(1).upper() == "RX"
    sufiks = {"ti": " Ti", "xt": " XT"}.get((m.group(3) or "").lower(), "")
    nazwa = f"{'AMD Radeon RX' if amd else 'NVIDIA GeForce RTX'} {m.group(2)}{sufiks}"
    return nazwa, norm(f"{m.group(1)}{m.group(2)}{sufiks}")


def gpu_z_karty(w, tytul):
    """Kanoniczna karta jak nowe_pc.gpu_kanoniczna („NVIDIA GeForce RTX 5060 Ti 8GB”), z pamięcią
    z pola „Ilość pamięci karty graficznej”. Karta w tytule musi zgadzać się ze specyfikacją."""
    chip = pole(w, "Chipset graficzny")
    k = karta_z_tekstu(chip)
    if not k:
        raise BrakDanych(f"karta spoza zakresu (RTX/RX/Arc): {chip!r}")
    nazwa, klucz = k
    kt = karta_z_tekstu(tytul)
    if kt and kt[1] != klucz:
        raise BrakDanych(f"karta w specyfikacji ({chip}) różni się od karty w tytule ({kt[0]}): "
                         f"dane oferty są sprzeczne")
    vram = pole(w, "Ilość pamięci karty graficznej")
    mv = re.fullmatch(r"\s*(\d{1,2})\s*GB\s*", vram, re.I)
    if not mv:
        raise BrakDanych(f"nieczytelna pamięć karty: {vram!r}")
    for zrodlo, tekst in (("chipsecie", chip), ("tytule", tytul)):
        m = re.search("(?:" + GPU_W_TEKSCIE.pattern + r")\s*(\d{1,2})\s*GB", tekst or "", re.I)
        if m and m.group(5) != mv.group(1):
            raise BrakDanych(f"pamięć karty w {zrodlo} ({m.group(5)} GB) różni się od specyfikacji "
                             f"({mv.group(1)} GB)")
    if ocena_pc.znormalizuj_gpu(nazwa).replace("radeon ", "") not in ocena_pc.KLASA_GPU:
        raise BrakDanych(f"karta {nazwa!r} spoza słownika klas ocena_pc.KLASA_GPU")
    gpu = f"{nazwa} {mv.group(1)}GB"
    ocena_pc.klasa_gpu(gpu)
    return gpu


CPU_W_TYTULE = re.compile(r"Ryzen\s*\d\s*(?:AI\s*)?[A-Z0-9]+|Core\s*Ultra\s*\d\s*[A-Z0-9]+|Core\s*i\d\s*-?\s*[A-Z0-9]+",
                          re.I)


def cpu_z_karty(w, tytul):
    cpu = re.sub(r"\s+", " ", pole(w, "Model procesora")).strip()
    mt = CPU_W_TYTULE.search(tytul or "")
    bez_marki = lambda t: re.sub(r"^(amd|intel)", "", norm(t))
    if mt and bez_marki(mt.group(0)) != bez_marki(cpu):
        raise BrakDanych(f"procesor w specyfikacji ({cpu}) różni się od procesora w tytule ({mt.group(0)})")
    if re.match(r"core\b", cpu, re.I):
        cpu = "Intel " + cpu
    ocena_pc.klasa_cpu(cpu)                 # brak reguły klasy = pominięcie (BrakDanych)
    return cpu


def pojemnosc_gb(txt):
    """„1 TB” → 1000, „512 GB” → 512 (TB liczone jak ocena_pc: 1000); „Brak” → None."""
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(TB|GB)\s*", txt or "", re.I)
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    return int(round(n * 1000)) if m.group(2).upper() == "TB" else int(round(n))


def dysk_z_karty(w, tytul):
    """(„1TB SSD”, interfejs). Pola „Pojemność dysku SSD…” mogą powtarzać pojemność jednego dysku,
    więc o tym, ile jest dysków, rozstrzyga tytuł oferty — i musi zgadzać się ze specyfikacją."""
    pola = {k: pojemnosc_gb(v) for k, v in w.items() if k.lower().startswith("pojemność dysku ssd")}
    pola = {k: gb for k, gb in pola.items() if gb}
    if not pola:
        raise BrakDanych("brak dysku SSD w specyfikacji")
    wartosci = set(pola.values())
    z_tytulu = [pojemnosc_gb(a + b) for a, b in re.findall(
        r"(\d+(?:[.,]\d+)?)\s*(TB|GB)(?=\s*(?:M\.2|SSD|NVMe|PCIe))", tytul or "", re.I)]
    if len(z_tytulu) == 1 and z_tytulu[0]:
        gb = z_tytulu[0]
        if gb not in wartosci and gb != sum(pola.values()):
            raise BrakDanych(f"dysk w tytule ({gb} GB) nie zgadza się ze specyfikacją ({sorted(wartosci)} GB)")
    elif len(pola) == 1:
        gb = next(iter(wartosci))
    else:
        raise BrakDanych("kilka pól dysku bez jednoznacznej pojemności w tytule — nie wiem, ile jest dysków")
    storage = f"{gb // 1000}TB SSD" if gb % 1000 == 0 else f"{gb}GB SSD"
    interfejsy = [re.sub(r"^pojemność dysku ssd\s*", "", k, flags=re.I).strip() or "SSD" for k in pola]
    return storage, ", ".join(sorted(set(interfejsy)))


def zasilacz(w):
    m = re.search(r"(\d{3,4})\s*W\b", pole(w, "Moc"))
    if not m:
        raise BrakDanych(f"nieczytelna moc zasilacza: {w.get('Moc')!r}")
    return f"{m.group(1)}W"


def system(w):
    """Karta Morele nie ma konfiguratora: system jest w cenie albo go nie ma (dopłata = None)."""
    nazwa = w.get("System operacyjny")
    if not nazwa or BRAK.match(nazwa):
        return {"w_cenie": None, "doplata": None, "nazwa": None}
    if re.match(r"\s*windows", nazwa, re.I):
        w_cenie = True
    elif re.search(r"bez systemu|brak systemu|freedos|\bdos\b|linux", nazwa, re.I):
        w_cenie = False
    else:
        w_cenie = None
    return {"w_cenie": w_cenie, "doplata": None, "nazwa": nazwa}


def zdjecie_url(o, s):
    img = o.get("image")
    img = img[0] if isinstance(img, list) and img else img
    if isinstance(img, dict):
        img = img.get("url")
    if not img:
        m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', s)
        img = m.group(1) if m else None
    if not img:
        raise BrakDanych("brak zdjęcia na stronie produktu")
    return htmllib.unescape(img)


def odczytaj_pc(url, html):
    """Karta komputera → słownik z kontraktu adaptera. BrakDanych, gdy czegokolwiek brakuje,
    dane są sprzeczne albo oferta nie spełnia kryteriów (DDR5, karta ze słownika klas)."""
    s = html
    o = produkt(s)
    nazwa = re.sub(r"\s+", " ", htmllib.unescape(str(o.get("name") or ""))).strip()
    if not nazwa:
        raise BrakDanych("brak nazwy")
    pid = str(o.get("productID") or o.get("sku") or "")
    m = re.search(r"-(\d{6,9})/?(?:\?.*)?$", url)
    if m and pid and m.group(1) != pid:
        raise BrakDanych(f"adres prowadzi do innego produktu (id {pid}, oczekiwano {m.group(1)})")
    of = o.get("offers") or {}
    of = of[0] if isinstance(of, list) and of else of
    if not isinstance(of, dict) or not str(of.get("availability", "")).endswith("InStock"):
        raise BrakDanych("nie ma w sprzedaży (availability ≠ InStock)")
    cena_jsonld = z._liczba(of.get("price"))
    if not cena_jsonld:
        raise BrakDanych("brak ceny")
    cena, kod, promo = cena_bez_kodu(url, s, cena_jsonld)
    if not (CENA_PC_OD <= cena <= CENA_PC_DO):
        raise BrakDanych(f"cena {cena} zł poza wiarygodnym zakresem {CENA_PC_OD}–{CENA_PC_DO} zł")

    w = wlasciwosci(o)
    ram = ram_ddr5(w, nazwa)
    gpu = gpu_z_karty(w, nazwa)
    cpu = cpu_z_karty(w, nazwa)
    storage, dysk_typ = dysk_z_karty(w, nazwa)
    psu = zasilacz(w)
    mpn = str(o.get("mpn") or "").strip()
    ean = re.sub(r"\D", "", str(o.get("gtin13") or o.get("gtin") or ""))
    return {"nazwa": nazwa, "url": url, "cpu": cpu, "gpu": gpu, "ram": ram, "storage": storage,
            "psu": psu, "cena_bazowa": cena, "system": system(w), "dostepny": True,
            "sprzedawca": sprzedawca(s), "zdjecie": zdjecie_url(o, s), "ean": ean or None,
            "kod_modelu": mpn if re.search(r"\d", mpn) and not re.search(r"\s", mpn) else None,
            "opcje": {}, "dysk_typ": dysk_typ, "kod_rabatowy": kod,
            "cena_z_kodem": cena_jsonld if kod else None, "promo": promo}
