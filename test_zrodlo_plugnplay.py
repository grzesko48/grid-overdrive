#!/usr/bin/env python3
"""Test kontrolny adapterów zrodla/plugnplay.py i zrodla/goblinpc.py na zapisanych stronach (bez sieci).

Sprawdza to, co przy naborze komputerów z tych sklepów może zepsuć stronę po cichu:
  1. kontrakt adaptera (SKLEP, LOKALNIE, SKLEP_UWAGI, cztery funkcje, komplet kluczy wyniku),
  2. listy: parser kafelków, paginacja (rel=next), przesiew DDR4 i ceny, kopia robots.txt,
     zachowanie przy HTTP ≠ 200 i przy zmianie układu — przez WSTRZYKNIĘTĄ atrapę `pobierz`,
  3. karty komputerów: pola z bloku specyfikacji i konfiguratora (PlugNPlay), z kafelków „Pod maską"
     (GoblinPC); karty do odrzucenia (DDR4, brak pamięci karty, zdjęcie tylko pod zakazanym adresem),
  4. odrzucenia wymuszone na prawdziwych kartach przez zmianę jednego pola (brak w sprzedaży, brak
     ceny, DDR4, brak dysku, karta/procesor spoza słownika, sprzeczność pamięci karty…),
  5. zgodność wyniku z ocena_pc (klasy karty i procesora znane, oceny się liczą),
  6. MONITORY: oba sklepy zwracają [] bez żądania (PlugNPlay: zakres zlecenia — sklep ma kategorię
     Monitor; GoblinPC: sklep nie sprzedaje monitorów).

Fixtury w tests_fixtures/ to prawdziwe strony pobrane 30.10.2026; usunięto z nich tylko bloki <style>,
<svg>, skrypty inne niż ld+json i nadmiarowe białe znaki (rozmiar). Sieć jest w teście ZABLOKOWANA.
"""
import os, re, socket, sys

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)


import ocena_pc
from ocena_pc import BrakDanych
import nowe_pc
from zrodla import plugnplay as pnp
from zrodla import goblinpc as gob


def _zakaz_sieci(*a, **k):
    raise RuntimeError("test nie może używać sieci")


# po zaimportowaniu modułów (ssl dziedziczy po socket.socket) wyłączamy sieć na czas testu
socket.socket = _zakaz_sieci
socket.create_connection = _zakaz_sieci

F = os.path.join(BAZA, "tests_fixtures")
bledy = []


def czytaj(n):
    return open(os.path.join(F, n + ".html"), encoding="utf-8").read()


def oczekuj(warunek, opis):
    if not warunek:
        bledy.append(opis)
        print("  BŁĄD:", opis)


def odrzucone(modul, plik_lub_html, fragment, opis, url="https://przyklad.pl/x"):
    """Karta ma być odrzucona z powodem zawierającym `fragment`."""
    html = plik_lub_html if plik_lub_html.lstrip().startswith("<") else czytaj(plik_lub_html)
    try:
        modul.odczytaj_pc(url, html)
        oczekuj(False, f"{opis}: powinno być odrzucone")
    except BrakDanych as x:
        oczekuj(fragment.lower() in str(x).lower(), f"{opis}: zły powód odrzucenia: {x}")


def atrapa(strony):
    """pobierz-atrapa: {adres: html lub (kod, html)}; zapisuje żądania. Adres spoza słownika = 404."""
    wywolania = []

    def pobierz(url):
        wywolania.append(url)
        if url in strony:
            v = strony[url]
            return v if isinstance(v, tuple) else (200, v)
        return (404, "")

    pobierz.wywolania = wywolania
    return pobierz


WYMAGANE_KLUCZE = {"nazwa", "url", "cpu", "gpu", "ram", "storage", "psu", "cena_bazowa", "system",
                   "dostepny", "sprzedawca", "zdjecie", "ean"}


def sprawdz_zgodnosc_z_ocena(d, opis):
    """Wynik adaptera musi dać się policzyć przez ocena_pc (klasy znane, pamięć karty, RAM, dysk)."""
    try:
        sc = ocena_pc.oceny(d["cpu"], d["gpu"], d["ram"], d["storage"], d["psu"], "Windows 11 Home", 1)
        oczekuj(60 <= sc["perf"] <= 100 and ocena_pc.pamiec_gpu_gb(d["gpu"]) >= 8, f"{opis}: oceny {sc}")
    except BrakDanych as x:
        oczekuj(False, f"{opis}: ocena_pc odrzuca wynik adaptera: {x}")
    oczekuj(d["gpu"] == nowe_pc.gpu_kanoniczna(d["gpu"], {}), f"{opis}: karta nie jest kanoniczna: {d['gpu']!r}")
    oczekuj(re.fullmatch(r"\d+GB DDR5( \d+MHz)?", d["ram"]) is not None, f"{opis}: zapis RAM {d['ram']!r}")


