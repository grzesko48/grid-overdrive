#!/usr/bin/env python3
"""Test (bez sieci): odczyt promocji ze stron sklepów i wyliczanie promocji z historii cen.

Strony-fixtury to wycinki prawdziwych stron zapisanych 30.10.2026. Pilnujemy dwóch rzeczy:
  1. odczyt „najniższej ceny z 30 dni" / ceny bez kodu / kodu daje wartości ze strony, a strony BEZ promocji
     (także z pułapkami: cudzy tekst Omnibus w karuzeli, przekreślona cena bez odznaki) dają None;
  2. wyliczanie promocji: próg, minimalna historia, wykluczenie marketplace/wyprzedanych/niezweryfikowanych.
"""
import os, sys
BAZA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BAZA)
import zbieraj_ceny as z
import historia_cen as h

F = os.path.join(BAZA, "tests_fixtures")
bledy = []


def ok(w, opis):
    if not w:
        bledy.append(opis); print("  BŁĄD:", opis)


def strona(n):
    return open(os.path.join(F, n), encoding="utf-8").read()


# 1. odczyt ze stron
r = z.promo_ze_strony("morele", "", strona("promo_morele_kod.html"))
ok(r == {"omn": 1569, "bk": 1569, "kod": "BLACK26"}, f"Morele z kodem: {r}")
ok(z.promo_ze_strony("morele", "", strona("promo_morele_bez.html")) is None, "Morele bez promocji powinno dać None")
r = z.promo_ze_strony("xkom", "", strona("promo_xkom_obnizka.html"))
ok(r is not None and r["omn"] == 669 and r["bk"] == 729, f"x-kom z obniżką: {r}")
ok(z.promo_ze_strony("xkom", "", strona("promo_xkom_bez.html")) is None, "x-kom: cudzy tekst Omnibus w karuzeli nie jest promocją")
r = z.promo_ze_strony("hardpc", "", strona("promo_hardpc_obnizka.html"))
ok(r is not None and r["omn"] == 11349, f"Hard-PC z obniżką: {r}")
ok(z.promo_ze_strony("hardpc", "", strona("promo_hardpc_old_bez_odznaki.html")) is None,
   "Hard-PC: przekreślona cena bez odznaki nie jest promocją")
ok(z._zl("1 569,00 zł") == 1569 and z._zl("2 195,67 zł") == 2196 and z._zl(None) is None, "parsowanie kwot")

# 2. wyliczanie z historii
D = h.d2n("2026-10-30")
def rec(punkty, ost=D):
    return {"p": [[h.d2n(d), c] for d, c in punkty], "o": h.d2n(ost) if isinstance(ost, str) else ost}
def poz(**kw):
    p = {"rodzaj": "monitor", "ceny": {"morele": 1000}, "wyprzedane": [], "ukryty": False, "urls": {"morele": "u"}, "marketplace": []}
    p.update(kw); return p
hist = {"A": {"morele": rec([("2026-10-20", 1300), ("2026-10-28", 1000)])}}          # 8 dni po 1300, 3 dni po 1000
l, k = h.wylicz(hist, "2026-10-30", {"A": poz()})
ok(len(l) == 1 and l[0]["t"] == "h" and 20 <= l[0]["p"] <= 24, f"promocja z historii: {l}")
hist2 = {"A": {"morele": rec([("2026-10-27", 1300), ("2026-10-29", 1000)])}}          # historia za krótka (3 dni)
ok(h.wylicz(hist2, "2026-10-30", {"A": poz()})[0] == [], "historia krótsza niż 4 dni nie daje promocji")
ok(h.wylicz(hist, "2026-10-30", {"A": poz(marketplace=["morele"])})[0] == [], "marketplace nie jest promocją")
ok(h.wylicz(hist, "2026-10-30", {"A": poz(wyprzedane=["morele"])})[0] == [], "wyprzedane nie jest promocją")
ok(h.wylicz(hist, "2026-10-30", {"A": poz(ukryty=True)})[0] == [], "ukryta pozycja nie jest promocją")
hist3 = {"A": {"morele": rec([("2026-10-20", 1300), ("2026-10-28", 1000)], ost="2026-10-29")}}   # sklep niezweryfikowany dziś
ok(h.wylicz(hist3, "2026-10-30", {"A": poz()})[0] == [], "sklep niezweryfikowany dziś nie daje promocji")
hist4 = {"A": {"morele": rec([("2026-10-20", 1000), ("2026-10-28", 970)])}}            # −3%: poniżej progu
ok(h.wylicz(hist4, "2026-10-30", {"A": poz(ceny={"morele": 970})})[0] == [], "spadek poniżej 8% nie jest promocją")

print("\nTEST ZALICZONY: promocje" if not bledy else f"\nTEST NIEZALICZONY: {len(bledy)} błędów")
sys.exit(1 if bledy else 0)
