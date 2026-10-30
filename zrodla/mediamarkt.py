#!/usr/bin/env python3
"""Adapter sklepu MediaMarkt (mediamarkt.pl): monitory QHD 26-28" 240-500 Hz i gotowe komputery DDR5.

Adapter jest CZYSTY: funkcje odczytu biorą adres i tekst strony, niczego nie pobierają. Pobieranie
robi wyłącznie wstrzyknięty argument `pobierz` (w produkcji zbieraj_ceny.pobierz, w teście atrapa).

Skąd biorą się dane (rozpoznanie 30.10.2026, 21 zapytań, robots.txt przeczytany):
- strona produktu ma blok JSON-LD „BuyAction" z ofertą TEGO produktu (cena, dostępność, zdjęcie)
  oraz osadzony stan aplikacji `window.__PRELOADED_STATE__` z tabelą cech (Matryca, Przekątna,
  Procesor, Typ pamięci RAM, Moc zasilania…), ceną, statusem dostępności i sprzedawcą;
- w nagłówku strony bywają też oferty SĄSIEDNICH wariantów (inny kolor, inny model serii). Dlatego
  cenę czytamy z oferty dopasowanej do numeru produktu, nigdy z „pierwszej oferty na stronie"
  (tak działa zbieraj_ceny.z_mediamarkt i przez to zwraca cenę wariantu: patrz test);
- strona jest wybierana po numerze na końcu adresu (nazwa w adresie jest dowolna), a sklepy potrafią
  przydzielić numer ponownie innemu SKU — sprawdzamy więc zgodność numeru z JSON-LD oraz rodzaj
  produktu (MONITOR / PERSONAL_COMPUTER); stan strony zawiera też obce produkty (akcesoria), więc
  produkt zawsze wybieramy po numerze, nigdy »pierwszy z brzegu«;
- lista kategorii podaje 12 produktów na stronę, tytuł, adres i cenę. Filtrów sklepu NIE wolno
  używać: robots.txt zabrania adresów z „?filter", „?sort=", „query", „pl/search".

ZASADA jak w całym serwisie: BRAK zamiast zgadywania. Każda dana pochodzi ze strony sklepu;
brak, sprzeczność albo niejednoznaczność = ocena_pc.BrakDanych z powodem po polsku.
"""
import html as htmllib, json, os, re, sys, urllib.parse

BAZA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BAZA not in sys.path:
    sys.path.insert(0, BAZA)
import ocena_pc
from ocena_pc import BrakDanych

SKLEP = "mediamarkt"
LOKALNIE = False                      # MediaMarkt odpowiada także z chmury
SKLEP_UWAGI = (
    "Listy: tylko kategorie BEZ filtrów (robots.txt zabrania ?filter/?sort/query/pl/search), "
    "12 pozycji na stronę, ?page=N, maxPage kategorii wynosi najwyżej 30 (407 pozycji = 34 strony). Monitory: "
    "»Monitory OLED« (73 poz.) i »Monitory dla graczy« (407 poz.); brak kategorii 240 Hz, więc "
    "prefiltr po tytule i cenie z listy, resztę rozstrzyga karta. Komputery: »Komputery gamingowe« "
    "(258 poz.), prawie wyłącznie marketplace (BEASTCOM, Nitropc, Bleu Jour, KUBB). Karta podaje "
    "sprzedawcę marketplace, zasilacz i pamięć karty tylko u części sprzedawców (w sprawdzonych "
    "kartach BEASTCOM brak obu, a mają też DDR4: odrzucenie), a system jako cechę »System operacyjny« bez "
    "osobnej ceny licencji. Ceny podane z groszami (9329,99) zaokrąglamy do pełnych złotych."
)

HOST = "mediamarkt.pl"
KATEGORIE_MONITOROW = ("/pl/category/monitory-oled-70392.html",
                       "/pl/category/monitory-dla-graczy-31050.html")
KATEGORIA_PC = "/pl/category/komputery-gamingowe-50070.html"
STRON_MAKS = 30                       # maxPage podawane przez sklep nie przekracza 30 (407 pozycji = 34 strony)
ADRESOW_MAKS = 400                    # górny limit adresów oddawanych z jednego wywołania

HZ_OD, HZ_DO = 240, 500               # jak w nowe_monitory.py
DIAG_OD, DIAG_DO = 26.0, 28.0
CENA_MON_OD, CENA_MON_DO = 500, 6000  # poza zakresem to błąd odczytu, nie monitor
CENA_PC_OD, CENA_PC_DO = 5000, 10000  # = nowe_pc.CENA_OD_BEZ_SYSTEMU / SUFIT_Z_WINDOWS (pilnuje test)
ZASILACZ_WYMAGANY = True              # False: brak zasilacza daje psu=None zamiast odrzucenia

MARKI = {"asus": "ASUS", "msi": "MSI", "aoc": "AOC", "lg": "LG", "hp": "HP", "dell": "Dell",
         "acer": "Acer", "benq": "BenQ", "aorus": "AORUS", "samsung": "Samsung",
         "gigabyte": "Gigabyte", "lenovo": "Lenovo", "philips": "Philips", "iiyama": "iiyama",
         "viewsonic": "ViewSonic", "alienware": "Alienware", "asrock": "ASRock",
         "dahua": "Dahua", "koorui": "Koorui"}


