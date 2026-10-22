#!/usr/bin/env python3
"""Jawne wzory ocen zestawów PC: moc, podzespoły, kompletność, lata długowieczności.

Do 22.10.2026 te cztery składniki były liczby wpisanymi w szablonie, a kod, który je
wyprodukował, żył w jednorazowych skryptach z 17-18.09 (pc_audit/, recheck/), których nie
da się dziś uruchomić. Ten moduł odtwarza je co do wpisu: na 355 zestawach z szablonu
daje moc 355/355, kompletność 355/355, lata 355/355, podzespoły 354/355 (test:
test_ocena_pc.py). Jest jedynym źródłem tych wzorów — przelicz_oceny.py liczy nimi oceny
istniejących zestawów, a nowe_pc.py oceny zestawów dopisywanych automatycznie.

ZASADA: brak danych to wyjątek BrakDanych, nigdy wartość domyślna. Stare funkcje wpadały
po cichu w klasę 3 dla nieznanej karty/procesora i w 8 GB dla karty bez podanej pamięci;
zestaw trafiał do rankingu z oceną wziętą z powietrza i nikt tego nie widział.
"""
import re


class BrakDanych(Exception):
    """Zamiast wstawienia wartości domyślnej. Wywołujący pomija pozycję i zgłasza ją."""


# ------------------------------------------------------------------ klasy podzespołów
# Skala klas karty jest INNA niż w słowniku GPU_TIER w szablonie (tam 1-8 do pokazywania
# segmentów); ta wyprowadza moc i lata, i odtwarza dotychczasowe oceny. Klasa nie zależy
# od ilości pamięci — o pamięci decyduje osobna poprawka w latach długowieczności.
KLASA_GPU = {
    "rtx 5090": 10, "rtx 5080": 9, "rtx 5070 ti": 7, "rtx 5070": 6, "rtx 5060 ti": 4,
    "rtx 5060": 3, "rtx 5050": 2, "rtx 4060": 3, "rx 9070 xt": 7, "rx 9070": 6,
    "rx 9060 xt": 4, "rx 9060": 3, "rx 7600": 2, "arc b580": 3, "arc a750": 2,
    # RX 7700 XT dostawała 3 przez cichą wartość domyślną; zostaje 3, teraz JAWNIE.
    # Słownik GPU_TIER na stronie stawia ją w klasie 5 (wyżej niż RTX 5060 Ti 8GB), więc 3
    # wygląda na zaniżone, ale klasa 4 podniosłaby ocenę Ultra jedynego takiego zestawu
    # o 9 pkt (58 → 67) — to decyzja właściciela, nie skutek uboczny poprawki.
    "rx 7700 xt": 3,
}
# Karty, które istnieją w JEDNEJ wersji pamięci — brak GB w opisie nie jest wtedy niejasny.
JEDNA_PAMIEC_GB = {"rtx 5090": 32, "rtx 5080": 16, "rtx 5070 ti": 16, "rtx 5070": 12,
                   "rtx 5060": 8, "rtx 5050": 8, "rx 9070 xt": 16, "rx 9070": 16,
                   "rx 7600": 8, "rx 7700 xt": 12}

# Zakres mocy, względem którego skalujemy ocenę 60-100. Wcześniej min i max brano z
# aktualnego zbioru, więc dodanie jednego zestawu przestawiało oceny wszystkich —
# tę samą usterkę usunięto z „Opłacalności" i „Długowieczności". Wartości to końce
# zakresu z dnia audytu: RTX 5050 + najsłabszy procesor, RTX 5070 Ti + najmocniejszy.
MOC_MIN, MOC_MAX = 2.44, 6.78


def znormalizuj_gpu(surowa):
    g = (surowa or "").lower()
    g = g.replace("nvidia geforce ", "").replace("amd radeon ", "").replace("intel ", "")
    return re.sub(r"\s+", " ", g).strip()


def _klucz_gpu(gpu):
    g = znormalizuj_gpu(gpu)
    for k in sorted(KLASA_GPU, key=len, reverse=True):
        if k in g:
            return k
    raise BrakDanych(f"karta spoza słownika klas: {gpu!r} — dopisz ją do KLASA_GPU "
                     f"z klasą ustaloną na podstawie testów albo pomiń zestaw")


