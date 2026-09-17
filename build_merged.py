#!/usr/bin/env python3
"""monitors_1700_template.html + images/*.json  →  index.html

Krok budowania strony. Szablon trzyma cały kod, dane i ceny, a obrazy — 10 MB base64 — leżą
obok w dwóch plikach, żeby szablon dało się otwierać i edytować jak normalny plik.

ŹRÓDŁEM PRAWDY JEST SZABLON. index.html jest wynikiem i nie należy go edytować ręcznie:
`apply_price_updates.py` (Routine cen) też pisze do szablonu i dopiero potem uruchamia ten skrypt.
Wcześniej ceny szły prosto do index.html, przez co szablon się rozjeżdżał i przebudowa cofała
tydzień aktualizacji — stąd ta zasada.

Kontrola na wyjściu: strona musi być samowystarczalna (zero żądań sieciowych przy otwarciu),
mieć komplet obrazów i domknięty szkielet dokumentu.
"""
import json, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
J = lambda *p: os.path.join(BASE, *p)

MAPY = [
    ("IMG",  "/*IMG_JSON*/{}",    "images/monitors.json"),
    ("PIMG", "/*PC_IMG_JSON*/{}", "images/pcs.json"),
]


def main():
    szablon = open(J("monitors_1700_template.html"), encoding="utf-8").read()
    wynik = szablon

    for zmienna, znacznik, plik in MAPY:
        assert wynik.count(znacznik) == 1, \
            f"{znacznik}: wystąpień {wynik.count(znacznik)}, oczekiwano jednego"
        surowy = open(J(plik), encoding="utf-8").read()
        dane = json.loads(surowy)                      # kontrola poprawności przed wstawieniem
        assert dane, f"{plik}: pusta mapa obrazów"
        wynik = wynik.replace(znacznik, surowy)
        print(f"  {zmienna:<5} ← {plik:<22} {len(dane):>4} obrazów")

    # Każdy klucz img: w danych musi mieć swój obraz — inaczej karta pokaże pustą ramkę.
    obrazy = set()
    for _, _, plik in MAPY:
        obrazy |= set(json.loads(open(J(plik), encoding="utf-8").read()))
    uzyte = set(re.findall(r"\{img:['\"]([^'\"]+)['\"]", wynik))
    brak = sorted(uzyte - obrazy)
    assert not brak, f"pozycje bez obrazu ({len(brak)}): {brak[:5]}"

    # Zasoby POBIERANE przy otwarciu. Liczą się tylko te, które przeglądarka ściąga sama:
    # src=…, <link rel=stylesheet href=…>, @import, url(…) w CSS. Zwykłe <a href> do sklepów
    # (aoc.com, goblinpc.pl, x-kom…) to odnośniki dla czytelnika, nie żądania — nie wolno ich
    # mylić z zależnościami, bo wtedy kontrola krzyczy na każdą kartę produktu.
    # Google Fonts jest świadomie przyjętą zależnością tej strony (Rajdhani/Inter/JetBrains Mono)
    # i mieści się w dozwolonych źródłach artefaktu. Bez sieci kroje schodzą do zastępczych.
    DOZWOLONE = ("https://fonts.googleapis.com", "https://fonts.gstatic.com")
    pobierane = re.findall(r'\bsrc\s*=\s*"([^"]{0,300})"', wynik)
    pobierane += re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="([^"]{0,300})"', wynik)
    pobierane += re.findall(r'@import\s+(?:url\()?["\']([^"\']{0,300})', wynik)
    pobierane += re.findall(r'url\(\s*["\']?(https?://[^"\')]{0,300})', wynik)
    obce = [u for u in pobierane
            if re.match(r'https?://|//', u) and not u.startswith(DOZWOLONE)]
    assert not obce, f"nieoczekiwane żądania sieciowe przy otwarciu: {obce[:3]}"
    assert "<meta charset" in wynik, "brak deklaracji kodowania — polskie znaki się posypią"
    assert "/*IMG_JSON*/" not in wynik and "/*PC_IMG_JSON*/" not in wynik, \
        "w wyniku został niezastąpiony znacznik"

    # ── dwa wyjścia, bo dwa miejsca publikacji mają różne wymagania ──────────────
    # Artefakt sam owija treść w szkielet dokumentu (dokłada charset i viewport), więc
    # dostaje goły fragment. GitHub Pages nie owija niczego — i właśnie dlatego żywa strona
    # chodziła w trybie zgodności wstecznej (document.compatMode = BackCompat), a na telefonie
    # składała się na 980 px i była pomniejszana do 38%, bo brakowało meta viewport.
    # Stąd pełny szkielet wyłącznie w pliku dla Pages.
    fragment = wynik
    i = fragment.index("<style")
    glowa, tresc = fragment[:i], fragment[i:]
    assert '<meta charset="utf-8">' in glowa, "nagłówek bez charset"
    glowa = glowa.replace(
        '<meta charset="utf-8">',
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">',
        1)
    pelny = ('<!doctype html>\n<html lang="pl">\n<head>\n'
             + glowa.strip() + "\n</head>\n<body>\n" + tresc.rstrip() + "\n</body>\n</html>\n")

    for nazwa, tekst in (("index.html", pelny), ("artifact.html", fragment)):
        open(J(nazwa), "w", encoding="utf-8").write(tekst)

    # kontrola wyjścia dla Pages: tryb standardowy i skala na telefonie
    assert pelny.startswith("<!doctype html>"), "brak DOCTYPE — przeglądarka wejdzie w tryb zgodności"
    assert 'name="viewport"' in pelny, "brak meta viewport — telefon pomniejszy stronę"
    assert pelny.rstrip().endswith("</html>"), "dokument nie jest domknięty"
    assert "<title>" in pelny.split("</head>")[0], "tytuł poza nagłówkiem"
    assert 'name="viewport"' not in fragment, "fragment dla artefaktu nie powinien mieć szkieletu"

    print(f"  index.html    — {os.path.getsize(J('index.html'))/1024/1024:.2f} MB  "
          f"(pełny dokument: DOCTYPE + viewport → GitHub Pages)")
    print(f"  artifact.html — {os.path.getsize(J('artifact.html'))/1024/1024:.2f} MB  "
          f"(goły fragment → publikacja jako artefakt)")
    print(f"  pozycji z obrazem: {len(uzyte)}")


if __name__ == "__main__":
    main()
