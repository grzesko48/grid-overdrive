#!/usr/bin/env python3
"""Dopisuje do strony NOWE monitory QHD 26–28" 240–500 Hz z katalogu Morele.

Do 22.10.2026 automat odświeżał tylko ceny istniejących pozycji. Nowy monitor pojawiał się
w sklepach, a strona o nim nie wiedziała. Ten skrypt dopisuje go sam — ale uczciwie:

- wpis powstaje WYŁĄCZNIE z tego, co podaje karta produktu w sklepie (marka, model, matryca,
  przekątna, rozdzielczość, odświeżanie, cena, zdjęcie). Brakująca dana = pominięcie
  i wpis w raporcie, nigdy wartość domyślna;
- oceny obrazu i funkcji wymagają recenzji (pomiarów), których automat nie ma — nowy
  monitor dostaje więc tylko oceny liczone ze specyfikacji (moc z Hz, opłacalność z zł/Hz)
  i znacznik „nowy — bez oceny ogólnej". Ocenę ogólną widać dopiero po ręcznym dodaniu
  recenzji; do tego czasu monitor jest na stronie, ale POZA rankingiem;
- tylko towar w sprzedaży (InStock) i tylko to, co da się kupić w Morele.

Użycie:
  python3 nowe_monitory.py --na-sucho            # pokaż, co zostałoby dopisane
  python3 nowe_monitory.py --dopisz --limit 10   # dopisz najwyżej 10, przelicz, zbuduj
"""
import argparse, base64, hashlib, html as htmllib, io, json, os, re, subprocess, sys, urllib.request

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
from ocena_pc import BrakDanych
import przelicz_oceny as po
import zbieraj_ceny as z

SZABLON = os.path.join(BAZA, "monitors_1700_template.html")
OBRAZY = os.path.join(BAZA, "images", "monitors.json")
ODRZUCONE = os.path.join(BAZA, "monitory_odrzucone.json")
UA = z.UA if hasattr(z, "UA") else "Mozilla/5.0"

LISTA = "https://www.morele.net/kategoria/monitory-523/,,,,,,,,0,,,,{filtry}/{strona}"
FILTR_WQHD = "28249O991076"
HZ_OD, HZ_DO = 240, 500
DIAG_OD, DIAG_DO = 26.0, 28.0
CENA_OD, CENA_DO = 500, 6000          # poza tym zakresem to błąd odczytu, nie monitor
NAZWA_SKLEPU = "Morele.net"
# Artefakt w aplikacji Claude ma twardy limit 16 MB (dziś ~14,4 MB, z czego prawie całość to
# zdjęcia w base64). Powyżej tego budżetu nie dopisujemy niczego nowego — zamiast tego raport.
BUDZET_BAJTOW = 15_300_000

MARKI = {"asus": "ASUS", "msi": "MSI", "aoc": "AOC", "lg": "LG", "hp": "HP", "dell": "Dell",
         "acer": "Acer", "benq": "BenQ", "msi": "MSI", "aorus": "AORUS"}


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


def czestotliwosci(s):
    """Identyfikatory faset „N Hz" (240–500) z listy Morele. Faseta nie istnieje → pusto."""
    wyniki = {}
    for m in re.finditer(r'<input[^>]*?\bid="(\d+)"[^>]*?name="30331"[^>]*?data-label="(\d+) Hz"', s, re.S):
        hz = int(m.group(2))
        if HZ_OD <= hz <= HZ_DO:
            wyniki[hz] = m.group(1)
    return wyniki


def lista_morele(maks_stron=6):
    """{adres: (nazwa, cena)} — monitory WQHD o odświeżaniu 240–500 Hz z katalogu sklepu."""
    kod, s = z.pobierz(LISTA.format(filtry=FILTR_WQHD, strona=""))
    if kod != 200:
        raise BrakDanych(f"lista Morele: HTTP {kod}")
    fasety = czestotliwosci(s)
    if not fasety:
        raise BrakDanych("lista Morele: nie znaleziono faset częstotliwości — zmienił się układ strony")
    wynik = {}
    for hz, fid in sorted(fasety.items()):
        for strona in range(1, maks_stron + 1):
            kod, s = z.pobierz(LISTA.format(filtry=f"{FILTR_WQHD},30331O{fid}",
                                            strona=f"{strona}/" if strona > 1 else ""))
            if kod != 200:
                break
            nowych = 0
            for o in jsonld(s):
                if o.get("@type") != "ItemList":
                    continue
                for el in o.get("itemListElement", []):
                    it = el.get("item", el)
                    adres, nazwa = it.get("url"), it.get("name")
                    of = it.get("offers") or {}
                    of = of[0] if isinstance(of, list) and of else of
                    cena = z._liczba(of.get("price")) if isinstance(of, dict) else None
                    if adres and nazwa and adres not in wynik:
                        wynik[adres] = (nazwa, cena)
                        nowych += 1
            if nowych == 0:
                break
    return wynik