def klasa_gpu(gpu):
    return KLASA_GPU[_klucz_gpu(gpu)]


def pamiec_gpu_gb(gpu):
    m = re.search(r"(\d{1,2})\s*GB", gpu or "", re.I)
    if m:
        return int(m.group(1))
    k = _klucz_gpu(gpu)
    if k in JEDNA_PAMIEC_GB:
        return JEDNA_PAMIEC_GB[k]
    raise BrakDanych(f"brak pojemności pamięci karty {gpu!r}, a ten model ma co najmniej "
                     f"dwie wersje — nie zakładam 8 GB")


def klasa_cpu(cpu):
    c = (cpu or "").lower()
    # „Intel Ultra 225F" i „Intel Core Ultra 5 225F" to ten sam procesor zapisany dwoma
    # sposobami; pierwszy dostawał klasę 3 przez wartość domyślną, drugi 5 (8 pkt różnicy
    # w „Podzespołach" za samą pisownię). 225F to Core Ultra 5, 270K to Core Ultra 7.
    if re.search(r"\b225f\b", c):
        return 5
    if re.search(r"\b270k\b", c):
        return 6
    # „ryzen 9" / „i9" bez dokładniejszej reguły = klasa 6 (zachowawczo: więcej rdzeni niż Ryzen 7 / i7,
    # ale bez pamięci 3D V-Cache i bez przewagi Ultra 9; dopisane 22.10.2026, żeby automat nie odrzucał
    # takich zestawów — wcześniej każdy zestaw z Ryzen 9 był pomijany jako „procesor bez reguły klasy").
    for fragment, klasa in (("ultra 9", 7), ("ultra 7 2", 7), ("ryzen 7 9700x", 6),
                            ("8745hx", 6), ("ultra 7", 6), ("7800x3d", 6), ("9800x3d", 6),
                            ("7500x3d", 6), ("9600x", 5), ("9500f", 5), ("ultra 5", 5),
                            ("ryzen 9", 6), ("i9", 6), ("ryzen 7", 5), ("i7", 5), ("7500f", 4), ("8400f", 4),
                            ("ryzen 5", 4), ("i5", 4)):
        if fragment in c:
            return klasa
    raise BrakDanych(f"procesor bez reguły klasy: {cpu!r} — dopisz regułę w klasa_cpu()")


def zaokr(v, lo=1, hi=100):
    return max(lo, min(hi, int(round(v))))


def pojemnosc_ram_gb(ram):
    m = re.search(r"(\d+)\s*GB", ram or "", re.I)
    if not m:
        raise BrakDanych(f"brak pojemności RAM w {ram!r}")
    return int(m.group(1))


def jakosc_ram(ram):
    # 32 GB to OPTIMUM (decyzja właściciela 22.10.2026): więcej nie daje już punktów.
    cap = pojemnosc_ram_gb(ram)
    q = 11 if cap >= 32 else 5 if cap >= 16 else 0
    return q + (6 if "ddr5" in (ram or "").lower() else 0)


# Kary rankingowe (w punktach Ultra i oceny ogólnej PC). To jawne reguły właściciela, nie
# pomiar: zestaw poniżej optimum nie może wygrać z zestawem kompletnym i optymalnym.
KARA_RAM_PONIZEJ_32GB = 10   # 16 GB RAM nie może być na szczycie; 32 GB jest optymalne
KARA_BRAK_DYSKU = 20         # komputer bez dysku nie jest gotowy do pracy


def kary_rankingu(ram, dysk):
    """Suma kar [pkt] odejmowana od Ultra i oceny ogólnej PC. BrakDanych, gdy RAM nieczytelny."""
    kara = 0
    if pojemnosc_ram_gb(ram) < 32:
        kara += KARA_RAM_PONIZEJ_32GB
    if bez_ssd(dysk):
        kara += KARA_BRAK_DYSKU
    return kara


def pojemnosc_dysku_gb(dysk):
    """Pojemność w GB; TB liczone jako 1000 (tak podają producenci). None = brak dysku."""
    s = (dysk or "").upper()
    if re.search(r"\bBRAK\b|SSD:\s*BRAK", s):
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*TB", s)
    if m:
        return int(round(float(m.group(1).replace(",", ".")) * 1000))
    m = re.search(r"(\d+)\s*GB", s)
    return int(m.group(1)) if m else 0


