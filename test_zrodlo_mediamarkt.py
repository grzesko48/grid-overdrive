#!/usr/bin/env python3
"""Test kontrolny zrodla/mediamarkt.py na zapisanych stronach MediaMarkt (bez sieci).

Fixtury (tests_fixtures/mediamarkt_*.html) to PRAWDZIWE strony pobrane 30.10.2026, przycięte do
tego, co czyta parser (nagłówek każdej mówi, co usunięto). Test sprawdza:
  1. kontrakt modułu (SKLEP, LOKALNIE, SKLEP_UWAGI, cztery funkcje, klucze słownika monitora = klucze
     nowe_monitory.odczytaj + kod_modelu + ean) oraz zgodność progów z nowe_monitory / nowe_pc,
  2. robots.txt: adresy list i kart nie łamią reguł z zapisanego robots.txt (wzorce z „*" liczone
     niezależnie od adaptera), a zakazane adresy (?filter, ?sort=, query, pl/search) są odrzucane,
  3. monitory: 5 kart do przyjęcia (marketplace i sprzedaż własna, IPS, VA z zakrzywieniem, OLED
     i QD-OLED) oraz 2 do odrzucenia (przekątna 32" UHD, pozycja wycofana ze sprzedaży),
  4. komputery: 3 karty do przyjęcia (w tym jedna sprzedawana przez MediaMarkt, sprzedawca None)
     oraz 2 do odrzucenia (DDR4, sprzeczne dane o pamięci) i warianty tych kart z jedną usuniętą lub
     zmienioną daną (pamięć karty, zasilacz, dysk, dostępność, cena, numer produktu, rodzaj),
  5. listy: parser stron kategorii przez wstrzykniętą atrapę `pobierz` (kolejność, ?page=N, prefiltr,
     limity, blokada 403 = pusta lista, zmiana układu = BrakDanych),
  6. wpisy przechodzą przez prawdziwy kod integracji (nowe_monitory.wpis, ocena_pc.oceny).
Bez sieci: adapter nie importuje żadnego modułu pobierającego, pobieranie robi atrapa.
"""
import json, os, re, sys, urllib.parse

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import ocena_pc
from ocena_pc import BrakDanych
import nowe_monitory as nm
import nowe_pc as npc
import zbieraj_ceny as z
from zrodla import mediamarkt as mm

F = os.path.join(BAZA, "tests_fixtures")
bledy = []
sprawdzen = 0
U = "https://mediamarkt.pl/pl/product/"


def czytaj(n):
    return open(os.path.join(F, n), encoding="utf-8").read()


def oczekuj(warunek, opis):
    global sprawdzen
    sprawdzen += 1
    if not warunek:
        bledy.append(opis)
        print("  BŁĄD:", opis)


def odrzucone(fn, url, html, fragment, opis):
    """fn(url, html) ma rzucić BrakDanych, a powód zawierać `fragment`."""
    try:
        fn(url, html)
        oczekuj(False, f"{opis}: powinno być odrzucone")
    except BrakDanych as x:
        oczekuj(fragment in str(x), f"{opis}: oczekiwano »{fragment}« w powodzie, jest: {x}")


def wariant(plik, zmiana):
    """Fixtura z jedną zmianą w stanie strony (apolloState) — do sprawdzenia pojedynczej reguły."""
    s = czytaj(plik)
    znacznik = "window.__PRELOADED_STATE__ = "
    i = s.index(znacznik) + len(znacznik)
    j = s.index(";</script>", i)
    stan = json.loads(s[i:j])
    zmiana(stan["apolloState"])
    return s[:i] + json.dumps(stan, ensure_ascii=False) + s[j:]


def pid_z(plik):
    return re.search(r'"sku":"(\d+)"', czytaj(plik)).group(1)


def bez_cech(plik, *nazwy):
    pid = pid_z(plik)

    def zmiana(a):
        for g in a[f"GraphqlProductFeatureGroups:{pid}"]["featureGroups"]:
            g["features"] = [r for r in g["features"] if a[r["__ref"]]["name"] not in nazwy]
    return wariant(plik, zmiana)


def z_cecha(plik, nazwa, wartosc, dodaj=False):
    """Ustawia wartość cechy (albo dodaje cechę), nie ruszając współdzielonych obiektów cech."""
    pid = pid_z(plik)

    def zmiana(a):
        grupy = a[f"GraphqlProductFeatureGroups:{pid}"]["featureGroups"]
        if dodaj:
            klucz = f"GraphqlProductFeature:TEST:{nazwa}"
            a[klucz] = {"__typename": "GraphqlProductFeature", "featureId": "TEST", "name": nazwa,
                        "value": wartosc, "unit": None}
            grupy[0]["features"].append({"__ref": klucz})
            return
        for g in grupy:
            for i, r in enumerate(g["features"]):
                if a[r["__ref"]]["name"] == nazwa:
                    klucz = f"GraphqlProductFeature:TEST:{nazwa}:{i}"
                    a[klucz] = dict(a[r["__ref"]], value=wartosc)
                    g["features"][i] = {"__ref": klucz}
    return wariant(plik, zmiana)


def ld_oferta(plik):
    """Cena i sprzedawca z JSON-LD BuyAction — liczone w teście niezależnie od adaptera."""
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', czytaj(plik), re.S):
        d = json.loads(m.group(1))
        if d.get("@type") == "BuyAction":
            of = d["object"]["offers"]
            of = of[0] if isinstance(of, list) else of
            return d["object"]["sku"], of["price"], (of.get("seller") or {}).get("name")
    return None


# ------------------------------------------------------------------ 0. kontrakt modułu
oczekuj(mm.SKLEP == "mediamarkt", f"SKLEP = {mm.SKLEP!r}")
oczekuj(mm.LOKALNIE is False, "LOKALNIE powinno być False")
oczekuj(isinstance(mm.SKLEP_UWAGI, str) and len(mm.SKLEP_UWAGI) > 40, "SKLEP_UWAGI puste")
for nazwa in ("lista_monitorow", "odczytaj_monitor", "lista_pc", "odczytaj_pc"):
    oczekuj(callable(getattr(mm, nazwa, None)), f"brak funkcji {nazwa}")
oczekuj((mm.HZ_OD, mm.HZ_DO, mm.DIAG_OD, mm.DIAG_DO) == (nm.HZ_OD, nm.HZ_DO, nm.DIAG_OD, nm.DIAG_DO),
        "progi Hz/przekątnej różnią się od nowe_monitory")