# ---------------------------------------------------------------- 1. kontrakt
for modul, klucz in ((pnp, "plugnplay"), (gob, "goblinpc")):
    oczekuj(modul.SKLEP == klucz, f"{klucz}: SKLEP = {modul.SKLEP!r}")
    oczekuj(modul.LOKALNIE is False, f"{klucz}: LOKALNIE powinno być False")
    oczekuj(isinstance(modul.SKLEP_UWAGI, str) and len(modul.SKLEP_UWAGI) > 80, f"{klucz}: SKLEP_UWAGI")
    for fn in ("lista_monitorow", "odczytaj_monitor", "lista_pc", "odczytaj_pc"):
        oczekuj(callable(getattr(modul, fn, None)), f"{klucz}: brak funkcji {fn}")
oczekuj("tabeli parametrów" in pnp.SKLEP_UWAGI, "PlugNPlay: SKLEP_UWAGI wyjaśnia brak tabeli parametrów monitorów")

# ---------------------------------------------------------------- 6. monitory (jawnie)
print("INFO PlugNPlay: monitory poza zakresem zlecenia (adapter tylko komputery); sklep ma jednak kategorię "
      "Monitor — fixtura plugnplay_lista_monitory.html")
print("INFO GoblinPC: sklep nie sprzedaje monitorów (tylko gotowe zestawy i konfigurator komputerów)")
nic = atrapa({})
for modul, klucz in ((pnp, "plugnplay"), (gob, "goblinpc")):
    oczekuj(modul.lista_monitorow(nic) == [], f"{klucz}: lista_monitorow powinna zwracać []")
    oczekuj(modul.lista_monitorow(nic, uwagi=[]) == [], f"{klucz}: lista_monitorow z opcjonalnym uwagi=[]")
    try:
        modul.odczytaj_monitor("https://x/y", "<html></html>")
        oczekuj(False, f"{klucz}: odczytaj_monitor powinien rzucać BrakDanych")
    except BrakDanych:
        pass
oczekuj(nic.wywolania == [], f"monitory: adaptery nie mogą wysyłać żądań, wysłały {nic.wywolania}")
kafle_mon = pnp.kafelki(czytaj("plugnplay_lista_monitory"))
oczekuj(len(kafle_mon) >= 5 and all(k["nazwa"].startswith("Monitor") for k in kafle_mon),
        f"fixtura kategorii Monitor PlugNPlay: {[k['nazwa'] for k in kafle_mon][:3]}")

# ---------------------------------------------------------------- 2a. PlugNPlay: listy
L1, L2 = czytaj("plugnplay_lista_komputery_1"), czytaj("plugnplay_lista_komputery_2")
URL2 = pnp.LISTA_PC + "/2"
k1, k2 = pnp.kafelki(L1), pnp.kafelki(L2)
oczekuj([k["id"] for k in k1] == ["310", "221", "233", "1028", "240", "210", "272", "226"],
        f"strona 1: kafelki {[k['id'] for k in k1]}")
oczekuj(len(k2) == 9 and k2[0]["cena"] == 7599, f"strona 2: {len(k2)} kafelków")
oczekuj(pnp.nastepna_strona(L1, pnp.LISTA_PC) == URL2, "strona 1: link rel=next")
oczekuj(pnp.nastepna_strona(L1.replace('rel="next"', 'rel="nofollow"'), pnp.LISTA_PC) is None,
        "brak rel=next powinien kończyć paginację")
oczekuj(pnp.nastepna_strona(L1.replace("https://plugnplay.sklep.pl/kategoria-produktu/komputery/2",
                                       "https://obcy.pl/kategoria-produktu/komputery/2"), pnp.LISTA_PC) is None,
        "rel=next na obcą domenę powinno być odrzucone")

