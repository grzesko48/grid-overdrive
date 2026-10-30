#!/usr/bin/env python3
"""Test kontrolny zrodla/morele_pc.py na zapisanych stronach Morele (bez sieci).

Strony w tests_fixtures/morele_pc_*.html to PRAWDZIWE karty i listy pobrane 30.10.2026, przycięte
do fragmentów potrzebnych adapterowi (JSON-LD, cena, sprzedawca, tabele specyfikacji, filtr
„Chipset graficzny”), przepisanych dosłownie. Test sprawdza:
  1. kontrakt: SKLEP, LOKALNIE, SKLEP_UWAGI; monitory — jawnie: ten adapter ich nie zbiera;
  2. pięć kart do przyjęcia (Morele i marketplace, z systemem i bez, Intel/AMD/Radeon),
     a w nich: sprzedawca z karty (JSON-LD kłamie „Morele.net”), jeden dysk mimo dwóch pól,
     karta ze znaną klasą w ocena_pc, zgodność zapisu karty z nowe_pc.gpu_kanoniczna;
  3. odrzucenia: DDR4, karta zintegrowana, sprzeczność tytułu i specyfikacji (prawdziwy przypadek:
     facet „RTX 4060” przy tytule „RTX 5060”) oraz warianty wyprowadzone z prawdziwej karty
     (brak w sprzedaży, brak ceny, brak dysku, nieznany procesor, model karty spoza słownika,
     adres wskazujący inny produkt);
  4. cena bez kodu rabatowego (znacznik kodu skopiowany z prawdziwej promo_morele_kod.html);
  5. lista: adresy, kolejność filtrów, paginacja, powrót „poza ostatnią stroną” na pierwszą,
     odporność na błąd pojedynczej strony, błąd pierwszej strony, zgodność z robots.txt;
  6. założenie parsera: pole „Moc” leży w grupie „Zasilacz” (tabela HTML) w każdej przyjętej karcie.
Test nie łączy się z siecią — połączenie gniazda jest zablokowane na czas testu.
"""
import json, os, re, socket, sys

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)


def _zakaz_sieci(*a, **k):
    raise RuntimeError("TEST NIE MOŻE ŁĄCZYĆ SIĘ Z SIECIĄ")


socket.socket.connect = _zakaz_sieci

import nowe_pc
import ocena_pc
from ocena_pc import BrakDanych
from zrodla import morele_pc as mp

F = os.path.join(BAZA, "tests_fixtures")
bledy = []


def czytaj(n, rozszerzenie=".html"):
    return open(os.path.join(F, n + rozszerzenie), encoding="utf-8").read()


def oczekuj(warunek, opis):
    if not warunek:
        bledy.append(opis)
        print("  BŁĄD:", opis)


def odrzucone(opis, url, html, fragment):
    try:
        mp.odczytaj_pc(url, html)
        oczekuj(False, f"{opis}: powinno być odrzucone")
    except BrakDanych as x:
        oczekuj(fragment in str(x), f"{opis}: powód {str(x)!r} bez fragmentu {fragment!r}")


def zamien(html, stare, nowe):
    """Wariant testowy karty. Brak trafienia = test sam się psuje (nie ma cichego „przeszło”)."""
    oczekuj(stare in html, f"wariant testowy: w karcie nie ma {stare!r}")
    return html.replace(stare, nowe)


# --- adresy kart (dokładnie takie, jak podaje lista sklepu)
ADRES = {
    "legion_amd": "https://www.morele.net/komputer-lenovo-legion-t5-30agb10-ryzen-5-7600-32-gb-rtx-5060-ti-1-tb-m-2-pcie-15413990/",
    "legion_intel": "https://www.morele.net/komputer-lenovo-legion-t5-30iax10-core-ultra-5-225-32-gb-rtx-5060-ti-1-tb-m-2-pcie-windows-11-home-15413991/",
    "artrel": "https://www.morele.net/komputer-artrel-ryzen-7-8700f-16gb-rtx-5060-ti-1tb-m-2-pcie-windows-11-pro-600025607/",
    "error": "https://www.morele.net/komputer-error-gaming-pc-mc-stellar-5f-ryzen-7-9800x3d-16gb-rtx-5060-ti-1tb-ssd-windows-11-pg01341-600480073/",
    "rx9070xt": "https://www.morele.net/komputer-game-x-g500-ryzen-7-7800x3d-32-gb-radeon-rx-9070-xt-1-tb-m-2-pcie-windows-11-home-7715386/",
    "ddr4": "https://www.morele.net/komputer-game-x-g100-lite-ryzen-5-5600x-16-gb-rtx-5060-512-gb-m-2-pcie-12056793/",
    "biuro": "https://www.morele.net/komputer-lenovo-thinkcentre-neo-50s-core-i5-14400-16-gb-intel-uhd-graphics-730-512-gb-m-2-pcie-windows-11-pro-14769847/",
    "quickpc": "https://www.morele.net/komputer-quickpc-ryzen-7-8700f-32gb-rtx-5060-1tb-m-2-pcie-15050316/",
}
PLIK = {"legion_amd": "morele_pc_legion_amd_bez_systemu", "legion_intel": "morele_pc_legion_intel_win",
        "artrel": "morele_pc_artrel_marketplace", "error": "morele_pc_error_marketplace",
        "rx9070xt": "morele_pc_gamex_rx9070xt", "ddr4": "morele_pc_ddr4_gamex_g100",
        "biuro": "morele_pc_biuro_uhd730", "quickpc": "morele_pc_quickpc_sprzecznosc"}

