#!/usr/bin/env python3
"""Test kontrolny zrodla/xkom.py na zapisanych stronach x-kom (bez sieci).

Fixtury (tests_fixtures/xkom_*.html) to prawdziwe strony x-kom pobrane 30.10.2026, ODCHUDZONE o
bloki <style> i <svg> (poza skryptami); dane — ld+json i stan strony — są nietknięte. Sprawdzone
osobno: adapter daje na odchudzonych i na surowych stronach identyczne wyniki (11 z 11).

Sprawdza to, co przy naborze z x-kom może zepsuć stronę po cichu:
  1. monitory: pola z karty (nazwa, przekątna, Hz natywne vs OC, matryca, cena promocyjna,
     zdjęcie, kod producenta) i zgodność kluczy z nowe_monitory.odczytaj;
  2. odrzucenia monitora: za duża przekątna, inna rozdzielczość, brak w sprzedaży, rozjazd ceny,
     karta innego produktu niż w adresie, pusta strona;
  3. lista monitorów: parser stanu strony, przesiew po podsumowaniu cech, stronicowanie przez
     <link rel="next">, limit stron, kod 403 → [] (x-kom z chmury), ekran blokady → BrakDanych;
  4. komputery: cpu/gpu/ram/dysk/zasilacz/cena/system/opcje, zgodność z ocena_pc i
     nowe_pc.gpu_kanoniczna; odrzucenia: wycofany, DDR4, brak dysku, nieznany procesor/karta;
  5. lista komputerów: trzy przebiegi po typie RAM, przesiew po cenie/karcie/procesorze, 403 → [];
  6. robots.txt: kopia reguł pozwala na użyte adresy, zabrania koszyka i konta;
  7. brak sieci: test zamyka gniazda, więc każda próba połączenia to błąd.

Mutacje (oznaczone „zmodyfikowana kopia”) to prawdziwe karty z jednym podmienionym fragmentem —
testują gałęzie odrzuceń, których żywa strona akurat nie pokazuje.
"""
import json, os, socket, sys

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)


import nowe_monitory as nm
import nowe_pc
import ocena_pc
from ocena_pc import BrakDanych
from zrodla import xkom as x


def _zakaz(*a, **k):
    raise RuntimeError("test nie może łączyć się z siecią")


# blokada sieci PO importach (ssl dziedziczy po socket.socket przy imporcie)
socket.socket = _zakaz
socket.create_connection = _zakaz
socket.getaddrinfo = _zakaz

F = os.path.join(BAZA, "tests_fixtures")
bledy = []


def czytaj(n):
    return open(os.path.join(F, n + ".html"), encoding="utf-8").read()


def oczekuj(warunek, opis):
    if not warunek:
        bledy.append(opis)
        print("  BŁĄD:", opis)


def odrzuca(funkcja, fragment, opis, *arg):
    """Wywołanie musi rzucić BrakDanych z `fragment` w komunikacie."""
    try:
        funkcja(*arg)
        oczekuj(False, f"{opis}: powinno być odrzucone")
    except BrakDanych as e:
        oczekuj(fragment in str(e), f"{opis}: powód „{e}” nie zawiera „{fragment}”")


def zmien(html, stare, nowe, po=None):
    """Zmodyfikowana kopia: podmienia JEDNO wystąpienie `stare` (po znaczniku `po`, jeśli podany)."""
    od = html.index(po) if po else 0
    i = html.index(stare, od)
    return html[:i] + nowe + html[i + len(stare):]


U = "https://www.x-kom.pl/p/"
URL = {
    "go27q24a": U + "1542556-monitor-led-27-265-284-gigabyte-go27q24a.html",
    "aoc_q27g4zr": U + "1358598-monitor-led-27-265-284-aoc-q27g4zr.html",
    "xg27aqdmgr": U + "1469778-monitor-led-27-265-284-asus-rog-strix-oled-xg27aqdmgr.html",
    "dell": U + "1577846-monitor-led-32-i-wiekszy-dell-alienware-aw3226dm.html",
    "pg27ucdm": U + "1416572-monitor-led-27-265-284-asus-rog-swift-oled-pg27ucdm.html",
    "legion": U + "1361184-desktop-lenovo-legion-t5-ryzen-5-7600-32gb-1tb-win11x-rtx5070.html",
    "g4m3r": U + "1491049-desktop-g4m3r-hero-20-i5-14400f-32gb-1tb-rtx-5060ti-w11x.html",
    "omen": U + "1367242-desktop-hp-omen-35l-ryzen-5-8400f-32gb-1tb-rtx5060.html",
    "smx": U + "1540864-desktop-smx-battlestation-m3a-i5-14400f-32gb-1tb-rtx5060ti.html",
}