# ------------------------------------------------------------------ rozpoznanie duplikatu
def kody_modelu(nazwa):
    """Słowa z cyfrą (kody modeli), bez końcówek wariantów regionalnych „/00" i bez drobnicy."""
    kod = set()
    for w in re.split(r"[^A-Za-z0-9]+", nazwa.upper()):
        if not w or not re.search(r"\d", w):
            continue
        if re.fullmatch(r"\d{1,3}", w):
            continue                                  # „00", „69" — wariant regionalny
        kod.add(w)
    return kod


def juz_jest(nazwa, katalog_nazw, id_morele, adres):
    m = re.search(r"-(\d{6,9})/?$", adres)
    if m and m.group(1) in id_morele:
        return "adres Morele już na stronie"
    k = kody_modelu(nazwa)
    if not k:
        return None
    for n in katalog_nazw:
        if kody_modelu(n) == k:
            return f"ten sam model co „{n}”"
    return None


# ------------------------------------------------------------------ odczyt karty produktu
def produkt(s):
    for o in jsonld(s):
        if o.get("@type") == "Product":
            return o
    raise BrakDanych("strona bez danych produktu (JSON-LD Product)")


def wlasciwosci(o):
    return {p.get("name"): str(p.get("value", "")).strip() for p in o.get("additionalProperty", [])
            if isinstance(p, dict)}


def liczba(txt):
    m = re.search(r"\d+(?:[.,]\d+)?", txt or "")
    return float(m.group(0).replace(",", ".")) if m else None


def matryca(typ, ekran):
    """(panelName, panel) z pola „Typ matrycy". Typ spoza listy = pominięcie, nie zgadywanie."""
    t = (typ or "").strip()
    u = t.upper()
    if u == "QD-OLED":
        nazwa, klucz = "QD-OLED", "qdoled"
    elif u == "WOLED":
        nazwa, klucz = "OLED (WOLED)", "oled"
    elif u == "OLED":
        nazwa, klucz = "OLED", "oled"
    elif u in ("TANDEM OLED", "TANDEM WOLED"):
        nazwa, klucz = "OLED (Tandem)", "oled"
    elif re.fullmatch(r"(FAST |RAPID |NANO |SS |SUPER SPEED )?IPS( BLACK)?", u):
        nazwa, klucz = t, "ips"
    elif u == "VA":
        nazwa, klucz = "VA", "va"
    else:
        raise BrakDanych(f"typ matrycy „{t or 'brak'}” spoza zakresu (IPS/VA/OLED/QD-OLED)")
    if (ekran or "").lower().startswith("zakrzyw"):
        nazwa += ", zakrzywiony"
    return nazwa, klucz


def czysta_nazwa(o):
    """Nazwa w stylu strony: bez przedrostka „Monitor", bez numeru katalogowego w nawiasie,
    gdy nazwa ma już kod modelu; kod z nawiasu zostaje, gdy to jedyny kod modelu."""
    n = htmllib.unescape(o.get("name", "")).strip()
    n = re.sub(r"^Monitor\s+", "", n, flags=re.I)
    m = re.search(r"\(([^()]*)\)\s*$", n)
    if m:
        przed = n[:m.start()].strip()
        if any(len(k) >= 6 for k in kody_modelu(przed)):
            n = przed
        else:
            n = f"{przed} {m.group(1).strip()}"
    if '"' in n or len(n) > 60 or re.search(r"pikseli|aspect ratio", n, re.I):
        # nazwa-opis z karty (sklep wkleił specyfikację do tytułu): bierzemy markę + model
        marka = o.get("brand")
        marka = marka.get("name") if isinstance(marka, dict) else marka
        model = (o.get("model") or o.get("mpn") or "").strip()
        if not marka or len(model) < 4 or len(model) > 30:
            raise BrakDanych(f"tytuł karty nie jest nazwą modelu: {n[:50]!r}")
        n = f"{marka} {model}"
    n = n.replace("'", "’")
    w = n.split(" ", 1)
    if w and w[0].lower() in MARKI:
        n = MARKI[w[0].lower()] + (" " + w[1] if len(w) > 1 else "")
    n = re.sub(r"\s+", " ", n).strip()
    s = n.split(" ")
    if len(s) > 3 and re.sub(r"\W", "", s[0]).lower() == re.sub(r"\W", "", s[1] + s[2]).lower():
        n = " ".join([s[0]] + s[3:])                  # „LC-Power LC Power X" → „LC-Power X"
    return n


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


