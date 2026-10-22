#!/usr/bin/env python3
"""Dopisuje do strony NOWE zestawy PC z katalogu Hard-PC — razem z oceną, tekstem i zdjęciem.

Do 22.10.2026 automat umiał tylko odświeżać ceny i ukrywać wycofane pozycje; nowy zestaw
wymagał „osobnej pracy" (sprawdz_katalogi.py wypisywał kandydatów i na tym kończył).
Dziś oceny PC liczy kod (ocena_pc.py), więc nowa pozycja może dostać pełną, uczciwą ocenę.

ZASADY (ta sama co w całym serwisie: BRAK zamiast zgadywania):
- zestaw dopisujemy tylko wtedy, gdy każdą daną da się odczytać ze strony sklepu: procesor,
  karta (łącznie z pamięcią), RAM DDR5, dysk, zasilacz, cena Windows z konfiguratora;
- brakująca dana = pominięcie i wpis w raporcie, nigdy wartość domyślna;
- próg ceny: od 5000 zł bez systemu do 10 000 zł Z DOLICZONYM WINDOWSEM (decyzja
  właściciela z 21.10.2026);
- wpis wskazujemy położeniem, nie kluczem zdjęcia (jedna obudowa = jedno zdjęcie).

Użycie:
  python3 nowe_pc.py --na-sucho            # pokaż, co zostałoby dopisane
  python3 nowe_pc.py --dopisz --limit 25   # dopisz najwyżej 25 zestawów, przelicz, zbuduj
"""
import argparse, base64, hashlib, html as htmllib, io, json, os, re, subprocess, sys, urllib.request

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import ocena_pc
from ocena_pc import BrakDanych
import zbieraj_ceny as z

SZABLON = os.path.join(BAZA, "monitors_1700_template.html")
OBRAZY_PC = os.path.join(BAZA, "images", "pcs.json")
UA = z.UA if hasattr(z, "UA") else "Mozilla/5.0"

CENA_OD_BEZ_SYSTEMU = 5000
SUFIT_Z_WINDOWS = 10000
# Artefakt w aplikacji Claude ma twardy limit 16 MB; zdjęcia w base64 to prawie cały rozmiar.
BUDZET_BAJTOW = 15_300_000
OPCJA_WINDOWS = re.compile(r"^Windows 11 Home", re.I)


# ------------------------------------------------------------------ odczyt strony
def rozbierz_tytul(tytul):
    """„Zestaw | CPU, GPU, RAM, [dysk,] zasilacz, obudowa" → części. BrakDanych, gdy
    tytuł nie ma znanego kształtu — nie zgadujemy, która część jest którą."""
    m = re.match(r"^Zestaw \| (.+)$", (tytul or "").strip())
    if not m:
        raise BrakDanych(f"tytuł w nieznanym kształcie: {tytul!r}")
    czesci = [c.strip() for c in m.group(1).split(",")]
    wynik = {"cpu": None, "gpu": None, "ram": None, "dysk": None, "psu": None, "obudowa": []}
    for c in czesci:
        if re.search(r"\b(RTX|RX)\s*\d{4}", c, re.I) and not wynik["gpu"]:
            wynik["gpu"] = c
        elif re.search(r"\d+\s*GB\s*DDR[45]", c, re.I) and not wynik["ram"]:
            wynik["ram"] = c
        elif re.search(r"^\d{3,4}\s*W$", c, re.I):
            wynik["psu"] = re.sub(r"\s+", "", c).upper()
        elif re.search(r"^\d+(?:[.,]\d+)?\s*(TB|GB)\s*(SSD|HDD)", c, re.I):
            wynik["dysk"] = c
        elif re.search(r"(Ryzen|Intel|Core|Ultra|\bi[3579]\b)", c, re.I) and not wynik["cpu"]:
            wynik["cpu"] = c
        else:
            wynik["obudowa"].append(c)
    for k in ("cpu", "gpu", "ram"):
        if not wynik[k]:
            raise BrakDanych(f"w tytule nie ma pola {k}: {tytul!r}")
    return wynik