# ------------------------------------------------------------------ robots.txt
# robots.txt MediaMarkt (User-agent: *) zabrania adresów ZAWIERAJĄCYCH te fragmenty (wzorce
# „*?filter*", „*?sort=*", „*query*", „*pl/search", „*pl/promo-list") oraz kilku ścieżek technicznych.
# urllib.robotparser nie rozumie znaków „*", więc zbieraj_ceny.REGULAMIN.wolno() takich adresów NIE
# zatrzyma — dlatego adapter pilnuje ich sam, zanim cokolwiek trafi do `pobierz`.
ZAKAZANE_FRAGMENTY = ("?filter", "?sort=", "query", "pl/search", "pl/promo-list")
ZAKAZANE_PREFIKSY = ("/cdn-cgi/", "/rde_server/", "/api/v1/", "/public/setcookie/", "/myaccount/auth")


def dozwolony(url):
    """True tylko dla adresów kategorii i produktów na mediamarkt.pl, których robots.txt nie zabrania."""
    try:
        p = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if p.scheme != "https" or p.netloc.lower() != HOST:
        return False
    if not (p.path.startswith("/pl/category/") or p.path.startswith("/pl/product/")):
        return False
    if p.query and not re.fullmatch(r"page=\d{1,3}", p.query):
        return False                                    # jedyny parametr, jakiego używamy, to ?page=N
    cel = (p.path + ("?" + p.query if p.query else "")).lower()
    return not (any(f in cel for f in ZAKAZANE_FRAGMENTY) or any(cel.startswith(x) for x in ZAKAZANE_PREFIKSY))


def adres_listy(sciezka, numer):
    """Strona 1 bez parametrów, kolejne jako ?page=N (jedyny parametr, którego robots.txt nie zabrania)."""
    return f"https://{HOST}{sciezka}" + ("" if numer <= 1 else f"?page={numer}")


# ------------------------------------------------------------------ odczyt strony
def stan_strony(s):
    """Obiekt apolloState z `window.__PRELOADED_STATE__`. Sklep wypisuje tam `undefined`, które nie jest
    JSON-em, więc zamieniamy je na null. Brak stanu = zmieniony układ albo strona blokady."""
    znacznik = "window.__PRELOADED_STATE__ = "
    i = (s or "").find(znacznik)
    if i < 0:
        raise BrakDanych("strona niedostępna: strona bez stanu aplikacji (window.__PRELOADED_STATE__) — "
                         "zmienił się układ strony albo to strona blokady")
    i += len(znacznik)
    j = s.find("</script>", i)
    tekst = re.sub(r":undefined\b", ":null", s[i:j if j > 0 else None].strip().rstrip(";"))
    try:
        stan = json.loads(tekst)
    except ValueError:
        raise BrakDanych("strona niedostępna: stan strony nie jest poprawnym JSON-em — zmienił się układ strony")
    a = stan.get("apolloState") if isinstance(stan, dict) else None
    if not isinstance(a, dict):
        raise BrakDanych("strona niedostępna: stan strony bez apolloState — zmienił się układ strony")
    return a


def jsonld(s):
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', s or "", re.S):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:
            continue
        for o in (d if isinstance(d, list) else [d]):
            if isinstance(o, dict):
                yield o


def produkt_ld(s):
    """Product z bloku BuyAction (oferta tej strony) albo None — wycofana pozycja nie ma tego bloku."""
    for o in jsonld(s):
        if o.get("@type") == "BuyAction" and isinstance(o.get("object"), dict):
            return o["object"]
    return None


def oferty_ld(prod):
    of = (prod or {}).get("offers") or []
    of = of if isinstance(of, list) else [of]
    return [o for o in of if isinstance(o, dict)]


def zl(x):
    """Cena ze strony → pełne złote (jak zbieraj_ceny._liczba: 9329,99 → 9330). None, gdy to nie cena."""
    try:
        w = float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return int(round(w)) if 1 <= w <= 100000 else None


def czysty(t):
    return re.sub(r"\s+", " ", htmllib.unescape(str(t or ""))).strip()


def numer_z_adresu(url):
    m = re.search(r"-(\d{5,12})\.html(?:[?#].*)?$", url or "")
    return m.group(1) if m else None


def znajdz(a, typ, **pola):
    """Pierwszy obiekt stanu o danym __typename i polach (np. id)."""
    for v in a.values():
        if isinstance(v, dict) and v.get("__typename") == typ and all(v.get(k) == w for k, w in pola.items()):
            return v
    return None


def cechy(a, pid):
    """Tabela cech produktu: nazwa → lista (wartość, jednostka) w kolejności ze strony. Ta sama cecha
    bywa podana kilka razy (np. »Rozdzielczość« jako »2560 x 1440« i »QHD 2560 x 1440«)."""
    if not isinstance(a, dict):
        raise BrakDanych("karta bez tabeli cech produktu")
    grupy = a.get(f"GraphqlProductFeatureGroups:{pid}")
    if not isinstance(grupy, dict):
        raise BrakDanych("karta bez tabeli cech produktu")
    f_groups = grupy.get("featureGroups")
    if not isinstance(f_groups, list):
        return {}
    wynik = {}
    for g in f_groups:
        if not isinstance(g, dict):
            continue
        features = g.get("features")
        if not isinstance(features, list):
            continue
        for r in features:
            if not isinstance(r, dict):
                continue
            ref = r.get("__ref")
            if not isinstance(ref, str):
                continue
            f = a.get(ref)
            if isinstance(f, dict) and f.get("name"):
                wynik.setdefault(czysty(f["name"]), []).append((czysty(f.get("value")), czysty(f.get("unit"))))
    return wynik


def wartosc(c, nazwa):
    """Jedyna wartość cechy (tekst) albo None. Dwie RÓŻNE wartości tej samej cechy = sprzeczność."""
    wartosci = []
    for w, _ in c.get(nazwa, []):
        if w and w not in wartosci:
            wartosci.append(w)
    if len(wartosci) > 1:
        raise BrakDanych(f"sprzeczne wartości cechy »{nazwa}«: {wartosci[:3]}")
    return wartosci[0] if wartosci else None