oczekuj((mm.CENA_MON_OD, mm.CENA_MON_DO) == (nm.CENA_OD, nm.CENA_DO), "zakres ceny monitora różni się od nowe_monitory")
oczekuj((mm.CENA_PC_OD, mm.CENA_PC_DO) == (npc.CENA_OD_BEZ_SYSTEMU, npc.SUFIT_Z_WINDOWS),
        "progi ceny PC różnią się od nowe_pc")
zrodlo_adaptera = open(os.path.join(BAZA, "zrodla", "mediamarkt.py"), encoding="utf-8").read()
oczekuj(not re.search(r"urlopen|import requests|http\.client|urllib\.request|subprocess|curl", zrodlo_adaptera),
        "adapter zawiera kod sieciowy — pobieranie ma robić wyłącznie wstrzyknięte `pobierz`")
oczekuj(mm.SKLEP in {"xkom", "morele", "mediamarkt", "hardpc", "plugnplay", "goblinpc"}, "klucz sklepu spoza listy")

# ------------------------------------------------------------------ 1. robots.txt
robots = czytaj("mediamarkt_robots.html")
reguly = []                       # Disallow z bloku „User-agent: *"
w_bloku = False
for linia in robots.splitlines():
    linia = linia.strip()
    if linia.lower().startswith("user-agent:"):
        w_bloku = linia.split(":", 1)[1].strip() == "*"
    elif w_bloku and linia.lower().startswith("disallow:") and linia.split(":", 1)[1].strip():
        reguly.append(linia.split(":", 1)[1].strip())
oczekuj(len(reguly) >= 15 and "*?filter*" in reguly and "*query*" in reguly, f"nie wczytano reguł robots.txt: {reguly[:5]}")


def zabroniony_wg_robots(url):
    """Niezależna od adaptera implementacja wzorców robots.txt (znak „*", koniec „$")."""
    p = urllib.parse.urlparse(url)
    cel = p.path + ("?" + p.query if p.query else "")
    for r in reguly:
        wz = "^" + re.escape(r.rstrip("$")).replace(r"\*", ".*") + ("$" if r.endswith("$") else "")
        if re.search(wz, cel):
            return True
    return False


kat = "https://mediamarkt.pl/pl/category/monitory-oled-70392.html"
for u in (kat, kat + "?page=2", U + "_monitor-gigabyte-go27q24a-czarny-176372795.html"):
    oczekuj(mm.dozwolony(u) and not zabroniony_wg_robots(u), f"dozwolony adres uznany za zakazany: {u}")
for u in (kat + "?filter=a:b", kat + "?sort=price", kat + "?query=monitor", "https://mediamarkt.pl/pl/search.html?query=x",
          "https://mediamarkt.pl/pl/promo-list/x"):
    oczekuj(zabroniony_wg_robots(u) and not mm.dozwolony(u), f"adres zakazany przez robots.txt uznany za dozwolony: {u}")
for u in (kat + "?page=2&sort=price", kat + "?page=2&filter=x", kat + "?utm=1", "http://mediamarkt.pl/pl/category/x.html",
          "https://www.mediamarkt.pl/pl/category/x.html", "https://example.com/pl/category/x.html",
          "https://mediamarkt.pl/api/v1/graphql", "https://mediamarkt.pl/pl/category/x.html?FILTER=1",
          "https://mediamarkt.pl/cdn-cgi/rum"):
    oczekuj(not mm.dozwolony(u), f"adres spoza zakresu adaptera uznany za dozwolony: {u}")

# ------------------------------------------------------------------ 2. monitory
KARTY_MON = {
    # plik: (url, nazwa, hz, diag, panelName, panel, cena, kod_modelu, ean, sprzedawca)
    "mediamarkt_mon_asus_xg27aqdpg.html": (
        U + "_monitor-asus-rog-strix-xg27aqdpg-265-wqhd-oled-003ms-500hz-amd-freesync-premium-pro-g-sync-czarny-1501523.html",
        "ASUS ROG Strix XG27AQDPG", 500, 26.5, "OLED", "oled", 3399, "90LM0C50-B01971", "4711636032605", None),
    "mediamarkt_mon_gigabyte_go27q24a.html": (
        U + "_monitor-gigabyte-go27q24a-czarny-176372795.html",
        "Gigabyte GO27Q24A", 240, 27.0, "QD-OLED", "qdoled", 1690, None, "4719331873974", "Action S.A. PL"),
    "mediamarkt_mon_msi_274qp.html": (
        U + "_monitor-msi-mag-274qp-qd-oled-x24-czarny-174093419.html",
        "MSI MAG 274QP QD-OLED X24", 240, 27.0, "QD-OLED", "qdoled", 1699, None, "0824142437360", "Action S.A. PL"),
    "mediamarkt_mon_lenovo_27q10.html": (
        U + "_monitor-lenovo-legion-27q-10-27-qhd-ips-05ms-240hz-amd-freesync-premium-nvidia-g-sync-czarny-1498879.html",
        "Lenovo Legion 27Q-10", 240, 27.0, "IPS", "ips", 799, "68C6GAC4EU", "0198156960689", None),
    "mediamarkt_mon_asus_xg27wcms_va.html": (
        U + "_monitor-asus-rog-strix-xg27wcms-27-wqhd-va-1ms-280hz-amd-freesync-premium-hdr10-czarny-1501524.html",
        "ASUS ROG Strix XG27WCMS", 280, 27.0, "VA, zakrzywiony", "va", 1549, "90LM09Y1-B01370", "4711387530146", None),
}
oczekuj(len(KARTY_MON) >= 3, "za mało kart monitorów")
wzorzec_kluczy = set(nm.odczytaj("https://www.morele.net/x-15625114/", czytaj("morele_asus_xg27aqdmgr.html")))
for plik, (url, nazwa, hz, diag, pn, pk, cena, kod, ean, sprzedawca) in KARTY_MON.items():
    d = mm.odczytaj_monitor(url, czytaj(plik))
    oczekuj(set(d) == wzorzec_kluczy | {"kod_modelu", "ean"}, f"{plik}: klucze {sorted(d)}")
    oczekuj(d["nazwa"] == nazwa, f"{plik}: nazwa {d['nazwa']!r}, oczekiwano {nazwa!r}")
    oczekuj((d["hz"], d["diag"]) == (hz, diag), f"{plik}: hz/diag {d['hz']} {d['diag']}")
    oczekuj((d["panelName"], d["panel"]) == (pn, pk), f"{plik}: matryca {d['panelName']!r}/{d['panel']!r}")
    oczekuj(d["cena"] == cena and isinstance(d["cena"], int), f"{plik}: cena {d['cena']!r}")
    oczekuj(d["kod_modelu"] == kod and d["ean"] == ean, f"{plik}: kod/ean {d['kod_modelu']!r} {d['ean']!r}")
    oczekuj(d["url"] == url and d["zdjecie"].startswith("https://assets.mmsrg.com/"), f"{plik}: url/zdjęcie")
    sku, cena_ld, sp_ld = ld_oferta(plik)
    oczekuj(sku == url.rsplit("-", 1)[1].split(".")[0] and round(cena_ld) == d["cena"],
            f"{plik}: cena adaptera {d['cena']} ≠ oferta JSON-LD {cena_ld}")
    oczekuj(mm.sprzedawca_z_karty(czytaj(plik)) == sprzedawca == sp_ld,
            f"{plik}: sprzedawca {mm.sprzedawca_z_karty(czytaj(plik))!r}, oczekiwano {sprzedawca!r}")
    e = nm.wpis(d, nm.klucz_zdjecia(901, d["nazwa"]))            # wpis składa się prawdziwym kodem
    oczekuj(set(e["scores"]) == {"perf", "value"} and e["hz"] == hz, f"{plik}: wpis nowe_monitory.wpis")

