#!/usr/bin/env python3
"""Liczy różnicę między ocenami sprzed naprawy a obecnymi — W PUNKTACH, nie w miejscach.

Dlaczego nie w miejscach: miejsce jest właściwością sąsiedztwa, nie pozycji. Pomiar
z 18 września 2026 pokazał, że 27 zestawów nie zmieniło ANI JEDNEGO punktu, a mimo to
wszystkie zmieniły miejsce (średnio o 27, maksymalnie o 63), oraz że ten sam niezmieniony
ranking przy innej regule remisu daje inne miejsce 281 z 355 zestawów. Miejsce mierzyłoby
niestabilność sortowania, nie skutek naprawy.

Rozdzielamy też przyczyny: samą naprawę opłacalności od reszty zmian tego dnia (usunięcie
duplikatów, korekta ceny systemu). Bez tego rozdziału sekcja przypisałaby naprawie ruch,
którego nie wywołała.
"""
import argparse, json, os, re, subprocess, sys
from collections import Counter

BAZA = os.path.dirname(os.path.abspath(__file__))
PLIK = "monitors_1700_template.html"
KUBELKI = [(0, "bez zmiany"), (1, "1 punkt"), (2, "2 punkty"), (3, "3 punkty"),
           (4, "4 punkty"), (5, "5 punktów"), (6, "6 punktów i więcej")]


def stan(tresc):
    pkt = [(m.start(), "pc") for m in re.finditer(r'\{img:"p[^"]*", name:"', tresc)]
    pkt += [(m.start(), "monitor") for m in re.finditer(r"\{img:'\d\d_[^']+', name:'", tresc)]
    pkt.sort()
    out = {}
    for i, (a, rodzaj) in enumerate(pkt):
        b = pkt[i + 1][0] if i + 1 < len(pkt) else len(tresc)
        seg = tresc[a:b]
        if re.search(r"(?<![A-Za-z])ukryty:1", seg):
            continue
        sc = re.search(r"scores:\{([^}]*)\}", seg)
        nm = re.search(r"name:['\"]([^'\"]*)", seg)
        cn = re.search(r"(?<![A-Za-z])price:(\d+)", seg)
        if not (sc and nm and cn):
            continue
        s = {k: int(v) for k, v in re.findall(r"(\w+):(\d+)", sc.group(1))}
        kl = "ultra" if rodzaj == "pc" else "overall"
        if kl in s:
            out[nm.group(1)] = {"wynik": s[kl], "cena": int(cn.group(1)), "rodzaj": rodzaj}
    return out


def z_commita(c):
    t = subprocess.run(["git", "show", f"{c}:{PLIK}"], capture_output=True, text=True,
                       cwd=BAZA).stdout
    if not t:
        sys.exit(f"nie odczytano {PLIK} z {c}")
    return stan(t)


def porownaj(A, B, rodzaj):
    wsp = [n for n in A if n in B and A[n]["rodzaj"] == rodzaj]
    delty = {n: B[n]["wynik"] - A[n]["wynik"] for n in wsp}
    kub = Counter()
    for d in delty.values():
        kub[min(abs(d), 6)] += 1
    return wsp, delty, kub