def liczba(txt):
    m = re.search(r"\d+(?:[.,]\d+)?", txt or "")
    return float(m.group(0).replace(",", ".")) if m else None


# ------------------------------------------------------------------ wspólny odczyt karty
def karta(url, s, rodzaj_produktu, opis_rodzaju):
    """Dane wspólne monitora i komputera. Rzuca BrakDanych, gdy strona jest innym produktem, towar
    nie jest nowy albo nie ma go w sprzedaży."""
    a = stan_strony(s)
    pid = numer_z_adresu(url)
    ld = produkt_ld(s)
    if ld and ld.get("sku") and pid and str(ld["sku"]) != pid:
        raise BrakDanych(f"adres prowadzi do innego produktu (sku {ld['sku']} ≠ {pid} z adresu)")
    pid = pid or (str(ld["sku"]) if ld and ld.get("sku") else None)
    if not pid:
        raise BrakDanych("nie da się ustalić numeru produktu z adresu ani ze strony")
    prod = znajdz(a, "GraphqlProduct", id=pid, salesLine="Media")
    if not prod:
        raise BrakDanych(f"strona niedostępna: stan strony nie zawiera produktu {pid} — zmienił się układ strony")
    tytul = czysty(prod.get("title"))
    if re.search(r"EKSPOZYCJ|OUTLET|ODNOWION|REFURB|UŻYWAN|PO ZWROCIE|USZKODZON|OTWART", tytul, re.I):
        raise BrakDanych("towar nie jest nowy (tytuł)")
    refurb = znajdz(a, "CofrRefurbishedGoodsFeature", id=f"Media:pl:{pid}")
    if isinstance(refurb, dict) and refurb.get("type") == "MARKETPLACE_REFURBISHED":
        raise BrakDanych("oferta odnowiona")
    if prod.get("kindOfProduct") != rodzaj_produktu:
        raise BrakDanych(f"to nie {opis_rodzaju} (rodzaj produktu: {prod.get('kindOfProduct')}, "
                         f"tytuł: {tytul[:50]!r})")
    status = znajdz(a, "CofrOnlineStatusFeature", id=f"Media:pl:{pid}")
    if not status:
        raise BrakDanych("strona niedostępna: karta bez statusu dostępności")
    if status.get("isAvailableAndBuyable") is not True:
        raise BrakDanych(f"nie ma w sprzedaży (status: {status.get('onlineStatus')})")
    oferta_ld = oferty_ld(ld)
    if ld and oferta_ld and not str(oferta_ld[0].get("availability", "")).endswith("InStock"):
        raise BrakDanych(f"nie ma w sprzedaży (availability {oferta_ld[0].get('availability')})")
    for o in oferta_ld:
        if o.get("itemCondition") and not str(o["itemCondition"]).endswith("NewCondition"):
            raise BrakDanych(f"towar nie jest nowy ({str(o['itemCondition']).split('/')[-1]})")
    cp = znajdz(a, "CofrPriceFeature", id=f"Media:pl:{pid}") or {}
    cena = zl(((cp.get("price") or {}).get("amount")))
    if cena is None and oferta_ld:
        cena = zl(oferta_ld[0].get("price"))
    if cena is None:
        raise BrakDanych("brak ceny")
    cena_ld = [zl(o.get("price")) for o in oferta_ld]
    if cena_ld and all(x is not None and abs(x - cena) > 1 for x in cena_ld):
        raise BrakDanych(f"rozbieżne ceny: stan strony {cena} zł, JSON-LD {cena_ld[0]} zł")
    sprzedawca = None
    if cp.get("isProductOfTypeMarketplace"):
        sp = cp.get("marketplaceSeller") or {}
        sprzedawca = czysty(sp.get("sellerName")) or None
        if not sprzedawca and oferta_ld:
            sprzedawca = czysty((oferta_ld[0].get("seller") or {}).get("name")) or None
        if not sprzedawca:
            raise BrakDanych("oferta marketplace bez nazwy sprzedawcy")
    if sprzedawca and re.search(r"refurb", sprzedawca, re.I):
        raise BrakDanych(f"towar nie jest nowy (sprzedawca: {sprzedawca})")
    zdjecie = (ld or {}).get("image")
    zdjecie = zdjecie[0] if isinstance(zdjecie, list) and zdjecie else zdjecie
    if not zdjecie or not str(zdjecie).startswith("http"):
        raise BrakDanych("brak zdjęcia na stronie produktu")
    ean = next((re.sub(r"\D", "", str(x)) for x in (prod.get("ean"), (ld or {}).get("gtin13"))
                if re.fullmatch(r"\d{8,14}", re.sub(r"\D", "", str(x or "")))), None)
    return {"id": pid, "tytul": tytul, "producent": czysty(prod.get("manufacturer")), "cena": cena,
            "sprzedawca": sprzedawca, "zdjecie": str(zdjecie), "ean": ean, "cechy": cechy(a, pid)}


def sprzedawca_z_karty(s):
    """Nazwa sprzedawcy zewnętrznego (marketplace) albo None, gdy towar sprzedaje MediaMarkt sam.
    Monitory też bywają z marketplace (Gigabyte GO27Q24A: Action S.A. PL); kontrakt monitora nie ma
    na to pola, więc to osobna funkcja pomocnicza."""
    a = stan_strony(s)
    ld = produkt_ld(s)
    pid = str(ld["sku"]) if ld and ld.get("sku") else None
    cp = znajdz(a, "CofrPriceFeature", id=f"Media:pl:{pid}") if pid else None
    if not cp or not cp.get("isProductOfTypeMarketplace"):
        return None
    return czysty((cp.get("marketplaceSeller") or {}).get("sellerName")) or None


