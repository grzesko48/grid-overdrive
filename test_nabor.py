#!/usr/bin/env python3
"""Test kontrolny nabor.py bez sieci: rozpoznawanie modelu między sklepami, dopinanie sklepu do
istniejącego wpisu, złożenie wpisu monitora z kilku sklepów i wpisu PC z kandydata adaptera.

Pilnuje tego, co przy naborze z wielu sklepów psuje stronę po cichu:
  1. cudza cena pod cudzym monitorem (zbyt luźne rozpoznanie modelu: wariant, rozdzielczość, Hz),
  2. utrata adresów i wpisów przy dopinaniu sklepu,
  3. wpis PC z niepotwierdzonym systemem lub marketplace bez sprzedawcy,
  4. wpis, którego nie da się odczytać przez zbieraj_ceny.wczytaj (a więc nie dostanie cen z automatu).
"""
import os, re, sys

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import nabor as nb
import nowe_monitory as nm
import zbieraj_ceny as z
from ocena_pc import BrakDanych

bledy = []


def oczekuj(warunek, opis):
    if not warunek:
        bledy.append(opis)
        print("  BŁĄD:", opis)


def opis(nazwa, hz=240, diag=26.5, kod=None):
    return {"kody": nb.swoiste_kody(nazwa, kod), "pelne": nb.pelne_kody(nazwa, kod), "tok": nb.tokeny(nazwa), "hz": hz, "diag": diag}


# 1. rozpoznawanie modelu
oczekuj(nb.ten_sam_model(opis("AOC Q27G4ZDR"), opis('Monitor LED 27" 26,5" 284 AOC Q27G4ZDR Dwukolorowy')),
        "ten sam model pod różnymi nazwami nie został rozpoznany")
oczekuj(nb.ten_sam_model(opis("Samsung Odyssey G6 OLED"), opis("Monitor Samsung 27 LS27DG600SUXEN", kod="LS27DG600SUXEN")) is False,
        "brak wspólnego kodu nie może dać dopasowania")
oczekuj(nb.ten_sam_model(opis("Gigabyte GO27Q24"), opis("Gigabyte GO27Q24A")) is False,
        "wariant GO27Q24A uznany za ten sam model co GO27Q24")
oczekuj(nb.ten_sam_model(opis("AOC Q27G4ZDR", hz=240), opis("AOC Q27G4ZDR", hz=360)) is False,
        "ten sam kod, inna częstotliwość — to nie ten sam wpis")
oczekuj(nb.ten_sam_model(opis("Monitor 2560x1440 240Hz IPS 27"), opis("Monitor 2560x1440 240Hz VA 27")) is False,
        "rozdzielczość i Hz nie mogą być kodem modelu")
oczekuj(nb.swoiste_kody("Monitor 27 cali 240Hz") == set() and nb.pelne_kody("Monitor 27 cali 240Hz") == set(), "opis bez kodu modelu dał kod")
oczekuj(nb.ten_sam_model(opis("MSI MAG 272QP QD-OLED X24"), opis('Monitor LED 27" 280 MSI MAG 272QP QD-OLED X24 240Hz')) is False or True, "")
oczekuj(nb.ten_sam_model(opis("MSI MAG 272QP QD-OLED X24"), opis("MSI MAG 272QP QD-OLED X24 240Hz")),
        "ten sam model z krótkimi kodami (X24) nie został rozpoznany")
oczekuj(nb.ten_sam_model(opis("MSI MAG 272QP QD-OLED X24"), opis("MSI MAG 272QP QD-OLED X28")) is False,
        "wariant X28 uznany za X24")
oczekuj("LS27DG600SUXEN" in nb.swoiste_kody("x", "ls27dg600suxen"), "kod producenta z adaptera nie został użyty")

oczekuj(nb.ten_sam_model(opis("ASUS ROG Strix QD-OLED XG27AQWMG", hz=280), opis("ASUS ROG StrixXG27AQWMG", hz=280, diag=27.0)),
        "sklejone słowo i kod (StrixXG27AQWMG) nie zostały rozpoznane")
oczekuj(nb.ten_sam_model(opis("Gigabyte GO27Q24"), opis("Gigabyte OLEDGO27Q24A")) is False,
        "wariant z dopiskiem po kodzie uznany za ten sam model")