# 0. kontrakt adaptera
oczekuj(x.SKLEP == "xkom", f"SKLEP: {x.SKLEP!r}")
oczekuj(x.LOKALNIE is True, "LOKALNIE musi być True (x-kom odpowiada tylko z komputera właściciela)")
oczekuj(isinstance(x.SKLEP_UWAGI, str) and len(x.SKLEP_UWAGI) > 40, "SKLEP_UWAGI puste")
oczekuj(all(callable(getattr(x, n, None)) for n in
            ("lista_monitorow", "odczytaj_monitor", "lista_pc", "odczytaj_pc")), "brak funkcji kontraktu")
oczekuj((x.HZ_OD, x.HZ_DO, x.DIAG_OD, x.DIAG_DO) == (nm.HZ_OD, nm.HZ_DO, nm.DIAG_OD, nm.DIAG_DO),
        "progi Hz/przekątnej różnią się od nowe_monitory")
oczekuj((x.CENA_MONITORA_OD, x.CENA_MONITORA_DO) == (nm.CENA_OD, nm.CENA_DO),
        "zakres wiarygodnej ceny monitora różni się od nowe_monitory")
oczekuj((x.CENA_LISTY_PC_OD, x.CENA_LISTY_PC_DO) == (nowe_pc.CENA_OD_BEZ_SYSTEMU, nowe_pc.SUFIT_Z_WINDOWS),
        "przesiew cen komputerów różni się od progów nowe_pc")

# 1. monitory: poprawne karty
d = x.odczytaj_monitor(URL["go27q24a"], czytaj("xkom_monitor_go27q24a"))
oczekuj(d["nazwa"] == "Gigabyte GO27Q24A", f"nazwa: {d['nazwa']!r}")
oczekuj((d["hz"], d["diag"], d["cena"]) == (240, 27.0, 1529), f"hz/diag/cena: {d['hz']} {d['diag']} {d['cena']}")
oczekuj((d["panelName"], d["panel"]) == ("QD-OLED", "qdoled"), f"matryca: {d['panelName']}")
oczekuj(d["kod_modelu"] == "GO27Q24A", f"kod modelu: {d['kod_modelu']!r}")
oczekuj(d["zdjecie"].startswith("https://cdn.x-kom.pl/") and "{SEO}" not in d["zdjecie"]
        and d["zdjecie"].endswith(".jpg"), f"zdjęcie: {d['zdjecie']!r}")
klucze_nm = {"nazwa", "url", "hz", "diag", "panelName", "panel", "cena", "zdjecie"}
oczekuj(set(d) == klucze_nm | {"kod_modelu"}, f"klucze monitora: {sorted(d)}")
oczekuj(isinstance(d["hz"], int) and isinstance(d["cena"], int) and isinstance(d["diag"], float),
        "typy hz/cena/diag inne niż w nowe_monitory.odczytaj")

# Hz: natywne 240, OC 260 tylko w nazwie matrycy; cena 759 to cena promocyjna z ld+json (regularna 799)
d = x.odczytaj_monitor(URL["aoc_q27g4zr"], czytaj("xkom_monitor_aoc_q27g4zr"))
oczekuj(d["hz"] == 240, f"Hz natywne, jest {d['hz']}")
oczekuj((d["panelName"], d["panel"]) == ("Fast IPS (260 Hz OC)", "ips"), f"matryca: {d['panelName']}")
oczekuj(d["cena"] == 759, f"cena bieżąca (promocja) z ld+json, jest {d['cena']}")
oczekuj(d.get("cena_bez_kodu") == 799, f"cena bez kodu: {d.get('cena_bez_kodu')}")
oczekuj(d.get("kod_rabatowy") == "black-weeks2", f"kod rabatowy: {d.get('kod_rabatowy')}")
oczekuj(d.get("kod_do") == "2026-11-01T22:59:59Z", f"termin promocji: {d.get('kod_do')}")

d = x.odczytaj_monitor(URL["xg27aqdmgr"], czytaj("xkom_monitor_asus_xg27aqdmgr"))
oczekuj(d["diag"] == 26.5 and d["nazwa"] == "ASUS ROG Strix OLED XG27AQDMGR",
        f"26,5\" / nazwa: {d['diag']} {d['nazwa']!r}")
oczekuj((d["panelName"], d["panel"]) == ("OLED (WOLED)", "oled"), f"WOLED: {d['panelName']}")
oczekuj(d["kod_modelu"] == "90LM0CC0-B01171", f"kod modelu: {d['kod_modelu']!r}")