# ------------------------------------------------------------------ monitory: lista
def tytul_monitora_odpada(t):
    """Powód odrzucenia po samym tytule z listy albo None. Odrzuca WYŁĄCZNIE przy jawnym przeciwieństwie
    (inne odświeżanie, ultrawide/4K/FHD, przekątna spoza 26-28"): tytuł bez parametrów, jak
    »Monitor GIGABYTE GO27Q24A Czarny« u sprzedawców marketplace, idzie dalej do karty."""
    if re.search(r"EKSPOZYCJ|OUTLET|ODNOWION|REFURB|UŻYWAN|PO ZWROCIE|USZKODZON|OTWART", t or "", re.I):
        return "towar nie jest nowy (tytuł)"
    herce = [int(x) for x in re.findall(r"(?<![\d.,])(\d{2,3})\s?Hz\b", t or "", re.I)]
    if herce and max(herce) < HZ_OD:
        return f"{max(herce)} Hz poniżej {HZ_OD} Hz"
    wysoka = re.search(r"\b(UW\s?QHD|UWHD|WUHD|WFHD|UWFHD|UHD|4K|5K|FHD|Full HD)\b", t or "", re.I)
    if wysoka and not re.search(r"(?<![A-Za-z])W?QHD\b", t or "", re.I):
        return f"rozdzielczość {wysoka.group(1)} (wymagane QHD 2560 x 1440)"
    przekatne = [float(x.replace(",", ".")) for x in re.findall(
        r"""(?<![\d.,A-Za-z-])(\d{2}(?:[.,]\d)?)\s*(?:"|”|″|'')""", t or "")]
    przekatne += [float(x.replace(",", ".")) for x in re.findall(
        r"(?<![\d.,A-Za-z-])(\d{2}(?:[.,]\d)?)\s+(?=(?:UW|W)?(?:QHD|FHD|UHD|4K|2K|OLED|IPS|VA)\b)", t or "", re.I)]
    if przekatne and not any(DIAG_OD <= x <= DIAG_DO for x in przekatne):
        return f"przekątna {przekatne[0]:g}\" poza zakresem {DIAG_OD:g}-{DIAG_DO:g}\""
    return None


def produkty_z_listy(s):
    """(produkty, maks_stron) ze strony kategorii. Produkt: {id, tytul, url (bezwzględny), cena|None,
    sprzedawca|None}; kolejność jak w sklepie, bez powtórzeń."""
    a = stan_strony(s)
    spis = next((v for v in a.values() if isinstance(v, dict) and v.get("__typename") == "ProductList"), None)
    strony = [v for v in a.values() if isinstance(v, dict) and v.get("__typename") == "ProductListPage"]
    if spis is None or not strony:
        raise BrakDanych("strona niedostępna: strona kategorii bez listy produktów — zmienił się układ strony")
    wynik, widziane = [], set()
    for st in strony:
        if not isinstance(st, dict):
            continue
        products = st.get("products")
        if not isinstance(products, list):
            continue
        for p in products:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("productId", ""))
            gp = znajdz(a, "GraphqlProduct", id=pid, salesLine="Media")
            if not pid or pid in widziane or not isinstance(gp, dict) or not gp.get("url"):
                continue
            widziane.add(pid)
            cp = znajdz(a, "CofrPriceFeature", id=f"Media:pl:{pid}")
            cp = cp if isinstance(cp, dict) else {}
            price_obj = cp.get("price") if isinstance(cp, dict) else None
            price_amount = price_obj.get("amount") if isinstance(price_obj, dict) else None
            seller_obj = cp.get("marketplaceSeller") if isinstance(cp, dict) else None
            seller_name = seller_obj.get("sellerName") if isinstance(seller_obj, dict) else None
            refurb = znajdz(a, "CofrRefurbishedGoodsFeature", id=f"Media:pl:{pid}")
            refurb_type = refurb.get("type") if isinstance(refurb, dict) else None
            wynik.append({"id": pid, "tytul": czysty(gp.get("title")),
                          "url": f"https://{HOST}{gp['url']}" if str(gp["url"]).startswith("/") else gp["url"],
                          "cena": zl(price_amount),
                          "sprzedawca": czysty(seller_name) or None,
                          "refurb_type": refurb_type})
    maks = spis.get("maxPage")
    return wynik, int(maks) if isinstance(maks, int) and maks > 0 else 1


def zbierz_adresy(pobierz, kategorie, maks_stron, maks_adresow, odpada):
    """Adresy kart z kategorii. Strona inna niż 200 (403, limit, błąd sieci) kończy tę kategorię:
    blokady nie obchodzimy, oddajemy to, co już mamy. Zmiana układu na PIERWSZEJ stronie to BrakDanych."""
    wynik, widziane = [], set()
    for sciezka in kategorie:
        for nr in range(1, max(1, min(int(maks_stron), STRON_MAKS)) + 1):
            url = adres_listy(sciezka, nr)
            if not dozwolony(url):
                break
            kod, s = pobierz(url)
            if kod != 200 or not s:
                break
            try:
                produkty, maks = produkty_z_listy(s)
            except BrakDanych as x:
                if nr == 1:
                    raise BrakDanych(f"lista MediaMarkt niedostępna ({sciezka}): {x}")
                break
            for p in produkty:
                if p["url"] in widziane or not dozwolony(p["url"]) or odpada(p):
                    continue
                widziane.add(p["url"])
                wynik.append(p["url"])
                if len(wynik) >= maks_adresow:
                    return wynik
            if not produkty or nr >= maks:
                break
    return wynik