# odrzucenia
odrzucone(mm.odczytaj_monitor,
          U + "_monitor-samsung-odyssey-oled-g7-ls32hg730suxen-32-uhd-4k-oled-03ms-330hz-freesync-premium-pro-g-sync-czarny-1506197.html",
          czytaj("mediamarkt_mon_samsung_g7_32uhd.html"), "przekątna 32", "monitor 32\" UHD")
odrzucone(mm.odczytaj_monitor, U + "_gaming-monitor-gigabyte-gs27q-x-czarny-162031026.html",
          czytaj("mediamarkt_mon_gigabyte_gs27qx_wycofany.html"), "nie ma w sprzedaży", "pozycja wycofana")
odrzucone(mm.odczytaj_monitor, U + "_komputer-x-174360814.html", czytaj("mediamarkt_pc_nitropc_extremo.html"),
          "to nie monitor", "karta komputera podana jako monitor")
odrzucone(mm.odczytaj_monitor, U + "_monitor-gigabyte-go27q24a-czarny-111111111.html",
          czytaj("mediamarkt_mon_gigabyte_go27q24a.html"), "innego produktu", "numer w adresie ≠ sku strony")
odrzucone(mm.odczytaj_monitor, "https://mediamarkt.pl/pl/product/_x-1.html", "<html>blokada</html>",
          "bez stanu aplikacji", "strona bez stanu")
odrzucone(mm.odczytaj_monitor, "https://mediamarkt.pl/pl/product/_x-1.html", "<html>blokada</html>",
          "niedostęp", "strona bez stanu zawiera niedostęp")
# warianty: jedna zmieniona dana
P = "mediamarkt_mon_lenovo_27q10.html"
UP = KARTY_MON[P][0]
odrzucone(mm.odczytaj_monitor, UP, wariant(P, lambda a: [v.update(title="PRODUKT PO EKSPOZYCJI - " + str(v["title"]))
          for v in a.values() if isinstance(v, dict) and v.get("__typename") == "GraphqlProduct" and v.get("title")]),
          "nie jest nowy", "monitor po ekspozycji")
odrzucone(mm.odczytaj_monitor, UP, wariant(P, lambda a: a.update({f"CofrRefurbishedGoodsFeature:Media:pl:{pid_z(P)}": {
          "__typename": "CofrRefurbishedGoodsFeature", "id": f"Media:pl:{pid_z(P)}", "type": "MARKETPLACE_REFURBISHED"}})),
          "oferta odnowiona", "monitor z MARKETPLACE_REFURBISHED")
odrzucone(mm.odczytaj_monitor, UP, z_cecha(P, "Matryca", "TN (Twisted Nematic)"), "typ matrycy", "matryca TN")
odrzucone(mm.odczytaj_monitor, UP, z_cecha(P, "Częstotliwość odświeżania (maksymalna)", "144"), "144 Hz poza", "144 Hz")
odrzucone(mm.odczytaj_monitor, UP, z_cecha(P, "Przekątna ekranu (cal)", "24"), "przekątna 24", "przekątna 24\"")
odrzucone(mm.odczytaj_monitor, UP, bez_cech(P, "Częstotliwość odświeżania (maksymalna)"), "brak częstotliwości", "brak Hz")
odrzucone(mm.odczytaj_monitor, UP, bez_cech(P, "Przekątna ekranu (cal)"), "brak przekątnej", "brak przekątnej")
odrzucone(mm.odczytaj_monitor, UP, czytaj(P).replace("NewCondition", "UsedCondition"), "nie jest nowy", "towar używany")
odrzucone(mm.odczytaj_monitor, UP, wariant(P, lambda a: [v.update(value="3440 x 1440") for v in a.values()
          if isinstance(v, dict) and v.get("name") == "Rozdzielczość"]), "rozdzielczość", "ultrawide")


def cena_stanu(a):
    for v in a.values():
        if isinstance(v, dict) and v.get("__typename") == "CofrPriceFeature" and v.get("price"):
            v["price"] = dict(v["price"], amount=4999)


odrzucone(mm.odczytaj_monitor, UP, wariant(P, cena_stanu), "rozbieżne ceny", "cena stanu ≠ JSON-LD")
d_wariant = mm.odczytaj_monitor(UP, z_cecha(P, "Zakrzywiony ekran", "tak"))
oczekuj(d_wariant["panelName"] == "IPS, zakrzywiony", f"zakrzywiony IPS: {d_wariant['panelName']!r}")
oczekuj(mm.matryca("OLED (Organic Light-Emitting Diode)", "Monitor X QD-OLED", None, "nie") == ("QD-OLED", "qdoled"),
        "OLED + QD-OLED w tytule")
oczekuj(mm.matryca("OLED", "Monitor X WOLED", None, "nie") == ("OLED (WOLED)", "oled"), "OLED + WOLED w tytule")
oczekuj(mm.matryca("Fast IPS (xx)", "", None, "nie") == ("Fast IPS", "ips"), "Fast IPS")
try:
    mm.matryca("IPS", "Monitor X OLED", None, "nie")
    oczekuj(False, "IPS z tytułem OLED powinno być sprzecznością")
