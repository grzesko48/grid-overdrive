# PC section expansion — ZAKOŃCZONE (9.09.2026)

Zadanie z /rada-firmy (9.09.2026): zebrać wszystkie PC 5-9k zł z Hard-PC.pl, sprawdzić realny
koszt customizacji RAM do 32GB, dodać warianty custom jako osobne pozycje rankingu, rozbudować
o wymiar długowieczności GPU, uwzględnić dysk, zrobić to samo dla GoblinPC, naprawić duplikaty
w filtrze GPU, poprawić szatę graficzną żeby pozycje się nie zlewały.

## Wynik
- 402 unikalne zestawy Hard-PC.pl (5-9k zł, deduplikowane po URL) + 3 modele GoblinPC.pl
  (potwierdzone jako CAŁY katalog sklepu w tym przedziale — sklep ma tylko 7 modeli w ogóle).
- 112 configów miało bazowo 16GB RAM — dla każdego sprawdzono w LIVE konfiguratorze sklepu
  realną cenę opcji "32GB RAM" (WebFetch był blokowany 403 przez Hard-PC — użyto Browser tools).
  Cena NIE jest uniwersalna: 899 zł typowo dla DDR5 (1x16GB), 449 zł dla DDR4 (2x8GB), pojedyncze
  wyjątki (500 zł), 13 configów bez tej opcji w ogóle.
- 100 wariantów "(custom: 32GB RAM)" dodanych jako osobne pozycje = baza + dopłata.
- Naprawiono duplikaty starszej próbki (7 Hard-PC + 3 GoblinPC) już obecnej w pc_data.py z
  wcześniejszej fazy tej samej sesji — usunięto przed scaleniem żeby nie liczyć produktów 2x.
- Nowy wymiar `longevity` (1-100): kalibrowany tak, że RTX 5070 (tier 6) daje ~1 rok dłużej
  komfortowej gry niż RTX 5060 (tier 3) — dokładnie przykład z briefu. Modyfikatory: VRAM
  (8GB=-0.3y, 16GB=+0.3y), RAM (32GB=+0.15y, 16GB=-0.15y).
- Nowy `ultra` score = perf*0.28 + longevity*0.30 + value*0.22 + components*0.12 + features*0.08
  — domyślny widok "Ranking" i domyślna opcja sortowania.
- GPU dedup: `normalizeGpu()` w JS (i odpowiednik w Pythonie dla danych źródłowych) sprowadza
  warianty zapisu do jednej nazwy — filtr "Model GPU" spadł z potencjalnych 25+ do 14 opcji.
- Redesign kart PC: kolorowy pasek boczny wg segmentu (budżet/średnia/wyższa/topowe), etykieta
  segmentu, chipy specyfikacji (RAM/dysk/PSU), wstążka "+ RAM 32GB (+X zł)" dla wariantów custom.
- Obrazy: 58 unikalnych zdjęć (55 Hard-PC + 3 GoblinPC) pobrane i osadzone w pcimg/manifest.json;
  3 zdjęcia GoblinPC (AI-generated, 1-2MB PNG) przeskalowane do ~20-30KB JPEG (limit Artifact 16MB).

## Pliki (ten katalog, do wznowienia/audytu)
- `hardpc_final.csv` — źródłowy scrape Hard-PC (405 wierszy, 402 unikalne).
- `goblinpc_catalog.json` — 3 modele GoblinPC ze zweryfikowanymi cenami opcji.
- `pc_ram_lookup.json` — 112 configów × realna cena opcji RAM z live konfiguratora.
- `pcs_final.json` — finalna, w pełni wyliczona lista 534 pozycji (ze scores, pros/cons).
- `build_pc_dataset.py`, `build_all_pcs.py` — pipeline: CSV+lookup → PCS → scoring → JSON.
  (gen_pdata_js_v2.py w scratchpadzie sesji konwertuje pcs_final.json na literał JS PDATA).

## Świadomie NIE zrobione (poza zakresem)
- Warianty customizacji dysku/zasilacza dla Hard-PC (tylko RAM) — user explicit example
  dotyczył RAM; storage/PSU pozostają czynnikiem w scoringu (components), nie osobnym wariantem.
  Wcześniejsza próbka w pc_data.py miała warianty dysku dla 3 GoblinPC — usunięte przy scaleniu
  dla spójności (Hard-PC nie miałby odpowiednika przy 402 produktach × warianty = eksplozja).
- Redesign vs wygląd strony Hard-PC.pl: ich strona jest bardzo minimalistyczna (goła lista
  tekstowa bez kart) — nasza strona z kartami/obrazami/filtrem/porównywarką jest już wyraźnie
  bogatsza wizualnie; dodatkowo wzmocniono separację przez tier-stripe/chips/eyebrow.