def lista_monitorow(pobierz, maks_stron=6, maks_adresow=ADRESOW_MAKS):
    """Adresy kart monitorów, które mogą być QHD 26-28" 240-500 Hz. `maks_stron` liczy się NA
    KATEGORIĘ (dwie kategorie, 12 pozycji na stronę): »Monitory OLED« ma 7 stron, »Monitory dla
    graczy« 30. Przed pobraniem karty odpadają pozycje bez ceny (nie do kupienia), z ceną poza
    zakresem i z jawnie niepasującym tytułem; resztę rozstrzyga odczytaj_monitor()."""
    def odpada(p):
        return (p["cena"] is None or not (CENA_MON_OD <= p["cena"] <= CENA_MON_DO)
                or tytul_monitora_odpada(p["tytul"]) is not None
                or p.get("refurb_type") == "MARKETPLACE_REFURBISHED"
                or bool(p.get("sprzedawca") and re.search(r"refurb", p["sprzedawca"], re.I)))
    return zbierz_adresy(pobierz, KATEGORIE_MONITOROW, maks_stron, maks_adresow, odpada)


# ------------------------------------------------------------------ monitory: karta
def nazwa_monitora(tytul, producent):
    """„Monitor ASUS ROG Strix XG27AQDPG 26,5 WQHD OLED 0.03ms 500Hz … Czarny" → „ASUS ROG Strix XG27AQDPG".
    Tytuł tnie się przy pierwszym parametrze (przekątna, odświeżanie, czas reakcji) i kolorze na końcu."""
    n = re.sub(r"^(?:Gaming[- ]?monitor|Monitor gamingowy|Monitor do gier|Gamingowy monitor|Monitor)\s+",
               "", czysty(tytul), flags=re.I)
    parametr = re.search(r"""\s(?:\d{2}(?:[.,]\d)?\s*(?:"|”|″)
                            |\d{2}(?:[.,]\d)?\s+(?=(?:UW|W)?(?:QHD|FHD|UHD|HD|2K|4K|OLED|IPS|VA)\b)
                            |\d{2,3}\s?Hz\b|\d(?:[.,]\d+)?\s?ms\b)""", n, re.I | re.X)
    if parametr:
        n = n[:parametr.start()]
    kolory = (r"czarny|biały|bialy|srebrny|szary|niebieski|czerwony|różowy|zielony|złoty|"
              r"dwukolorowy|biało-czarny|czarno-szary|brązowy|fioletowy|pomarańczowy")
    n = re.sub(rf"(?:[\s,;/]+(?:{kolory}))+\s*$", "", n, flags=re.I).strip(" ,;-|")
    n = re.sub(r"(?:\s+(?:W?QHD|OLED|QD-OLED|IPS|VA))+$", "", n, flags=re.I).strip(" ,;-|")
    n = n.replace("'", "’")
    s = n.split(" ")
    if len(s) > 1 and s[0].lower() == s[1].lower():
        s = s[1:]                                       # „LG LG UltraGear" → „LG UltraGear"
    if producent and s and s[0].lower() != producent.lower() and producent.lower() not in n.lower():
        s = [producent] + s
    if s and s[0].lower() in MARKI:
        s[0] = MARKI[s[0].lower()]
    n = " ".join(s).strip()
    if not n or len(n) > 60 or not re.search(r"[A-Za-z]*\d[A-Za-z0-9-]{2,}", n):
        raise BrakDanych(f"tytuł karty nie jest nazwą modelu: {tytul[:60]!r}")
    return n


def matryca(typ, tytul, typ_panelu, zakrzywiony):
    """(panelName, panel) z cechy »Matryca«. Typ spoza listy = odrzucenie, nie zgadywanie. Sklep podaje
    często ogólne »OLED«; jawne »QD-OLED« / »WOLED« / »Tandem« w tytule lub w etykiecie energetycznej
    (»Typ panelu«) tylko doprecyzowuje to samo pole — nie dopisujemy niczego, czego strona nie pisze."""
    t = (typ or "").strip()
    glowa = re.sub(r"\s*\(.*$", "", t).strip()
    u = glowa.upper()
    kontekst = f"{tytul or ''} {typ_panelu or ''}".upper()
    if u in ("OLED", "QD-OLED", "QD OLED", "WOLED", "TANDEM OLED", "TANDEM WOLED"):
        if u.startswith("QD") or re.search(r"QD[- ]?OLED", kontekst):
            nazwa, klucz = "QD-OLED", "qdoled"
        elif "TANDEM" in u or "TANDEM" in kontekst:
            nazwa, klucz = "OLED (Tandem)", "oled"
        elif u == "WOLED" or re.search(r"\bWOLED\b", kontekst):
            nazwa, klucz = "OLED (WOLED)", "oled"
        else:
            nazwa, klucz = "OLED", "oled"
    elif re.fullmatch(r"(FAST |RAPID |NANO |SS |SUPER SPEED )?IPS( BLACK)?", u):
        nazwa, klucz = glowa, "ips"
    elif u == "VA":
        nazwa, klucz = "VA", "va"
    else:
        raise BrakDanych(f"typ matrycy „{t or 'brak'}” spoza zakresu (IPS/VA/OLED/QD-OLED)")
    if klucz in ("ips", "va") and re.search(r"\bOLED\b", (tytul or "").upper()):
        raise BrakDanych(f"sprzeczny typ matrycy: cecha »{t}«, a tytuł mówi OLED")
    if (zakrzywiony or "").lower().startswith("tak"):
        nazwa += ", zakrzywiony"
    return nazwa, klucz