except BrakDanych:
    pass

# ------------------------------------------------------------------ 3. komputery
KARTY_PC = {
    # plik: (url, cpu, gpu, ram, storage, psu, cena, system(w_cenie, nazwa), sprzedawca, model)
    "mediamarkt_pc_nitropc_extremo.html": (
        U + "_pc-gaming-nitropc-extremo-czarny-174360814.html",
        "AMD Ryzen 5 8400F", "AMD Radeon RX 9060 XT 16GB", "32GB DDR5 6000MHz", "1TB SSD", "750W Bronze", 9330,
        (True, "Windows 11 Pro"), "Nitropc PL", "NITROPC Extremo"),
    "mediamarkt_pc_kubb_7800x3d.html": (
        U + "_gaming-pc-kubb-quantum-or-ryzen-7-7800x3d-or-ddr5-16gb-or-1tb-ssd-or-rtx-5060-8gb-or-watercooling-rgb-or-win11p-czarny-173203772.html",
        "AMD Ryzen 7 7800X3D", "NVIDIA GeForce RTX 5060 8GB", "16GB DDR5 5600MHz", "1TB SSD", "850W 80+ Bronze", 6939,
        (True, "Windows 11 Pro"), "Bleu Jour Tech PL", "KUBB QUANTUM"),
    "mediamarkt_pc_lenovo_loq.html": (
        U + "_komputer-stacjonarny-lenovo-loq-tower-26adr10-amd-ryzentm-7-8745hx-32gb-1tb-geforce-rtxtm-5050-windows-11-home-szaro-czarny-1504503.html",
        "AMD Ryzen 7 8745HX", "NVIDIA GeForce RTX 5050 8GB", "32GB DDR5 5200MHz", "1TB SSD", "500W", 6899,
        (True, "Windows 11 Home"), None, "LENOVO LOQ Tower 26ADR10"),
}
oczekuj(len(KARTY_PC) >= 3, "za mało kart komputerów")
KLUCZE_PC = {"nazwa", "url", "cpu", "gpu", "ram", "storage", "psu", "cena_bazowa", "system", "dostepny",
             "sprzedawca", "zdjecie", "ean", "opcje", "model"}
for plik, (url, cpu, gpu, ram, dysk, psu, cena, (w_cenie, os_), sprzedawca, model) in KARTY_PC.items():
    d = mm.odczytaj_pc(url, czytaj(plik))
    oczekuj(set(d) == KLUCZE_PC, f"{plik}: klucze {sorted(set(d) ^ KLUCZE_PC)}")
    oczekuj((d["cpu"], d["gpu"], d["ram"], d["storage"], d["psu"]) == (cpu, gpu, ram, dysk, psu),
            f"{plik}: podzespoły {(d['cpu'], d['gpu'], d['ram'], d['storage'], d['psu'])}")
    oczekuj(d["cena_bazowa"] == cena and isinstance(d["cena_bazowa"], int), f"{plik}: cena {d['cena_bazowa']!r}")
    oczekuj(d["system"] == {"w_cenie": w_cenie, "doplata": None, "nazwa": os_}, f"{plik}: system {d['system']}")
    oczekuj(d["sprzedawca"] == sprzedawca, f"{plik}: sprzedawca {d['sprzedawca']!r}")
    oczekuj(d["model"] == model, f"{plik}: model {d['model']!r}")
    oczekuj(d["dostepny"] is True and d["opcje"] == {} and d["url"] == url, f"{plik}: dostepny/opcje/url")
    oczekuj(d["zdjecie"].startswith("https://assets.mmsrg.com/") and re.fullmatch(r"\d{8,14}", d["ean"] or ""),
            f"{plik}: zdjęcie/ean {d['zdjecie']!r} {d['ean']!r}")
    sku, cena_ld, sp_ld = ld_oferta(plik)
    oczekuj(round(cena_ld) == d["cena_bazowa"], f"{plik}: cena adaptera {d['cena_bazowa']} ≠ JSON-LD {cena_ld}")
    # te same konwencje co nowe_pc / ocena_pc — wpis przejdzie przez kod integracji
    oczekuj(npc.dysk_znormalizowany({}, d["storage"]) == d["storage"], f"{plik}: zapis dysku niezgodny z nowe_pc")
    oczekuj(npc.gpu_kanoniczna(re.sub(r" \d+GB$", "", d["gpu"]), {"Pamięć karty graficznej": re.search(r"(\d+)GB$", d["gpu"]).group(1) + " GB"}) == d["gpu"],
            f"{plik}: karta niezgodna z nowe_pc.gpu_kanoniczna")
    try:
        ocena_pc.klasa_cpu(d["cpu"]); ocena_pc.klasa_gpu(d["gpu"])
        sc = ocena_pc.oceny(d["cpu"], d["gpu"], d["ram"], d["storage"], d["psu"], "Windows 11 Home", 1)
        oczekuj(1 <= sc["perf"] <= 100, f"{plik}: moc {sc['perf']}")
    except BrakDanych as x:
        oczekuj(False, f"{plik}: ocena_pc odrzuciła zestaw: {x}")

# pułapka „pierwszy produkt w stanie strony": w tych fixturach przed właściwym produktem stoi cudzy (akcesorium)
for plik in ("mediamarkt_pc_lenovo_loq.html", "mediamarkt_mon_asus_xg27aqdpg.html"):
    s = czytaj(plik)
    pierwszy = re.search(r'"GraphqlProduct:Media:pl-PL:(\d+)"', s).group(1)
    oczekuj(pierwszy != pid_z(plik), f"{plik}: fixtura nie zawiera już cudzego produktu przed właściwym")

# odrzucenia prawdziwych kart
odrzucone(mm.odczytaj_pc, U + "_desktop-gaming-beastcom-q5-pro-gaming-czarny-142245436.html",
          czytaj("mediamarkt_pc_beastcom_q5_ddr4.html"), "nie jest DDR5", "BEASTCOM Q5 (DDR4)")
odrzucone(mm.odczytaj_pc,
          U + "_komputer-stacjonarny-bleu-jour-byte-ai-ready-ultra-5-225frtx-5060-ti16gb-ddr5-6000mhz1tb-ssd-m2win11p-czarny-176391585.html",
          czytaj("mediamarkt_pc_bleujour_sprzecznosc_ddr.html"), "sprzeczne dane o pamięci", "Bleu Jour: DDR5 vs sloty DDR4")