L2_koniec = L2.replace('rel="next"', 'rel="nofollow"')
PNP = atrapa({pnp.LISTA_PC: L1, URL2: L2_koniec})
adresy = pnp.lista_pc(PNP)
oczekuj(PNP.wywolania == [pnp.LISTA_PC, URL2], f"dwie strony = dwa żądania, było {PNP.wywolania}")
B = "https://plugnplay.sklep.pl/pl/p/"
oczekuj(adresy == [B + "Komputer-RTX-5070-AMD-AM5-32GB-DDR5-1TB-BIALY/233", B + "Komputer-RTX-5060-Ti-AMD-AM5-32GB-DDR5-1TB/210",
                   B + "Komputer-RTX-5060-AMD-AM5-32GB-DDR5-1TB/196", B + "Komputer-RTX-5060-Ti-AMD-AM5-32GB-DDR5-1TB/219"],
        f"adresy (cena 5000–10000, bez DDR4): {adresy}")
oczekuj(not any("DDR4" in a for a in adresy), "na liście został adres DDR4")
oczekuj(all(pnp.dozwolony(a) for a in adresy + [pnp.LISTA_PC, URL2]), "adres sprzeczny z robots.txt")

# maks_stron jako dolna granica: nawet przy maks_stron=1 pobiera obie strony za rel=next
P1 = atrapa({pnp.LISTA_PC: L1, URL2: L2_koniec})
adresy_p1 = pnp.lista_pc(P1, maks_stron=1)
oczekuj(len(adresy_p1) == 4 and P1.wywolania == [pnp.LISTA_PC, URL2],
        f"maks_stron jako dolna granica: idzie za rel=next mimo maks_stron=1 ({P1.wywolania})")

# domyślne wywołanie idzie za rel=next poza 6 stron
strony_8 = {}
for i in range(1, 9):
    u = pnp.LISTA_PC if i == 1 else f"{pnp.LISTA_PC}/{i}"
    u_next = f"{pnp.LISTA_PC}/{i+1}"
    if i < 8:
        strony_8[u] = L1.replace('href="https://plugnplay.sklep.pl/kategoria-produktu/komputery/2"', f'href="{u_next}"')
    else:
        strony_8[u] = L1.replace('rel="next"', 'rel="nofollow"')
P8 = atrapa(strony_8)
oczekuj(len(pnp.lista_pc(P8)) > 0 and len(P8.wywolania) == 8,
        f"domyślne wywołanie idzie za rel=next poza 6 stron (odwiedzono {len(P8.wywolania)})")

# twardy sufit MAKS_STRON_TWARDO = 40
strony_45 = {}
for i in range(1, 46):
    u = pnp.LISTA_PC if i == 1 else f"{pnp.LISTA_PC}/{i}"
    u_next = f"{pnp.LISTA_PC}/{i+1}"
    strony_45[u] = L1.replace('href="https://plugnplay.sklep.pl/kategoria-produktu/komputery/2"', f'href="{u_next}"')
P45 = atrapa(strony_45)
pnp.lista_pc(P45)
oczekuj(len(P45.wywolania) == pnp.MAKS_STRON_TWARDO == 40,
        f"twardy sufit MAKS_STRON_TWARDO=40 zatrzymuje pętlę (odwiedzono {len(P45.wywolania)})")

# uwagi: 403 na pierwszej stronie zwraca [] i wpisuje uwagę
uw_pnp = []
res_403 = pnp.lista_pc(atrapa({pnp.LISTA_PC: (403, "forbidden")}), uwagi=uw_pnp)
oczekuj(res_403 == [] and len(uw_pnp) == 1 and "403" in uw_pnp[0],
        f"PlugNPlay: 403 na pierwszej stronie zwraca [] i wpisuje uwagę: {uw_pnp}")

# uwagi: błąd na stronie >= 2 zachowuje wynik pierwszej i wpisuje uwagę
uw_p2 = []
res_p2 = pnp.lista_pc(atrapa({pnp.LISTA_PC: L1, URL2: (403, "forbidden")}), uwagi=uw_p2)
oczekuj(len(res_p2) == 2 and len(uw_p2) == 1 and "403" in uw_p2[0],
        f"PlugNPlay: błąd HTTP na stronie >= 2 zachowuje dotychczasowe adresy i wpisuje uwagę: {uw_p2}")

oczekuj(len(pnp.lista_pc(atrapa({pnp.LISTA_PC: L1, URL2: L2_koniec}), maks_stron=2, cena_od=None, cena_do=None)) == 11,
        "bez przesiewu ceny powinno zostać 11 adresów (7 + 4, DDR4 odsiane)")
oczekuj(len(pnp.lista_pc(atrapa({pnp.LISTA_PC: L1}), maks_stron=5)) == 2,
        "brak 200 na drugiej stronie powinien zachować wynik pierwszej")
