#!/usr/bin/env python3
"""Nabór nowych pozycji ze WSZYSTKICH sklepów: monitory i gotowe komputery.

Dotąd nabór czytał tylko Morele (monitory) i Hard-PC (PC). Ten skrypt woła adaptery sklepów
z katalogu zrodla/ (x-kom, MediaMarkt, PlugNPlay, GoblinPC, Morele-PC…) i robi dwie rzeczy:

1. UZUPEŁNIA istniejące monitory — ten sam model znaleziony w innym sklepie dostaje jego adres
   i cenę (prices/urls), więc porównanie cen obejmuje wszystkie sklepy;
2. DOPISUJE nowe pozycje: monitor znaleziony w kilku sklepach powstaje jako JEDEN wpis ze
   wszystkimi adresami; zestaw PC powstaje z danych odczytanych ze strony sklepu.

Zasady (jak w całym serwisie): BRAK zamiast zgadywania. Każda dana pochodzi ze strony sklepu;
adapter rzuca BrakDanych, gdy czegoś brakuje. Ten sam model rozpoznajemy WYŁĄCZNIE po
identycznym, swoistym kodzie modelu + tej samej częstotliwości i przekątnej (lepiej dwa wpisy
niż cudza cena pod cudzym monitorem). Sklepy zablokowane (403) pomijamy bez obchodzenia
blokady. Robots.txt jest sprawdzany przed każdym pobraniem.

Użycie:
  python3 nabor.py --na-sucho
  python3 nabor.py --dopisz --limit-mon 10 --limit-pc 25
"""
import argparse, bisect, hashlib, importlib, inspect, json, os, re, subprocess, sys

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import ocena_pc
from ocena_pc import BrakDanych
import nowe_monitory as nm
import nowe_pc as npc
import zbieraj_ceny as z
import nanies_zmiany as nz

SZABLON = os.path.join(BAZA, "monitors_1700_template.html")
OBRAZY_MON = os.path.join(BAZA, "images", "monitors.json")
OBRAZY_PC = os.path.join(BAZA, "images", "pcs.json")
ODRZUCONE = os.path.join(BAZA, "nabor_odrzucone.json")
RAPORT = os.path.join(BAZA, "raport_nabor.json")
STAN = os.path.join(BAZA, "nabor_stan.json")        # kursory list między przebiegami (rotacja głębokości)

# kolejność = pierwszeństwo przy wyborze nazwy wpisu (Morele podaje najczystsze nazwy)
SKLEPY_MON = ["morele", "xkom", "mediamarkt"]
SKLEPY_PC = ["plugnplay", "goblinpc", "mediamarkt", "xkom", "morele_pc"]
MODULY = {"morele": "zrodla.morele", "xkom": "zrodla.xkom", "mediamarkt": "zrodla.mediamarkt",
          "plugnplay": "zrodla.plugnplay", "goblinpc": "zrodla.goblinpc", "morele_pc": "zrodla.morele_pc"}
NAZWY_SKLEPOW = {"morele": "Morele.net", "xkom": "x-kom", "mediamarkt": "MediaMarkt",
                 "plugnplay": "PlugNPlay.sklep.pl", "goblinpc": "GoblinPC.pl", "hardpc": "Hard-PC.pl"}
PREFIKS_PC = {"morele": "Morele", "xkom": "x-kom", "mediamarkt": "MediaMarkt",
              "plugnplay": "PlugNPlay", "goblinpc": "GoblinPC"}
BUDZET_BAJTOW = nm.BUDZET_BAJTOW
MAKS_POBRAN = 200            # górny limit kart produktów pobieranych w jednym przebiegu
# Przyczyny PRZEJŚCIOWE (blokada, zmiana układu, brak w sprzedaży): takiego odrzucenia nie zapamiętujemy na stałe.
PRZEJSCIOWE = re.compile(r"nie ma w sprzedaży|HTTP|brak zdjęcia|robots|niedostęp|zmienił się układ|pusta strona|"
                         r"bez danych produktu|ceny na stronie się różnią|blokad|lista niepełna", re.I)