odrzucone(mm.odczytaj_pc, KARTY_MON["mediamarkt_mon_gigabyte_go27q24a.html"][0],
          czytaj("mediamarkt_mon_gigabyte_go27q24a.html"), "to nie komputer", "monitor podany jako komputer")
# warianty karty NITROPC (jedna dana usunięta albo zmieniona)
N = "mediamarkt_pc_nitropc_extremo.html"
UN = KARTY_PC[N][0]
odrzucone(mm.odczytaj_pc, UN, bez_cech(N, "Dedykowana pamięć grafiki", "Pamięć grafiki", "Model karty graficznej"),
          "brak pojemności pamięci karty", "brak pamięci karty")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Pamięć grafiki", "8"), "sprzeczna pamięć karty", "dwie różne pamięci karty")
odrzucone(mm.odczytaj_pc, UN, bez_cech(N, "Moc zasilania", "Model zasilacza"), "brak mocy zasilacza", "brak zasilacza")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Moc zasilania", "650"), "sprzeczna moc zasilacza", "moc 650 W vs 750W Bronze")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Typ pamięci RAM", "DDR4"), "nie jest DDR5", "DDR4 w typie pamięci")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Dysk", "brak"), "brak dysku", "brak dysku")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Liczba zainstalowanych dysków", "2"), "dyski", "dwa dyski")
odrzucone(mm.odczytaj_pc, UN, bez_cech(N, "Pojemność dysku 1", "Dysk"), "dysk bez pojemności", "dysk bez pojemności")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Procesor", "Intel Pentium G7400"), "procesor bez reguły klasy", "procesor spoza słownika")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Procesor", "AMD Ryzen 7"), "brak modelu", "procesor bez modelu (Defekt 9a)")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Karta graficzna", "Radeon RX 7800 XT").replace("AMD Radeon RX 9060 XT", "Radeon RX 7800 XT"),
          "spoza słownika klas", "karta spoza słownika")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Model karty graficznej", "NVIDIA GeForce RTX 5070 Ti SUPER 16GB"),
          "SUPER/GRE", "karta SUPER (Defekt 9b)")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Pojemność dysku 2", "1TB", dodaj=True),
          "drugi dysk", "drugi dysk w zestawie (Defekt 9c)")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Typ pamięci RAM", "DDR5 / DDR4"), "nie jest DDR5", "DDR5 / DDR4 w typie RAM (Defekt 3)")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Typ pamięci RAM", "DDR4, DDR5"), "nie jest DDR5", "DDR4, DDR5 w typie RAM (Defekt 3)")
odrzucone(mm.odczytaj_pc, UN, wariant(N, lambda a: [v.update(title=str(v["title"]) + " DDR4")
          for v in a.values() if isinstance(v, dict) and v.get("__typename") == "GraphqlProduct" and v.get("title")]),
          "starszej generacji", "DDR4 w tytule karty PC (Defekt 3)")
oczekuj(mm.odczytaj_pc(UN, z_cecha(N, "Pamięć RAM", "2 x 16"))["ram"] == "32GB DDR5 6000MHz", "RAM 2 x 16 -> 32GB (Defekt 4)")
oczekuj(mm.odczytaj_pc(UN, z_cecha(N, "Pamięć RAM", "16 + 16"))["ram"] == "32GB DDR5 6000MHz", "RAM 16 + 16 -> 32GB (Defekt 4)")
oczekuj(mm.odczytaj_pc(UN, z_cecha(N, "Prędkość pamięci", "DDR5-6000"))["ram"] == "32GB DDR5 6000MHz", "Prędkość DDR5-6000 (Defekt 4)")
oczekuj(mm.odczytaj_pc(UN, z_cecha(N, "Prędkość pamięci", "6 000"))["ram"] == "32GB DDR5 6000MHz", "Prędkość 6 000 (Defekt 4)")
oczekuj(mm.odczytaj_pc(UN, z_cecha(N, "Prędkość pamięci", "6000 / 6400"))["ram"] == "32GB DDR5", "Niejednoznaczna prędkość RAM (Defekt 4)")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Pamięć RAM", "2 x 16 x 2"), "niejednoznaczna", "niejednoznaczna pojemność RAM (Defekt 4)")
odrzucone(mm.odczytaj_pc, UN, z_cecha(N, "Przekątna ekranu", "23.8", dodaj=True), "All-in-One", "komputer z ekranem")
d_ekran_brak = mm.odczytaj_pc(UN, z_cecha(N, "Przekątna ekranu", "-", dodaj=True))
oczekuj(d_ekran_brak["cpu"] == "AMD Ryzen 5 8400F", "Przekątna ekranu '-' nie odrzuca komputera stacjonarnego")
d_ekran_zero = mm.odczytaj_pc(UN, z_cecha(N, "Przekątna ekranu", "0", dodaj=True))
oczekuj(d_ekran_zero["cpu"] == "AMD Ryzen 5 8400F", "Przekątna ekranu '0' nie odrzuca komputera stacjonarnego")
d_ekran_brak2 = mm.odczytaj_pc(UN, z_cecha(N, "Przekątna ekranu", "brak", dodaj=True))
oczekuj(d_ekran_brak2["cpu"] == "AMD Ryzen 5 8400F", "Przekątna ekranu 'brak' nie odrzuca komputera stacjonarnego")
odrzucone(mm.odczytaj_pc, UN, wariant(N, lambda a: [v.update(marketplaceSeller={"sellerName": "PCrefurb Scandinavia PL"})
          for v in a.values() if isinstance(v, dict) and v.get("__typename") == "CofrPriceFeature"]),
          "nie jest nowy", "sprzedawca PCrefurb (Defekt 1)")
odrzucone(mm.odczytaj_pc, UN, wariant(N, lambda a: [v.update(isAvailableAndBuyable=False, onlineStatus="NO_VALID_MP_OFFER_PRICE")
          for v in a.values() if isinstance(v, dict) and v.get("__typename") == "CofrOnlineStatusFeature"]),
          "nie ma w sprzedaży", "niedostępny")
odrzucone(mm.odczytaj_pc, UN, wariant(N, lambda a: [v.update(price=None) for v in a.values()
          if isinstance(v, dict) and v.get("__typename") == "CofrPriceFeature"]) .replace('"price":9329.99', '"price":"x"'),
          "brak ceny", "brak ceny")