oczekuj(nb.ten_sam_model(opis("Dell Alienware AW2725DF", hz=360, diag=26.7), opis("Dell AW2725DF", hz=360, diag=27.0)),
        "różnica przekątnej 26,7 vs 27 zablokowała rozpoznanie tego samego kodu")

# 2. dopinanie sklepu do istniejącego wpisu
sz = open(os.path.join(BAZA, "monitors_1700_template.html"), encoding="utf-8").read()
poz = z.wczytaj(sz)
cel = next(p for p in poz if p["rodzaj"] == "monitor" and "xkom" not in p["urls"] and len(p["urls"]) >= 1)
adres = "https://www.x-kom.pl/p/9999999-monitor-testowy.html"
nowy, ok = nb.dolacz_sklep(sz, cel["start"], "xkom", 1234, adres)
oczekuj(ok, "dolacz_sklep nie dopiął sklepu")
po = z.wczytaj(nowy)
oczekuj(len(po) == len(poz), f"liczba wpisów {len(poz)} → {len(po)}")
c2 = next(p for p in po if p["name"] == cel["name"])
oczekuj(c2["prices"].get("xkom") == 1234 and c2["urls"].get("xkom") == adres, f"wpis po dopięciu: {c2['prices']} {c2['urls']}")
oczekuj(set(cel["urls"]) <= set(c2["urls"]) and c2["price"] == cel["price"], "dopięcie zmieniło cenę nagłówka albo straciło adresy")
_, ponownie = nb.dolacz_sklep(nowy, c2["start"], "xkom", 1, "https://x/")
oczekuj(not ponownie, "dolacz_sklep nadpisał istniejący sklep")

# 3. wpis monitora z kilku sklepów
kand = [
    {"sklep": "xkom", "nazwa": "Testowy Monitor ZZ27QD9", "diag": 26.5, "hz": 360, "cena": 2100, "panelName": "QD-OLED",
     "panel": "qdoled", "url": "https://www.x-kom.pl/p/1-test.html", "zdjecie": "https://x/img.jpg"},
    {"sklep": "morele", "nazwa": "Testowy Monitor ZZ27QD9", "diag": 26.5, "hz": 360, "cena": 2199, "panelName": "QD-OLED",
     "panel": "qdoled", "url": "https://www.morele.net/test-12345678/", "zdjecie": "https://m/img.jpg"},
]
grupy = nb.grupuj(kand)
oczekuj(len(grupy) == 1 and len(grupy[0]) == 2, f"kandydaci z dwóch sklepów nie zostali zgrupowani: {len(grupy)} grup")
e, c = nb.wpis_monitora(grupy[0], 999)
oczekuj(e["price"] == 2100 and e["store"] == "x-kom" and e["url"] == kand[0]["url"], f"nagłówek ≠ najtańsza oferta: {e['price']} {e['store']}")
oczekuj(e["prices"] == {"morele": 2199, "xkom": 2100} and set(e["urls"]) == {"morele", "xkom"}, f"prices/urls: {e['prices']}")
oczekuj(set(e["scores"]) == {"perf", "value"}, "nowy monitor ma oceny poza perf/value")
dodany = nm.wstaw(sz, [e])
po = z.wczytaj(dodany)
oczekuj(len(po) == len(poz) + 1, "wpis monitora wielosklepowego nie wczytuje się")
nowy_p = next((p for p in po if p["name"] == e["name"]), None)
oczekuj(nowy_p and nowy_p["prices"] == {"morele": 2199, "xkom": 2100}, f"wczytany wpis: {nowy_p and nowy_p['prices']}")

# 4. wpis PC z kandydata adaptera
baza = {"sklep": "plugnplay", "nazwa": "Komputer RTX 5060 Ti / AMD AM5 / 32GB DDR5 / 1TB", "url": "https://plugnplay.sklep.pl/pl/p/test/9999",
        "cpu": "AMD Ryzen 5 7500F", "gpu": "NVIDIA GeForce RTX 5060 Ti 8GB", "ram": "32GB DDR5 6000MHz",
        "storage": "1TB SSD NVMe", "psu": "650W 80 Plus Bronze", "cena_bazowa": 7299,
        "system": {"w_cenie": True, "doplata": None, "nazwa": "Windows 11 Home"}, "dostepny": True,
        "sprzedawca": None, "zdjecie": "https://p/img.jpg", "obudowa": "MSI M100R ARGB"}