# ------------------------------------------------------------------ pobieranie
def pobierz_grzecznie(url):
    """robots.txt + tempo sklepu (zbieraj_ceny). Zakaz = (None, "robots"), nie wyjątek."""
    if not z.REGULAMIN.wolno(url):
        return None, "robots"
    return z.pobierz(url)


def wczytaj_adaptery(klucze):
    wynik = {}
    for k in klucze:
        try:
            wynik[k] = importlib.import_module(MODULY[k])
        except ImportError as x:
            print(f"  adapter {k}: brak ({x}) — pomijam", file=sys.stderr)
    return wynik


# ------------------------------------------------------------------ rozpoznawanie modelu
_JEDNOSTKA = re.compile(r"^\d+(HZ|MS|CM|GB|TB|W|MHZ|INCH|NITS|PPI|X\d+)$|^\d{3,4}X\d{3,4}$")


def swoiste_kody(nazwa, kod_producenta=None):
    """Kody modeli wystarczająco swoiste, by uznać dwa wpisy za ten sam model: min. 6 znaków,
    litery i cyfry razem, bez jednostek (240HZ, 2560X1440)."""
    k = set(nm.kody_modelu(nazwa))
    if kod_producenta:
        k.add(re.sub(r"[^A-Z0-9]", "", str(kod_producenta).upper()))
    return {t for t in k if len(t) >= 6 and re.search(r"[A-Z]", t) and re.search(r"\d", t)
            and not _JEDNOSTKA.match(t)}


def pelne_kody(nazwa, kod_producenta=None):
    """Wszystkie kody modelu (także krótkie, jak X24), bez jednostek. Dwa wpisy bez swoistego kodu
    są tym samym modelem tylko przy IDENTYCZNYM zbiorze kodów (MAG 272QP X24 ≠ MAG 272QP X28)."""
    k = set(nm.kody_modelu(nazwa))
    if kod_producenta:
        k.add(re.sub(r"[^A-Z0-9]", "", str(kod_producenta).upper()))
    return {t for t in k if not _JEDNOSTKA.match(t)}


def tokeny(nazwa):
    return set(t for t in re.split(r"[^A-Z0-9]+", str(nazwa).upper()) if t)


def sklejony_kod(kody, tok):
    """Sklep skleił słowo z kodem („StrixXG27AQWMG”, „OLEDXG27ACDNG”): kod jest SUFIKSEM tokenu,
    a to, co przed nim, to same litery. Wariant z dopiskiem po kodzie (GO27Q24A) tu nie pasuje."""
    return any(len(c) >= 7 and any(t != c and t.endswith(c) and t[:-len(c)].isalpha() for t in tok)
               for c in kody)


def ten_sam_model(a, b):
    """a, b: {kody, pelne, tok, hz, diag}. Wspólny swoisty kod (także sklejony z poprzedzającym słowem)
    albo identyczny niepusty zbiór kodów, plus ta sama częstotliwość i przekątna (±1" — sklepy
    zaokrąglają ją różnie: 26,5 / 26,7 / 27). Kod modelu rozstrzyga, nie przekątna."""
    kod = (bool(a["kody"] & b["kody"]) or (bool(a["pelne"]) and a["pelne"] == b["pelne"])
           or sklejony_kod(a["kody"], b.get("tok", set())) or sklejony_kod(b["kody"], a.get("tok", set())))
    return kod and a["hz"] == b["hz"] and abs(a["diag"] - b["diag"]) <= 1.0


def diag_z_wpisu(seg):
    m = re.search(r"diag:'([\d.,]+)", seg)
    return float(m.group(1).replace(",", ".")) if m else None


def opis_istniejacych(sz, poz):
    gr = nz.granice(sz)
    wynik = []
    for p in poz:
        if p["rodzaj"] != "monitor":
            continue
        i = gr.index(p["start"])
        seg = sz[p["start"]: gr[i + 1] if i + 1 < len(gr) else len(sz)]
        hz = re.search(r"(?<![A-Za-z])hz:(\d+)", seg)
        pan = re.search(r"panel:'(\w+)'", seg)
        wynik.append({"poz": p, "kody": swoiste_kody(p["name"]), "pelne": pelne_kody(p["name"]), "tok": tokeny(p["name"]), "hz": int(hz.group(1)) if hz else None,
                      "diag": diag_z_wpisu(seg) or 0.0, "panel": pan.group(1) if pan else None})
    return wynik


