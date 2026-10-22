#!/usr/bin/env python3
"""Test regresyjny nanies_zmiany.py: wpis wskazujemy położeniem, nie kluczem zdjęcia.

Błąd z października 2026: jedna obudowa = jedno zdjęcie, więc wiele zestawów dzieli klucz
`img`. Wyszukiwanie po tym kluczu oddawało każdemu segmentowi dane OSTATNIEGO wpisu z tą
obudową — cena jednego zestawu trafiła do wszystkich (175 z 217 błędnych cen na żywej
stronie). Test bierze PRAWDZIWE wpisy z szablonu, dzieli je na mały szablon, podaje
sklepowi różne ceny i sprawdza, że każdy wpis dostał SWOJĄ.
Uruchomienie: python3 test_nanies.py   (kod wyjścia 0 = zaliczony)"""
import collections, json, os, re, sys, tempfile, io, contextlib
BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import nanies_zmiany as nz
from zbieraj_ceny import wczytaj

sz = open(nz.SZABLON, encoding="utf-8").read()
poz = [p for p in wczytaj(sz) if p["rodzaj"] == "pc" and "hardpc" in p["prices"]]
po_img = collections.defaultdict(list)
for p in poz:
    po_img[p["img"]].append(p)
# obudowa z największą liczbą NIE-customowych zestawów i z wariantem custom
wybrana = max(po_img.values(), key=lambda l: (sum("(custom:" not in x["name"] for x in l),
                                                 sum("(custom:" in x["name"] for x in l)))
nie_custom = [p for p in wybrana if "(custom:" not in p["name"]][:4]
customy = [p for p in wybrana if "(custom:" in p["name"]][:2]
assert len(nie_custom) >= 3, "brak obudowy współdzielonej przez >= 3 zestawy"
zestaw = nie_custom + customy

granice = nz.granice(sz)
def segment(p):
    i = granice.index(p["start"])
    return sz[p["start"]: granice[i + 1] if i + 1 < len(granice) else len(sz)]
mini = "var PDATA = [\n" + "".join(segment(p) for p in zestaw) + "\n];\n"

# sklep podaje RÓŻNE ceny dla różnych adresów; każdy zestaw ma mieć swoją
adresy, oczekiwane = {}, {}
for n, p in enumerate(nie_custom):
    u = p["urls"]["hardpc"]
    cena = p["prices"]["hardpc"] + 100 * (n + 1)          # inna zmiana dla każdego adresu
    adresy[f"hardpc|{u}"] = {"stan": "ok", "cena": cena, "nazwa": p["name"], "niedostepny": False,
                             "opcje": {"32GB": 1199}}     # sklep żąda dziś +1199 zł (było +899)
    oczekiwane[p["name"]] = cena
tmp = tempfile.mkdtemp()
pl_szablon, pl_zeb = os.path.join(tmp, "t.html"), os.path.join(tmp, "z.json")
open(pl_szablon, "w", encoding="utf-8").write(mini)
json.dump({"adresy": adresy, "pobrano": {}}, open(pl_zeb, "w"))

zapisany = {}
orig = nz.kontrola_zgodnosci
def podsluch(poz_, wynik, *a):
    zapisany["wynik"] = wynik
    return orig(poz_, wynik, *a)
nz.kontrola_zgodnosci = podsluch
nz.SZABLON = pl_szablon
sys.argv = ["nanies", "--zebrane", pl_zeb, "--na-sucho", "--prog", "10"]
bufor = io.StringIO()
with contextlib.redirect_stdout(bufor):
    try:
        nz.main()
    except SystemExit as e:
        print("KOD WYJSCIA", e.code)
wyn = {p["name"]: p for p in wczytaj(zapisany["wynik"])}
bledy = []
for nazwa, cena in oczekiwane.items():
    if wyn[nazwa]["prices"]["hardpc"] != cena:
        bledy.append(f"{nazwa[:55]}: jest {wyn[nazwa]['prices']['hardpc']}, ma być {cena}")
for p in customy:   # wariant custom zachowuje dopłatę względem bazy
    baza = [x for x in nie_custom if x["urls"]["hardpc"] == p["urls"]["hardpc"]]
    if len(baza) == 1:
        b = baza[0]
        ma = wyn[p["name"]]["prices"]["hardpc"] - wyn[b["name"]]["prices"]["hardpc"]
        if ma != 1199:
            bledy.append(f"custom {p['name'][-30:]}: dopłata {ma}, sklep żąda dziś 1199")
        # etykieta, pole i zaleta mają mówić to samo co cena
        seg = zapisany["wynik"]
        i = seg.index(p["name"]); fr = seg[i: i + 4000]
        for wz in (r"ramUpgradeCost:1199", r"customLabel:\"\+ RAM 32GB \(\+1199 zł\)\"",
                   r"RAM podniesiony do 32GB za dopłatą 1199 zł"):
            if not re.search(wz, fr):
                bledy.append(f"custom {p['name'][-30:]}: brak '{wz}' w wpisie po odświeżeniu dopłaty")
if "BRAMKA ZGODNOŚCI NIE PRZESZŁA" in bufor.getvalue():
    bledy.append("bramka zgodności odrzuciła poprawny wynik")
print(f"obudowa współdzielona przez {len(wybrana)} wpisów; sprawdzono {len(oczekiwane)} zestawów "
      f"+ {len(customy)} wariantów custom")
if bledy:
    print("TEST NIE PRZESZEDŁ:"); [print("  ", b) for b in bledy]; sys.exit(1)
print("TEST ZALICZONY: każdy zestaw ma własną cenę, warianty custom dostały aktualną dopłatę sklepu")