odrzucone(mm.odczytaj_pc, UN, czytaj(N).replace("NewCondition", "RefurbishedCondition"), "nie jest nowy", "towar odnowiony")
odrzucone(mm.odczytaj_pc, UN.replace("174360814", "174360812"), czytaj(N), "innego produktu", "numer w adresie ≠ sku")
bez_sprzedawcy_stanu = wariant(N, lambda a: [v.update(marketplaceSeller=None) for v in a.values()
                                              if isinstance(v, dict) and v.get("__typename") == "CofrPriceFeature"])
oczekuj(mm.odczytaj_pc(UN, bez_sprzedawcy_stanu)["sprzedawca"] == "Nitropc PL", "sprzedawca z JSON-LD, gdy stan go nie podaje")
odrzucone(mm.odczytaj_pc, UN, re.sub(r'"seller":\{[^}]*\}', '"seller":{}', bez_sprzedawcy_stanu),
          "bez nazwy sprzedawcy", "marketplace bez nazwy sprzedawcy")
oczekuj(mm.odczytaj_pc(UN, z_cecha(N, "System operacyjny", "Brak systemu"))["system"] == {"w_cenie": False, "doplata": None, "nazwa": "Brak systemu"},
        "system: brak systemu")
oczekuj(mm.odczytaj_pc(UN, z_cecha(N, "System operacyjny", "Windows 11 Home (bez licencji)"))["system"] == {
        "w_cenie": False, "doplata": None, "nazwa": "Windows 11 Home (bez licencji)"},
        "system: Windows bez licencji (Defekt 5)")
oczekuj(mm.odczytaj_pc(UN, z_cecha(N, "System operacyjny", "Linux"))["system"] == {
        "w_cenie": None, "doplata": None, "nazwa": "Linux"},
        "system: Linux (Defekt 5)")
oczekuj(mm.odczytaj_pc(UN, bez_cech(N, "System operacyjny"))["system"] == {"w_cenie": None, "doplata": None, "nazwa": None},
        "system: brak cechy powinien dać w_cenie None")
mm.ZASILACZ_WYMAGANY = False
try:
    oczekuj(mm.odczytaj_pc(UN, bez_cech(N, "Moc zasilania", "Model zasilacza"))["psu"] is None, "ZASILACZ_WYMAGANY=False: psu powinno być None")
finally:
    mm.ZASILACZ_WYMAGANY = True

# jednostkowo: zasilacz, dysk (wejścia w formie cech: nazwa → [(wartość, jednostka)])
oczekuj(mm.zasilacz({"Moc zasilania": [("500", "W")], "Model zasilacza": [("500W80+BRONZE", "")]}) == "500W 80+ Bronze", "zasilacz 500W80+BRONZE")
oczekuj(mm.zasilacz({"Model zasilacza": [("850 W 80 PLUS GOLD", "")]}) == "850W 80 Plus Gold", "zasilacz 80 PLUS GOLD")
oczekuj(mm.zasilacz({"Moc zasilania": [("650", "W")]}) == "650W", "zasilacz sama moc")
oczekuj(mm.zasilacz({}) is None, "zasilacz bez danych")
oczekuj(mm.dysk({"Rodzaj dysku 1": [("SSD", "")], "Pojemność dysku 1": [("512", "GB")]}) == "512GB SSD", "dysk 512GB")
oczekuj(mm.dysk({"Rodzaj dysku 1": [("SSD", "")], "Pojemność dysku 1": [("1.5", "TB")]}) == "1.5TB SSD", "dysk 1.5TB")
oczekuj(mm.dysk({"Dysk": [("HDD , 2 TB , SATA", "")]}) == "2TB HDD", "dysk z opisu")
oczekuj(mm.stan_strony('<script>window.__PRELOADED_STATE__ = {"apolloState":{"a":undefined,"b":1}};</script>') == {"a": None, "b": 1},
        "stan strony z wartością undefined")
oczekuj(mm.cechy({"GraphqlProductFeatureGroups:1": {"featureGroups": "nie-lista"}}, "1") == {}, "cechy: odporność na featureGroups nie-lista (Defekt 9d)")
oczekuj(mm.cechy({"GraphqlProductFeatureGroups:1": {"featureGroups": [{"features": "nie-lista"}]}}, "1") == {}, "cechy: odporność na features nie-lista (Defekt 9d)")
oczekuj(mm.cechy({"GraphqlProductFeatureGroups:1": {"featureGroups": [{"features": [{"__ref": None}]}]}}, "1") == {}, "cechy: odporność na ref None (Defekt 9d)")

# ------------------------------------------------------------------ 4. listy (atrapa pobierz)
def atrapa(mapa, zadania, kod_domyslny=404):
    def pobierz(url):
        zadania.append(url)
        if url in mapa:
            return 200, czytaj(mapa[url]) if not mapa[url].startswith("<") else mapa[url]
        return kod_domyslny, ""
    return pobierz


C = "https://mediamarkt.pl/pl/category/"
MAPA_MON = {C + "monitory-oled-70392.html": "mediamarkt_lista_monitory_oled_1.html",
            C + "monitory-oled-70392.html?page=2": "mediamarkt_lista_monitory_oled_2.html",
            C + "monitory-dla-graczy-31050.html": "mediamarkt_lista_monitory_graczy_1.html"}
zad = []
adresy = mm.lista_monitorow(atrapa(MAPA_MON, zad), maks_stron=2)
oczekuj(zad == [C + "monitory-oled-70392.html", C + "monitory-oled-70392.html?page=2",
                C + "monitory-dla-graczy-31050.html", C + "monitory-dla-graczy-31050.html?page=2"],
        f"żądania listy monitorów: {zad}")
oczekuj(len(adresy) == len(set(adresy)) == 18, f"adresów monitorów: {len(adresy)} (unikalnych {len(set(adresy))}), oczekiwano 18")
oczekuj(all(a.startswith("https://mediamarkt.pl/pl/product/") for a in adresy), "adres karty monitora poza /pl/product/")
oczekuj(any("xg27aqdpg" in a for a in adresy) and any("ls27dg610suxen" in a for a in adresy), "brak znanych monitorów 240+ Hz")
oczekuj(not any(re.search(r"ls32hg730|45gx950|xg32ucds|24g411|ls27fg500|g2741hsu|ls27cg552", a) for a in adresy),
        "na liście zostały monitory odrzucane po tytule (inne Hz / UHD / 32\" / 23,8\")")