# ------------------------------------------------------------------ zbieranie kandydatów
class Licznik:
    def __init__(self, maks):
        self.maks, self.n = maks, 0

    def wolno(self):
        return self.n < self.maks

    def zuzyj(self):
        self.n += 1


def wywolaj_liste(fn, klucz, rodzaj, maks_stron, stan, uwagi):
    """Woła lista_* adaptera. Opcjonalne argumenty (po sygnaturze): uwagi — niepowodzenia stron ≥2
    zamiast ich połykania; strona_od — kursor rotacji głębokości zapamiętany między przebiegami
    (lista większa niż jeden przebieg obejmie, więc cały katalog zostanie przejrzany w kilka dni)."""
    par = inspect.signature(fn).parameters
    kw = {"uwagi": uwagi} if "uwagi" in par else {}
    if "strona_od" not in par:
        return list(fn(pobierz_grzecznie, maks_stron, **kw))
    kursor = int(stan.get(klucz, {}).get(rodzaj, 1))
    adresy = list(fn(pobierz_grzecznie, maks_stron, strona_od=kursor, **kw))
    if not adresy and kursor > 1:                  # kursor za końcem listy → od początku
        kursor = 1
        adresy = list(fn(pobierz_grzecznie, maks_stron, strona_od=1, **kw))
    stan.setdefault(klucz, {})[rodzaj] = (kursor + maks_stron) if adresy else 1
    return adresy


def zbierz(adaptery, rodzaj, znane, odrzucone, nowe_odrzucone, pominiete, licznik, maks_stron, stan_sklepow, stan, kwota):
    """Kandydaci z list sklepów: tylko adresy, których nie ma jeszcze w bazie ani w pamięci odrzuconych."""
    lista_fn, czytaj_fn = (("lista_monitorow", "odczytaj_monitor") if rodzaj == "monitor"
                           else ("lista_pc", "odczytaj_pc"))
    kandydaci = []
    for klucz, ad in adaptery.items():
        uwagi = []
        try:
            adresy = sorted(set(wywolaj_liste(getattr(ad, lista_fn), klucz, rodzaj, maks_stron, stan, uwagi)))
        except BrakDanych as x:
            stan_sklepow.setdefault(klucz, {})[rodzaj] = f"lista niedostępna: {x}"
            print(f"  {klucz} [{rodzaj}]: {x}", file=sys.stderr)
            continue
        except Exception as x:
            stan_sklepow.setdefault(klucz, {})[rodzaj] = f"BŁĄD TECHNICZNY listy: {type(x).__name__}: {x}"
            pominiete.append((klucz, f"BŁĄD TECHNICZNY listy {rodzaj}: {type(x).__name__}: {x}"))
            continue
        nowe = [u for u in adresy if u not in znane and f"{klucz}|{u}" not in odrzucone]
        stan_sklepow.setdefault(klucz, {})[rodzaj] = (f"lista {len(adresy)}, do sprawdzenia {len(nowe)}"
                                                      + (f", UWAGI: {len(uwagi)}" if uwagi else ""))
        if uwagi:
            pominiete.append((klucz, f"lista niepełna ({rodzaj}): {uwagi[0]}"))
        pobrano, odlozone = 0, 0
        for u in nowe:
            if pobrano >= kwota or not licznik.wolno():
                odlozone += 1
                continue
            pobrano += 1
            licznik.zuzyj()
            kod, s = pobierz_grzecznie(u)
            if kod != 200:
                pominiete.append((u, f"HTTP {kod}"))
                continue
            try:
                d = getattr(ad, czytaj_fn)(u, s)
                d["sklep"] = ad.SKLEP
                d["_klucz"] = klucz                    # klucz modułu (morele_pc ≠ SKLEP "morele") do pamięci odrzuconych
                kandydaci.append(d)
            except BrakDanych as x:
                pominiete.append((u, str(x)))
                if not PRZEJSCIOWE.search(str(x)):
                    nowe_odrzucone[f"{klucz}|{u}"] = str(x)
            except Exception as x:
                pominiete.append((u, f"BŁĄD TECHNICZNY: {type(x).__name__}: {x}"))
        if odlozone:
            pominiete.append((klucz, f"limit pobrań ({kwota} na sklep) — {odlozone} adresów w następnych przebiegach"))
    return kandydaci