# 2. odrzucenia monitora
odrzuca(x.odczytaj_monitor, "przekątna", "Dell 31,5\"", URL["dell"], czytaj("xkom_monitor_dell_aw3226dm_za_duzy"))
odrzuca(x.odczytaj_monitor, "rozdzielczość", "PG27UCDM 4K", URL["pg27ucdm"], czytaj("xkom_monitor_asus_pg27ucdm_4k"))
go = czytaj("xkom_monitor_go27q24a")
odrzuca(x.odczytaj_monitor, "nie ma w sprzedaży", "zmodyfikowana kopia: ld+json OutOfStock", URL["go27q24a"],
        zmien(go, '"availability":"http://schema.org/InStock"', '"availability":"http://schema.org/OutOfStock"'))
odrzuca(x.odczytaj_monitor, "nie ma w sprzedaży", "zmodyfikowana kopia: status Unavailable", URL["go27q24a"],
        zmien(go, '"availabilityStatus":"Available"', '"availabilityStatus":"Unavailable"', po='"1542556":{"isFetching"'))
odrzuca(x.odczytaj_monitor, "ceny na stronie się różnią", "zmodyfikowana kopia: cena ld+json 1111",
        URL["go27q24a"], zmien(go, '"price":1529,"itemCondition"', '"price":1111,"itemCondition"'))
odrzuca(x.odczytaj_monitor, "strona niedostępna", "rozjazd cen zawiera niedostępna",
        URL["go27q24a"], zmien(go, '"price":1529,"itemCondition"', '"price":1111,"itemCondition"'))
odrzuca(x.odczytaj_monitor, "adres wskazuje", "karta innego produktu niż w adresie", URL["aoc_q27g4zr"], go)
odrzuca(x.odczytaj_monitor, "strona niedostępna", "karta innego produktu zawiera niedostępna", URL["aoc_q27g4zr"], go)
odrzuca(x.odczytaj_monitor, "pusta strona", "pusty html", URL["go27q24a"], "")
odrzuca(x.odczytaj_monitor, "strona niedostępna", "pusta strona zawiera niedostępna", URL["go27q24a"], "")
odrzuca(x.odczytaj_monitor, "JSON-LD Product", "strona bez ld+json", URL["go27q24a"], "<html><body>Access denied</body></html>")
odrzuca(x.odczytaj_monitor, "strona niedostępna", "brak ld+json zawiera niedostępna", URL["go27q24a"], "<html><body>Access denied</body></html>")
odrzuca(x.odczytaj_monitor, "nie jest kartą produktu", "adres bez /p/<id>-", "https://www.x-kom.pl/g-6/c/15-monitory.html", go)
odrzuca(x.odczytaj_monitor, "brak productID/sku", "brak productID i sku w JSON-LD", URL["go27q24a"],
        zmien(zmien(go, '"productID":"1542556",', ''), '"sku":"1542556",', ''))
odrzuca(x.odczytaj_monitor, "towar nie jest nowy", "itemCondition UsedCondition", URL["go27q24a"],
        zmien(go, '"itemCondition":"http://schema.org/NewCondition"', '"itemCondition":"http://schema.org/UsedCondition"'))
odrzuca(x.odczytaj_monitor, "towar z outletu", "isOutlet True", URL["go27q24a"],
        zmien(go, '"isOutlet":false', '"isOutlet":true', po='"1542556":{"isFetching"'))
# Defekt 2: Hz bez OC w polu, ale w opisie podkręcenie
go_oc_opis = zmien(go, '"name":"240 Hz"', '"name":"280 Hz"', po='"key":"Częstotliwość odświeżania ekranu"')
go_oc_opis = zmien(go_oc_opis, '<div class="content">', '<div class="content"><p>do 280 Hz przy podkręceniu</p>')
odrzuca(x.odczytaj_monitor, "Hz z podkręcenia (OC) bez wartości natywnej", "280 Hz z OC w opisie", URL["go27q24a"], go_oc_opis)

# matryca i Hz — przypadki z żywej listy x-kom
for rodzaj, ekran, dod, oc, oczekiwane in [
    ("LED, Fast IPS", "Płaski", None, 260, ("Fast IPS (260 Hz OC)", "ips")),
    ("LED, IPS Black", "Płaski", None, None, ("IPS Black", "ips")),
    ("LED, Rapid IPS", "Płaski", None, None, ("Rapid IPS", "ips")),
    ("LED, IPS", "Płaski", None, None, ("IPS", "ips")),
    ("WOLED 4. generacji", "Płaski", None, None, ("OLED (WOLED, 4. generacji)", "oled")),
    ("Tandem OLED", "Płaski", None, None, ("OLED (Tandem)", "oled")),
    ("QD-OLED", "Płaski", None, None, ("QD-OLED", "qdoled")),
    ("LED, Rapid VA", "Płaski", None, None, ("Rapid VA", "va")),
    ("LED, VA", "Zakrzywiony", ["Wbudowany HUB USB", "Zakrzywienia ekranu - 1500R"], None,
     ("VA, zakrzywiony 1500R", "va")),
]:
    oczekuj(x.matryca(rodzaj, ekran, dod, oc) == oczekiwane, f"matryca({rodzaj!r}) = {x.matryca(rodzaj, ekran, dod, oc)}")