def specyfikacja(s):
    """Etykieta → wartość z bloku „Dane techniczne" na stronie produktu."""
    i = s.find('class="list-specification"')
    if i < 0:
        raise BrakDanych("strona nie ma bloku danych technicznych")
    j = s.find("</ul>", i)
    pary = re.findall(r"<li><p>(.*?)</p><p>(.*?)</p></li>", s[i:j], re.S)
    return {re.sub(r"<[^>]+>", "", a).strip(): htmllib.unescape(re.sub(r"<[^>]+>", "", b)).strip()
            for a, b in pary}


def dysk_znormalizowany(spec, tytul_dysk):
    """„500GB SSD" / „1TB SSD" / „SSD: brak (potwierdzone przez sklep)". Zapis jest
    ZAWSZE prosty (bez „NVMe"/„M.2"): stary wzór dawał +4 pkt za samo słowo NVMe, więc
    ten sam dysk zapisany raz tak, raz inaczej dostawał inną ocenę."""
    wartosc = next((v for k, v in spec.items() if k.lower().startswith("dysk")), None)
    if wartosc is not None and re.search(r"\bbrak\b", wartosc, re.I):
        return "SSD: brak (potwierdzone przez sklep)"
    zrodlo = tytul_dysk or wartosc
    if not zrodlo:
        raise BrakDanych("brak danych o dysku ani w tytule, ani w specyfikacji")
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(TB|GB)", zrodlo, re.I)
    if not m:
        raise BrakDanych(f"dysk bez pojemności: {zrodlo!r}")
    liczba = m.group(1).replace(",", ".")
    liczba = liczba[:-2] if liczba.endswith(".0") else liczba
    rodzaj = "HDD" if re.search(r"\bHDD\b", zrodlo, re.I) and not re.search(r"SSD", zrodlo, re.I) else "SSD"
    return f"{liczba}{m.group(2).upper()} {rodzaj}"


def gpu_kanoniczna(gpu_tytul, spec):
    """„NVIDIA GeForce RTX 5060 Ti 16GB". Pamięć bierzemy ze specyfikacji (źródło
    rozstrzygające), a tytuł tylko potwierdza — zestaw z kartą bez podanej pamięci
    dawał dotąd cichą wartość domyślną 8 GB."""
    m = re.search(r"\b(RTX|RX)\s*(\d{4})\s*(Ti|XT)?\b", gpu_tytul, re.I)
    if not m:
        raise BrakDanych(f"nie rozpoznaję karty w {gpu_tytul!r}")
    amd = m.group(1).upper() == "RX"
    sufiks = (m.group(3) or "")
    sufiks = " Ti" if sufiks.upper() == "TI" else " XT" if sufiks.upper() == "XT" else ""
    nazwa = f"{'AMD Radeon RX' if amd else 'NVIDIA GeForce RTX'} {m.group(2)}{sufiks}"
    vt = re.search(r"(\d{1,2})\s*GB", gpu_tytul, re.I)
    vs = next((re.search(r"(\d{1,2})\s*GB", v) for k, v in spec.items()
               if k.lower().startswith("pamięć karty") and re.search(r"\d\s*GB", v)), None)
    if vt and vs and vt.group(1) != vs.group(1):
        raise BrakDanych(f"pamięć karty w tytule ({vt.group(1)} GB) różni się od specyfikacji "
                         f"({vs.group(1)} GB): {gpu_tytul!r}")
    pamiec = (vt or vs)
    if not pamiec:
        raise BrakDanych(f"brak pojemności pamięci karty: {gpu_tytul!r}")
    return f"{nazwa} {pamiec.group(1)}GB"