# ------------------------------------------------------------------ monitory
def grupuj(kandydaci):
    """Kandydaci z różnych sklepów, którzy są tym samym modelem, w jedną grupę."""
    opis = [{"d": d, "kody": swoiste_kody(d["nazwa"], d.get("kod_modelu")),
             "pelne": pelne_kody(d["nazwa"], d.get("kod_modelu")), "tok": tokeny(d["nazwa"]),
             "hz": d["hz"], "diag": d["diag"]}
            for d in kandydaci]
    grupy = []
    for o in opis:
        for g in grupy:
            if any(ten_sam_model(o, x) for x in g):
                g.append(o)
                break
        else:
            grupy.append([o])
    return grupy


def dolacz_sklep(sz, start, sklep, cena, url):
    """Dopisuje sklep do prices/urls istniejącego wpisu (nie nadpisuje obecnego)."""
    gr = nz.granice(sz)
    i = gr.index(start)
    koniec = gr[i + 1] if i + 1 < len(gr) else len(sz)
    seg = sz[start:koniec]
    mp = re.search(r"prices:\{([^}]*)\}", seg)
    mu = re.search(r"urls:\{([^}]*)\}", seg)
    if not mp or not mu or mp.start() > mu.start() or re.search(r"\b%s:" % sklep, mp.group(1)):
        return sz, False
    cudz = "'" if "'" in mu.group(1) else '"'
    seg = seg[:mu.end(1)] + f",{sklep}:{cudz}{url}{cudz}" + seg[mu.end(1):]
    seg = seg[:mp.end(1)] + f",{sklep}:{cena}" + seg[mp.end(1):]     # prices stoi przed urls
    return sz[:start] + seg + sz[koniec:], True


def wpis_monitora(grupa, numer):
    """Jeden wpis z grupy ofert tego samego modelu: najtańsza oferta daje cenę i sklep nagłówka."""
    porzadek = {k: i for i, k in enumerate(SKLEPY_MON)}
    c = sorted((o["d"] for o in grupa), key=lambda d: porzadek.get(d["sklep"], 99))
    nazwa_od = c[0]
    najtanszy = min(c, key=lambda d: d["cena"])
    e = nm.wpis(dict(nazwa_od, cena=najtanszy["cena"], url=najtanszy["url"]),
                nm.klucz_zdjecia(numer, nazwa_od["nazwa"]))
    e["store"] = NAZWY_SKLEPOW[najtanszy["sklep"]]
    e["prices"] = {d["sklep"]: d["cena"] for d in c}
    e["urls"] = {d["sklep"]: d["url"] for d in c}
    return e, c


# ------------------------------------------------------------------ PC
def krotko_cpu(c):
    return re.sub(r"^(AMD|Intel)\s+", "", c.strip(), flags=re.I)


def krotko_gpu(g):
    return re.sub(r"^(NVIDIA GeForce|AMD Radeon|GeForce|Radeon)\s+", "", g.strip(), flags=re.I)