for zly in ("LED, TN", "Mini LED", "", "LED, IPS, VA"):
    odrzuca(x.matryca, "spoza zakresu", f"matryca {zly!r}", zly, "Płaski", None, None)
oczekuj(x.czestotliwosci(["260 Hz - OC", "240 Hz"]) == (240, 260), "Hz: OC + natywne")
oczekuj(x.czestotliwosci(["240 Hz"]) == (240, None), "Hz: jedna wartość")
odrzuca(x.czestotliwosci, "kilka natywnych wartości Hz — niejednoznaczne", "Hz: dwie natywne", ["144 Hz", "165 Hz"])
odrzuca(x.czestotliwosci, "same wartości OC", "Hz tylko OC", ["260 Hz - OC"])
odrzuca(x.czestotliwosci, "brak natywnej", "Hz puste", [])

# 3. lista monitorów
lista_mon = czytaj("xkom_lista_monitory_wqhd")
poz = x.pozycje_listy(lista_mon)
oczekuj(len(poz) == 90, f"pozycji na stronie listy: {len(poz)}")
oczekuj(all(p["url"].startswith(x.ADRES + "/p/") and "?" not in p["url"] for p in poz), "adresy kart listy")
oczekuj(all(p["cechy"] is not None for p in poz), "wszystkie kafelki tej strony mają podsumowanie cech")
przechodza = sorted(p["url"] for p in poz if x.powod_odrzucenia_monitora(p) is None)
oczekuj(len(przechodza) == 31, f"monitorów po przesiewie: {len(przechodza)}")
powody = {p["nazwa"]: x.powod_odrzucenia_monitora(p) for p in poz}
oczekuj("przekątna" in (powody["Dell Alienware AW3226DM"] or ""), f"Dell 31,5\": {powody['Dell Alienware AW3226DM']}")
oczekuj("kilka rozdzielczości" in (powody["AOC CQ27G4Z2"] or ""), f"AOC CQ27G4Z2 (tryb 1440p/720p): {powody['AOC CQ27G4Z2']}")
oczekuj((powody["Gigabyte GS27QA"] or "").startswith("180"), "monitor 180 Hz powinien odpaść")
for u in (URL["go27q24a"], URL["aoc_q27g4zr"], URL["xg27aqdmgr"]):
    oczekuj(u in przechodza, f"brak na liście: {u}")
oczekuj(URL["dell"] not in przechodza, "Dell 31,5\" nie powinien być na liście")


class Atrapa:
    """Zastępuje zbieraj_ceny.pobierz: zapisuje adresy i oddaje zapisany html (albo kod błędu)."""
    def __init__(self, html=None, kod=200):
        self.html, self.kod, self.adresy = html, kod, []

    def __call__(self, url):
        self.adresy.append(url)
        return (self.kod, self.html if self.kod == 200 else "")


a = Atrapa(lista_mon)
adresy = x.lista_monitorow(a)
oczekuj(adresy == przechodza, f"lista_monitorow: {len(adresy)} adresów, oczekiwano {len(przechodza)}")
oczekuj(adresy == sorted(set(adresy)), "adresy niepowtarzalne i posortowane")
oczekuj(a.adresy[0] == x.LISTA_MONITOROW, f"pierwsze żądanie: {a.adresy[0]}")
oczekuj(len(a.adresy) == 2 and "page=2" in a.adresy[1],
        f"stronicowanie przez rel=next (strona 2 powtarza stronę 1, więc stop): {a.adresy}")
oczekuj(all(u.startswith(x.ADRES + "/g-6/c/15-monitory") for u in a.adresy), "żądania poza listą monitorów")
a = Atrapa(lista_mon)
oczekuj(len(x.lista_monitorow(a, maks_stron=1)) == 31 and len(a.adresy) == 1, "maks_stron=1 → jedno żądanie")
for kod in (403, 429, None):
    a = Atrapa(kod=kod)
    oczekuj(x.lista_monitorow(a) == [] and len(a.adresy) == 1, f"kod {kod} (x-kom z chmury) → [] bez wyjątku")
odrzuca(x.lista_monitorow, "brak listy produktów", "ekran blokady z kodem 200",
        Atrapa("<html><body>Verify you are human</body></html>"))