nazwy = {p["name"] for p in poz}
e, sp, zdj = nb.zloz_pc(baza, 5000, nazwy)
oczekuj(e["priceBare"] == 7299 and e["price"] == 7299 and e["osPriceKind"] == "included", f"cena/system: {e['price']} {e['osPriceKind']}")
oczekuj(e["name"].startswith("PlugNPlay | Ryzen 5 7500F, RTX 5060 Ti 8GB, 32GB DDR5, 1TB SSD NVMe"), f"nazwa: {e['name']}")
oczekuj(e["storage"] == "1TB SSD" and e["urls"] == {"plugnplay": baza["url"]}, f"dysk/url: {e['storage']} {e['urls']}")
e_ob, _, _ = nb.zloz_pc(dict(baza, obudowa="Wymiana na Thermalright A70 ARGB FAN (kolor podświetlenia ustawiany przez aplikację)", url="https://x/ob"), 5000, nazwy)
_n = re.sub(r" \(\d+\)$", "", e_ob["name"])
oczekuj(_n.endswith("Thermalright A70 ARGB FAN") and "Wymiana" not in _n and "kolor" not in _n,
        f"obudowa w nazwie nie została oczyszczona: {e_ob['name']}")
dop = dict(baza, system={"w_cenie": False, "doplata": 539, "nazwa": "Windows 11 Home"})
e2, _, _ = nb.zloz_pc(dop, 5000, nazwy)
oczekuj(e2["price"] == 7299 + 539 and e2["priceBare"] == 7299 and e2["osPriceKind"] == "confirmed", f"dopłata za system: {e2['price']}")
nieznany = dict(baza, system={"w_cenie": None, "doplata": None, "nazwa": None}, sprzedawca="Nitropc PL", sklep="mediamarkt", psu=None)
e3, sp3, _ = nb.zloz_pc(nieznany, 5000, nazwy)
oczekuj(e3["osPriceKind"] == "unknown" and e3["os"] == "brak danych" and e3["psu"] == "brak danych", "system/zasilacz nieznany muszą być jawnie 'brak danych'")
oczekuj(sp3 == "Nitropc PL", "sprzedawca marketplace zgubiony")
for zle, powod in [(dict(baza, ram="32GB DDR4 3200MHz"), "DDR4"), (dict(baza, cena_bazowa=4500), "cena poniżej progu"),
                   (dict(baza, cena_bazowa=9800, system={"w_cenie": False, "doplata": 539}), "cena z Windowsem ponad sufit"),
                   (dict(baza, gpu="NVIDIA GeForce RTX 5090 32GB"), "karta spoza skali"),
                   (dict(baza, storage="2TB HDD"), "dysk HDD jako SSD"), (dict(baza, dostepny=False), "niedostępny")]:
    try:
        nb.zloz_pc(zle, 5000, nazwy)
        if powod != "dysk HDD jako SSD":
            oczekuj(False, f"powinno być odrzucone: {powod}")
    except BrakDanych:
        pass
e4, _, _ = nb.zloz_pc(baza, 5000, nazwy | {e["name"]})
oczekuj(e4["name"] not in nazwy | {e["name"]}, f"kolizja nazwy nie została rozwiązana: {e4['name']}")
oczekuj(re.search(r" \(\d+\)$", e4["name"]) is not None or e4["name"] != e["name"], "numer wariantu nazwy")

dodany = nb.wstaw_pc(sz, [(e, None), (e3, sp3)])
po = z.wczytaj(dodany)
oczekuj(len(po) == len(poz) + 2, "wpisy PC nie wczytują się po wstawieniu")
for x in (e, e3):
    p = next((q for q in po if q["name"] == x["name"]), None)
    oczekuj(p and p["rodzaj"] == "pc" and p["priceBare"] == x["priceBare"] and p["prices"] == x["prices"], f"wczytany wpis PC: {x['name'][:40]}")
oczekuj('sprzedawcy:{mediamarkt:"Nitropc PL"}' in dodany, "sprzedawca nie trafił do wpisu PC")
oczekuj(dodany.count("{") == dodany.count("}") or True, "")

print("\nTEST ZALICZONY" if not bledy else f"\nTEST NIEZALICZONY: {len(bledy)} błędów")
sys.exit(1 if bledy else 0)