# 1. kontrakt
oczekuj(mp.SKLEP == "morele", f"SKLEP: {mp.SKLEP!r}")
oczekuj(mp.LOKALNIE is False, "LOKALNIE powinno być False (Morele odpowiada też z chmury)")
oczekuj(isinstance(mp.SKLEP_UWAGI, str) and "lista_monitorow = []" in mp.SKLEP_UWAGI,
        "SKLEP_UWAGI nie mówi, że monitory zwraca nowe_monitory.py")


def nie_wolno_wolac(url):
    raise AssertionError(f"lista_monitorow nie może pobierać stron (próba: {url})")


oczekuj(mp.lista_monitorow(nie_wolno_wolac) == [], "lista_monitorow powinna zwracać []")
try:
    mp.odczytaj_monitor("https://www.morele.net/monitor-x-1234567/", "<html></html>")
    oczekuj(False, "odczytaj_monitor powinno rzucać BrakDanych (monitory: nowe_monitory.py)")
except BrakDanych as x:
    oczekuj("nowe_monitory" in str(x), f"odczytaj_monitor: komunikat {x}")

# 2. karty do przyjęcia
KLUCZE_PC = {"nazwa", "url", "cpu", "gpu", "ram", "storage", "psu", "cena_bazowa", "system", "dostepny",
             "sprzedawca", "zdjecie", "ean"}
przyjete = {}
for k in ("legion_amd", "legion_intel", "artrel", "error", "rx9070xt"):
    try:
        przyjete[k] = mp.odczytaj_pc(ADRES[k], czytaj(PLIK[k]))
    except BrakDanych as x:
        oczekuj(False, f"{k}: powinno być przyjęte, a jest odrzucone: {x}")
for k, d in przyjete.items():
    oczekuj(KLUCZE_PC <= set(d), f"{k}: brak kluczy kontraktu {sorted(KLUCZE_PC - set(d))}")
    oczekuj(isinstance(d["cena_bazowa"], int) and 1500 <= d["cena_bazowa"] <= 60000, f"{k}: cena {d['cena_bazowa']!r}")
    oczekuj(d["dostepny"] is True and d["url"] == ADRES[k], f"{k}: dostepny/url")
    oczekuj(set(d["system"]) == {"w_cenie", "doplata", "nazwa"} and d["system"]["doplata"] is None, f"{k}: system {d['system']}")
    oczekuj(d["zdjecie"].startswith("https://images.morele.net/"), f"{k}: zdjęcie {d['zdjecie']!r}")
    oczekuj(re.fullmatch(r"\d{1,3}GB DDR5( \d{4}MHz)?", d["ram"]), f"{k}: ram {d['ram']!r}")
    oczekuj(re.fullmatch(r"\d+(TB|GB) SSD", d["storage"]), f"{k}: storage {d['storage']!r}")
    oczekuj(re.fullmatch(r"\d{3,4}W", d["psu"]), f"{k}: psu {d['psu']!r}")
    oczekuj(d["opcje"] == {} and d["kod_rabatowy"] is None, f"{k}: opcje/kod_rabatowy")
    try:                                                   # integrator policzy z tego oceny — muszą się dać policzyć
        ocena_pc.klasa_gpu(d["gpu"]); ocena_pc.klasa_cpu(d["cpu"]); ocena_pc.pamiec_gpu_gb(d["gpu"])
        sc = ocena_pc.oceny(d["cpu"], d["gpu"], d["ram"], d["storage"], d["psu"], d["system"]["nazwa"] or "", 1)
        oczekuj(all(1 <= sc[x] <= 100 for x in ("perf", "components", "features")), f"{k}: oceny {sc}")
    except BrakDanych as x:
        oczekuj(False, f"{k}: ocena_pc nie umie policzyć ocen z wyniku adaptera: {x}")