oczekuj(sum("ls27hg612suxen" in a for a in adresy) == 1, "monitor z dwóch kategorii powinien wystąpić raz")
oczekuj(all(mm.dozwolony(u) and not zabroniony_wg_robots(u) for u in zad + adresy), "lista monitorów łamie robots.txt")
# kategoria monitorów: 1 strona = 2 żądania; limit adresów
zad = []
oczekuj(len(mm.lista_monitorow(atrapa(MAPA_MON, zad), maks_stron=1)) == 6 and len(zad) == 2,
        f"maks_stron=1: żądań {len(zad)}")
oczekuj(len(mm.lista_monitorow(atrapa(MAPA_MON, []), maks_stron=2, maks_adresow=5)) == 5, "limit maks_adresow")
# blokada 403: pusta lista, bez wyjątku, bez ponawiania
zad = []
oczekuj(mm.lista_monitorow(atrapa({}, zad, 403), maks_stron=6) == [] and len(zad) == 2, f"403: żądań {len(zad)}")
zad = []
oczekuj(mm.lista_monitorow(lambda u: (None, "blad"), maks_stron=6) == [], "błąd sieci: pusta lista")
# zmiana układu na pierwszej stronie: BrakDanych (nie cicha pustka)
try:
    mm.lista_monitorow(atrapa({C + "monitory-oled-70392.html": "<html>zupełnie inna strona</html>"}, []), maks_stron=2)
    oczekuj(False, "zmiana układu listy powinna rzucić BrakDanych")
except BrakDanych as x:
    oczekuj("lista MediaMarkt" in str(x), f"komunikat zmiany układu: {x}")

MAPA_KAT2_BLAD = {C + "monitory-oled-70392.html": "mediamarkt_lista_monitory_oled_1.html",
                  C + "monitory-dla-graczy-31050.html": "<html>strona błędu bez stanu</html>"}
try:
    mm.lista_monitorow(atrapa(MAPA_KAT2_BLAD, []), maks_stron=1)
    oczekuj(False, "zmiana układu w kategorii 2 powinna rzucić BrakDanych (Defekt 8)")
except BrakDanych as x:
    oczekuj("lista MediaMarkt" in str(x) and "niedostęp" in str(x), f"komunikat zmiany układu kategoria 2: {x}")

MAPA_PC = {C + "komputery-gamingowe-50070.html": "mediamarkt_lista_pc_1.html",
           C + "komputery-gamingowe-50070.html?page=2": "mediamarkt_lista_pc_2.html"}
zad = []
adresy_pc = mm.lista_pc(atrapa(MAPA_PC, zad), maks_stron=3)
oczekuj(zad == [C + "komputery-gamingowe-50070.html", C + "komputery-gamingowe-50070.html?page=2",
                C + "komputery-gamingowe-50070.html?page=3"], f"żądania listy PC: {zad}")
oczekuj(len(adresy_pc) == len(set(adresy_pc)) == 13, f"adresów PC: {len(adresy_pc)}, oczekiwano 13 (cena 5000-10000 zł, bez DDR4 w tytule)")
oczekuj(not any(i in a for a in adresy_pc for i in ("181093255", "134377344", "133693803", "186258884")),
        "na liście PC zostały pozycje z DDR4 w tytule albo spoza progu ceny")
oczekuj(len(mm.lista_pc(atrapa(MAPA_PC, []), maks_stron=1, cena_od=0, cena_do=10 ** 6)) == 12, "lista PC bez progu ceny: 12 pozycji strony 1")
oczekuj(all(mm.dozwolony(u) and not zabroniony_wg_robots(u) for u in zad + adresy_pc), "lista PC łamie robots.txt")
oczekuj(mm.lista_pc(atrapa({}, [], 403), maks_stron=6) == [], "lista PC przy 403")
prod, maks = mm.produkty_z_listy(czytaj("mediamarkt_lista_pc_1.html"))
oczekuj(maks == 22 and len(prod) == 12 and prod[0]["id"] == "176855693" and prod[0]["cena"] == 6009 and prod[0]["sprzedawca"] == "BEASTCOM PL",
        f"produkty_z_listy: {maks} {len(prod)} {prod[0]}")
oczekuj(mm.produkty_z_listy(czytaj("mediamarkt_lista_monitory_graczy_1.html"))[1] == 30, "maxPage kategorii monitorów dla graczy")

MAPA_PC_REFURB = {C + "komputery-gamingowe-50070.html": wariant("mediamarkt_lista_pc_1.html",
                  lambda a: a.update({"CofrRefurbishedGoodsFeature:Media:pl:176855693": {
                      "__typename": "CofrRefurbishedGoodsFeature", "id": "Media:pl:176855693", "type": "MARKETPLACE_REFURBISHED"}}))}
adresy_bez_refurb = mm.lista_pc(atrapa(MAPA_PC_REFURB, []), maks_stron=1, cena_od=0, cena_do=10 ** 6)
oczekuj(not any("176855693" in u for u in adresy_bez_refurb), "lista_pc odrzuca MARKETPLACE_REFURBISHED (Defekt 1)")

MAPA_PC_SELLER_REFURB = {C + "komputery-gamingowe-50070.html": wariant("mediamarkt_lista_pc_1.html",
                         lambda a: [v.update(marketplaceSeller={"sellerName": "PCrefurb Scandinavia PL"})
                                    for v in a.values() if isinstance(v, dict) and v.get("id") == "Media:pl:176855693"
                                    and v.get("__typename") == "CofrPriceFeature"])}
adresy_bez_seller_refurb = mm.lista_pc(atrapa(MAPA_PC_SELLER_REFURB, []), maks_stron=1, cena_od=0, cena_do=10 ** 6)
oczekuj(not any("176855693" in u for u in adresy_bez_seller_refurb), "lista_pc odrzuca sprzedawcę refurb (Defekt 1)")