def odczytaj_monitor(url, html):
    """Dane z karty monitora → słownik z kluczami nowe_monitory.odczytaj (+ kod_modelu, ean).
    BrakDanych, gdy czegokolwiek brakuje, nie pasuje albo nie ma towaru w sprzedaży."""
    k = karta(url, html, "MONITOR", "monitor")
    c = k["cechy"]
    diag = liczba(wartosc(c, "Przekątna ekranu (cal)"))
    if diag is None:
        raise BrakDanych("brak przekątnej")
    if not (DIAG_OD <= diag <= DIAG_DO):
        raise BrakDanych(f"przekątna {diag:g}\" poza zakresem {DIAG_OD:g}–{DIAG_DO:g}\"")
    rozdzielczosci = {r for w, _ in c.get("Rozdzielczość", []) for r in re.findall(r"\d{3,5}\s*x\s*\d{3,5}", w, re.I)}
    rozdzielczosci = {re.sub(r"\s+", "", r).lower() for r in rozdzielczosci}
    if rozdzielczosci != {"2560x1440"}:
        raise BrakDanych(f"rozdzielczość „{', '.join(sorted(rozdzielczosci)) or 'brak'}” (wymagane 2560 x 1440)")
    hz = liczba(wartosc(c, "Częstotliwość odświeżania (maksymalna)") or wartosc(c, "Częstotliwość odświeżania"))
    if hz is None:
        raise BrakDanych("brak częstotliwości odświeżania")
    hz = int(hz)
    if not (HZ_OD <= hz <= HZ_DO):
        raise BrakDanych(f"{hz} Hz poza zakresem {HZ_OD}–{HZ_DO} Hz")
    nazwa_matrycy, klucz_matrycy = matryca(wartosc(c, "Matryca"), k["tytul"], wartosc(c, "Typ panelu"),
                                           wartosc(c, "Zakrzywiony ekran"))
    if not (CENA_MON_OD <= k["cena"] <= CENA_MON_DO):
        raise BrakDanych(f"cena {k['cena']} zł poza wiarygodnym zakresem {CENA_MON_OD}–{CENA_MON_DO} zł")
    nazwa = nazwa_monitora(k["tytul"], k["producent"])      # na końcu: najpierw powód z parametrów
    kod = wartosc(c, "Kod producenta")
    kod = None if not kod or kod.lower() in ("-", "brak", "n/a", "nie dotyczy") else kod
    return {"nazwa": nazwa, "url": url, "hz": hz, "diag": diag, "panelName": nazwa_matrycy,
            "panel": klucz_matrycy, "cena": k["cena"], "zdjecie": k["zdjecie"],
            "kod_modelu": kod, "ean": k["ean"]}


# ------------------------------------------------------------------ komputery: lista
def lista_pc(pobierz, maks_stron=6, maks_adresow=ADRESOW_MAKS, cena_od=CENA_PC_OD, cena_do=CENA_PC_DO):
    """Adresy kart gotowych komputerów z kategorii »Komputery gamingowe« (12 na stronę, 22 strony).
    Sklep nie pozwala filtrować po standardzie pamięci (filtry zabronione), więc po liście odpadają
    tylko: brak ceny, cena poza progiem naboru, tytuł z DDR4 i komputery All-in-One. Tytuły są
    ogólne (»DESKTOP GAMING BEASTCOM Q5«) — specyfikację czyta odczytaj_pc() z tabeli cech."""
    def odpada(p):
        return (p["cena"] is None or not (cena_od <= p["cena"] <= cena_do)
                or bool(re.search(r"DDR4|All[- ]?in[- ]?One|\bAIO\b", p["tytul"], re.I))
                or bool(re.search(r"EKSPOZYCJ|OUTLET|ODNOWION|REFURB|UŻYWAN|PO ZWROCIE|USZKODZON|OTWART", p["tytul"], re.I))
                or p.get("refurb_type") == "MARKETPLACE_REFURBISHED"
                or bool(p.get("sprzedawca") and re.search(r"refurb", p["sprzedawca"], re.I)))
    return zbierz_adresy(pobierz, (KATEGORIA_PC,), maks_stron, maks_adresow, odpada)