def jakosc_dysku(dysk):
    """Progi na pojemności w GB. Wersja z 17.09 mnożyła TB przez 1024, ale GB brała
    dosłownie, więc „1000GB" przy progu 1024 lądowało piętro niżej niż „1TB" — ta sama
    fizyczna pojemność, o 4 pkt mniej w ocenie."""
    gb = pojemnosc_dysku_gb(dysk)
    if gb is None:
        return 0
    # Progi jak dotąd (512 GB → 4, 500 GB → 0): przesunięcie na 500 ruszyłoby 133 zestawy.
    q = 12 if gb >= 2000 else 8 if gb >= 1000 else 4 if gb >= 512 else 0
    if "NVME" in (dysk or "").upper() or "M.2" in (dysk or "").upper():
        q += 4
    return q


def bez_ssd(dysk):
    s = (dysk or "").upper()
    return ("HDD" in s and "SSD" not in s) or pojemnosc_dysku_gb(dysk) is None


def podzespoly(cpu, ram, dysk):
    # Zestaw bez żadnego dysku dostaje tę samą karę co zestaw z samym HDD. Wcześniej
    # „brak dysku" dawał tyle samo punktów co 500 GB: urządzenie, którego nie da się
    # uruchomić bez dokupienia nośnika, oceniano jak kompletne.
    return zaokr(58 + klasa_cpu(cpu) * 4 + jakosc_ram(ram) + jakosc_dysku(dysk)
                 - (15 if bez_ssd(dysk) else 0))


def moc(gpu, cpu):
    p = klasa_gpu(gpu) * 0.78 + klasa_cpu(cpu) * 0.22
    return zaokr(60 + (p - MOC_MIN) / (MOC_MAX - MOC_MIN) * 40)


def kompletnosc(zasilacz, system, liczba_sklepow):
    w = 0
    m = re.search(r"(\d{3,4})W", zasilacz or "")
    if m:
        w = int(m.group(1))
    f = 58.0
    f += 12 if w >= 750 else 6 if w >= 600 else -6 if w == 0 else 0
    z = (zasilacz or "").lower()
    # ZNANA USTERKA, ZACHOWANA CELOWO: rozpoznajemy wyłącznie zapis „80+ gold/bronze".
    # Zasilacze zapisane „80 Plus Gold" (kilkadziesiąt zestawów) premii nie dostają,
    # choć to ta sama certyfikacja. Poprawka podniosłaby ich ocenę o 1 pkt — to decyzja
    # właściciela, nie skutek uboczny; do czasu decyzji wzór odtwarza dotychczasowe oceny.
    if "80+ gold" in z:
        f += 7
    elif "80+ bronze" in z:
        f += 3
    if system and "windows" in system.lower():
        f += 7
    if liczba_sklepow >= 2:
        f += 6
    return zaokr(f)


def lata_dlugowiecznosci(gpu, ram):
    wyjscie = 1.0 + klasa_gpu(gpu) / 3.0
    vram = pamiec_gpu_gb(gpu)
    wyjscie += -0.3 if vram <= 8 else 0.3 if vram >= 16 else 0.0
    wyjscie += 0.15 if pojemnosc_ram_gb(ram) >= 32 else -0.15
    return round(wyjscie, 2)


def oceny(cpu, gpu, ram, dysk, zasilacz, system, liczba_sklepow):
    """Wszystkie cztery składniki naraz; BrakDanych, jeśli któregoś nie da się policzyć."""
    return {"perf": moc(gpu, cpu), "components": podzespoly(cpu, ram, dysk),
            "features": kompletnosc(zasilacz, system, liczba_sklepow),
            "longevityYears": lata_dlugowiecznosci(gpu, ram)}