for nazwa, strony, fragment in (("HTTP 404 na pierwszej stronie", {}, "HTTP 404"),
                                ("zmiana układu", {pnp.LISTA_PC: "<html><body>nic</body></html>"}, "niedostępne")):
    try:
        pnp.lista_pc(atrapa(strony))
        oczekuj(False, f"PlugNPlay lista: {nazwa} powinno rzucać BrakDanych")
    except BrakDanych as x:
        oczekuj(fragment in str(x), f"PlugNPlay lista: {nazwa}: {x}")
oczekuj(not pnp.dozwolony("https://plugnplay.sklep.pl/pl/basket") and not pnp.dozwolony("https://plugnplay.sklep.pl/pl/login")
        and not pnp.dozwolony("https://plugnplay.sklep.pl/application/x") and not pnp.dozwolony("https://inny.pl/pl/p/x/1")
        and pnp.dozwolony("https://plugnplay.sklep.pl/environment/cache/images/a.jpg"),
        "kopia robots.txt PlugNPlay źle rozstrzyga adresy")

# ---------------------------------------------------------------- 3a. PlugNPlay: karty
U = "https://plugnplay.sklep.pl/pl/p/Komputer-RTX-5060-Ti-AMD-AM5-32GB-DDR5-1TB/210"
d = pnp.odczytaj_pc(U, czytaj("plugnplay_pc_210_5060ti_ryzen"))
oczekuj(WYMAGANE_KLUCZE <= set(d), f"210: brakuje kluczy {WYMAGANE_KLUCZE - set(d)}")
oczekuj((d["cpu"], d["gpu"], d["ram"], d["storage"], d["psu"]) ==
        ("Ryzen 5 7500F", "NVIDIA GeForce RTX 5060 Ti 8GB", "32GB DDR5 6000MHz", "1TB SSD M.2", "750W 80 Plus Bronze"),
        f"210: specyfikacja {(d['cpu'], d['gpu'], d['ram'], d['storage'], d['psu'])}")
oczekuj(d["cena_bazowa"] == 7799 and isinstance(d["cena_bazowa"], int), f"210: cena {d['cena_bazowa']!r}")
oczekuj(d["system"] == {"w_cenie": True, "doplata": 0, "nazwa": "Windows 11"}, f"210: system {d['system']}")
oczekuj(d["dostepny"] is True and d["sprzedawca"] is None and d["ean"] is None, "210: dostępność/sprzedawca/ean")
oczekuj(d["zdjecie"].startswith("https://plugnplay.sklep.pl/") and d["url"] == U, f"210: zdjęcie {d['zdjecie']!r}")
oczekuj(d["nazwa"] == "PlugNPlay | Ryzen 5 7500F, RTX 5060 Ti 8GB, 32GB DDR5, 1TB SSD M.2, KRUX EXO",
        f"210: nazwa {d['nazwa']!r}")
oczekuj(d["obudowa"] == "KRUX EXO" and d["vram_zrodlo"] == "konfigurator", f"210: obudowa/vram {d['obudowa']} {d['vram_zrodlo']}")
oczekuj(d["domyslne"] == {"Wersja karty (ilość VRAM)": "8GB", "Procesor": "Ryzen 5 7500F", "Gwarancja": "24 miesiące"},
        f"210: domyślne {d['domyslne']}")
oczekuj(d["opcje"].get("Wersja karty (ilość VRAM): 16GB") == 1000 and d["opcje"].get("Procesor: Ryzen 5 7600X") == 150
        and d["opcje"].get("Gwarancja: 36 miesięcy") == 199 and "Procesor: Ryzen 5 7500F" not in d["opcje"],
        f"210: opcje {d['opcje']}")
sprawdz_zgodnosc_z_ocena(d, "210")

d = pnp.odczytaj_pc("u", czytaj("plugnplay_pc_926_5060ti_intel"))
oczekuj((d["cpu"], d["cena_bazowa"], d["psu"], d["ram"]) == ("Core Ultra 5 245KF", 8999, "650W 80 Plus Bronze", "32GB DDR5 6000MHz"),
        f"926 (Intel, etykieta „RAM RGB”): {(d['cpu'], d['cena_bazowa'], d['psu'], d['ram'])}")
oczekuj(d["obudowa"] == "Krux Tano + 3 wentylatory reverse", f"926: obudowa {d['obudowa']!r}")
sprawdz_zgodnosc_z_ocena(d, "926")