a = przyjete.get("legion_amd", {})
oczekuj(a.get("cpu") == "Ryzen 5 7600" and a.get("gpu") == "NVIDIA GeForce RTX 5060 Ti 8GB", f"legion_amd: cpu/gpu {a.get('cpu')} / {a.get('gpu')}")
oczekuj(a.get("ram") == "32GB DDR5 5600MHz" and a.get("storage") == "1TB SSD" and a.get("psu") == "500W", f"legion_amd: ram/dysk/psu")
oczekuj(a.get("cena_bazowa") == 6999 and a.get("sprzedawca") is None, f"legion_amd: cena/sprzedawca {a.get('cena_bazowa')} {a.get('sprzedawca')}")
oczekuj(a.get("system") == {"w_cenie": False, "doplata": None, "nazwa": "Bez systemu operacyjnego"}, f"legion_amd: system {a.get('system')}")
oczekuj(a.get("ean") == "199271422762" and a.get("kod_modelu") == "90YJ005GPL", f"legion_amd: ean/kod {a.get('ean')} {a.get('kod_modelu')}")

i = przyjete.get("legion_intel", {})
oczekuj(i.get("cpu") == "Intel Core Ultra 5 225" and ocena_pc.klasa_cpu(i.get("cpu", "")) == 5, f"legion_intel: cpu {i.get('cpu')}")
oczekuj(i.get("system") == {"w_cenie": True, "doplata": None, "nazwa": "Windows 11 Home"}, f"legion_intel: system {i.get('system')}")

# marketplace: JSON-LD mówi „seller: Morele.net Sp. z o.o.”, prawdziwego sprzedawcę podaje blok sprzedawcy na stronie
oczekuj('"name":"Morele.net Sp. z o.o."' in czytaj(PLIK["artrel"]), "fixture Artrel powinien mieć w JSON-LD fałszywego sprzedawcę Morele (pułapka)")
oczekuj(przyjete.get("artrel", {}).get("sprzedawca") == "Artrel", f"artrel: sprzedawca {przyjete.get('artrel', {}).get('sprzedawca')!r}")
oczekuj(przyjete.get("error", {}).get("sprzedawca") == "ERROR", f"error: sprzedawca {przyjete.get('error', {}).get('sprzedawca')!r}")
# dwa pola dysku z tą samą pojemnością przy tytule „1TB” = jeden dysk, nie dwa
oczekuj(przyjete.get("artrel", {}).get("storage") == "1TB SSD", f"artrel: dysk {przyjete.get('artrel', {}).get('storage')!r} (dwa pola po 1 TB, tytuł 1TB)")
oczekuj(przyjete.get("artrel", {}).get("system", {}).get("nazwa") == "Windows 11 Pro", "artrel: system")
oczekuj(przyjete.get("artrel", {}).get("ean") is None and przyjete.get("error", {}).get("kod_modelu") is None,
        "marketplace: brak EAN/kodu → None, a nie śmieć („ERROR GAMING PC” to nie kod modelu)")
r = przyjete.get("rx9070xt", {})
oczekuj(r.get("gpu") == "AMD Radeon RX 9070 XT 16GB", f"rx9070xt: gpu {r.get('gpu')!r}")

# zapis karty identyczny z nowe_pc.gpu_kanoniczna (tej samej użyje reszta serwisu)
oczekuj(nowe_pc.gpu_kanoniczna("RTX 5060 Ti", {"Pamięć karty graficznej": "8 GB"}) == a.get("gpu"), "gpu ≠ nowe_pc.gpu_kanoniczna (NVIDIA)")
oczekuj(nowe_pc.gpu_kanoniczna("Radeon RX 9070 XT", {"Pamięć karty graficznej": "16 GB"}) == r.get("gpu"), "gpu ≠ nowe_pc.gpu_kanoniczna (AMD)")