# ------------------------------------------------------------------ komputery: karta
def bez_znakow_firmowych(t):
    t = re.sub(r"[™®©]|\((?:R|TM)\)", "", t or "", flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def procesor(c):
    t = bez_znakow_firmowych(wartosc(c, "Procesor") or wartosc(c, "Model procesora"))
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()      # „(6 rdzeni, 12 wątków | 4,20 GHz …)" na końcu
    if not t:
        raise BrakDanych("brak procesora")
    if not re.search(r"\d{4,5}|Ultra \d \d{3}", t, re.I):
        raise BrakDanych(f"zbyt ogólna nazwa procesora (brak modelu): {t!r}")
    ocena_pc.klasa_cpu(t)                                # procesor bez reguły klasy = odrzucenie
    return t


def karta_graficzna(c):
    """„NVIDIA GeForce RTX 5060 Ti 8GB" jak nowe_pc.gpu_kanoniczna. Pamięć karty musi być podana przez
    stronę (cecha lub liczba w nazwie modelu) i być spójna; RTX 5060 Ti istnieje w 8 i 16 GB."""
    zrodlo = bez_znakow_firmowych(wartosc(c, "Model karty graficznej") or wartosc(c, "Karta graficzna"))
    m = re.search(r"\b(RTX|RX)\s*(\d{4})\s*(Ti|XT)?\b", zrodlo or "", re.I)
    if not m:
        raise BrakDanych(f"nie rozpoznaję karty graficznej: {zrodlo or 'brak'!r}")
    if re.search(r"\b(SUPER|GRE)\b", (zrodlo or "")[m.end():], re.I):
        raise BrakDanych(f"nierozpoznany wariant karty graficznej (SUPER/GRE): {zrodlo!r}")
    sufiks = " Ti" if (m.group(3) or "").upper() == "TI" else " XT" if (m.group(3) or "").upper() == "XT" else ""
    nazwa = f"{'AMD Radeon RX' if m.group(1).upper() == 'RX' else 'NVIDIA GeForce RTX'} {m.group(2)}{sufiks}"
    pamieci = set()
    vm = re.search(r"(\d{1,2})\s*GB", zrodlo, re.I)
    if vm:
        pamieci.add(int(vm.group(1)))
    for cecha in ("Dedykowana pamięć grafiki", "Pamięć grafiki"):
        for w, jedn in c.get(cecha, []):
            if liczba(w) is not None and (jedn.upper() == "GB" or re.search(r"\bGB\b", w, re.I)):
                pamieci.add(int(liczba(w)))
    if not pamieci:
        raise BrakDanych(f"brak pojemności pamięci karty (strona jej nie podaje): {zrodlo!r}")
    if len(pamieci) > 1:
        raise BrakDanych(f"sprzeczna pamięć karty: {sorted(pamieci)} GB w {zrodlo!r}")
    gpu = f"{nazwa} {pamieci.pop()}GB"
    ocena_pc.klasa_gpu(gpu)                              # karta spoza słownika klas = odrzucenie
    return gpu


def pamiec_ram(c, tytul=None):
    """„32GB DDR5 6000MHz". Standard musi być DDR5; wzmianka o DDR4 gdziekolwiek w opisie płyty lub
    konfiguracji pamięci to sprzeczność (zestaw nie może mieć DDR5 w gniazdach DDR4)."""
    if tytul and re.search(r"\bDDR[1-4]\b", tytul, re.I):
        raise BrakDanych(f"tytuł karty wskazuje na pamięć starszej generacji: {tytul!r}")
    typ = wartosc(c, "Typ pamięci RAM")
    if not typ:
        raise BrakDanych("brak typu pamięci RAM")
    if not re.search(r"DDR5", typ, re.I) or re.search(r"\bDDR[1-4]\b", typ, re.I):
        raise BrakDanych(f"pamięć nie jest DDR5: {typ!r}")
    for cecha in ("Pamięć RAM (konfiguracja)", "Sloty"):
        w = wartosc(c, cecha) or ""
        m = re.search(r"DDR[34]\b", w, re.I)
        if m:
            fragment = re.sub(r"\s+", " ", w[max(0, m.start() - 25):m.end() + 15]).strip()
            raise BrakDanych(f"sprzeczne dane o pamięci: typ DDR5, a »{cecha}« mówi: …{fragment}…")
    raw_gb = wartosc(c, "Pamięć RAM")
    if not raw_gb:
        raise BrakDanych("brak pojemności pamięci RAM")
    clean_gb = czysty(raw_gb)
    if re.search(r"[xX*+]", clean_gb):
        mx = re.fullmatch(r"(\d+)\s*[xX*]\s*(\d+)(?:\s*GB)?", clean_gb, re.I)
        mplus = re.fullmatch(r"(\d+)\s*\+\s*(\d+)(?:\s*GB)?", clean_gb, re.I)
        if mx:
            gb = int(mx.group(1)) * int(mx.group(2))
        elif mplus:
            gb = int(mplus.group(1)) + int(mplus.group(2))
        else:
            raise BrakDanych(f"niejednoznaczna pojemność pamięci RAM: {raw_gb!r}")
    else:
        gb = liczba(raw_gb)
    if gb is None or gb <= 0:
        raise BrakDanych("brak pojemności pamięci RAM")

    raw_mhz = wartosc(c, "Prędkość pamięci")
    mhz = None
    if raw_mhz:
        t = re.sub(r"DDR\d*", "", raw_mhz, flags=re.I)
        t = re.sub(r"(?<=\d)\s+(?=\d)", "", t)
        matches = re.findall(r"\b(\d{3,5})\b", t)
        if len(matches) == 1 and 2000 <= int(matches[0]) <= 12000:
            mhz = int(matches[0])
    return f"{int(gb)}GB DDR5" + (f" {mhz}MHz" if mhz else "")


def dysk(c):
    """„1TB SSD" — zapis prosty, jak nowe_pc.dysk_znormalizowany (bez NVMe/M.2, które zmieniają ocenę)."""
    n = liczba(wartosc(c, "Liczba zainstalowanych dysków"))
    if n is not None and n > 1:
        raise BrakDanych(f"zestaw ma {int(n)} dyski — niejednoznaczna pojemność")
    for k, pary in c.items():
        if k.startswith("Rodzaj dysku 2") or k.startswith("Pojemność dysku 2"):
            if isinstance(pary, list):
                for para in pary:
                    if isinstance(para, (tuple, list)) and len(para) >= 1:
                        w = para[0]
                        if w and str(w).lower() not in ("brak", "-", "nie dotyczy", "n/a", "0"):
                            raise BrakDanych(f"zestaw posiada drugi dysk: cecha »{k}« ({w})")
    opis = wartosc(c, "Dysk") or ""
    if re.search(r"\bbrak\b|bez dysku", opis, re.I):
        raise BrakDanych("brak dysku w zestawie (potwierdzone przez sklep)")
    rodzaj = (wartosc(c, "Rodzaj dysku 1") or (re.search(r"\b(SSD|HDD)\b", opis, re.I) or [None, ""])[1]).upper()
    if rodzaj not in ("SSD", "HDD"):
        raise BrakDanych(f"nieznany rodzaj dysku: {rodzaj or 'brak'!r}")
    poj = next(((w, u) for w, u in c.get("Pojemność dysku 1", []) if w), None)
    if poj and liczba(poj[0]) is not None and poj[1].upper() in ("TB", "GB"):
        liczba_, jedn = liczba(poj[0]), poj[1].upper()
    else:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(TB|GB)", opis, re.I)
        if not m:
            raise BrakDanych(f"dysk bez pojemności: {opis or 'brak danych'!r}")
        liczba_, jedn = float(m.group(1).replace(",", ".")), m.group(2).upper()
    tekst = f"{liczba_:g}"
    return f"{tekst}{jedn} {rodzaj}"


def zasilacz(c):
    """„850W 80+ Bronze" / „750W Bronze" / „650W". Certyfikat przepisujemy tak, jak pisze sklep
    (»80+« i »80 Plus« to dwa zapisy, które ocena_pc.kompletnosc rozróżnia); sama moc, gdy certyfikatu brak."""
    moc = wartosc(c, "Moc zasilania")
    model = wartosc(c, "Model zasilacza") or ""
    w1 = int(liczba(moc)) if moc and liczba(moc) is not None else None
    m2 = re.search(r"(\d{3,4})\s*W\b", model, re.I) or re.search(r"(\d{3,4})\s*W(?=80)", model, re.I)
    w2 = int(m2.group(1)) if m2 else None
    if w1 and w2 and w1 != w2:
        raise BrakDanych(f"sprzeczna moc zasilacza: {w1} W i {w2} W")
    w = w1 or w2
    if not w:
        return None
    cert = re.search(r"80\s*(\+|plus)\s*[-–]?\s*(?:cybenetics\s*)?(bronze|silver|gold|platinum|titanium)?",
                     model, re.I)
    if cert:
        opis = ("80+" if cert.group(1) == "+" else "80 Plus") + (f" {cert.group(2).capitalize()}" if cert.group(2) else "")
    else:
        sam_stopien = re.search(r"\b(bronze|silver|gold|platinum|titanium)\b", model, re.I)
        opis = sam_stopien.group(1).capitalize() if sam_stopien else ""
    return f"{w}W" + (f" {opis}" if opis else "")


def system_operacyjny(c):
    v = wartosc(c, "System operacyjny")
    if not v:
        return {"w_cenie": None, "doplata": None, "nazwa": None}
    if re.search(r"\bbrak\b|bez systemu|free\s?dos|\bno os\b|bez licencji|nieaktywowan|bez aktywacji|do aktywacji", v, re.I):
        return {"w_cenie": False, "doplata": None, "nazwa": v}
    if re.search(r"windows", v, re.I):
        return {"w_cenie": True, "doplata": None, "nazwa": v}
    return {"w_cenie": None, "doplata": None, "nazwa": v}


def model_pc(tytul):
    """„PC Gaming NITROPC Extremo Czarny" → „NITROPC Extremo"; None, gdy tytuł nie daje krótkiej nazwy."""
    n = re.sub(r"^(?:Komputer(?:y)? (?:stacjonarny|gamingowy?)|Komputer|Gaming[- ]?PC|PC Gaming|PC|"
               r"DESKTOP GAMING|Desktop)\s+", "", czysty(tytul), flags=re.I)
    n = re.split(r"\s[|/]\s|\s(?=(?:Ultra|Ryzen|Intel|AMD|Core|i[3579]-?\d|RTX|RX\s?\d|DDR[45]|\d+\s?GB|\d+\s?TB)\b)", n)[0]
    n = re.sub(r"(?:[\s,;/]+(?:i\s+)?(?:czarny|biały|bialy|srebrny|szary|niebieski|czerwony|różowy|zielony|złoty|szaro-czarny))+\s*$",
               "", n, flags=re.I).strip(" ,;-|")
    s = n.split(" ")
    if len(s) > 1 and s[0].lower() == s[1].lower():
        n = " ".join(s[1:])                              # „ASUS Asus ROG" → „Asus ROG"
    return n if 3 <= len(n) <= 40 else None


def odczytaj_pc(url, html):
    """Dane z karty gotowego komputera. BrakDanych: nie komputer, nie DDR5, sprzeczna lub brakująca
    dana (pamięć karty, zasilacz, dysk), brak ceny, brak w sprzedaży. Specyfikację czytamy z tabeli
    cech, nigdy z tytułu (tytuły typu »NITROPC Extremo Czarny« nic o podzespołach nie mówią).
    Cena i skład dotyczą oferty widocznej na stronie; kart z konfiguratorem opcji MediaMarkt nie ma,
    więc `opcje` jest puste. Klucz `model` (krótka nazwa z tytułu, np. »NITROPC Extremo«) nie należy do
    kontraktu, ale nabor.zloz_pc czyta go opcjonalnie do nazwy wpisu; None, gdy tytuł jej nie daje."""
    k = karta(url, html, "PERSONAL_COMPUTER", "komputer stacjonarny")
    c = k["cechy"]
    for n, pary in c.items():
        if n.startswith("Przekątna ekranu") and isinstance(pary, list):
            for para in pary:
                if isinstance(para, (tuple, list)) and len(para) >= 1:
                    val = liczba(para[0])
                    if val is not None and val > 0:
                        raise BrakDanych("komputer z wbudowanym ekranem (All-in-One)")
    ram = pamiec_ram(c, k["tytul"])                  # najpierw standard pamięci: DDR4 to najczęstszy powód odrzucenia
    cpu = procesor(c)
    gpu = karta_graficzna(c)
    storage = dysk(c)
    psu = zasilacz(c)
    if psu is None and ZASILACZ_WYMAGANY:
        raise BrakDanych("brak mocy zasilacza (strona jej nie podaje)")
    return {"nazwa": k["tytul"], "url": url, "cpu": cpu, "gpu": gpu, "ram": ram, "storage": storage,
            "psu": psu, "cena_bazowa": k["cena"], "system": system_operacyjny(c), "dostepny": True,
            "sprzedawca": k["sprzedawca"], "zdjecie": k["zdjecie"], "ean": k["ean"], "opcje": {},
            "model": model_pc(k["tytul"])}