def ram_ddr5(ram_tytul, spec):
    if not re.search(r"DDR5", ram_tytul, re.I):
        raise BrakDanych(f"pamięć nie jest DDR5: {ram_tytul!r}")
    w = next((v for k, v in spec.items() if k.lower().startswith("pamięć ram")), None)
    # Tytuł mówi DDR5; specyfikacja bywa lakoniczna („Adata/Goodram 32GB 6000MHz") i samego
    # standardu nie powtarza. Odrzucamy dopiero sprzeczność — DDR4 w specyfikacji — a nie
    # brak słowa „DDR5": 6000 MHz przy tytule DDR5 nie jest powodem do pominięcia zestawu.
    if w is not None and re.search(r"DDR4", w, re.I):
        raise BrakDanych(f"specyfikacja podaje DDR4, tytuł DDR5: {w!r}")
    m = re.search(r"(\d+)\s*GB", ram_tytul, re.I)
    return f"{m.group(1)}GB DDR5"


def zdjecie_url(s):
    m = re.search(r'og:image"\s+content="([^"]+)"', s)
    if not m:
        raise BrakDanych("strona nie podaje zdjęcia produktu")
    return m.group(1)


# ------------------------------------------------------------------ składanie wpisu
def zloz_wpisy(url, s, ceny_min_istniejace, nazwy_istniejace, klucz_zdjecia):
    """Zwraca listę wpisów (bazowy + ewentualny wariant custom 32GB) albo rzuca BrakDanych."""
    if "OutOfStock" in s and '"InStock"' not in s:
        raise BrakDanych("towar niedostępny")
    tytul = z.nazwa_ze_strony(s)
    t = rozbierz_tytul(tytul)
    spec = specyfikacja(s)
    cena_bare, _ = z.wyciagnij("hardpc", url, s)
    if not cena_bare:
        raise BrakDanych("nie udało się odczytać ceny")
    opcje = z.opcje_konfiguratora(s)
    okno = next((v for k, v in opcje.items() if OPCJA_WINDOWS.match(k)), None)
    if okno is None:
        # Sklep instaluje nieaktywowany Windows, ale na tej stronie nie sprzedaje licencji.
        # Cena „z Windowsem" nie istnieje, więc nie ma z czym porównać progu 10 000 zł.
        raise BrakDanych("strona nie oferuje licencji Windows 11 Home — brak ceny z systemem")

    gpu = gpu_kanoniczna(t["gpu"], spec)
    ram = ram_ddr5(t["ram"], spec)
    dysk = dysk_znormalizowany(spec, t["dysk"])
    psu = t["psu"]
    if not psu:
        w = next((v for k, v in spec.items() if k.lower() == "zasilacz"), "")
        m = re.search(r"(\d{3,4})\s*W", w)
        if not m:
            raise BrakDanych("brak mocy zasilacza")
        psu = f"{m.group(1)}W"
    cpu = t["cpu"]
    ocena_pc.klasa_cpu(cpu)        # brak reguły klasy = pominięcie zestawu (BrakDanych)
    ocena_pc.klasa_gpu(gpu)

    if not (CENA_OD_BEZ_SYSTEMU <= cena_bare and cena_bare + okno <= SUFIT_Z_WINDOWS):
        raise BrakDanych(f"cena poza progiem: {cena_bare} zł bez systemu, {cena_bare + okno} z Windowsem")

    nazwa = tytul
    n = 1
    while nazwa in nazwy_istniejace:
        n += 1
        nazwa = f"{tytul} ({n})"

    def jeden(ram_, bare, custom=None):
        sc = ocena_pc.oceny(cpu, gpu, ram_, dysk, psu, "Windows 11 Home", 1)
        cena = bare + okno
        value = _wartosc(cena, sc["perf"])
        wynik = {"longevity": _dlugowiecznosc(sc["longevityYears"]), "value": value,
                 "longevityYears": sc["longevityYears"]}
        zestaw = {"cpu": cpu, "gpu": gpu, "ram": ram_, "storage": dysk, "psu": psu,
                  "os": "Windows 11 Home", "price": cena, "liczba_sklepow": 1,
                  # tekst wady o RAM bez kwoty: kwota dopłaty zmienia się w sklepie, a tekst
                  # zamarzałby na starej (tak się stało z 66 wariantami)
                  "dopłata_ram": None}
        zal, wad = ocena_pc.zalety_wady(zestaw, wynik, custom, ceny_min_istniejace)
        scores = _sumy(sc, value, wynik["longevity"])
        return {
            "img": klucz_zdjecia, "name": nazwa + (" (custom: 32GB RAM)" if custom else ""),
            "cpu": cpu, "gpu": gpu, "ram": ram_ + (" DDR5" if "DDR5" not in ram_ else ""),
            "storage": dysk, "psu": psu, "os": "Windows 11 Home (doliczony do ceny)",
            "price": cena, "store": "Hard-PC.pl", "prices": {"hardpc": bare},
            "urls": {"hardpc": url}, "scores": scores, "pros": zal, "cons": wad,
            "longevityYears": sc["longevityYears"],
            "osPriceNote": (f"Cena bazowa (bez systemu): {bare} zl + Windows 11 Home (potwierdzona "
                            f"w konfiguratorze Hard-PC.pl): {okno} zl."),
            "priceBare": bare, "osPriceKind": "confirmed",
        }, custom

    ram_gb = ocena_pc.pojemnosc_ram_gb(ram)
    opcje_ram = next((v for k, v in opcje.items() if re.match(r"^32\s*GB", k)), None) if ram_gb == 16 else None
    wpisy = []
    baza, _ = jeden(ram, cena_bare)
    wpisy.append(baza)
    if ram_gb == 16 and opcje_ram:
        bare32 = cena_bare + opcje_ram
        if bare32 + okno <= SUFIT_Z_WINDOWS:
            custom = {"dopłata": opcje_ram, "baza_ram": ram}
            w32, _ = jeden("32GB DDR5", bare32, custom)
            w32.update({"isCustom": True, "customLabel": f"+ RAM 32GB (+{opcje_ram} zł)",
                        "baseName": nazwa, "baseRam": ram, "ramUpgradeCost": opcje_ram})
            wpisy.append(w32)
    return wpisy