# 4. komputery: poprawne karty
lg = czytaj("xkom_pc_legion_t5_rtx5070_win11")
p = x.odczytaj_pc(URL["legion"], lg)
oczekuj(p["cpu"] == "AMD Ryzen 5 7600", f"cpu: {p['cpu']!r}")
oczekuj(p["gpu"] == "NVIDIA GeForce RTX 5070 12GB", f"gpu: {p['gpu']!r}")
oczekuj(p["ram"] == "32GB DDR5 5600MHz", f"ram: {p['ram']!r}")
oczekuj(p["storage"] == "1TB SSD", f"dysk: {p['storage']!r}")
oczekuj(p["psu"] == "500W", f"zasilacz bez certyfikatu: {p['psu']!r}")
oczekuj(p["cena_bazowa"] == 10599, f"cena: {p['cena_bazowa']!r}")
oczekuj(p["system"] == {"w_cenie": True, "doplata": None, "nazwa": "Microsoft Windows 11 Home"}, f"system: {p['system']}")
oczekuj(p["dostepny"] is True and p["sprzedawca"] is None, "dostepny/sprzedawca")
oczekuj(p["opcje"] == {"Microsoft Windows 11 Pro": 200}, f"opcje: {p['opcje']}")
oczekuj(p["opcje_adresy"].get("Microsoft Windows 11 Pro", "").startswith(U + "1361185-"), f"adresy opcji: {p['opcje_adresy']}")
oczekuj(p["nazwa"] == "Lenovo Legion T5 Ryzen 5-7600/32GB/1TB/Win11X RTX5070", f"nazwa: {p['nazwa']!r}")
oczekuj(p["zdjecie"].startswith("https://cdn.x-kom.pl/") and "{SEO}" not in p["zdjecie"], f"zdjęcie: {p['zdjecie']!r}")
oczekuj(set(p) == {"nazwa", "url", "cpu", "gpu", "ram", "storage", "psu", "cena_bazowa", "system", "dostepny",
                   "sprzedawca", "zdjecie", "opcje", "opcje_adresy"}, f"klucze komputera: {sorted(p)}")

gh = czytaj("xkom_pc_g4m3r_hero_dimm_ddr5")
p2 = x.odczytaj_pc(URL["g4m3r"], gh)
oczekuj(p2["gpu"] == "NVIDIA GeForce RTX 5060 Ti 8GB", f"gpu (8 GB z 8192 MB): {p2['gpu']!r}")
oczekuj(p2["ram"] == "32GB DDR5 6000MHz" and p2["psu"] == "850W 80 Plus Gold", f"ram/psu: {p2['ram']} {p2['psu']}")
oczekuj(p2["cena_bazowa"] == 8400 and p2["cpu"] == "Intel Core i5-14400F", f"cena/cpu: {p2['cena_bazowa']} {p2['cpu']}")
oczekuj("RTX 5060Ti" in p2["nazwa"] and "™" not in p2["nazwa"], f"nazwa bez ™: {p2['nazwa']!r}")

# wynik przechodzi przez ocena_pc i zgadza się z nowe_pc.gpu_kanoniczna
for wynik in (p, p2):
    sc = ocena_pc.oceny(wynik["cpu"], wynik["gpu"], wynik["ram"], wynik["storage"], wynik["psu"], "Windows 11 Home", 1)
    oczekuj(all(isinstance(v, (int, float)) for k, v in sc.items()), f"ocena_pc.oceny: {sc}")
oczekuj(nowe_pc.gpu_kanoniczna("NVIDIA GeForce RTX 5060 Ti", {"Pamięć karty graficznej": "8 GB"}) == p2["gpu"],
        "gpu różni się od nowe_pc.gpu_kanoniczna")
oczekuj(ocena_pc.pamiec_gpu_gb(p["gpu"]) == 12 and ocena_pc.klasa_gpu(p["gpu"]) == 6, "pamięć/klasa karty")

# 4b. odrzucenia komputera
odrzuca(x.odczytaj_pc, "nie ma w sprzedaży", "HP OMEN 35L wycofany", URL["omen"], czytaj("xkom_pc_omen35l_wycofany"))
odrzuca(x.odczytaj_pc, "nie jest DDR5", "SMX z DDR4", URL["smx"], czytaj("xkom_pc_smx_m3a_ddr4"))
M = "zmodyfikowana kopia: "
odrzuca(x.odczytaj_pc, "brak pola „Dysk”", M + "brak pola Dysk", URL["g4m3r"],
        zmien(gh, '"key":"Dysk"', '"key":"Dysk_"'))
odrzuca(x.odczytaj_pc, "bez reguły klasy", M + "procesor spoza słownika (i3)", URL["g4m3r"],
        zmien(gh, "Intel Core i5-14400F (", "Intel Core i3-12100F (", po='"key":"Procesor"'))
odrzuca(x.odczytaj_pc, "karta spoza słownika", M + "karta spoza słownika (RTX 4090)", URL["g4m3r"],
        zmien(gh, "NVIDIA GeForce RTX 5060 Ti", "NVIDIA GeForce RTX 4090", po='"key":"Karta graficzna"'))