def odczytaj(url, s):
    """Dane z karty produktu → słownik. BrakDanych, gdy czegokolwiek brakuje albo nie pasuje."""
    o = produkt(s)
    w = wlasciwosci(o)
    nazwa = czysta_nazwa(o)
    if not nazwa:
        raise BrakDanych("brak nazwy")
    diag = liczba(w.get("Przekątna ekranu"))
    if diag is None:
        raise BrakDanych("brak przekątnej")
    if not (DIAG_OD <= diag <= DIAG_DO):
        raise BrakDanych(f"przekątna {diag:g}\" poza zakresem {DIAG_OD:g}–{DIAG_DO:g}\"")
    if not re.search(r"2560\s*x\s*1440", w.get("Rozdzielczość", ""), re.I):
        raise BrakDanych(f"rozdzielczość „{w.get('Rozdzielczość', 'brak')}” (wymagane 2560 x 1440)")
    hz = liczba(w.get("Częstotliwość odświeżania"))
    if hz is None:
        raise BrakDanych("brak częstotliwości odświeżania")
    hz = int(hz)
    if not (HZ_OD <= hz <= HZ_DO):
        raise BrakDanych(f"{hz} Hz poza zakresem {HZ_OD}–{HZ_DO} Hz")
    nazwa_matrycy, klucz_matrycy = matryca(w.get("Typ matrycy"), w.get("Ekran"))
    of = o.get("offers") or {}
    of = of[0] if isinstance(of, list) and of else of
    cena = z._liczba(of.get("price")) if isinstance(of, dict) else None
    if not cena:
        raise BrakDanych("brak ceny")
    if not (CENA_OD <= cena <= CENA_DO):
        raise BrakDanych(f"cena {cena} zł poza wiarygodnym zakresem {CENA_OD}–{CENA_DO} zł")
    if not str(of.get("availability", "")).endswith("InStock"):
        raise BrakDanych("nie ma w sprzedaży (availability ≠ InStock)")
    return {"nazwa": nazwa, "diag": diag, "hz": hz, "cena": cena, "panelName": nazwa_matrycy,
            "panel": klucz_matrycy, "url": url, "zdjecie": zdjecie_url(o, s)}


# ------------------------------------------------------------------ złożenie wpisu
def diag_tekst(d):
    return (f"{d:g}".replace(".", ",")) + '"'


def klucz_zdjecia(numer, nazwa):
    slug = re.sub(r"[^a-z0-9]+", "_", nazwa.lower()).strip("_")[:26].strip("_")
    return f"{numer:02d}_{slug}"


def wpis(dane, klucz):
    cena, hz = dane["cena"], dane["hz"]
    perf = int(round(60 + (hz - 240) / 260 * 40))                 # ta sama reguła co 8/8 istniejących
    value = po.ocena_wartosci(cena / hz, "monitor")
    oled = dane["panel"] in ("oled", "qdoled")
    pros = [f"Matryca {dane['panelName']} i {hz} Hz natywnie przy QHD — wg specyfikacji sklepu."]
    cons = ["Brak niezależnej recenzji — oceny obrazu, funkcji i oceny ogólnej nie ma."]
    if oled:
        cons.append("Typowe dla OLED ryzyko wypalenia przy długotrwałych, statycznych elementach obrazu.")
    review = {"coverage": "brak", "pros": [], "cons": [], "sources": [],
              "note": "Model dopisany automatycznie na podstawie specyfikacji ze sklepu. "
                      "Brak recenzji — oceny obrazu i funkcji do uzupełnienia."}
    return {"img": klucz, "name": dane["nazwa"], "price": cena, "store": NAZWA_SKLEPU,
            "diag": diag_tekst(dane["diag"]), "panelName": dane["panelName"], "panel": dane["panel"],
            "hz": hz, "url": dane["url"],
            "note": "Nowy model — dopisany automatycznie, bez oceny ogólnej (brak recenzji).",
            "prices": {"morele": cena}, "urls": {"morele": dane["url"]},
            "review": review, "scores": {"perf": perf, "value": value}, "pros": pros, "cons": cons}