d = pnp.odczytaj_pc("u", czytaj("plugnplay_pc_250_rx9070xt"))
oczekuj((d["gpu"], d["vram_zrodlo"], d["psu"], d["cena_bazowa"]) == ("AMD Radeon RX 9070 XT 16GB", "opis", "850W 80 Plus Gold", 8999),
        f"250 (pamięć karty z opisu): {(d['gpu'], d['vram_zrodlo'], d['psu'], d['cena_bazowa'])}")
oczekuj("Wersja karty (ilość VRAM)" not in d["domyslne"], "250: ta strona nie ma wyboru VRAM")
sprawdz_zgodnosc_z_ocena(d, "250")

d = pnp.odczytaj_pc("u", czytaj("plugnplay_pc_231_5060_biala"))
oczekuj((d["gpu"], d["psu"], d["obudowa"], d["cena_bazowa"]) == ("NVIDIA GeForce RTX 5060 8GB", "650W 80 Plus Bronze", "KRUX EXO biała", 8199),
        f"231 (wiersze „Zasilacz…Obudowa” bez <br>): {(d['gpu'], d['psu'], d['obudowa'], d['cena_bazowa'])}")
sprawdz_zgodnosc_z_ocena(d, "231")

# karty do odrzucenia
odrzucone(pnp, "plugnplay_pc_226_ddr4", "DDR4", "226 (platforma AM4, DDR4)")
odrzucone(pnp, "plugnplay_pc_1004_bez_vram", "brak pamięci karty", "1004 (RTX 5060 Ti bez pamięci w opisie i bez wyboru VRAM)")
odrzucone(pnp, "<html><body>Peryferia</body></html>", "brak ceny", "strona bez danych produktu")

# ---------------------------------------------------------------- 4a. PlugNPlay: odrzucenia wymuszone mutacją prawdziwej karty
K = czytaj("plugnplay_pc_210_5060ti_ryzen")


def zmien(tekst, wzor, nowy, ile=1):
    wynik, n = re.subn(wzor, nowy, tekst)
    oczekuj(n >= ile, f"mutacja {wzor!r}: nic nie zmieniła (fixtura się zmieniła?)")
    return wynik


odrzucone(pnp, zmien(K, r"schema\.org/InStock", "schema.org/OutOfStock"), "nie ma w sprzedaży", "brak w sprzedaży")
odrzucone(pnp, zmien(K, r'"price":\s*7799', '"price":null', 2), "brak ceny", "brak ceny")
odrzucone(pnp, zmien(K, r'"price":\s*7799', '"price":99999999', 2), "poza wiarygodnym", "cena poza zakresem")
odrzucone(pnp, zmien(K, r"AMD AM5 \(DDR5\)", "AMD AM4 (DDR4)", 2), "DDR4", "DDR4 w platformie")
odrzucone(pnp, zmien(K, r"AMD AM5 \(DDR5\)", "AMD AM5", 2), "nie potwierdza DDR5", "brak potwierdzenia DDR5")
odrzucone(pnp, zmien(K, r"Dysk SSD M\.2:\s*1TB", "Dysk SSD M.2: brak"), "brak dysku", "brak dysku")
odrzucone(pnp, zmien(K, r"Dysk SSD M\.2:\s*1TB", "Dysk HDD: 2TB\nDysk SSD M.2: 1TB"), "niejednoznaczna", "wiele etykiet Dysk w specyfikacji")
odrzucone(pnp, zmien(K, r"Dysk SSD M\.2:\s*1TB", "Dysk SSD M.2: 250GB SSD + 1TB HDD"), "złożona konfiguracja", "dysk z plusem (+)")
odrzucone(pnp, zmien(K, r"Dysk SSD M\.2:\s*1TB", "Dysk SSD M.2: 2x 1TB SSD"), "wielokrotny dysk", "dysk z 2x")
odrzucone(pnp, zmien(K, r"Dysk SSD M\.2:\s*1TB", "Dysk: 1TB SSD 2TB HDD"), "jednocześnie SSD i HDD", "dysk SSD i HDD")
odrzucone(pnp, zmien(K, r"Zasilacz:\s*750W 80 Plus Bronze", "Zasilacz: markowy"), "mocy zasilacza", "brak mocy zasilacza")
odrzucone(pnp, zmien(K, r"Karta graficzna: GeForce RTX 5060\s+Ti", "Karta graficzna: GeForce RTX 5060 Ti 16GB"),
          "różni się", "pamięć karty w opisie ≠ domyślna w konfiguratorze")
odrzucone(pnp, zmien(K, r"Karta graficzna: GeForce RTX 5060\s+Ti", "Karta graficzna: GeForce RTX 4090"),
          "spoza słownika", "karta spoza słownika klas")