odrzuca(x.odczytaj_pc, "brak pola „Wielkość pamięci karty graficznej”", M + "brak pamięci karty", URL["g4m3r"],
        zmien(gh, '"key":"Wielkość pamięci karty graficznej"', '"key":"Wielkosc"'))
odrzuca(x.odczytaj_pc, "brak karty dyskretnej", M + "tylko karta zintegrowana", URL["g4m3r"],
        zmien(gh, "NVIDIA GeForce RTX 5060 Ti", "Intel Graphics", po='"key":"Karta graficzna"'))
odrzuca(x.odczytaj_pc, "brak mocy zasilacza", M + "zasilacz bez mocy", URL["g4m3r"],
        zmien(gh, "850 W", "bez danych", po='"key":"Zasilacz"'))
odrzuca(x.odczytaj_pc, "brak ceny", M + "brak ceny w ld+json", URL["g4m3r"],
        zmien(gh, '"price":8400,"itemCondition"', '"price":null,"itemCondition"'))
odrzuca(x.odczytaj_pc, "ceny na stronie się różnią", M + "rozjazd ceny", URL["g4m3r"],
        zmien(gh, '"price":8400,"itemCondition"', '"price":7000,"itemCondition"'))
odrzuca(x.odczytaj_pc, "strona niedostępna", M + "rozjazd ceny niedostępna", URL["g4m3r"],
        zmien(gh, '"price":8400,"itemCondition"', '"price":7000,"itemCondition"'))
odrzuca(x.odczytaj_pc, "nie jest wspieranym systemem", M + "system Linux", URL["g4m3r"],
        zmien(gh, "Microsoft Windows 11 Home", "Linux", po='"key":"System operacyjny"'))
odrzuca(x.odczytaj_pc, "brak dopłaty do Windows 11 Home", M + "brak systemu bez dopłaty", URL["g4m3r"],
        zmien(gh, "Microsoft Windows 11 Home", "Brak systemu", po='"key":"System operacyjny"'))

# jednostki: pola komputera
oczekuj(x._ram(["16 GB (UDIMM DDR5)"]) == "16GB DDR5", "ram bez MHz")
odrzuca(x._ram, "nie podaje standardu", "RAM bez standardu", ["32 GB"])
odrzuca(x._ram, "nieczytelna", "RAM nieczytelny", ["dużo"])
odrzuca(x._ram, "kilka wartości", "dwie wartości RAM", ["16 GB (DDR5)", "16 GB (DDR5)"])
for wejscie, wynik in [(["512 GB SSD M.2 PCIe"], "512GB SSD"), (["2000 GB SSD M.2 PCIe 4.0"], "2TB SSD"),
                       (["1 TB HDD"], "1TB HDD"), (["1,5 TB SSD"], "1500GB SSD"),
                       (["Brak"], "SSD: brak (potwierdzone przez sklep)")]:
    oczekuj(x._dysk(wejscie) == wynik, f"_dysk({wejscie}) = {x._dysk(wejscie)!r}")