def js1(x):
    return "'" + str(x).replace("\\", "\\\\").replace("'", "\\'") + "'"


def wpis_js(e):
    lista = lambda l: "[" + ",".join(js1(x) for x in l) + "]"
    review = json.dumps(e["review"], ensure_ascii=False).replace("\\", "\\\\").replace("'", "\\'")
    czesci = [("img", js1(e["img"])), ("name", js1(e["name"])), ("price", e["price"]),
              ("store", js1(e["store"])), ("diag", js1(e["diag"])), ("panelName", js1(e["panelName"])),
              ("panel", js1(e["panel"])), ("hz", e["hz"]), ("url", js1(e["url"])),
              ("note", js1(e["note"])), ("nowy", 1),
              ("prices", "{" + ",".join(f"{k}:{v}" for k, v in e["prices"].items()) + "}"),
              ("urls", "{" + ",".join(f"{k}:{js1(v)}" for k, v in e["urls"].items()) + "}"),
              ("reviewData", f"JSON.parse('{review}')"),
              ("scores", "{" + ",".join(f"{k}:{v}" for k, v in e["scores"].items()) + "}"),
              ("pros", lista(e["pros"])), ("cons", lista(e["cons"])), ("coverage", js1("brak"))]
    return "{" + ", ".join(f"{k}:{v}" for k, v in czesci) + "}"


def wstaw(sz, wpisy):
    """Dopisuje wpisy na koniec DATA (monitory). Zwraca nowy tekst szablonu."""
    i = sz.index("var DATA")
    koniec = i + re.search(r"\n\s*\];", sz[i:]).start()
    glowa = sz[:koniec].rstrip()
    if not glowa.endswith(","):
        glowa += ","
    return glowa + "\n    " + ",\n    ".join(wpis_js(e) for e in wpisy) + sz[koniec:]