odrzucone(pnp, zmien(K, r"Karta graficzna: GeForce RTX 5060\s+Ti", "Karta graficzna: GeForce RTX 5070 Ti SUPER 16GB"),
          "nieobsługiwanym przyrostkiem", "karta z przyrostkiem SUPER")
odrzucone(pnp, zmien(K, r"Karta graficzna: GeForce RTX 5060\s+Ti", "Karta graficzna: Radeon RX 9070 GRE 16GB"),
          "nieobsługiwanym przyrostkiem", "karta z przyrostkiem GRE")
odrzucone(pnp, zmien(K, r"Karta graficzna: GeForce RTX 5060\s+Ti", "Karta graficzna: Radeon RX 7900 XTX 24GB"),
          "nieobsługiwanym przyrostkiem", "karta z przyrostkiem XTX")
odrzucone(pnp, zmien(K, r"Karta graficzna: GeForce RTX 5060\s+Ti", "Karta graficzna: GeForce RTX 4060 Ti 8GB"),
          "spoza słownika", "RTX 4060 Ti nie zgaduje RTX 4060")
odrzucone(pnp, zmien(K, r"Karta graficzna: GeForce RTX 5060\s+Ti", "Karta graficzna: Radeon RX 7600 XT"),
          "spoza słownika", "RX 7600 XT bez VRAM nie zgaduje 8GB z RX 7600")
odrzucone(pnp, zmien(K, r"(class=[\"\x27][^\"]*js__special-offer-price-value[^\"]*[\"\x27][^>]*>)[^<]+(</span>)",
                     r"\g<1>8 999,00 zł\2", 2), "rozbieżność ceny", "rozbieżność ld+json i widocznej ceny js__special-offer-price-value")
odrzucone(pnp, zmien(K, r'data-user-value="Ryzen 5 7500F"', 'data-user-value="Threadripper 7980X"'),
          "bez reguły klasy", "procesor spoza słownika klas")
odrzucone(pnp, zmien(K, r"DOK[ŁL]ADNA SPECYFIKACJA", "OPIS"), "niedostępny blok", "brak bloku specyfikacji")
# konfiguracja domyślna: jedyna opcja bez dopłaty, niekoniecznie pierwsza
oczekuj(pnp.domyslne({"G": [("a", -150), ("b", None), ("c", 100)]}) == {"G": "b"}, "domyslne: opcja bez dopłaty nie jest pierwsza")
for zle in ({"G": [("a", 100)]}, {"G": [("a", None), ("b", 0)]}):
    try:
        pnp.domyslne(zle)
        oczekuj(False, f"domyslne({zle}) powinno rzucać BrakDanych")
    except BrakDanych:
        pass
oczekuj(pnp.opcje_konfiguratora(czytaj("plugnplay_pc_226_ddr4"))["PROCESOR"][0] == ("Ryzen 3 4100", -150),
        "226: ujemna dopłata pierwszej opcji (konfiguracja domyślna to druga)")

# ---------------------------------------------------------------- 2b. GoblinPC: lista
GL = czytaj("goblinpc_lista_komputery")
kg = gob.kafelki(GL)
oczekuj([(k["nazwa"], k["cena"]) for k in kg][:4] == [("Utopiec", 6310), ("Goblin", 8800), ("Widmo", 9750), ("Kobold", 9930)]
        and len(kg) == 9, f"GoblinPC: kafelki {[(k['nazwa'], k['cena']) for k in kg]}")
oczekuj(gob._deklarowana_liczba(GL) == 9, "GoblinPC: deklarowana liczba zestawów")
G = atrapa({gob.LISTA_PC: GL})
ga = gob.lista_pc(G)
oczekuj(G.wywolania == [gob.LISTA_PC], f"GoblinPC: lista = jedno żądanie, było {G.wywolania}")
oczekuj(ga == ["https://goblinpc.pl/product/" + n for n in ("utopiec", "goblin", "widmo", "kobold")], f"GoblinPC: adresy {ga}")
oczekuj(len(gob.lista_pc(atrapa({gob.LISTA_PC: GL}), cena_od=None, cena_do=None)) == 9, "GoblinPC: bez przesiewu ceny 9 adresów")

# uwagi: 403 na pierwszej stronie zwraca [] i wpisuje uwagę
uw_gob = []
res_gob_403 = gob.lista_pc(atrapa({gob.LISTA_PC: (403, "forbidden")}), uwagi=uw_gob)
oczekuj(res_gob_403 == [] and len(uw_gob) == 1 and "403" in uw_gob[0],
        f"GoblinPC: 403 na pierwszej stronie zwraca [] i wpisuje uwagę: {uw_gob}")