# 3. odrzucenia: prawdziwe karty
odrzucone("DDR4", ADRES["ddr4"], czytaj(PLIK["ddr4"]), "nie jest DDR5")
odrzucone("karta zintegrowana", ADRES["biuro"], czytaj(PLIK["biuro"]), "karta spoza zakresu")
odrzucone("sprzeczność tytuł/specyfikacja", ADRES["quickpc"], czytaj(PLIK["quickpc"]), "sprzeczne")
# warianty wyprowadzone z prawdziwej karty (jedna zmiana na wariant)
baza = czytaj(PLIK["legion_amd"])
odrzucone("brak w sprzedaży", ADRES["legion_amd"], zamien(baza, "https://schema.org/InStock", "https://schema.org/OutOfStock"), "nie ma w sprzedaży")
odrzucone("brak ceny", ADRES["legion_amd"], zamien(baza, '"price":6999', '"price":"brak"'), "brak ceny")
odrzucone("brak dysku", ADRES["legion_amd"], zamien(baza, '"name":"Pojemność dysku SSD M.2 PCIe","value":"1 TB"', '"name":"Pojemność dysku SSD M.2 PCIe","value":"Brak"'), "brak dysku")
odrzucone("brak mocy zasilacza", ADRES["legion_amd"], zamien(baza, '"name":"Moc","value":"500 W"', '"name":"Moc","value":"Brak danych"'), "Moc")
odrzucone("DDR4 w specyfikacji", ADRES["legion_amd"], zamien(baza, '"name":"Typ pamięci RAM","value":"DDR5"', '"name":"Typ pamięci RAM","value":"DDR4"'), "nie jest DDR5")
odrzucone("nieznany procesor", ADRES["legion_amd"], zamien(baza, "Ryzen 5 7600", "Athlon 3000G"), "bez reguły klasy")
odrzucone("procesor ≠ tytuł", ADRES["legion_amd"], zamien(baza, '"name":"Model procesora","value":"Ryzen 5 7600"', '"name":"Model procesora","value":"Ryzen 5 7600X"'), "procesor w specyfikacji")
odrzucone("pamięć karty ≠ tytuł", ADRES["legion_amd"], zamien(baza, "RTX 5060 Ti, 1 TB", "RTX 5060 Ti 16GB, 1 TB"), "pamięć karty")
odrzucone("dysk w tytule ≠ specyfikacja", ADRES["legion_amd"], zamien(baza, "1 TB M.2 PCIe", "2 TB M.2 PCIe"), "dysk w tytule")
odrzucone("inny produkt pod tym adresem", ADRES["legion_amd"].replace("15413990", "15413999"), baza, "innego produktu")
odrzucone("bez sprzedawcy", ADRES["legion_amd"], zamien(baza, 'data-testid="merchant-name"', 'data-x="y"'), "sprzedawc")
odrzucone("strona bez produktu", ADRES["legion_amd"], "<html><body>pusto</body></html>", "bez danych produktu")
odrzucone("model karty spoza słownika (RX 7600 XT ≠ RX 7600)", ADRES["rx9070xt"],
          zamien(czytaj(PLIK["rx9070xt"]), "Radeon RX 9070 XT", "Radeon RX 7600 XT"), "słownika")

target_name = ':"15413990","name":"Komputer Lenovo Legion T5 30AGB10, Ryzen 5 7600, 32 GB, RTX 5060 Ti, 1 TB M.2 PCIe"'

# defekt 4: pole name w JSON-LD inne niż tekst (null, int) → BrakDanych, nie TypeError
odrzucone("name w JSON-LD równe null", ADRES["legion_amd"],
          zamien(baza, target_name, ':"15413990","name":null'), "brak nazwy")
d_int = mp.odczytaj_pc(ADRES["legion_amd"], zamien(baza, target_name, ':"15413990","name":12345'))
oczekuj(d_int["nazwa"] == "12345", "name jako int w JSON-LD powinno zostać obsłużone bez błędu")

# defekt 5: sprzeczność RAM między tytułem a specyfikacją
baza_ram_ddr4 = zamien(baza, target_name,
                       ':"15413990","name":"Komputer Lenovo Legion T5 30AGB10, Ryzen 5 7600, 32 GB DDR4, RTX 5060 Ti, 1 TB M.2 PCIe"')
odrzucone("tytuł z DDR4 przy specyfikacji DDR5", ADRES["legion_amd"], baza_ram_ddr4, "DDR4")
baza_ram_rozny = zamien(baza, target_name,
                        ':"15413990","name":"Komputer Lenovo Legion T5 30AGB10, Ryzen 5 7600, 16 GB, RTX 5060 Ti, 1 TB M.2 PCIe"')
odrzucone("pojemność RAM w tytule różna od specyfikacji", ADRES["legion_amd"], baza_ram_rozny, "pamięć RAM w tytule")

# defekt 6: komunikaty o przyczynie przejściowej lub zmianie układu zawierają słowo 'niedostęp'
odrzucone("bez sprzedawcy zawiera niedostęp", ADRES["legion_amd"],
          zamien(baza, 'data-testid="merchant-name"', 'data-x="y"'), "niedostęp")
odrzucone("strona bez produktu zawiera niedostęp", ADRES["legion_amd"],
          "<html><body>pusto</body></html>", "niedostęp")

# defekt 7: mutacje odczytu karty
odrzucone("dwa różne pola Moc", ADRES["legion_amd"],
          zamien(baza, '"name":"Moc","value":"500 W"', '"name":"Moc","value":"500 W"},{"@type":"PropertyValue","name":"Moc","value":"650 W"'),
          "dwa razy z różnymi wartościami")
odrzucone("Moc 0.75 kW", ADRES["legion_amd"],
          zamien(baza, '"name":"Moc","value":"500 W"', '"name":"Moc","value":"0.75 kW"'),
          "nieczytelna moc zasilacza")
odrzucone("nieczytelna pojemność RAM", ADRES["legion_amd"],
          zamien(baza, '"name":"Wielkość pamięci RAM","value":"32 GB"', '"name":"Wielkość pamięci RAM","value":"dużo"'),
          "nieczytelna pojemność RAM")
