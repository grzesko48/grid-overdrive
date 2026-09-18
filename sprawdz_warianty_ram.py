#!/usr/bin/env python3
"""Odczytuje z konfiguratora sklepu realną dopłatę za pamięć i melduje, czego brakuje.

Użytkownik chce, żeby 16 GB i 32 GB były DWIEMA osobnymi pozycjami przy każdym zestawie.
Dziś wariant 32 GB ma tylko 68 zestawów ze 195, które startują z 16 GB — reszta nie ma go
wcale. Dopłaty nie wolno zgadywać ani uśredniać: konfigurator Hard-PC podaje ją wprost
w opcji wyboru (`32GB (+899,00 zł)`), więc bierzemy ją stamtąd albo nie bierzemy w ogóle.

Skrypt niczego nie dopisuje do danych — zbiera dopłaty i wypisuje raport. Dopisanie wpisu
to osobny krok, bo nowa pozycja zmienia normalizację ocen w całym zbiorze.
"""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor

BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
from zbieraj_ceny import wczytaj, pobierz, REGULAMIN                # noqa: E402

# `32GB (+899,00 zł)` w <option> konfiguratora. Bierzemy TYLKO opcje z jawną dopłatą —
# „32GB" bez kwoty oznacza, że sklep nie podał ceny, a nie że rozszerzenie jest darmowe.
OPCJA = re.compile(r"<option[^>]*>\s*(\d{2,3})\s*GB\s*\(\+\s*([\d\s ,.]+)\s*z[łl]\s*\)", re.I)


def na_liczbe(t):
    return round(float(re.sub(r"[^\d,]", "", t).replace(",", ".")))


def dop(seg):
    """Mapa 'rozmiar RAM' -> dopłata, z konfiguratora strony produktu."""
    return {int(r): na_liczbe(c) for r, c in OPCJA.findall(seg)}


def main():
    sz = open(os.path.join(BAZA, "monitors_1700_template.html"), encoding="utf-8").read()
    poz = [p for p in wczytaj(sz) if p["rodzaj"] == "pc" and not p["ukryty"]]

    maja_32 = {p["name"].split(" (custom:")[0] for p in poz if "(custom:" in p["name"]}
    kandydaci = [p for p in poz
                 if "(custom:" not in p["name"]
                 and p["ram"].startswith("16")
                 and p["name"] not in maja_32
                 and p["urls"].get("hardpc", "").startswith("http")]

    print(f"zestawów 16 GB bez wariantu 32 GB, z adresem Hard-PC: {len(kandydaci)}",
          file=sys.stderr)

    def zadanie(p):
        u = p["urls"]["hardpc"]
        if not REGULAMIN.wolno(u):
            return {"name": p["name"], "stan": "robots"}
        kod, s = pobierz(u)
        if kod != 200 or not s:
            return {"name": p["name"], "stan": "blad", "kod": kod}
        opcje = dop(s)
        if 32 not in opcje:
            return {"name": p["name"], "stan": "brak_opcji_32",
                    "widziane": sorted(opcje)}
        return {"name": p["name"], "img": p["img"], "stan": "ok",
                "priceBare": p["priceBare"], "doplata_32gb": opcje[32],
                "priceBare_32gb": (p["priceBare"] or 0) + opcje[32],
                "doplata_os": p["price"] - (p["priceBare"] or p["price"]),
                "url": u}

    wyniki = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, w in enumerate(ex.map(zadanie, kandydaci), 1):
            wyniki.append(w)
            if i % 25 == 0 or i == len(kandydaci):
                print(f"  {i}/{len(kandydaci)}", file=sys.stderr)

    ok = [w for w in wyniki if w["stan"] == "ok"]
    json.dump({"kandydatow": len(kandydaci), "z_doplata": len(ok), "wyniki": wyniki},
              open(os.path.join(BAZA, "raport_ram.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    from collections import Counter
    print(f"\nz odczytaną dopłatą: {len(ok)}/{len(kandydaci)}")
    print("stany:", dict(Counter(w["stan"] for w in wyniki)))
    if ok:
        kwoty = Counter(w["doplata_32gb"] for w in ok)
        print("rozkład dopłat za 32 GB:")
        for k, n in kwoty.most_common():
            print(f"   {k:5d} zł  ×{n}")
    print("\n→ raport_ram.json (nic nie dopisano do danych)")


if __name__ == "__main__":
    main()