# prefiltr po tytule: odrzuca tylko przy jawnym przeciwieństwie
for tytul, powinno_odpasc in [
    ("PRODUKT PO EKSPOZYCJI - Monitor LENOVO Legion 27Q-10 27 QHD", True),
    ("OUTLET - Monitor ASUS ROG Strix XG27AQDPG 26,5 WQHD OLED", True),
    ("Monitor SAMSUNG Odyssey G5 LS27FG502EUXEN 27 QHD IPS 1ms 180Hz FreeSync G-Sync Czarny", True),
    ("Monitor LG LG UltraGear 45GX950A-B 45 WUHD OLED 0.03ms 330Hz (WFHD) 165Hz (WUHD) FreeSync", True),
    ("Monitor LENOVO Legion Pro 32UD-10 31.5 UHD 4K OLED 0.03ms 240Hz FreeSync Premium Pro", True),
    ('Monitor LG 23,8" UltraGear 24G411A-B IPS FHD 144Hz HDMI DP Czarny', True),
    ("Monitor SAMSUNG LS32CG552EUXEN 32 QHD VA 1ms 165Hz", True),
    ("Monitor SAMSUNG Odyssey G5 LC34G55TWWPXEN 34 UWHD VA 1ms", True),
    ("Monitor ASUS ROG Strix XG27AQDPG 26,5 WQHD OLED 0.03ms 500Hz AMD FreeSync Premium Pro G-Sync Czarny", False),
    ("Monitor SAMSUNG Odyssey OLED G6 LS27DG610SUXEN 27 QHD OLED 0.03 ms 240Hz", False),
    ("Monitor IIYAMA G-Master GOB2701QSC-B1 Titan Falcon 27 WQHD OLED 0.03ms 280Hz HDR True Black 400 G-Sync Czarny", False),
    ("Monitor SAMSUNG Odyssey OLED G6 LS27HG612SUXEN 27 QHD OLED FreeSync Premium HDR10+ Gaming Czarny", False),
    ("Monitor GIGABYTE GO27Q24A Czarny", False),                       # marketplace: tytuł bez parametrów idzie do karty
    ("Gaming-monitor DELL AW2725DF Czarny", False),
]:
    oczekuj((mm.tytul_monitora_odpada(tytul) is not None) == powinno_odpasc, f"prefiltr tytułu: {tytul[:60]!r} → {mm.tytul_monitora_odpada(tytul)!r}")

# nazwy monitorów z prawdziwych tytułów
for tytul, marka, nazwa in [
    ("Monitor LG 27GX790A-B QHD OLED 0,03 ms 480Hz AMD FreeSync", "LG", "LG 27GX790A-B"),
    ("Monitor ASUS ROG Strix XG27AQDPG 26,5 WQHD OLED 0.03ms 500Hz AMD FreeSync Premium Pro G-Sync Czarny", "ASUS", "ASUS ROG Strix XG27AQDPG"),
    ("Monitor SAMSUNG Odyssey OLED G6 LS27DG610SUXEN 27 QHD OLED 0.03 ms 240Hz", "SAMSUNG", "Samsung Odyssey OLED G6 LS27DG610SUXEN"),
    ("Monitor IIYAMA G-Master GOB2701QSC-B1 Titan Falcon 27 WQHD OLED 0.03ms 280Hz HDR True Black 400 G-Sync Czarny", "IIYAMA", "iiyama G-Master GOB2701QSC-B1 Titan Falcon"),
    ("Monitor GIGABYTE GO27Q24A Czarny", "GIGABYTE", "Gigabyte GO27Q24A"),
    ("Monitor MSI MAG 274QP QD-OLED X24 Czarny", "MSI", "MSI MAG 274QP QD-OLED X24"),
    ("Gaming-monitor LENOVO Legion Pro 27UD-10 Czarny, Szary", "LENOVO", "Lenovo Legion Pro 27UD-10"),
    ("Monitor gamingowy GIGABYTE MO27Q28GR biały", "GIGABYTE", "Gigabyte MO27Q28GR"),
    ("Monitor LG LG UltraGear 45GX950A-B 45 WUHD OLED 0.03ms 330Hz (WFHD) 165Hz (WUHD)", "LG", "LG UltraGear 45GX950A-B"),
    ("Monitor SAMSUNG Odyssey G5 LC34G55TWWPXEN 34 UWHD VA 1ms", "SAMSUNG", "Samsung Odyssey G5 LC34G55TWWPXEN"),
]:
    try:
        oczekuj(mm.nazwa_monitora(tytul, marka) == nazwa, f"nazwa z tytułu {tytul[:50]!r}: {mm.nazwa_monitora(tytul, marka)!r}")
    except BrakDanych as x:
        oczekuj(False, f"nazwa z tytułu {tytul[:50]!r}: {x}")
for zly in ("Monitor SAMSUNG", 'Monitor LG 23,8" UltraGear 24G411A-B IPS FHD 144Hz'):
    try:
        mm.nazwa_monitora(zly, "LG")
        oczekuj(False, f"tytuł bez modelu powinien dać BrakDanych: {zly!r}")
    except BrakDanych:
        pass

# nazwy modeli komputerów
for tytul, model in [("PC Gaming NITROPC Extremo Czarny", "NITROPC Extremo"),
                     ("DESKTOP GAMING BEASTCOM Q5 | Pro Gaming Czarny", "BEASTCOM Q5"),
                     ("Komputer stacjonarny BLEU JOUR Byte AI Ready Ultra 5 225F/RTX 5060 Ti/16GB DDR5 6000MHz/1TB SSD M.2,Win11P Czarny", "BLEU JOUR Byte AI Ready")]:
    oczekuj(mm.model_pc(tytul) == model, f"model PC z {tytul[:40]!r}: {mm.model_pc(tytul)!r}")

# ------------------------------------------------------------------ informacja o istniejącym trackerze
# zbieraj_ceny.z_mediamarkt bierze PIERWSZĄ ofertę-obiekt na stronie, a ta bywa ofertą sąsiedniego wariantu
# (inny kolor/model serii). To nie jest błąd adaptera i test go nie egzekwuje; wypisujemy rozbieżności,
# żeby było je widać przy każdym uruchomieniu.
uwagi = []
for plik in list(KARTY_MON) + list(KARTY_PC):
    cena_tracker, _ = z.z_mediamarkt(czytaj(plik))
    cena_strony = round(ld_oferta(plik)[1])
    if cena_tracker != cena_strony:
        uwagi.append(f"{plik}: zbieraj_ceny.z_mediamarkt = {cena_tracker} zł, oferta tej strony = {cena_strony} zł")
for plik in ("mediamarkt_pc_beastcom_q5_ddr4.html",):
    cena_tracker, _ = z.z_mediamarkt(czytaj(plik))
    cena_strony = round(ld_oferta(plik)[1])
    if cena_tracker != cena_strony:
        uwagi.append(f"{plik}: zbieraj_ceny.z_mediamarkt = {cena_tracker} zł, oferta tej strony = {cena_strony} zł")
for u in uwagi:
    print("  UWAGA (poza zakresem adaptera):", u)

print(f"\nsprawdzeń: {sprawdzen}")
print("TEST ZALICZONY" if not bledy else f"TEST NIEZALICZONY: {len(bledy)} błędów")
sys.exit(1 if bledy else 0)