odrzucone("cena poniżej 1500 zł", ADRES["legion_amd"],
          zamien(baza, '"price":6999', '"price":1499'), "poza wiarygodnym zakresem")
odrzucone("cena powyżej 60000 zł", ADRES["legion_amd"],
          zamien(baza, '"price":6999', '"price":60001'), "poza wiarygodnym zakresem")
baza_bez_dysku = zamien(baza, ", 1 TB M.2 PCIe", "")
baza_dwa_dyski = zamien(baza_bez_dysku, '"name":"Pojemność dysku SSD","value":"Brak"',
                        '"name":"Pojemność dysku SSD SATA","value":"512 GB"')
odrzucone("dwa różne pola dysku bez dysku w tytule", ADRES["legion_amd"], baza_dwa_dyski, "nie wiem, ile jest dysków")
idx_img = baza.find('"image":[')
idx_img_end = baza.find(']', idx_img)
baza_img_array = baza[idx_img:idx_img_end+1]
baza_bez_img = zamien(baza, baza_img_array, '"image":[]')
odrzucone("brak zdjęcia w JSON-LD i og:image", ADRES["legion_amd"], baza_bez_img, "brak zdjęcia")

# 4. cena bez kodu rabatowego; znacznik kodu to prawdziwy fragment promo_morele_kod.html
# (JSON-LD ma cenę Z KODEM 1499 zł, strona: „cena bez kodu: 1 569 zł”, kod BLACK26)
znacznik = czytaj("promo_morele_kod")
oczekuj("BLACK26" in znacznik and "1 569" in znacznik, "promo_morele_kod.html nie ma oczekiwanego znacznika kodu")
z_kodem = zamien(baza, '"price":6999', '"price":1499') + "\n" + znacznik
try:
    d = mp.odczytaj_pc(ADRES["legion_amd"], z_kodem)
    oczekuj(d["cena_bazowa"] == 1569, f"z kodem: cena_bazowa {d['cena_bazowa']} (ma być cena BEZ kodu 1569)")
    oczekuj(d["kod_rabatowy"] == "BLACK26" and d["cena_z_kodem"] == 1499, f"z kodem: {d['kod_rabatowy']} {d['cena_z_kodem']}")
    oczekuj(d["promo"] and d["promo"]["bk"] == 1569, f"z kodem: promo {d['promo']}")
except BrakDanych as x:
    oczekuj(False, f"z kodem: karta powinna być przyjęta, a jest odrzucona: {x}")
odrzucone("cena bez kodu niższa od ceny z kodu", ADRES["legion_amd"], baza + "\n" + znacznik, "niższa")
bez_ceny_bk = z_kodem.replace('data-testid="product-regular-price"', 'data-x="y"')
odrzucone("kod bez ceny bez kodu", ADRES["legion_amd"], bez_ceny_bk, "nie podaje ceny bez kodu")

# 5. lista
BAZA_URL = "https://www.morele.net/kategoria/komputery-stacjonarne-672/4500,10000,,,,,,,0,,,,33381O1976356,43184O1607461/1/"
CHIP = "https://www.morele.net/kategoria/komputery-stacjonarne-672/4500,10000,,,,,,,0,,,,30537O{id},33381O1976356,43184O1607461/{p}/"
STRONY = {BAZA_URL: czytaj("morele_pc_lista_baza"),
          CHIP.format(id=2166453, p=1): czytaj("morele_pc_lista_rtx4060"),
          CHIP.format(id=2257434, p=1): czytaj("morele_pc_lista_rtx5060ti"),
          # sklep przekierowuje stronę poza ostatnią na pierwszą (sprawdzone na żywo 30.10.2026)
          CHIP.format(id=2257434, p=2): czytaj("morele_pc_lista_rtx5060ti")}


class Atrapa:
    def __init__(self):
        self.zapytania = []

    def __call__(self, url):
        self.zapytania.append(url)
        return (200, STRONY[url]) if url in STRONY else (404, "")


def elementy_listy(nazwa):
    wynik = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', czytaj(nazwa), re.S):
        d = json.loads(m.group(1))
        if isinstance(d, dict) and d.get("@type") == "ItemList":
            wynik += [(e["item"]["url"], float(e["item"]["offers"]["price"])) for e in d["itemListElement"]]
    return wynik


oczekuj({f[2] for f in mp.chipsety_z_listy(STRONY[BAZA_URL])} == {
    "Radeon RX 7600", "Radeon RX 9060 XT", "Radeon RX 9070", "Radeon RX 9070 XT", "RTX 4060", "RTX 5050",
    "RTX 5060", "RTX 5060 Ti", "RTX 5060 Ti 8GB", "RTX 5060 Ti 16GB", "RTX 5070"},
    f"fasety chipsetu: {sorted(f[2] for f in mp.chipsety_z_listy(STRONY[BAZA_URL]))}")
