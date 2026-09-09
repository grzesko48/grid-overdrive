# Grid Overdrive

Porównywarka 57 monitorów gamingowych QHD (240-500 Hz) i 46 zestawów PC (5000-9000 zł).

Ceny dla wpisów kupowanych w x-kom.pl lub Morele.net (50 z 57 monitorów) są odświeżane
automatycznie, raz dziennie, przez zaplanowane zadanie Claude Code (Routine). Pozostałe
7 wpisów (Media Expert) blokuje automatyczne pobieranie (HTTP 403 nawet dla prostego
zapytania) i wymaga ręcznej weryfikacji — oznaczone w metodyce na stronie.

Strona: https://grzesko48.github.io/grid-overdrive/

## Pliki automatyzacji
- `check_list_auto.json` — 50 wpisów (x-kom.pl / Morele.net) do codziennego sprawdzenia
- `check_list_manual.json` — 7 wpisów (Media Expert) poza zasięgiem automatyzacji
- `apply_price_updates.py` — nanosi zebrane ceny na `index.html`, aktualizuje też
  `prices{}` danego wpisu i etykietę "ostatnia weryfikacja"
- `price_updates.json` — plik roboczy zapisywany przez Routine w każdym przebiegu (WebFetch
  wynik dla każdego z 50 adresów), niezachowywany między przebiegami