def rekomendacje(stanD, rodzaj, progi):
    """Najlepiej oceniony zestaw mieszczący się w progu — to jest to, co czytelnik
    realnie czyta z rankingu przy swoim budżecie."""
    out = {}
    poz = [(n, d) for n, d in stanD.items() if d["rodzaj"] == rodzaj]
    for p in progi:
        kand = [(n, d) for n, d in poz if d["cena"] <= p]
        if kand:
            kand.sort(key=lambda x: (-x[1]["wynik"], x[1]["cena"], x[0]))
            out[p] = kand[0][0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--przed", default="1c77dfe", help="stan przed naprawą opłacalności")
    ap.add_argument("--po-naprawie", default="7ca3127", help="stan zaraz po naprawie")
    a = ap.parse_args()

    A = z_commita(a.przed)
    B = z_commita(a.po_naprawie)
    C = stan(open(os.path.join(BAZA, PLIK), encoding="utf-8").read())

    raport = {"przed": a.przed, "po_naprawie": a.po_naprawie, "sekcje": {}}
    progi = list(range(6000, 11001, 500))

    for rodzaj, etyk in (("pc", "zestawy"), ("monitor", "monitory")):
        wsp, dAC, kubAC = porownaj(A, C, rodzaj)
        _, dAB, _ = porownaj(A, B, rodzaj)
        _, dBC, _ = porownaj(B, C, rodzaj)

        zmienilo = sum(1 for d in dAC.values() if d != 0)
        istotne = sum(1 for d in dAC.values() if abs(d) >= 3)
        duze = sorted([(n, d) for n, d in dAC.items() if abs(d) >= 6],
                      key=lambda x: -abs(x[1]))

        rA = rekomendacje(A, rodzaj, progi) if rodzaj == "pc" else {}
        rC = rekomendacje(C, rodzaj, progi) if rodzaj == "pc" else {}
        zm_rek = [{"prog": p, "przed": rA.get(p), "po": rC.get(p)}
                  for p in progi if p in rA and p in rC and rA[p] != rC[p]]

        raport["sekcje"][etyk] = {
            "porownanych": len(wsp),
            "zmienilo_ocene": zmienilo,
            "zmienilo_o_3_lub_wiecej": istotne,
            "kubelki": [{"prog": k, "etykieta": e, "ile": kubAC.get(k, 0)} for k, e in KUBELKI],
            "skrajne": {"w_dol": min(dAC.values()) if dAC else 0,
                        "w_gore": max(dAC.values()) if dAC else 0},
            "z_samej_naprawy": sum(1 for d in dAB.values() if d != 0),
            "z_reszty_dnia": sum(1 for d in dBC.values() if d != 0),
            "maks_z_reszty_dnia": max((abs(d) for d in dBC.values()), default=0),
            "duze_zmiany": [{"nazwa": n, "delta": d} for n, d in duze],
            "progi_budzetu": len(rA),
            "progi_ze_zmiana": zm_rek,
        }

    json.dump(raport, open(os.path.join(BAZA, "porownanie_rankingow.json"), "w",
                           encoding="utf-8"), ensure_ascii=False, indent=1)

    for etyk, d in raport["sekcje"].items():
        print(f"=== {etyk.upper()} ===")
        print(f"   porównanych: {d['porownanych']}   zmieniło ocenę: {d['zmienilo_ocene']}"
              f"   o 3 punkty i więcej: {d['zmienilo_o_3_lub_wiecej']}")
        print(f"   kubełki: " + "  ".join(f"{k['prog']}→{k['ile']}" for k in d['kubelki']))
        print(f"   skrajne: {d['skrajne']['w_dol']} … +{d['skrajne']['w_gore']} pkt")
        print(f"   z samej naprawy: {d['z_samej_naprawy']}   z reszty dnia: "
              f"{d['z_reszty_dnia']} (maks {d['maks_z_reszty_dnia']} pkt)")
        if d["progi_budzetu"]:
            print(f"   progi budżetu: {d['progi_budzetu']}   zmieniła się rekomendacja w: "
                  f"{len(d['progi_ze_zmiana'])}")
            for z in d["progi_ze_zmiana"]:
                print(f"      {z['prog']} zł: {str(z['przed'])[:40]} → {str(z['po'])[:40]}")
        if d["duze_zmiany"]:
            print(f"   zmian o 6+ punktów: {len(d['duze_zmiany'])}")
            for x in d["duze_zmiany"][:4]:
                print(f"      {x['delta']:+d} pkt  {x['nazwa'][:52]}")
        print()


if __name__ == "__main__":
    main()