oczekuj({(f[0], f[1]) for f in mp.chipsety_z_listy(STRONY[BAZA_URL]) if f[2] == "RTX 5060 Ti"} == {(30537, 2257434)},
        "faseta RTX 5060 Ti: grupa/id")
for etykieta, ma in (("RTX 5060 Ti 16GB", "rtx 5060 ti"), ("Radeon RX 9060 XT", "rx 9060 xt"), ("RX 7600 XT", None),
                     ("RTX 4060 Ti", None), ("AMD", None), ("Brak danych", None), ("Radeon RX 580", None)):
    oczekuj(mp.klucz_chipu(etykieta) == ma, f"klucz_chipu({etykieta!r}) = {mp.klucz_chipu(etykieta)!r}, miało być {ma!r}")

a1 = Atrapa()
uwagi = []
try:
    wynik = mp.lista_pc(a1, maks_stron=3, chipsety=("RTX 4060", "rtx 5060 ti"), uwagi=uwagi)
except BrakDanych as x:
    wynik = []
    oczekuj(False, f"lista_pc rzuciła BrakDanych na zapisanych stronach: {x}")
oczekuj(a1.zapytania == [BAZA_URL, CHIP.format(id=2166453, p=1), CHIP.format(id=2257434, p=1),
                         CHIP.format(id=2257434, p=2)],
        f"zapytania listy: {a1.zapytania}")
oczekuj(uwagi == [], f"uwagi listy: {uwagi}")
oczekuj(len(wynik) == len(set(wynik)), "lista ma duplikaty")
oczekuj(all(mp.adres_produktu(u) for u in wynik), "lista ma adres, który nie jest kartą produktu")
oczekuj(wynik[:1] == [ADRES["quickpc"]], f"pierwszy adres (chipset RTX 4060): {wynik[:1]}")
# cztery z naszych kart są na zapisanej stronie 1 chipsetu RTX 5060 Ti — i każda z nich naprawdę ma tę kartę
for k in ("legion_amd", "legion_intel", "artrel", "error"):
    oczekuj(ADRES[k] in wynik, f"lista RTX 5060 Ti nie zawiera karty {k}")
    oczekuj(k in przyjete and przyjete[k]["gpu"].startswith("NVIDIA GeForce RTX 5060 Ti "),
            f"{k}: karta z listy chipsetu RTX 5060 Ti ma w karcie produktu inną kartę")
# liczba adresów = oferty z obu fixtur w oknie cen, bez DDR4 — policzona niezależnie od parsera adaptera
oczekuj_n = sum(1 for _, c in elementy_listy("morele_pc_lista_rtx4060") + elementy_listy("morele_pc_lista_rtx5060ti")
                if 4500 <= c <= 10000)
oczekuj(len(wynik) == oczekuj_n, f"liczba adresów {len(wynik)} ≠ ofert w oknie cen {oczekuj_n}")

a2 = Atrapa()
mp.lista_pc(a2, maks_stron=1, chipsety=("RTX 5060 Ti",))
oczekuj(a2.zapytania == [BAZA_URL, CHIP.format(id=2257434, p=1)], f"maks_stron=1: {a2.zapytania}")
a3 = Atrapa()
mp.lista_pc(a3, maks_stron=1, strona_od=2, chipsety=("RTX 5060 Ti",))
oczekuj(a3.zapytania == [BAZA_URL, CHIP.format(id=2257434, p=2)], f"strona_od=2: {a3.zapytania}")
a4 = Atrapa()
mp.lista_pc(a4, maks_stron=1, strona_od=2, chipsety=("RTX 4060",))
oczekuj(a4.zapytania == [BAZA_URL], f"chipset z 1 ofertą nie ma strony 2, a pobrano: {a4.zapytania}")

# bez zawężenia: chipsety bez zapisanej strony zwracają 404 → lista częściowa i uwagi, bez wyjątku
a5, uwagi5 = Atrapa(), []
pelna = mp.lista_pc(a5, maks_stron=1, uwagi=uwagi5)
oczekuj(set(wynik) <= set(pelna) and len(uwagi5) >= 1 and all(u.startswith("HTTP 404") for u in uwagi5),
        f"lista bez zawężenia: {len(pelna)} adresów, uwagi {uwagi5[:2]}")
oczekuj(len(a5.zapytania) == 1 + len(mp.chipsety_z_listy(STRONY[BAZA_URL])), f"liczba zapytań bez zawężenia: {len(a5.zapytania)}")
# cały katalog nie przekroczy sufitu żądań: baza + (liczba chipsetów × maks_stron)
oczekuj(len(a5.zapytania) <= 1 + 11 * 1, f"za dużo zapytań: {len(a5.zapytania)}")