# --- wartości zależne od przelicz_oceny (progi bezwzględne), żeby wpis był od razu spójny
def _wartosc(cena, perf):
    import przelicz_oceny as po
    return po.ocena_wartosci(cena / perf, "pc")


def _dlugowiecznosc(lata):
    import przelicz_oceny as po
    return po.ocena_dlugowiecznosci(str(lata))


def _sumy(sc, value, longevity):
    import przelicz_oceny as po
    from fractions import Fraction
    s = {"perf": sc["perf"], "components": sc["components"], "value": value,
         "features": sc["features"], "longevity": longevity}
    def suma(wagi):
        v = sum(Fraction(s[k]) * Fraction(str(w)) for k, w in wagi)
        return int(round(v))
    s["overall"] = suma(po.WZORY["pc"]["overall"])
    s["ultra"] = suma(po.WZORY["pc"]["ultra"])
    return {k: s[k] for k in ("perf", "components", "value", "features", "overall", "longevity", "ultra")}


# ------------------------------------------------------------------ zapis do szablonu
def js_tekst(x):
    return '"' + str(x).replace("\\", "\\\\").replace('"', '\\"') + '"'


def wpis_js(e):
    def lista(l): return "[" + ",".join(js_tekst(x) for x in l) + "]"
    def slownik(d, tekst=False):
        return "{" + ",".join(f"{k}:{js_tekst(v) if tekst else v}" for k, v in d.items()) + "}"
    p = [("img", js_tekst(e["img"])), ("name", js_tekst(e["name"])), ("cpu", js_tekst(e["cpu"])),
         ("gpu", js_tekst(e["gpu"])), ("ram", js_tekst(e["ram"])), ("storage", js_tekst(e["storage"])),
         ("psu", js_tekst(e["psu"])), ("os", js_tekst(e["os"])), ("price", e["price"]),
         ("store", js_tekst(e["store"])), ("prices", slownik(e["prices"])),
         ("urls", slownik(e["urls"], True)), ("scores", slownik(e["scores"])),
         ("pros", lista(e["pros"])), ("cons", lista(e["cons"]))]
    if e.get("isCustom"):
        p += [("isCustom", "true"), ("customLabel", js_tekst(e["customLabel"])),
              ("baseName", js_tekst(e["baseName"])), ("baseRam", js_tekst(e["baseRam"])),
              ("ramUpgradeCost", e["ramUpgradeCost"])]
    p += [("longevityYears", e["longevityYears"]), ("osPriceNote", js_tekst(e["osPriceNote"])),
          ("priceBare", e["priceBare"]), ("osPriceKind", js_tekst(e["osPriceKind"]))]
    return "{" + ", ".join(f"{k}:{v}" for k, v in p) + "}"