def zloz_pc(d, najnizsza, nazwy):
    """Wpis PC z kandydata adaptera. BrakDanych, gdy czegokolwiek nie da się potwierdzić."""
    cpu, gpu = d["cpu"], d["gpu"]
    ocena_pc.klasa_cpu(cpu)
    if ocena_pc.klasa_gpu(gpu) > 7:
        raise BrakDanych(f"karta {gpu!r} spoza skali mocy rankingu (klasa > 7)")
    ocena_pc.pamiec_gpu_gb(gpu)
    ram = d["ram"]
    if not re.search(r"DDR5", ram, re.I):
        raise BrakDanych(f"pamięć nie jest DDR5: {ram!r}")
    if ocena_pc.pojemnosc_ram_gb(ram) < 16:
        raise BrakDanych(f"pamięć poniżej 16 GB: {ram!r}")
    dysk = npc.dysk_znormalizowany({}, d["storage"])
    bare = int(d["cena_bazowa"])
    if not d.get("dostepny", True):
        raise BrakDanych("nie ma w sprzedaży")
    if bare < npc.CENA_OD_BEZ_SYSTEMU:
        raise BrakDanych(f"cena {bare} zł poniżej progu {npc.CENA_OD_BEZ_SYSTEMU} zł")
    sys_ = d.get("system") or {}
    sklep = d["sklep"]
    if sys_.get("w_cenie") is True:
        cena, os_, rodzaj = bare, sys_.get("nazwa") or "Windows 11", "included"
        nota = "Windows 11 w cenie bazowej (wg opisu sklepu)."
    elif sys_.get("doplata") is not None:
        dop = int(sys_["doplata"])
        cena, os_, rodzaj = bare + dop, "Windows 11 Home (doliczony do ceny)", "confirmed"
        nota = (f"Cena bazowa (bez systemu): {bare} zl + Windows 11 Home (potwierdzona w "
                f"{NAZWY_SKLEPOW[sklep]}): {dop} zl.")
    else:
        cena, os_, rodzaj = bare, "brak danych", "unknown"
        nota = "System operacyjny nieznany — cena bez korekty (BRAK potwierdzonych danych)."
    if cena > npc.SUFIT_Z_WINDOWS:
        raise BrakDanych(f"cena z systemem {cena} zł powyżej progu {npc.SUFIT_Z_WINDOWS} zł")
    psu = d.get("psu") or "brak danych"
    os_oceny = "Windows 11 Home" if rodzaj in ("included", "confirmed") and "windows" in os_.lower() else os_
    sc = ocena_pc.oceny(cpu, gpu, ram, dysk, psu, os_oceny, 1)
    value = npc._wartosc(cena, sc["perf"])
    wynik = {"longevity": npc._dlugowiecznosc(sc["longevityYears"]), "value": value,
             "longevityYears": sc["longevityYears"]}
    zestaw = {"cpu": cpu, "gpu": gpu, "ram": ram, "storage": dysk, "psu": psu, "os": os_oceny,
              "price": cena, "liczba_sklepow": 1, "dopłata_ram": None}
    zal, wad = ocena_pc.zalety_wady(zestaw, wynik, None, najnizsza)
    scores = npc._sumy(sc, value, wynik["longevity"], ocena_pc.kary_rankingu(ram, dysk))
    ram_gb = ocena_pc.pojemnosc_ram_gb(ram)
    czesci = [krotko_cpu(cpu), krotko_gpu(gpu), f"{ram_gb}GB DDR5", d["storage"].strip()]
    obudowa = re.sub(r"^(Wymiana na|Zmiana na)\s+", "", (d.get("obudowa") or "").strip(), flags=re.I)
    obudowa = re.sub(r"\s*\([^)]*\)", "", obudowa).strip()          # „(kolor podświetlenia ustawiany…)” to opis, nie nazwa
    if obudowa:
        czesci.append(obudowa)
    model = (d.get("model") or "").strip()
    baza = (f"{model} ({krotko_cpu(cpu)}, {krotko_gpu(gpu)})" if model
            else f"{PREFIKS_PC[sklep]} | " + ", ".join(czesci))
    nazwa, n = baza, 1
    while nazwa in nazwy:
        n += 1
        nazwa = f"{baza} ({n})"
    klucz = f"pcimg_{sklep[:3]}_" + hashlib.sha1(d["zdjecie"].encode()).hexdigest()[:10]
    e = {"img": klucz, "name": nazwa, "cpu": cpu, "gpu": gpu, "ram": ram, "storage": dysk, "psu": psu,
         "os": os_, "price": cena, "store": NAZWY_SKLEPOW[sklep], "prices": {sklep: bare},
         "urls": {sklep: d["url"]}, "scores": scores, "pros": zal, "cons": wad,
         "longevityYears": sc["longevityYears"], "osPriceNote": nota, "priceBare": bare,
         "osPriceKind": rodzaj}
    return e, d.get("sprzedawca"), d["zdjecie"]


