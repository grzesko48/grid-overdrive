#!/usr/bin/env python3
"""Historia cen i wykrywanie PROMOCJI (spadków ceny) — tylko z tego, co bot rzeczywiście zaobserwował.

Po każdym nanoszeniu cen (nanies_zmiany.py) ten skrypt:
  1. dopisuje do historia_cen.json cenę każdego sklepu ZWERYFIKOWANĄ w tym przebiegu (przechowujemy
     punkty zmiany ceny + datę ostatniej obserwacji, więc plik rośnie powoli),
  2. wylicza, które pozycje mają dziś cenę wyraźnie niższą niż typowa z ostatnich dni,
  3. wpisuje wynik do szablonu jako `var PROMOCJE = {...}` (strona pokazuje sekcję „Promocje" i znaczniki).

ZASADY (ta sama co w całym serwisie: zero zmyślonych danych):
- „typowa cena" = mediana dziennych cen TEGO SKLEPU z okna do 45 dni, wyłącznie z dni, w których bot
  ją widział; wymagane ≥ 5 dni obserwacji i najstarsza obserwacja ≥ 4 dni wstecz — krótsza historia
  nie daje promocji, a dni obserwacji są pokazywane obok liczby;
- promocja = cena dziś ≤ 92% typowej i oszczędność ≥ 60 zł (monitory) / 200 zł (PC); w sekcji „Promocje"
  tylko ≥ 10%; „super" ≥ 20%;
- pozycje ukryte, wyprzedane w danym sklepie, oferty zewnętrznych sprzedawców (marketplace) i sklepy
  niezweryfikowane dziś nie są promocją;
- historia sięga 22.10.2026 (naprawiony stan danych); starsze dane PC były zepsute (błąd kluczy zdjęć).

Użycie:
  python3 historia_cen.py --backfill    # jednorazowo: odtwarza historię z commitów szablonu (od 22.10)
  python3 historia_cen.py               # zwykły przebieg: dopisz dzisiejsze ceny, przelicz promocje, wpisz do szablonu
"""
import argparse, datetime, json, os, re, statistics, subprocess, sys

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import zbieraj_ceny as z

SZABLON = os.path.join(BAZA, "monitors_1700_template.html")
PLIK = os.path.join(BAZA, "historia_cen.json")
PIERWSZY_COMMIT = "c5296b1"          # 22.10.2026 13:39 — pierwszy stan po naprawie cen
OKNO_DNI = 45
MIN_DNI_OBS, MIN_WSTECZ = 5, 4
PROG_PROMOCJA, PROG_LISTA, PROG_SUPER = 0.08, 0.10, 0.20
MIN_ZL = {"monitor": 60, "pc": 200}
UTRZYMAJ_DNI = 150


def d2n(iso):
    return datetime.date.fromisoformat(iso).toordinal()


def n2d(n):
    return datetime.date.fromordinal(n).isoformat()


# ------------------------------------------------------------------ odczyt szablonu
def stan_szablonu(sz):
    """(data_iso, {sklep: data_weryfikacji}, pozycje) — pozycje: nazwa → {rodzaj, ceny, wyprzedane, ukryty, url}"""
    m = re.search(r"var PRICE_CHECK_ISO = '(\d{4}-\d{2}-\d{2})';", sz)
    ms = re.search(r"var SHOP_VERIFIED = (\{[^;]*\});", sz)
    if not (m and ms):
        raise SystemExit("szablon bez PRICE_CHECK_ISO / SHOP_VERIFIED")
    weryf = json.loads(ms.group(1))
    poz = {}
    wszystkie = sorted(z.wczytaj(sz), key=lambda p: p["start"])
    for i, p in enumerate(wszystkie):
        koniec = wszystkie[i + 1]["start"] if i + 1 < len(wszystkie) else len(sz)
        seg = sz[p["start"]:koniec]
        ms_ = re.search(r"sprzedawcy:\{([^}]*)\}", seg)
        # oferta zewnętrznego sprzedawcy (marketplace MediaMarkt) skacze między sprzedawcami — to nie promocja sklepu
        marketplace = re.findall(r"(\w+):'", ms_.group(1)) if ms_ else []
        poz[p["name"]] = {"rodzaj": p["rodzaj"], "ceny": dict(p["prices"]), "wyprzedane": list(p.get("soldout") or []),
                          "ukryty": bool(p.get("ukryty")), "urls": p["urls"], "marketplace": marketplace}
    return m.group(1), weryf, poz


# ------------------------------------------------------------------ historia
def wczytaj_historie():
    try:
        return json.load(open(PLIK, encoding="utf-8"))
    except Exception:
        return {}