odrzuca(x._dysk, "bez pojemności", "dysk bez pojemności", ["SSD M.2"])
odrzuca(x._dysk, "nieznany rodzaj", "dysk bez rodzaju", ["1000 GB"])
odrzuca(x._dysk, "kilka dysków", "SSD+HDD w polu", ["500 GB SSD + 1 TB HDD"])
oczekuj(x._vram_gb(["8192 MB GDDR7 (pamięć własna)"]) == 8, "VRAM 8192 MB")
oczekuj(x._vram_gb(["16 GB GDDR7", "512 MB (pamięć współdzielona)"]) == 16, "VRAM z pamięcią współdzieloną")
odrzuca(x._vram_gb, "brak pola", "brak VRAM", [])
odrzuca(x._vram_gb, "nie umiem ustalić", "dwie różne pamięci własne", ["8192 MB GDDR7", "16384 MB GDDR7"])
odrzuca(x._vram_gb, "pełną liczbą", "VRAM niecałkowity", ["6000 MB"])
oczekuj(x._gpu_dyskretny(["NVIDIA GeForce RTX 5070Ti"]) == "NVIDIA GeForce RTX 5070 Ti", "RTX 5070Ti → 5070 Ti")
oczekuj(x._gpu_dyskretny(["NVIDIA GeForce RTX 5060 Ti", "Intel Graphics"]) == "NVIDIA GeForce RTX 5060 Ti", "karta + iGPU")
oczekuj(x._gpu_dyskretny(["AMD Radeon™ RX 9070 XT"]) == "AMD Radeon RX 9070 XT", "RX 9070 XT")
oczekuj(ocena_pc.klasa_gpu(x._gpu_dyskretny(["NVIDIA GeForce RTX 5070Ti"])) == 7, "klasa RTX 5070 Ti = 7, nie 6")
odrzuca(x._gpu_dyskretny, "brak karty dyskretnej", "sama zintegrowana", ["AMD Radeon™ Graphics"])
odrzuca(x._gpu_dyskretny, "kilka kart dyskretnych", "dwie karty", ["NVIDIA GeForce RTX 5060", "AMD Radeon RX 9060"])
odrzuca(x._gpu_dyskretny, "nieobsługiwany wariant", "SUPER", ["NVIDIA GeForce RTX 5070 SUPER"])
odrzuca(x._gpu_dyskretny, "nieobsługiwany wariant", "GRE", ["AMD Radeon RX 7900 GRE"])
odrzuca(x._gpu_dyskretny, "nieobsługiwany wariant", "D", ["NVIDIA GeForce RTX 4090 D"])
odrzuca(x._gpu_dyskretny, "nieobsługiwany wariant", "Laptop", ["NVIDIA GeForce RTX 4060 Laptop"])
odrzuca(x._gpu_dyskretny, "spoza słownika", "RTX 4060 Ti", ["NVIDIA GeForce RTX 4060 Ti"])
odrzuca(x._gpu_dyskretny, "spoza słownika", "RX 7600 XT", ["AMD Radeon RX 7600 XT"])
oczekuj(x._cpu("AMD Ryzen™ 5 8400F (6 rdzeni, 12 wątków, 4.20-4.70 GHz, 22 MB cache)") == "AMD Ryzen 5 8400F", "cpu: ™ i nawias")
oczekuj(ocena_pc.klasa_cpu(x._cpu("AMD Ryzen™ 5 8400F (6 rdzeni)")) == 4, "klasa procesora po oczyszczeniu")

# system i dopłata do Windows — karty bez systemu (obie odrzucone z innych powodów, ale _system działa na ich danych)
for nazwa_f, url, cena, doplata in [("xkom_pc_omen35l_wycofany", URL["omen"], 6099, 800),
                                    ("xkom_pc_smx_m3a_ddr4", URL["smx"], 6400, 500)]:
    ld, encja, cechy = x._karta(url, czytaj(nazwa_f))
    system, opcje, adresy_opcji = x._system(cechy, encja, cena)
    oczekuj(system == {"w_cenie": False, "doplata": doplata, "nazwa": "Brak systemu"}, f"{nazwa_f}: system {system}")
    oczekuj(opcje == {"Microsoft Windows 11 Home": doplata}, f"{nazwa_f}: opcje {opcje}")
    oczekuj("Microsoft Windows 11 Home" in adresy_opcji, f"{nazwa_f}: adres wariantu z Windows")

sys_lin, _, _ = x._system({"System operacyjny": ["Linux"]}, {}, 5000)
oczekuj(sys_lin["w_cenie"] is None and sys_lin["nazwa"] == "Linux", "_system: Linux daje w_cenie=None")
encja_alt = {"id": "1", "alternativeProducts": [{"name": "System operacyjny", "alternativeSpecifications": [
    {"productId": "2", "label": "Microsoft Windows 11 Home", "priceInfo": {"price": 5500}, "grayedOutOption": True}
]}]}
_, opc_gray, _ = x._system({"System operacyjny": ["Brak systemu"]}, encja_alt, 5000)
oczekuj(opc_gray == {}, "grayedOutOption pominięte w opcjach")
encja_alt2 = {"id": "1", "alternativeProducts": [{"name": "System operacyjny", "alternativeSpecifications": [
    {"productId": "2", "label": "Microsoft Windows 11 Home", "priceInfo": {"price": 5500},
     "promotionInfo": {"discountedPrice": 5300}, "grayedOutOption": False}
]}]}
_, opc_prom, _ = x._system({"System operacyjny": ["Brak systemu"]}, encja_alt2, 5000)
oczekuj(opc_prom.get("Microsoft Windows 11 Home") == 300, f"promocyjna dopłata: {opc_prom}")

# 5. lista komputerów
lista_pc_html = czytaj("xkom_lista_pc_udimm_ddr5")
poz = x.pozycje_listy(lista_pc_html)
oczekuj(len(poz) == 90 and all(p["cechy"] and "Grafika" in p["cechy"] for p in poz), "pozycje listy komputerów")
kandydaci_przed = [p for p in poz if x.powod_odrzucenia_pc(p) is None]
oczekuj(len(kandydaci_przed) == 25, f"kandydatów przed zwinięciem wariantów systemu: {len(kandydaci_przed)}")
a = Atrapa(lista_pc_html)
adresy_pc = x.lista_pc(a)
oczekuj(len(adresy_pc) == 15, f"komputerów po przesiewie i zwinięciu wariantów: {len(adresy_pc)}")
oczekuj(adresy_pc == sorted(set(adresy_pc)), "adresy PC niepowtarzalne i posortowane")
oczekuj([u for u in a.adresy if "?page=" not in u] == list(x.LISTY_PC),
        f"trzy przebiegi po typie RAM, w kolejności: {a.adresy}")