def zdjecie_data_uri(url_zdjecia):
    from PIL import Image
    if not z.REGULAMIN.wolno(url_zdjecia):
        raise BrakDanych("robots.txt nie pozwala pobrać zdjęcia")
    z.TEMPO.czekaj(re.sub(r"^https?://([^/]+)/.*$", r"\1", url_zdjecia))
    r = urllib.request.Request(url_zdjecia, headers={"User-Agent": UA})
    surowe = urllib.request.urlopen(r, timeout=30).read()
    im = Image.open(io.BytesIO(surowe))
    if im.mode in ("RGBA", "LA", "P"):
        tlo = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA"); tlo.paste(im, mask=im.split()[-1]); im = tlo
    else:
        im = im.convert("RGB")
    im.thumbnail((520, 520))
    b = io.BytesIO(); im.save(b, "JPEG", quality=80, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


# ------------------------------------------------------------------ przebieg
def wczytaj_odrzucone():
    try:
        return json.load(open(ODRZUCONE, encoding="utf-8"))
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--na-sucho", action="store_true")
    ap.add_argument("--dopisz", action="store_true")
    ap.add_argument("--limit", type=int, default=10, help="najwyżej tyle NOWYCH monitorów na przebieg")
    a = ap.parse_args()
    if not (a.na_sucho or a.dopisz):
        ap.error("podaj --na-sucho albo --dopisz")

    sz = open(SZABLON, encoding="utf-8").read()
    poz = [p for p in z.wczytaj(sz) if p["rodzaj"] == "monitor"]
    nazwy = [p["name"] for p in poz]
    id_morele = {m.group(1) for p in poz for u in p["urls"].values()
                 if (m := re.search(r"morele\.net/.*-(\d{6,9})/?$", u))}
    obrazy = json.load(open(OBRAZY, encoding="utf-8"))
    rozmiar = os.path.getsize(os.path.join(BAZA, "index.html"))
    odrzucone = wczytaj_odrzucone()
    numery = [int(k.split("_")[0]) for k in obrazy if re.match(r"\d{2,}_", k)]
    nast = max(numery) + 1 if numery else 1

    print("pobieram listę monitorów z Morele…", file=sys.stderr)
    lista = lista_morele()
    print(f"na liście Morele: {len(lista)} monitorów WQHD {HZ_OD}–{HZ_DO} Hz", file=sys.stderr)

    nowe, pominiete, nowe_obrazy, nowe_odrzucone = [], [], {}, {}
    for adres, (nazwa_listy, _) in sorted(lista.items()):
        idm = (re.search(r"-(\d{6,9})/?$", adres) or [None, adres])[1]
        powod = juz_jest(nazwa_listy, nazwy + [e["name"] for e in nowe], id_morele, adres)
        if powod:
            continue                                  # to nie „pominięcie" — to już mamy
        if idm in odrzucone:
            continue                                  # odrzucone definitywnie w poprzednim przebiegu
        if len(nowe) >= a.limit:
            pominiete.append((nazwa_listy, "limit przebiegu — dopisane w następnym")); continue
        if rozmiar + sum(len(v) for v in nowe_obrazy.values()) > BUDZET_BAJTOW:
            pominiete.append((nazwa_listy, "budżet rozmiaru strony (16 MB limitu artefaktu) wyczerpany")); continue
        kod, s = z.pobierz(adres)
        if kod != 200:
            pominiete.append((nazwa_listy, f"HTTP {kod}")); continue
        try:
            dane = odczytaj(adres, s)
            powod = juz_jest(dane["nazwa"], nazwy + [e["name"] for e in nowe], id_morele, adres)
            if powod:
                nowe_odrzucone[idm] = powod; continue
            klucz = klucz_zdjecia(nast, dane["nazwa"])
            e = wpis(dane, klucz)
            if a.dopisz:
                nowe_obrazy[klucz] = zdjecie_data_uri(dane["zdjecie"])
        except BrakDanych as x:
            tekst = str(x)
            pominiete.append((nazwa_listy, tekst))
            # definitywne odrzucenia (parametry produktu) zapamiętujemy; przejściowe (brak w sprzedaży) nie
            if not re.search(r"nie ma w sprzedaży|HTTP|brak zdjęcia|robots", tekst):
                nowe_odrzucone[idm] = tekst
            continue
        except Exception as x:
            pominiete.append((nazwa_listy, f"błąd: {type(x).__name__}: {x}")); continue
        nowe.append(e)
        nast += 1

    print(f"\nDO DOPISANIA: {len(nowe)} monitorów")
    for e in nowe:
        print(f"   {e['price']:5d} zł  {e['hz']:3d} Hz  {e['diag']:>6}  {e['panelName']:<18} "
              f"perf {e['scores']['perf']:3d} value {e['scores']['value']:3d}  {e['name']}")
    print(f"\nPOMINIĘTE: {len(pominiete)}")
    powody = {}
    for _, p in pominiete:
        k = re.sub(r"\d+(?:[.,]\d+)?", "N", p)[:70]
        powody[k] = powody.get(k, 0) + 1
    for p, n in sorted(powody.items(), key=lambda x: -x[1])[:12]:
        print(f"   {n:3d}× {p}")

    if a.na_sucho or not nowe:
        if a.dopisz and nowe_odrzucone:
            odrzucone.update(nowe_odrzucone)
            json.dump(odrzucone, open(ODRZUCONE, "w", encoding="utf-8"), ensure_ascii=False, indent=1,
                      sort_keys=True)
        return {"dopisane": len(nowe), "pominiete": pominiete}

    nowy_sz = wstaw(sz, nowe)
    sprawdz = [p for p in z.wczytaj(nowy_sz) if p["rodzaj"] == "monitor"]
    if len(sprawdz) != len(poz) + len(nowe):
        sys.exit(f"KONTROLA NIE PRZESZŁA: monitorów było {len(poz)}, miało być {len(poz) + len(nowe)}, "
                 f"jest {len(sprawdz)} — nic nie zapisano")
    open(SZABLON, "w", encoding="utf-8").write(nowy_sz)
    obrazy.update(nowe_obrazy)
    open(OBRAZY, "w", encoding="utf-8").write(json.dumps(obrazy, ensure_ascii=False))
    odrzucone.update(nowe_odrzucone)
    json.dump(odrzucone, open(ODRZUCONE, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    raport = {"dopisane": [e["name"] for e in nowe], "pominiete": pominiete}
    json.dump(raport, open(os.path.join(BAZA, "raport_nowe_monitory.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nszablon zapisany; przeliczam oceny i buduję stronę")
    subprocess.run([sys.executable, os.path.join(BAZA, "przelicz_oceny.py"), "--bez-przebudowy"], check=True)
    subprocess.run([sys.executable, os.path.join(BAZA, "build_merged.py")], check=True)
    return raport


if __name__ == "__main__":
    main()