def zapisz_historie(h):
    json.dump(h, open(PLIK, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def dopisz(h, data_iso, weryf, poz):
    """Dopisuje obserwacje dla sklepów zweryfikowanych DZIŚ (weryf[sklep] == data_iso)."""
    dzis = d2n(data_iso)
    for nazwa, p in poz.items():
        for sklep, cena in p["ceny"].items():
            if weryf.get(sklep) != data_iso or not isinstance(cena, int) or cena <= 0:
                continue
            rec = h.setdefault(nazwa, {}).setdefault(sklep, {"p": [], "o": 0})
            if rec["o"] > dzis:
                continue                                  # nie cofamy się w czasie
            if rec["p"] and rec["p"][-1][1] == cena:
                pass
            elif rec["p"] and rec["p"][-1][0] == dzis:
                rec["p"][-1][1] = cena                    # ten sam dzień, nowsza cena
            else:
                rec["p"].append([dzis, cena])
            rec["o"] = dzis
    return h


def przytnij(h, dzis):
    graniczny = dzis - UTRZYMAJ_DNI
    for nazwa in list(h):
        for sklep in list(h[nazwa]):
            rec = h[nazwa][sklep]
            p = rec["p"]
            while len(p) > 1 and p[1][0] <= graniczny:
                p.pop(0)
            if rec["o"] < graniczny:
                del h[nazwa][sklep]
        if not h[nazwa]:
            del h[nazwa]
    return h


def dni_cen(rec, od, do):
    """Lista cen dzień po dniu w [od, do], tylko dni objęte obserwacją (od pierwszego punktu do rec['o'])."""
    if not rec["p"]:
        return []
    start = max(od, rec["p"][0][0])
    koniec = min(do, rec["o"])
    wynik, i = [], 0
    for d in range(start, koniec + 1):
        while i + 1 < len(rec["p"]) and rec["p"][i + 1][0] <= d:
            i += 1
        wynik.append(rec["p"][i][1])
    return wynik


# ------------------------------------------------------------------ promocje
def wczytaj_zebrane():
    """Surowy zrzut z dzisiejszego zbierania (gitignorowany, istnieje tylko w katalogu przebiegu)."""
    try:
        return json.load(open(os.path.join(BAZA, "zebrane_ceny.json"), encoding="utf-8")).get("adresy", {})
    except Exception:
        return {}


def deklaracje(zeb, poz):
    """{(nazwa, sklep): (cena_dziś, promo)} — tylko ceny OK z dzisiejszego zbierania, które mają blok promo."""
    wynik = {}
    for nazwa, p in poz.items():
        for sklep, url in p["urls"].items():
            w = zeb.get(f"{sklep}|{url}")
            if w and w.get("stan") == "ok" and w.get("promo") and isinstance(w.get("cena"), int):
                wynik[(nazwa, sklep)] = (w["cena"], w["promo"])
    return wynik


def wylicz(h, data_iso, poz):
    dzis = d2n(data_iso)
    dekl = deklaracje(wczytaj_zebrane(), poz)
    lista, kody = [], []
    # --- promocje DEKLAROWANE przez sklep (Omnibus: najniższa cena z 30 dni przed obniżką) — od pierwszego dnia
    for (nazwa, sklep), (cena, pr) in dekl.items():
        p = poz[nazwa]
        if p["ukryty"] or sklep in p["wyprzedane"] or sklep in p["marketplace"]:
            continue
        if pr.get("kod"):
            kody.append({"n": nazwa, "sk": sklep, "kod": pr["kod"], "c": cena, "bk": pr.get("bk") or 0})
        omn = pr.get("omn")
        if omn and omn > cena:
            oszcz = omn - cena
            if oszcz >= MIN_ZL[p["rodzaj"]] and cena <= (1 - PROG_PROMOCJA) * omn:
                lista.append({"n": nazwa, "k": p["rodzaj"], "sk": sklep, "c": cena, "r": omn,
                              "p": round(100.0 * oszcz / omn, 1), "o": oszcz, "dni": 30, "min": 0, "t": "s",
                              "kod": pr.get("kod") or "", "bk": pr.get("bk") or 0, "u": p["urls"].get(sklep, "")})
    for nazwa, p in poz.items():
        if p["ukryty"]:
            continue
        for sklep, rec in h.get(nazwa, {}).items():
            if rec["o"] != dzis or sklep in p["wyprzedane"] or sklep in p["marketplace"] or not rec["p"]:
                continue
            aktualna = rec["p"][-1][1]
            if p["ceny"].get(sklep) != aktualna:
                continue                                  # szablon i historia muszą się zgadzać
            dni = dni_cen(rec, dzis - OKNO_DNI, dzis)
            if len(dni) < MIN_DNI_OBS or dzis - rec["p"][0][0] < MIN_WSTECZ:
                continue
            typowa = int(round(statistics.median(dni)))
            oszcz = typowa - aktualna
            if oszcz < MIN_ZL[p["rodzaj"]] or aktualna > (1 - PROG_PROMOCJA) * typowa:
                continue
            wczesniej = [c for _, c in rec["p"][:-1]]
            lista.append({"n": nazwa, "k": p["rodzaj"], "sk": sklep, "c": aktualna, "r": typowa,
                          "p": round(100.0 * oszcz / typowa, 1), "o": oszcz, "dni": len(dni),
                          "min": 1 if (wczesniej and aktualna < min(wczesniej) and len(dni) >= 7) else 0,
                          "t": "h", "kod": "", "bk": 0, "u": p["urls"].get(sklep, "")})
    lista.sort(key=lambda x: (-x["p"], -x["o"], x["n"]))
    # najlepsza oferta na pozycję (jedna pozycja = jeden wpis; sklep o największym spadku)
    widziane, wynik = set(), []
    for x in lista:
        if x["n"] not in widziane:
            widziane.add(x["n"]); wynik.append(x)
    return wynik, kody


def wstaw(sz, data_iso, promocje, kody):
    blok = ("/*PROMO_START*/var PROMOCJE = " +
            json.dumps({"dzien": data_iso, "okno": OKNO_DNI, "prog_lista": int(PROG_LISTA * 100),
                        "prog_super": int(PROG_SUPER * 100), "lista": promocje, "kody": kody},
                       ensure_ascii=False, separators=(",", ":")) + ";/*PROMO_END*/")
    if "/*PROMO_START*/" in sz:
        return re.sub(r"/\*PROMO_START\*/.*?/\*PROMO_END\*/", lambda m: blok, sz, count=1, flags=re.S)
    i = sz.index("var PRICE_CHECK_LABEL")
    return sz[:i] + blok + "\n" + sz[i:]


# ------------------------------------------------------------------ odtworzenie z git
def backfill():
    h = {}
    commity = subprocess.run(["git", "log", "--reverse", "--format=%H", f"{PIERWSZY_COMMIT}^..HEAD", "--",
                              "monitors_1700_template.html"], capture_output=True, text=True, cwd=BAZA).stdout.split()
    for c in commity:
        blob = subprocess.run(["git", "show", f"{c}:monitors_1700_template.html"], capture_output=True,
                              text=True, cwd=BAZA).stdout
        try:
            data_iso, weryf, poz = stan_szablonu(blob)
        except SystemExit:
            continue
        dopisz(h, data_iso, weryf, poz)
    return h, len(commity)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--bez-szablonu", action="store_true", help="nie modyfikuj szablonu (tylko historia)")
    a = ap.parse_args()
    sz = open(SZABLON, encoding="utf-8").read()
    data_iso, weryf, poz = stan_szablonu(sz)
    if a.backfill:
        h, n = backfill()
        print(f"odtworzono historię z {n} commitów")
    else:
        h = wczytaj_historie()
    dopisz(h, data_iso, weryf, poz)
    przytnij(h, d2n(data_iso))
    zapisz_historie(h)
    promocje, kody = wylicz(h, data_iso, poz)
    if not a.bez_szablonu:
        nowy = wstaw(sz, data_iso, promocje, kody)
        if nowy != sz:
            open(SZABLON, "w", encoding="utf-8").write(nowy)
    n_obs = sum(len(r["p"]) for s in h.values() for r in s.values())
    print(f"historia: {len(h)} pozycji, {n_obs} punktów zmiany ceny | promocje dziś ({data_iso}): "
          f"{len(promocje)} (≥{int(PROG_LISTA*100)}%: {sum(1 for x in promocje if x['p'] >= PROG_LISTA*100)}) | "
          f"deklarowane przez sklep: {sum(1 for x in promocje if x['t']=='s')} | ceny z kodem: {len(kody)}")
    for x in promocje[:10]:
        zr = "Omnibus 30 dni" if x["t"] == "s" else f"typowo, {x['dni']} dni obserwacji"
        print(f"   −{x['p']:4.1f}%  {x['c']:5d} zł (ref. {x['r']} zł, {zr}, {x['sk']}{', kod '+x['kod'] if x['kod'] else ''})  {x['n'][:56]}")
    return promocje


if __name__ == "__main__":
    main()
