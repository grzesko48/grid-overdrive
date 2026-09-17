#!/usr/bin/env python3
"""index.html  →  monitors_1700_template.html + images/monitors.json + images/pcs.json

Odwrotność build_merged.py. Wyciąga dwie mapy obrazów (base64) z gotowej strony i zostawia
w ich miejsce znaczniki, których szuka build_merged.py.

Po co to istnieje: przez jedną sesję źródłem prawdy był szablon leżący w katalogu roboczym
sesji, a Routine dopisywała ceny wyłącznie do index.html. Katalog sesji zniknął razem ze
skryptem scalającym, a kopia szablonu w audit/ zostawała coraz bardziej w tyle za cenami
(AOC Q27G4ZR: 789 zł w szablonie wobec 899 zł na żywej stronie). Ten skrypt pozwala odtworzyć
szablon z aktualnej strony, więc dryf cen nigdy nie kasuje pracy.

Blok obrazów jest przenoszony DOSŁOWNIE, znak w znak — nie przez parsowanie i ponowny zapis.
Dzięki temu scalenie z powrotem daje plik bajtowo identyczny i da się to sprawdzić sumą SHA.
"""
import json, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
J = lambda *p: os.path.join(BASE, *p)

# (nazwa zmiennej w JS, znacznik w szablonie, plik docelowy)
MAPY = [
    ("IMG",  "/*IMG_JSON*/",    "images/monitors.json"),
    ("PIMG", "/*PC_IMG_JSON*/", "images/pcs.json"),
]


def wytnij_literal(s, poz):
    """Zwraca (początek, koniec) literału obiektu zaczynającego się od '{' na pozycji `poz`.

    Skanuje z poszanowaniem łańcuchów, więc nawias klamrowy w treści wartości nie urywa bloku.
    Base64 nawiasów nie zawiera, ale nie opieramy na tym poprawności.
    """
    assert s[poz] == "{", f"oczekiwano '{{' na {poz}, jest {s[poz]!r}"
    i, glebokosc, w_lancuchu, ucieczka = poz, 0, False, False
    while i < len(s):
        z = s[i]
        if w_lancuchu:
            if ucieczka:
                ucieczka = False
            elif z == "\\":
                ucieczka = True
            elif z == '"':
                w_lancuchu = False
        else:
            if z == '"':
                w_lancuchu = True
            elif z == "{":
                glebokosc += 1
            elif z == "}":
                glebokosc -= 1
                if glebokosc == 0:
                    return poz, i + 1
        i += 1
    raise ValueError("nie znaleziono domknięcia literału")


def zdejmij_szkielet(s):
    """Usuwa DOCTYPE/html/head/body, jeśli plik jest pełnym dokumentem.

    Szablon ma trzymać samą treść — szkielet dokłada build_merged.py przy budowaniu wersji
    dla GitHub Pages. Bez tego kroku szkielet trafiłby do szablonu i kolejna budowa owinęłaby
    stronę po raz drugi, zagnieżdżając <html> w <body>.
    """
    if not s.lstrip().lower().startswith("<!doctype"):
        return s, False
    glowa = re.search(r"<head[^>]*>(.*?)</head>", s, re.S | re.I)
    cialo = re.search(r"<body[^>]*>(.*?)</body>", s, re.S | re.I)
    assert glowa and cialo, "pełny dokument bez <head>/<body> — nie wiem, gdzie przebiega granica"
    g = glowa.group(1).strip()
    # viewport dokłada build, więc w szablonie go nie zostawiamy
    g = re.sub(r'\s*<meta name="viewport"[^>]*>', "", g)
    return g + "\n\n" + cialo.group(1).strip() + "\n", True


def main():
    zrodlo = J("index.html")
    s = open(zrodlo, encoding="utf-8").read()
    os.makedirs(J("images"), exist_ok=True)

    szablon, zdjeto = zdejmij_szkielet(s)
    if zdjeto:
        print("  zdjęto szkielet dokumentu (DOCTYPE/head/body) — szablon trzyma samą treść")
    for zmienna, znacznik, plik in MAPY:
        igla = f"  var {zmienna} = "
        i = szablon.index(igla)
        start_lit = i + len(igla)
        a, b = wytnij_literal(szablon, start_lit)
        surowy = szablon[a:b]

        # kontrola: blok musi być poprawnym JSON-em i mieć same wartości data:
        dane = json.loads(surowy)
        assert dane, f"{zmienna}: pusta mapa"
        zle = [k for k, v in dane.items() if not str(v).startswith("data:image")]
        assert not zle, f"{zmienna}: wartości spoza data:image — {zle[:3]}"

        open(J(plik), "w", encoding="utf-8").write(surowy)
        szablon = szablon[:a] + znacznik + "{}" + szablon[b:]
        print(f"  {zmienna:<5} → {plik:<22} {len(dane):>4} obrazów, {len(surowy)/1024/1024:5.2f} MB")

    open(J("monitors_1700_template.html"), "w", encoding="utf-8").write(szablon)
    print(f"  szablon → monitors_1700_template.html   {len(szablon)/1024:.0f} KB")

    # kontrola: znaczniki muszą być dokładnie po jednym, inaczej scalanie trafi w złe miejsce
    for _, znacznik, _ in MAPY:
        assert szablon.count(znacznik) == 1, f"{znacznik}: wystąpień {szablon.count(znacznik)}"

    # W szablonie nie może zostać żaden OSADZONY obraz. Samo wystąpienie ciągu „data:image"
    # nie wystarcza za dowód: strona cytuje ten ciąg w nocie opisującej dawny błąd podwójnie
    # doklejonego nagłówka. Liczy się długość — prawdziwy kadr to dziesiątki kilobajtów.
    duze = [m.group(0)[:40] for m in re.finditer(r'data:image[^"\')\s]{500,}', szablon)]
    assert not duze, f"w szablonie został osadzony obraz: {duze[:2]}"
    print(f"  kontrola: znaczniki po jednym, zero osadzonych kadrów "
          f"(wzmianek „data:image” w treści: {szablon.count('data:image')})")


if __name__ == "__main__":
    main()