def wpis_pc_js(e, sprzedawca):
    js = npc.wpis_js(e)
    if sprzedawca:
        sklep = next(iter(e["urls"]))
        js = re.sub(r"(, price:\d+)", lambda m: m.group(1) + ", sprzedawcy:{%s:%s}" % (
            sklep, npc.js_tekst(sprzedawca)), js, count=1)
    return js


def wstaw_pc(sz, wpisy):
    i = sz.index("var PDATA")
    koniec = i + re.search(r"\n\s*\];", sz[i:]).start()
    glowa = sz[:koniec].rstrip()
    if not glowa.endswith(","):
        glowa += ","
    return glowa + "\n    " + ",\n    ".join(wpis_pc_js(e, s) for e, s in wpisy) + "," + sz[koniec:]


# ------------------------------------------------------------------ przebieg
def wczytaj_json(sciezka, domyslne):
    try:
        return json.load(open(sciezka, encoding="utf-8"))
    except Exception:
        return domyslne


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--na-sucho", action="store_true")
    ap.add_argument("--dopisz", action="store_true")
    ap.add_argument("--limit-mon", type=int, default=10, help="najwyżej tyle NOWYCH monitorów na przebieg")
    ap.add_argument("--limit-pc", type=int, default=25, help="najwyżej tyle NOWYCH zestawów PC na przebieg")
    ap.add_argument("--maks-stron", type=int, default=6)
    ap.add_argument("--maks-pobran", type=int, default=MAKS_POBRAN)
    ap.add_argument("--sklepy", default="", help="np. xkom,mediamarkt (domyślnie wszystkie)")
    a = ap.parse_args()
    if not (a.na_sucho or a.dopisz):
        ap.error("podaj --na-sucho albo --dopisz")
    wybrane = {s for s in a.sklepy.split(",") if s}

    sz = open(SZABLON, encoding="utf-8").read()
    poz = z.wczytaj(sz)
    znane = {u for p in poz for u in p["urls"].values()}
    nazwy = {p["name"] for p in poz}
    odrzucone = wczytaj_json(ODRZUCONE, {})
    stan = wczytaj_json(STAN, {})
    nowe_odrzucone, pominiete, stan_sklepow = {}, [], {}
    licznik = Licznik(a.maks_pobran)
    rozmiar = os.path.getsize(os.path.join(BAZA, "index.html"))

    mon_klucze = [k for k in SKLEPY_MON if not wybrane or k in wybrane]
    pc_klucze = [k for k in SKLEPY_PC if not wybrane or k in wybrane]
    adaptery_mon = wczytaj_adaptery(mon_klucze)
    adaptery_pc = wczytaj_adaptery(pc_klucze)

    # ---- monitory
    kwota = max(15, a.maks_pobran // max(1, len(adaptery_mon) + len(adaptery_pc)))
    kand_mon = zbierz(adaptery_mon, "monitor", znane, odrzucone, nowe_odrzucone, pominiete, licznik,
                      a.maks_stron, stan_sklepow, stan, kwota)
    istniejace = opis_istniejacych(sz, poz)
    obrazy_mon = json.load(open(OBRAZY_MON, encoding="utf-8"))
    nast = max([int(k.split("_")[0]) for k in obrazy_mon if re.match(r"\d{2,}_", k)] or [0]) + 1
    uzupelnienia, konflikty, nowe_mon, nowe_obrazy_mon = [], [], [], {}
    for grupa in grupuj(kand_mon):
        dopasowane = [e for e in istniejace if any(ten_sam_model(o, e) for o in grupa)]
        if len(dopasowane) > 1:
            konflikty.append((grupa[0]["d"]["nazwa"], "kilka istniejących wpisów pasuje do tego modelu"))
            continue
        if dopasowane:
            e = dopasowane[0]
            for o in grupa:
                d = o["d"]
                if d["sklep"] in e["poz"]["urls"] or d["url"] in znane:
                    continue
                if e["panel"] and d["panel"] != e["panel"] and not {d["panel"], e["panel"]} <= {"oled", "qdoled"}:
                    konflikty.append((d["nazwa"], f"inna matryca niż w „{e['poz']['name']}” "
                                                  f"({d['panel']} ≠ {e['panel']}) — nie łączę"))
                    continue
                uzupelnienia.append((e["poz"]["start"], e["poz"]["name"], d["sklep"], d["cena"], d["url"]))
            continue
        nazwa = grupa[0]["d"]["nazwa"]
        if not any(o["pelne"] for o in grupa):
            pominiete.append((nazwa, "brak kodu modelu w nazwie — nie da się bezpiecznie sprawdzić duplikatu"))
            continue
        if len(nowe_mon) >= a.limit_mon:
            pominiete.append((nazwa, "limit przebiegu — dopisane w następnym"))
            continue
        if rozmiar + sum(len(v) for v in nowe_obrazy_mon.values()) > BUDZET_BAJTOW:
            pominiete.append((nazwa, "budżet rozmiaru strony (16 MB limitu artefaktu) wyczerpany"))
            continue
        panele = {o["d"]["panel"] for o in grupa}
        if len(panele) > 1 and not panele <= {"oled", "qdoled"}:
            konflikty.append((nazwa, f"sklepy podają różne matryce {sorted(panele)} — nie dopisuję"))
            continue
        e, c = wpis_monitora(grupa, nast)
        if e["name"] in nazwy or e["name"] in [x["name"] for x in nowe_mon]:
            pominiete.append((e["name"], "nazwa już istnieje na stronie"))
            continue
        if a.dopisz:
            try:
                nowe_obrazy_mon[e["img"]] = nm.zdjecie_data_uri(c[0]["zdjecie"])
            except Exception as x:
                pominiete.append((e["name"], f"BŁĄD TECHNICZNY (zdjęcie): {type(x).__name__}: {x}"))
                continue
        nowe_mon.append(e)
        nast += 1

    # ---- PC
    kand_pc = zbierz(adaptery_pc, "pc", znane, odrzucone, nowe_odrzucone, pominiete, licznik,
                     a.maks_stron, stan_sklepow, stan, kwota)
    widoczne = [p["price"] for p in poz if p["rodzaj"] == "pc" and not p["ukryty"]]
    najnizsza = min(widoczne) if widoczne else None
    obrazy_pc = json.load(open(OBRAZY_PC, encoding="utf-8"))
    nowe_pc, nowe_obrazy_pc = [], {}
    for d in kand_pc:
        if len(nowe_pc) >= a.limit_pc:
            pominiete.append((d["url"], "limit przebiegu — dopisane w następnym"))
            continue
        if rozmiar + sum(len(v) for v in nowe_obrazy_mon.values()) + sum(len(v) for v in nowe_obrazy_pc.values()) > BUDZET_BAJTOW:
            pominiete.append((d["url"], "budżet rozmiaru strony (16 MB limitu artefaktu) wyczerpany"))
            continue
        try:
            e, sprzedawca, zdj = zloz_pc(d, najnizsza, nazwy | {x["name"] for x, _ in nowe_pc})
            if a.dopisz and e["img"] not in obrazy_pc and e["img"] not in nowe_obrazy_pc:
                nowe_obrazy_pc[e["img"]] = npc.zdjecie_data_uri(zdj)
        except BrakDanych as x:
            pominiete.append((d["url"], str(x)))
            if not PRZEJSCIOWE.search(str(x)):
                nowe_odrzucone[f"{d.get('_klucz', d['sklep'])}|{d['url']}"] = str(x)
            continue
        except Exception as x:
            pominiete.append((d["url"], f"BŁĄD TECHNICZNY: {type(x).__name__}: {x}"))
            continue
        nowe_pc.append((e, sprzedawca))

    # ---- raport
    print(f"\nSKLEPY: " + "; ".join(f"{k} " + ", ".join(f"{r}: {t}" for r, t in v.items())
                                   for k, v in stan_sklepow.items()))
    print(f"\nUZUPEŁNIENIA istniejących monitorów: {len(uzupelnienia)}")
    for _, n, sk, c, u in uzupelnienia:
        print(f"   {c:5d} zł  {sk:<10}  {n}")
    print(f"DO DOPISANIA: {len(nowe_mon)} monitorów, {len(nowe_pc)} zestawów PC")
    for e in nowe_mon:
        print(f"   {e['price']:5d} zł  {e['hz']:3d} Hz  {e['diag']:>6}  sklepy: {','.join(e['urls'])}  {e['name']}")
    for e, _ in nowe_pc:
        print(f"   {e['price']:5d} zł  ultra {e['scores']['ultra']:3d}  {e['name'][:70]}")
    if konflikty:
        print(f"KONFLIKTY (nic nie zmieniono): {len(konflikty)}")
        for n, p in konflikty[:8]:
            print(f"   {n[:50]}: {p}")
    print(f"POMINIĘTE: {len(pominiete)}")
    powody = {}
    for _, p in pominiete:
        k = re.sub(r"\d+(?:[.,]\d+)?", "N", p)[:70]
        powody[k] = powody.get(k, 0) + 1
    for p, n in sorted(powody.items(), key=lambda x: -x[1])[:10]:
        print(f"   {n:3d}× {p}")
    techniczne = [p for _, p in pominiete if p.startswith("BŁĄD TECHNICZNY")]
    if techniczne:
        print(f"\n!!! UWAGA: {len(techniczne)} BŁĘDÓW TECHNICZNYCH (nie braków danych) — nabór jest "
              f"niepełny; to AWARIA do zgłoszenia: {techniczne[0][:150]}")

    if a.dopisz:
        json.dump(stan, open(STAN, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    if a.na_sucho or not (nowe_mon or nowe_pc or uzupelnienia):
        if a.dopisz and nowe_odrzucone:
            odrzucone.update(nowe_odrzucone)
            json.dump(odrzucone, open(ODRZUCONE, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
        return {"dopisane": len(nowe_mon) + len(nowe_pc), "uzupelnione": len(uzupelnienia)}

    # ---- zapis: od końca pliku, z kontrolą liczby wpisów
    nowy = sz
    zrobione = []
    for start, nazwa, sklep, cena, url in sorted(uzupelnienia, reverse=True):
        nowy, ok = dolacz_sklep(nowy, start, sklep, cena, url)
        if ok:
            zrobione.append((nazwa, sklep))
    if nowe_mon:
        nowy = nm.wstaw(nowy, nowe_mon)
    if nowe_pc:
        nowy = wstaw_pc(nowy, nowe_pc)
    sprawdz = z.wczytaj(nowy)
    if len(sprawdz) != len(poz) + len(nowe_mon) + len(nowe_pc):
        sys.exit(f"KONTROLA NIE PRZESZŁA: wpisów było {len(poz)}, miało być "
                 f"{len(poz) + len(nowe_mon) + len(nowe_pc)}, jest {len(sprawdz)} — nic nie zapisano")
    for p in sprawdz:
        stare = next((q for q in poz if q["start"] is not None and q["name"] == p["name"]), None)
        if stare and not set(stare["urls"]) <= set(p["urls"]):
            sys.exit(f"KONTROLA NIE PRZESZŁA: wpis „{p['name']}” stracił adresy sklepów — nic nie zapisano")
    open(SZABLON, "w", encoding="utf-8").write(nowy)
    if nowe_obrazy_mon:
        obrazy_mon.update(nowe_obrazy_mon)
        open(OBRAZY_MON, "w", encoding="utf-8").write(json.dumps(obrazy_mon, ensure_ascii=False))
    if nowe_obrazy_pc:
        obrazy_pc.update(nowe_obrazy_pc)
        open(OBRAZY_PC, "w", encoding="utf-8").write(json.dumps(obrazy_pc, ensure_ascii=False))
    odrzucone.update(nowe_odrzucone)
    json.dump(odrzucone, open(ODRZUCONE, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    raport = {"dopisane_monitory": [e["name"] for e in nowe_mon], "dopisane_pc": [e["name"] for e, _ in nowe_pc],
              "uzupelnione": zrobione, "konflikty": konflikty, "pominiete": pominiete, "sklepy": stan_sklepow}
    json.dump(raport, open(RAPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nszablon zapisany; przeliczam oceny i buduję stronę")
    subprocess.run([sys.executable, os.path.join(BAZA, "przelicz_oceny.py"), "--bez-przebudowy"], check=True)
    subprocess.run([sys.executable, os.path.join(BAZA, "build_merged.py")], check=True)
    return raport


if __name__ == "__main__":
    main()