def wstaw(sz, wpisy):
    """Dopisuje wpisy na koniec PDATA. Zwraca nowy tekst szablonu."""
    i = sz.index("var PDATA")
    koniec = i + re.search(r"\n\s*\];", sz[i:]).start()
    glowa = sz[:koniec].rstrip()
    if not glowa.endswith(","):
        glowa += ","
    nowe = ",\n    ".join(wpis_js(e) for e in wpisy)
    return glowa + "\n    " + nowe + "," + sz[koniec:]


def zdjecie_data_uri(url_zdjecia):
    from PIL import Image
    if not z.REGULAMIN.wolno(url_zdjecia):
        raise BrakDanych("robots.txt nie pozwala pobrać zdjęcia")
    z.TEMPO.czekaj("sklep.hard-pc.pl")
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
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--na-sucho", action="store_true")
    ap.add_argument("--dopisz", action="store_true")
    ap.add_argument("--limit", type=int, default=25, help="najwyżej tyle NOWYCH zestawów bazowych")
    a = ap.parse_args()
    if not (a.na_sucho or a.dopisz):
        ap.error("podaj --na-sucho albo --dopisz")

    import sprawdz_katalogi as sk
    sz = open(SZABLON, encoding="utf-8").read()
    poz = z.wczytaj(sz)
    nasze_id = {m.group(1) for p in poz for u in p["urls"].values()
                if (m := re.search(r"/p(\d+),", u))}
    nazwy = {p["name"] for p in poz}
    widoczne = [p["price"] for p in poz if p["rodzaj"] == "pc" and not p["ukryty"]]
    najnizsza = min(widoczne) if widoczne else None
    obrazy = json.load(open(OBRAZY_PC, encoding="utf-8"))
    rozmiar = os.path.getsize(os.path.join(BAZA, "index.html"))

    print("pobieram katalog Hard-PC…", file=sys.stderr)
    kat = sk.katalog()
    kandydaci, pominiete = [], []
    for pid, k in sorted(kat.items()):
        if pid in nasze_id:
            continue
        if "DDR4" in k["nazwa"].upper():
            continue
        if not re.search(r"\b(RTX|RX)\s*\d{4}", k["nazwa"], re.I):
            continue
        if k["cena"] < CENA_OD_BEZ_SYSTEMU or k["cena"] >= SUFIT_Z_WINDOWS:
            continue
        # wstępnie po samym tytule z katalogu: karta i procesor muszą mieć klasę w słowniku.
        # Odrzucenie tu nie jest zgadywaniem — ta sama kontrola pada i po pobraniu strony.
        try:
            tt = rozbierz_tytul(k["nazwa"])
            ocena_pc.klasa_cpu(tt["cpu"]); ocena_pc.klasa_gpu(tt["gpu"])
        except BrakDanych as x:
            pominiete.append((k["nazwa"], str(x))); continue
        kandydaci.append(k)
    print(f"kandydatów w katalogu: {len(kandydaci)} (nie ma ich jeszcze na stronie)", file=sys.stderr)

    nowe, dodane_baz = [], 0
    nowe_obrazy = {}
    for k in kandydaci:
        if dodane_baz >= a.limit:
            pominiete.append((k["nazwa"], "limit przebiegu — dopisane w następnym"))
            continue
        if rozmiar + sum(len(v) for v in nowe_obrazy.values()) > BUDZET_BAJTOW:
            pominiete.append((k["nazwa"], "budżet rozmiaru strony (16 MB limitu artefaktu) wyczerpany")); continue
        kod, s = z.pobierz(k["url"])
        if kod != 200:
            pominiete.append((k["nazwa"], f"HTTP {kod}")); continue
        try:
            klucz = "pcimg_hpc_" + hashlib.sha1(zdjecie_url(s).encode()).hexdigest()[:10]
            wpisy = zloz_wpisy(k["url"], s, najnizsza, nazwy | {e["name"] for e in nowe}, klucz)
            if klucz not in obrazy and klucz not in nowe_obrazy and a.dopisz:
                nowe_obrazy[klucz] = zdjecie_data_uri(zdjecie_url(s))
        except BrakDanych as x:
            pominiete.append((k["nazwa"], str(x))); continue
        except Exception as x:                       # nieoczekiwane: nie wywracamy całego przebiegu
            pominiete.append((k["nazwa"], f"błąd: {type(x).__name__}: {x}")); continue
        nowe.extend(wpisy)
        dodane_baz += 1

    print(f"\nDO DOPISANIA: {dodane_baz} zestawów bazowych + "
          f"{sum(1 for e in nowe if e.get('isCustom'))} wariantów custom")
    for e in nowe:
        print(f"   {e['price']:5d} zł  ultra {e['scores']['ultra']:3d}  {e['name'][:70]}")
    print(f"\nPOMINIĘTE: {len(pominiete)}")
    powody = {}
    for _, p in pominiete:
        powody[re.sub(r"\d+", "N", p)[:70]] = powody.get(re.sub(r"\d+", "N", p)[:70], 0) + 1
    for p, n in sorted(powody.items(), key=lambda x: -x[1])[:10]:
        print(f"   {n:3d}× {p}")

    if a.na_sucho or not nowe:
        return {"dopisane": len(nowe), "pominiete": pominiete}

    # kontrola przed zapisem: nowy szablon musi się wczytać, bez utraty wpisów
    nowy_sz = wstaw(sz, nowe)
    sprawdz = z.wczytaj(nowy_sz)
    if len(sprawdz) != len(poz) + len(nowe):
        sys.exit(f"KONTROLA NIE PRZESZŁA: wpisów było {len(poz)}, miało być {len(poz) + len(nowe)}, "
                 f"jest {len(sprawdz)} — nic nie zapisano")
    open(SZABLON, "w", encoding="utf-8").write(nowy_sz)
    if nowe_obrazy:
        obrazy.update(nowe_obrazy)
        open(OBRAZY_PC, "w", encoding="utf-8").write(json.dumps(obrazy, ensure_ascii=False))
    raport = {"dopisane": [e["name"] for e in nowe], "pominiete": pominiete}
    json.dump(raport, open(os.path.join(BAZA, "raport_nowe_pc.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nszablon zapisany; przeliczam oceny i buduję stronę")
    subprocess.run([sys.executable, os.path.join(BAZA, "przelicz_oceny.py"), "--bez-przebudowy"], check=True)
    subprocess.run([sys.executable, os.path.join(BAZA, "build_merged.py")], check=True)
    return raport


if __name__ == "__main__":
    main()