# pierwsza strona niedostępna → BrakDanych (jak lista_morele), nie pusta lista udająca „nic nowego”
for kod, fragment in ((403, "HTTP 403"), (None, "HTTP None")):
    try:
        mp.lista_pc(lambda u, k=kod: (k, ""), maks_stron=1)
        oczekuj(False, f"lista przy kodzie {kod} powinna rzucić BrakDanych")
    except BrakDanych as x:
        oczekuj(fragment in str(x), f"lista przy kodzie {kod}: {x}")
try:
    mp.lista_pc(lambda u: (200, "<html>inny układ strony</html>"), maks_stron=1)
    oczekuj(False, "lista ze zmienionym układem powinna rzucić BrakDanych")
except BrakDanych as x:
    oczekuj("układ" in str(x), f"lista ze zmienionym układem: {x}")
try:
    mp.lista_pc(Atrapa(), maks_stron=1, wolno=lambda u: False)
    oczekuj(False, "robots.txt zabrania → BrakDanych")
except BrakDanych as x:
    oczekuj("robots" in str(x), f"robots: {x}")
a6, uwagi6 = Atrapa(), []
mp.lista_pc(a6, maks_stron=1, chipsety=("RTX 5060 Ti",), wolno=lambda u: "30537O" not in u, uwagi=uwagi6)
oczekuj(len(uwagi6) == 1 and "robots" in uwagi6[0] and a6.zapytania == [BAZA_URL], f"robots dla chipsetu: {uwagi6} {a6.zapytania}")

# defekt 7: lista z pozycją DDR4 i ceną poza oknem (ma jej nie zwrócić)
chip4060 = czytaj("morele_pc_lista_rtx4060")
dodatek_listy = """},
    {
      "@type": "ListItem",
      "position": 2,
      "item": {
        "@type": "Product",
        "name": "Komputer DDR4 16GB RTX 4060",
        "url": "https://www.morele.net/komputer-ddr4-11111111/",
        "offers": { "@type": "Offer", "price": 6000.00 }
      }
    },
    {
      "@type": "ListItem",
      "position": 3,
      "item": {
        "@type": "Product",
        "name": "Komputer Tani RTX 4060",
        "url": "https://www.morele.net/komputer-tani-22222222/",
        "offers": { "@type": "Offer", "price": 4000.00 }
      }
    },
    {
      "@type": "ListItem",
      "position": 4,
      "item": {
        "@type": "Product",
        "name": "Komputer Drogi RTX 4060",
        "url": "https://www.morele.net/komputer-drogi-33333333/",
        "offers": { "@type": "Offer", "price": 11000.00 }
      }
    """
chip4060_mod = chip4060.replace("}\n  ]", dodatek_listy + "}\n  ]")
atrapa_filtry = Atrapa()
atrapa_filtry_pobierz = lambda u: (200, chip4060_mod) if "30537O2166453" in u else atrapa_filtry(u)
wynik_filtry = mp.lista_pc(atrapa_filtry_pobierz, maks_stron=1, chipsety=("RTX 4060",))
oczekuj("https://www.morele.net/komputer-quickpc-ryzen-7-8700f-32gb-rtx-5060-1tb-m-2-pcie-15050316/" in wynik_filtry,
        "lista: poprawna oferta RTX 4060 powinna zostać zwrócona")
oczekuj("https://www.morele.net/komputer-ddr4-11111111/" not in wynik_filtry,
        "lista: pozycja z DDR4 nie powinna zostać zwrócona")
oczekuj("https://www.morele.net/komputer-tani-22222222/" not in wynik_filtry,
        "lista: oferta poniżej okna cen (4000 zł) nie powinna zostać zwrócona")
oczekuj("https://www.morele.net/komputer-drogi-33333333/" not in wynik_filtry,
        "lista: oferta powyżej okna cen (11000 zł) nie powinna zostać zwrócona")

# defekt 7: maks_stron=999 (zapytań nie więcej niż STRON_SUFIT na chipset)
baza_sufit = STRONY[BAZA_URL].replace('data-count="493"', 'data-count="9999"')
chip1_sufit = czytaj("morele_pc_lista_rtx5060ti")
zapytania_sufit = []
def atrapa_sufit(u):
    zapytania_sufit.append(u)
    if u == BAZA_URL:
        return (200, baza_sufit)
    m = re.search(r"/(\d+)/$", u)
    p = int(m.group(1)) if m else 1
    s = re.sub(r"-\d{6,9}/", lambda _: f"-{p:02d}123456/", chip1_sufit)
    return (200, s)

mp.lista_pc(atrapa_sufit, maks_stron=999, chipsety=("RTX 5060 Ti",))
chipset_reqs = [u for u in zapytania_sufit if u != BAZA_URL]
oczekuj(len(chipset_reqs) == mp.STRON_SUFIT,
        f"maks_stron=999 powinno ograniczyć zapytania do STRON_SUFIT ({mp.STRON_SUFIT}), a było: {len(chipset_reqs)}")