for nazwa, strony, fragment in (("HTTP 404", {}, "HTTP 404"),
                                ("zmiana układu", {gob.LISTA_PC: "<html>nic</html>"}, "niedostępne"),
                                ("liczba kafelków ≠ deklarowanej", {gob.LISTA_PC: GL[:GL.index("/product/kobold")]}, "deklaruje 9")):
    try:
        gob.lista_pc(atrapa(strony))
        oczekuj(False, f"GoblinPC lista: {nazwa} powinno rzucać BrakDanych")
    except BrakDanych as x:
        oczekuj(fragment in str(x), f"GoblinPC lista: {nazwa}: {x}")
oczekuj(gob.dozwolony("https://goblinpc.pl/product/utopiec") and gob.dozwolony(gob.LISTA_PC)
        and not gob.dozwolony("https://goblinpc.pl/api/blob/x.png") and not gob.dozwolony("https://goblinpc.pl/checkout"),
        "kopia robots.txt GoblinPC źle rozstrzyga adresy")

# ---------------------------------------------------------------- 3b. GoblinPC: karty
d = gob.odczytaj_pc("https://goblinpc.pl/product/utopiec", czytaj("goblinpc_pc_utopiec"))
oczekuj(WYMAGANE_KLUCZE <= set(d), f"utopiec: brakuje kluczy {WYMAGANE_KLUCZE - set(d)}")
oczekuj((d["cpu"], d["gpu"], d["ram"], d["storage"], d["psu"], d["cena_bazowa"]) ==
        ("Ryzen 5 8400F", "NVIDIA GeForce RTX 5050 8GB", "16GB DDR5", "512GB SSD NVMe", "750W 80+ Gold", 6310),
        f"utopiec: {(d['cpu'], d['gpu'], d['ram'], d['storage'], d['psu'], d['cena_bazowa'])}")
oczekuj(d["nazwa"] == "Utopiec (GoblinPC)" and d["model"] == "Utopiec" and d["obudowa"] == "M30", f"utopiec: nazwa {d['nazwa']!r}")
oczekuj(d["system"] == {"w_cenie": True, "doplata": 0, "nazwa": "Windows 11"}, f"utopiec: system {d['system']}")
oczekuj(d["dostepny"] is True and d["sprzedawca"] is None and d["zdjecie"].startswith("https://"), "utopiec: dostępność/zdjęcie")
oczekuj(d["opcje"] == {} and d["opcje_bez_ceny"]["RAM"] == ["16GB", "32GB", "64GB"]
        and d["domyslne"] == {"Moc": "START", "RAM": "16GB", "Dysk": "512GB"}, f"utopiec: konfigurator {d['domyslne']}")
sprawdz_zgodnosc_z_ocena(d, "utopiec")

d = gob.odczytaj_pc("u", czytaj("goblinpc_pc_goblin"))
oczekuj((d["cpu"], d["gpu"], d["ram"], d["storage"], d["cena_bazowa"], d["domyslne"]["Moc"]) ==
        ("Ryzen 5 9600X", "NVIDIA GeForce RTX 5060 8GB", "32GB DDR5", "1TB SSD NVMe", 8800, "STANDARD"),
        f"goblin: {(d['cpu'], d['gpu'], d['ram'], d['storage'], d['cena_bazowa'])}")
sprawdz_zgodnosc_z_ocena(d, "goblin")

d = gob.odczytaj_pc("u", czytaj("goblinpc_pc_minotaur"))
oczekuj((d["cpu"], d["gpu"], d["psu"], d["cena_bazowa"]) == ("Ryzen 7 7800X3D", "AMD Radeon RX 9070 XT 16GB", "850W 80+ Gold", 12470),
        f"minotaur: {(d['cpu'], d['gpu'], d['psu'], d['cena_bazowa'])}")
sprawdz_zgodnosc_z_ocena(d, "minotaur")

# zestaw ze zdjęciami wyłącznie pod /api/blob/ (robots.txt: Disallow /api/) — nie podajemy zakazanego adresu
odrzucone(gob, "goblinpc_pc_kobold", "robots.txt", "kobold (zdjęcia tylko pod zakazanym /api/blob/)")
try:
    gob.odczytaj_pc("u", czytaj("goblinpc_pc_kobold"))
