# Grid Overdrive

Porównywarka 57 monitorów gamingowych QHD (240–500 Hz) i 492 zestawów PC (5000–9000 zł).

Ceny dla wpisów kupowanych w x-kom.pl lub Morele.net (50 z 57 monitorów) są odświeżane
automatycznie, raz dziennie, przez zaplanowane zadanie Claude Code (Routine). Pozostałe
7 wpisów (Media Expert) blokuje automatyczne pobieranie (HTTP 403 nawet dla prostego
zapytania) i wymaga ręcznej weryfikacji — oznaczone w metodyce na stronie.

Strona: https://grzesko48.github.io/grid-overdrive/

## Jak się buduje stronę

**Źródłem prawdy jest `monitors_1700_template.html`.** Trzyma cały kod, dane i ceny; obrazy
(10 MB base64) leżą osobno, żeby szablon dało się otwierać i edytować jak normalny plik.

```
monitors_1700_template.html + images/*.json  ──build_merged.py──►  index.html   (GitHub Pages)
                                                               └►  artifact.html (publikacja artefaktu)
```

```bash
python3 build_merged.py
```

**Dwa wyjścia, bo dwa miejsca publikacji mają różne wymagania:**
- `index.html` — pełny dokument (`<!doctype>`, `<html lang="pl">`, `charset`, `viewport`).
  GitHub Pages serwuje plik tak, jak leży, i nie dokłada niczego od siebie.
- `artifact.html` — goły fragment bez szkieletu, bo platforma artefaktu owija treść własnym
  szkieletem. Nie jest trzymany w repozytorium (powstaje przy budowaniu) — do publikacji
  artefaktu używać **jego**, nie `index.html`, inaczej `<html>` zagnieździ się w `<body>`.

`rozdziel_obrazy.py` robi krok odwrotny (`index.html` → szablon + `images/*.json`). Potrzebny
tylko przy odtwarzaniu szablonu z gotowej strony; obieg jest bezstratny i sprawdzalny sumą SHA.

### Czego nie robić
- **Nie edytować `index.html` ręcznie** — to plik wynikowy, przebudowa go nadpisze.
- **Nie publikować `index.html` jako artefaktu** — do tego jest `artifact.html`.

## Pliki automatyzacji
- `check_list_auto.json` — 50 wpisów (x-kom.pl / Morele.net) do codziennego sprawdzenia
- `check_list_manual.json` — 7 wpisów (Media Expert) poza zasięgiem automatyzacji
- `apply_price_updates.py` — nanosi zebrane ceny na `index.html` **oraz na szablon**,
  aktualizuje `prices{}` danego wpisu i etykietę „ostatnia weryfikacja"
- `price_updates.json` — plik roboczy zapisywany przez Routine w każdym przebiegu

Dopisywanie cen do szablonu jest konieczne, bo inaczej szablon zostaje w tyle za stroną:
przez tydzień ceny szły wyłącznie do `index.html` i szablon miał AOC Q27G4ZR za 789 zł, gdy
na stronie było 899 zł — przebudowa cofnęłaby wtedy cały tydzień pracy Routine.

## Dane źródłowe
- `audit/` — audyt inżynieryjny 57 monitorów (lab + specyfikacja producenta), `STATUS.md`
- `pc_audit/` — pipeline i dane sekcji PC (Hard-PC, PlugNPlay, GoblinPC), `STATUS.md`
- `images/monitors.json`, `images/pcs.json` — kadry produktowe w base64, wstawiane przy budowaniu