# ------------------------------------------------------------------ teksty zalet i wad
def zalety_wady(zestaw, wyniki, wariant_custom=None, najnizsza_cena=None):
    """Zalety i wady wpisu — te same reguły co przy zestawach już na stronie.

    `zestaw`: cpu, gpu, ram, storage, psu, os, price, liczba_sklepow.
    `wyniki`: gotowe oceny 0-100 (`longevity`, `value`) i `longevityYears` — teksty muszą
    mówić to samo co liczby na karcie, więc liczy je wołający, nie my.
    `wariant_custom`: None albo {"dopłata": 899, "baza_ram": "16GB DDR5"}."""
    z, w = zestaw, wyniki
    tier, ctier = klasa_gpu(z["gpu"]), klasa_cpu(z["cpu"])
    ram_gb = pojemnosc_ram_gb(z["ram"])
    m = re.search(r"(\d{3,4})W", z["psu"] or "")
    psu_w = int(m.group(1)) if m else 0
    zal = []
    if wariant_custom:
        zal.append(f"Wariant custom: RAM podniesiony do 32GB za dopłatą {wariant_custom['dopłata']} zł "
                   f"względem wersji bazowej ({wariant_custom['baza_ram']}) — realny wzrost trwałości platformy.")
    if tier >= 6:
        zal.append(f"Karta {z['gpu']} — wydajność wystarczająca do gier w 1440p w wysokich ustawieniach.")
    elif tier >= 4:
        zal.append(f"Karta {z['gpu']} — solidna wydajność 1080p/1440p w większości gier.")
    if ctier >= 6:
        zal.append(f"Procesor {z['cpu']} — jeden z mocniejszych w tym zestawieniu.")
    if w["longevity"] >= 75:
        zal.append(f"Wysoka długowieczność (szac. ~{w['longevityYears']:.1f} roku komfortowej gry w 1440p) — dobry wybór na dłuższą metę.")
    if w["value"] >= 82:
        zal.append("Jeden z najlepszych stosunków ceny do wydajności całego zestawu (GPU + CPU) w zestawieniu.")
    if ram_gb >= 32 and not wariant_custom:
        zal.append(f"{z['ram']} — komfortowy zapas na kolejne lata i multitasking.")
    if re.search(r"6000\s*MH?z", z["ram"] or "", re.I):
        zal.append("Szybka pamięć DDR5-6000 — realny plus w grach z platformą AM5/nowszym Intelem.")
    if z["os"] and "windows" in z["os"].lower():
        zal.append("System Windows 11 w cenie — gotowy do pracy po rozpakowaniu.")
    if najnizsza_cena is not None and z["price"] <= najnizsza_cena:
        zal.append("Najniższa cena w całym zestawieniu.")
    if len(zal) < 2:
        zal.append(f"Spełnia kryteria zestawienia: {z['gpu']}, {z['ram']}, w cenie {z['price']:.0f} zł.")

    wad = []
    # brak dysku to wada rozstrzygająca — nie może wypaść z listy przez limit dwóch pozycji
    if pojemnosc_dysku_gb(z["storage"]) is None:
        wad.append("Brak dysku SSD w zestawie (potwierdzone przez sklep) — trzeba dokupić go osobno.")
    if z["liczba_sklepow"] <= 1:
        wad.append("Potwierdzona dostępność tylko w 1 sklepie z tych sprawdzonych.")
    if ram_gb < 32 and not wariant_custom:
        if z.get("dopłata_ram"):
            wad.append(f"{z['ram']} — w sklepie dostępna opcja podniesienia do 32GB za {z['dopłata_ram']} zł (patrz wariant custom w rankingu).")
        else:
            wad.append(f"{z['ram']} — wystarczające dziś, ale bez dużego zapasu na przyszłość.")
    if psu_w and psu_w < 550:
        wad.append(f"Zasilacz {psu_w}W — ograniczony zapas mocy na ewentualny upgrade karty graficznej.")
    if "500GB" in (z["storage"] or "") or "512GB" in (z["storage"] or ""):
        wad.append("Dysk 500-512 GB — komfortowe na start, ale szybko zapełnione przy kilku dużych grach.")
    if "HDD" in (z["storage"] or "").upper() and "SSD" not in (z["storage"] or "").upper():
        wad.append("W zestawie dysk HDD — zauważalnie wolniejsze wczytywanie gier niż na SSD NVMe.")
    if tier <= 2:
        wad.append(f"Karta {z['gpu']} — segment budżetowy, krótszy realny okres komfortowej gry w wysokich ustawieniach 1440p.")
    if not wad:
        wad.append("Brak wyróżniających się wad poza typowymi ograniczeniami tej klasy cenowej.")
    return zal[:3], wad[:2]