oczekuj(len(a.adresy) == 4, f"liczba żądań (UDIMM 2 strony; DIMM i DDR5 po 1, bo powtarzają znane pozycje): {len(a.adresy)}")
oczekuj(all(u.startswith(x.ADRES + "/g-2/c/1708-desktopy") for u in a.adresy), "żądania poza listą komputerów")
oczekuj(all(p["cena"] is not None and x.CENA_LISTY_PC_OD <= p["cena"] <= x.CENA_LISTY_PC_DO
            for p in poz if p["url"] in adresy_pc), "cena kandydata poza przesiewem")
oczekuj(U + "1361184-desktop-lenovo-legion-t5-ryzen-5-7600-32gb-1tb-win11x-rtx5070.html" not in adresy_pc,
        "Legion za 10599 zł powinien odpaść z listy (sufit 10000 zł)")
bez_cen = x.lista_pc(Atrapa(lista_pc_html), cena_od=None, cena_do=None)
oczekuj(len(bez_cen) == 46, f"bez przesiewu cen po zwinięciu: {len(bez_cen)}")
a = Atrapa(lista_pc_html)
oczekuj(len(x.lista_pc(a, maks_stron=1)) == 15 and len(a.adresy) == 3, f"maks_stron=1 → po jednym żądaniu na przebieg: {len(a.adresy)}")
for kod in (403, None):
    a = Atrapa(kod=kod)
    oczekuj(x.lista_pc(a) == [] and len(a.adresy) == 3, f"kod {kod} (x-kom z chmury) → [] bez wyjątku")
odrzuca(x.lista_pc, "brak listy produktów", "ekran blokady z kodem 200", Atrapa("<html>captcha</html>"))
odrzuca(x.lista_pc, "strona niedostępna", "ekran blokady zawiera niedostępna", Atrapa("<html>captcha</html>"))

# Defekt 4: przesiew listy PC uwzględnia min(cena regularna, promocyjna z promotionInfo)
html_kafelek_promo = zmien(lista_pc_html,
    '"price":7689,',
    '"price":10200,"promotionInfo":{"discountedPrice":9700},',
    po='"1470934":{"featureSummary"')
p_promo = next(p for p in x.pozycje_listy(html_kafelek_promo) if p["id"] == "1470934")
oczekuj(p_promo["cena"] == 9700, f"cena kafelka z promocją: {p_promo['cena']}")
oczekuj(x.powod_odrzucenia_pc(p_promo) is None, "kafelek z ceną promocyjną poniżej sufitu przechodzi przesiew")
oczekuj(x.powod_odrzucenia_pc({"dostepny": True, "cena": 7000,
                               "cechy": {"Grafika": ["NVIDIA GeForce RTX 4090"], "Procesor": ["AMD Ryzen 9 9950X"]}})
        is not None, "RTX 4090 (spoza słownika klas) powinna odpaść na liście")
oczekuj(x.powod_odrzucenia_pc({"dostepny": True, "cena": 7000,
                               "cechy": {"Grafika": ["NVIDIA GeForce RTX 5060"], "Procesor": ["Intel Core i3-12100F"]}})
        is not None, "procesor spoza słownika klas powinien odpaść na liście")
oczekuj(x.powod_odrzucenia_pc({"dostepny": True, "cena": 7000, "cechy": None}) is None,
        "kafelek bez podsumowania przechodzi do karty")

# 6. robots.txt
for u in [x.LISTA_MONITOROW, *x.LISTY_PC, *adresy, *adresy_pc, *URL.values()]:
    oczekuj(x.dozwolony(u), f"robots.txt zabrania adresu, którego używamy: {u}")
for u in ["https://www.x-kom.pl/koszyk", "https://www.x-kom.pl/konto/zamowienia", "https://www.x-kom.pl/p//a",
          "https://www.x-kom.pl/zamowienie/krok-1", "https://example.com/p/1-a.html"]:
    oczekuj(not x.dozwolony(u), f"robots.txt powinien zabraniać: {u}")
oczekuj(x.dozwolony("https://www.x-kom.pl/src/banners/a.png") and not x.dozwolony("https://www.x-kom.pl/src/a.js"),
        "reguła Allow dłuższa niż Disallow")

print("\nTEST ZALICZONY" if not bledy else f"\nTEST NIEZALICZONY: {len(bledy)} błędów")
sys.exit(1 if bledy else 0)