except BrakDanych as x:
    oczekuj(re.search(r"nie ma w sprzedaży|HTTP|brak zdjęcia|robots|niedostęp", str(x), re.I) is not None,
            f"powód odrzucenia zdjęcia powinien być uznany za przejściowy przez nabor.PRZEJSCIOWE: {x}")
oczekuj(gob.pierwsze_dozwolone_zdjecie(["/api/blob/a.png", "https://cdn.przyklad.pl/b.png"], "https://goblinpc.pl/", "goblinpc.pl",
                                       gob.ROBOTS_REGULY) == "https://cdn.przyklad.pl/b.png",
        "zdjęcie na cudzej domenie nie podlega robots.txt sklepu")

# ---------------------------------------------------------------- 4b. GoblinPC: odrzucenia wymuszone mutacją
UT = czytaj("goblinpc_pc_utopiec")
odrzucone(gob, zmien(UT, r"16GB DDR5", "16GB DDR4", 2), "DDR4", "DDR4")
odrzucone(gob, zmien(UT, r"schema\.org/MadeToOrder", "schema.org/OutOfStock"), "nie ma w sprzedaży", "brak w sprzedaży")
odrzucone(gob, zmien(UT, r'"price":"6310\.00"', '"price":""'), "brak ceny", "brak ceny")
odrzucone(gob, zmien(UT, r'<span class="sp-tile-label">Dysk SSD</span>', '<span class="sp-tile-label">Dysk X</span>'), "nie ma pól", "brak kafelka dysku")
odrzucone(gob, zmien(UT, r'<span class="sp-tile-label">Dysk SSD</span>',
                     '<span class="sp-tile-label">Dysk HDD</span><span class="sp-tile-name">1TB HDD</span></div><div><span class="sp-tile-label">Dysk SSD</span>'),
          "niejednoznaczna", "GoblinPC wiele etykiet Dysk")
odrzucone(gob, zmien(UT, r"512GB NVMe", "512GB NVMe + 1TB HDD"), "złożona konfiguracja", "GoblinPC dysk z +")
odrzucone(gob, zmien(UT, r"512GB NVMe", "2x 512GB NVMe"), "wielokrotny dysk", "GoblinPC dysk 2x")
odrzucone(gob, zmien(UT, r"512GB NVMe", "512GB NVMe HDD"), "jednocześnie SSD i HDD", "GoblinPC SSD obok HDD")
odrzucone(gob, zmien(UT, r"RTX 5050 \(8GB\)", "RTX 5050", 2), "nie podaje pamięci", "karta bez pamięci")
odrzucone(gob, zmien(UT, r"RTX 5050 \(8GB\)", "RTX 4090 (24GB)", 2), "spoza słownika", "karta spoza słownika klas")
odrzucone(gob, zmien(UT, r"RTX 5050 \(8GB\)", "RTX 4060 Ti (8GB)", 2), "spoza słownika", "GoblinPC RTX 4060 Ti nie zgaduje RTX 4060")
odrzucone(gob, zmien(UT, r"RTX 5050 \(8GB\)", "RTX 5070 Ti SUPER (16GB)", 2), "nieobsługiwanym przyrostkiem", "GoblinPC RTX 5070 Ti SUPER")
odrzucone(gob, zmien(UT, r"RTX 5050 \(8GB\)", "RX 9070 GRE (16GB)", 2), "nieobsługiwanym przyrostkiem", "GoblinPC RX 9070 GRE")
odrzucone(gob, zmien(UT, r"Ryzen 5 8400f", "Core i3-12100", 2), "bez reguły klasy", "procesor spoza słownika klas")
odrzucone(gob, zmien(UT, r'<span class="sp-tile-name">16GB DDR5</span>', '<span class="sp-tile-name">32GB DDR5</span>'),
          "niejednoznaczny wariant", "RAM standardowy w konfiguratorze ≠ kafelek")
odrzucone(gob, zmien(UT, r'<span class="sp-tile-label">', '<span class="x-label">', 9), "niedostępna sekcja", "brak sekcji Pod maską")
odrzucone(gob, "<html><body>x</body></html>", "ld+json", "strona bez danych produktu")
bez_systemu = gob.odczytaj_pc("u", zmien(UT, r'<span class="sp-tile-label">System</span>', '<span class="sp-tile-label">Inne</span>'))
oczekuj(bez_systemu["system"] == {"w_cenie": None, "doplata": None, "nazwa": None},
        f"brak kafelka System = nie wiemy, a jest {bez_systemu['system']}")

print("\nTEST ZALICZONY" if not bledy else f"\nTEST NIEZALICZONY: {len(bledy)} błędów")
sys.exit(1 if bledy else 0)