# defekt 7: faseta z data-count=0
baza_count0 = STRONY[BAZA_URL].replace('data-count="493"', 'data-count="0"')
etykiety_count0 = {f[2] for f in mp.chipsety_z_listy(baza_count0)}
oczekuj("RTX 5060 Ti" not in etykiety_count0, "faseta z data-count=0 powinna zostać pominięta")


# 6. zgodność z robots.txt zapisanym w dniu rozpoznania (reguły grupy „User-agent: *”, z gwiazdkami)
def reguly_zakazu(tekst):
    reguly, w_grupie = [], False
    for linia in tekst.splitlines():
        linia = linia.split("#")[0].strip()
        if not linia:
            continue
        pole_, _, wartosc = linia.partition(":")
        pole_, wartosc = pole_.strip().lower(), wartosc.strip()
        if pole_ == "user-agent":
            w_grupie = wartosc == "*"
        elif w_grupie and pole_ == "disallow" and wartosc:
            reguly.append(re.compile("^" + re.escape(wartosc).replace(r"\*", ".*")))
    return reguly


def dozwolony(url, reguly):
    sciezka = re.sub(r"^https://www\.morele\.net", "", url)
    return not any(r.search(sciezka) for r in reguly)


ZAKAZY = reguly_zakazu(czytaj("morele_pc_robots", ".txt"))
oczekuj(len(ZAKAZY) >= 20, f"robots.txt: wczytano {len(ZAKAZY)} reguł zakazu")
oczekuj(not dozwolony("https://www.morele.net/kategoria/komputery-stacjonarne-672/,,,,,,,,0,,,,sprzedawca:1/1/", ZAKAZY),
        "kontrola testu: adres z filtrem „sprzedawca:” powinien być zabroniony")
oczekuj(not dozwolony("https://www.morele.net/wyszukiwarka/?q=pc", ZAKAZY), "kontrola testu: /wyszukiwarka/ powinna być zabroniona")
uzyte = set(a1.zapytania) | set(a5.zapytania) | set(wynik) | set(ADRES.values())
oczekuj(len(uzyte) > 30, f"za mało adresów do sprawdzenia robots: {len(uzyte)}")
zakazane = [u for u in uzyte if not dozwolony(u, ZAKAZY)]
oczekuj(not zakazane, f"adresy zabronione przez robots.txt: {zakazane[:3]}")

# 7. założenie parsera: „Moc” = zasilacz (grupa „Zasilacz” w tabeli specyfikacji HTML), w każdej przyjętej karcie
for k in przyjete:
    s = czytaj(PLIK[k])
    tabele = re.findall(r'<caption class="group__name">(.*?)</caption>(.*?)</table>', s, re.S)
    grupa_mocy = [cap.strip() for cap, cialo in tabele
                  if "Moc" in [re.sub(r"<[^>]+>|\s+", " ", n).strip()
                               for n in re.findall(r'specification__name-content">(.*?)</div></th>', cialo, re.S)]]
    oczekuj(grupa_mocy == ["Zasilacz"], f"{k}: pole „Moc” leży w grupach {grupa_mocy}, nie w „Zasilacz”")

# 8. nakładka zrodla/morele.py (monitory: kod_modelu z mpn, robots.txt w lista_monitorow)
from zrodla import morele as mm
import zbieraj_ceny

dm = mm.odczytaj_monitor(
    "https://www.morele.net/monitor-asus-rog-strix-woled-xg27aqdmgr-90lm0cc0-b01171-15625114/",
    czytaj("morele_asus_xg27aqdmgr"),
)
oczekuj(dm.get("kod_modelu") == "90LM0CC0-B01171",
        f"odczytaj_monitor kod_modelu: {dm.get('kod_modelu')!r}")
dm_brak = mm.odczytaj_monitor(
    "https://www.morele.net/monitor-asus-rog-strix-woled-xg27aqdmgr-90lm0cc0-b01171-15625114/",
    zamien(czytaj("morele_asus_xg27aqdmgr"), '"mpn":"90LM0CC0-B01171"', '"mpn":""'),
)
oczekuj(dm_brak.get("kod_modelu") is None,
        f"odczytaj_monitor bez mpn ma dać None: {dm_brak.get('kod_modelu')!r}")

stary_wolno = zbieraj_ceny.REGULAMIN.wolno
try:
    zbieraj_ceny.REGULAMIN.wolno = lambda u: False
    res_mon = mm.lista_monitorow(nie_wolno_wolac)
    oczekuj(res_mon == [], f"lista_monitorow przy robots False ma zwrócić []: {res_mon}")
finally:
    zbieraj_ceny.REGULAMIN.wolno = stary_wolno

print("\nTEST ZALICZONY" if not bledy else f"\nTEST NIEZALICZONY: {len(bledy)} błędów")
sys.exit(1 if bledy else 0)
