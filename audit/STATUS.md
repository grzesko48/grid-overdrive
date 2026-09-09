# Audyt inżynieryjny monitorów — STAN PRAC (zapis awaryjny, 9.09.2026)

Sesja zatrzymana przy ~90% limitu kontekstu na prośbę użytkownika. Nic nie jest zintegrowane
ze stroną jeszcze — to jest surowy research + plan. Wszystko poniżej jest na dysku i w repo.

## Cel (od użytkownika)
Rozbudować porównanie 57 monitorów o surowy, fizyczny audyt w stylu TFTCentral / RTINGS /
Monitors Unboxed — zero marketingu, tylko pomiary; filary A (czas reakcji, dark smearing,
overshoot, najlepszy profil OD), B (VRR flicker, BFI), C (subpiksele, text fringing),
D (HDR EOTF, ABL, peak nits), plus dE, input lag, powłoka, burn-in.
Pełny tekst persony/protokołu: `PERSONA_PROTOKOL.md` (ten katalog).
Dodatkowe polecenie użytkownika: szczegóły specyfikacji brać też ze stron PRODUCENTÓW
(samsung.com, lg.com, aoc.com, gigabyte, msi, asus, acer, philips, iiyama, lenovo, hp, dell,
hyperx) — jako OSOBNA warstwa "specyfikacja deklarowana", oddzielona od "pomiary laboratoryjne".

## Co jest ZROBIONE (pliki w tym katalogu)
- `lab_group1.json` … `lab_group4.json` — wyniki 4 z 6 agentów badawczych (monitory idx 0–39,
  klucze 01_… do 45_…). Format: JSON, pola A_*/B_*/C_*/D_*/E_*/F_*, "BRAK" = brak pomiaru,
  URL źródła inline. ZERO zmyślonych liczb.
- `monitor_list.json` — lista 57 monitorów (key, name, panel, hz, coverage) w kolejności DATA[].

## Co jest W TOKU / NIEZAPISANE
- Grupa 5 (idx 40–48: 46_hp_omen_27qs_g2 … 54_msi_mpg271qrx) i grupa 6 (idx 49–56:
  55_msi_mag273qp … 62_philips_evnia8500) — agenci uruchomieni w tle, wyniki NIE zapisane.
  Transkrypty JSONL (można z nich wyciągnąć końcowy JSON, ostatni wpis "result"):
  - grupa 5: /private/tmp/claude-501/-Users-grzegorzrybak-Claude/82884799-1aba-4c29-9150-8a28fda9e42e/tasks/acd5d796c6d558aa3.output
  - grupa 6: /private/tmp/claude-501/-Users-grzegorzrybak-Claude/82884799-1aba-4c29-9150-8a28fda9e42e/tasks/<id nieznany — uruchomiony jako ostatni z sześciu; szukać najnowszego pliku w tasks/>
  Jeśli plików nie ma — po prostu powtórzyć research dla tych 17 monitorów tym samym promptem
  (szablon promptu = ten użyty dla grup 1–4, patrz PERSONA_PROTOKOL.md sekcja "Prompt agenta").

## KLUCZOWE USTALENIA z researchu (ważne dla uczciwości strony)
1. RTINGS od 2026 blokuje WSZYSTKIE liczby za paywallem ("Locked") — dostępne tylko werdykty
   tekstowe. Nie da się z RTINGS wyciągnąć ms/nitów/dE.
2. TFTCentral to jedyne źródło z otwartymi liczbami; pełne recenzje tylko dla: AOC AG276QZD2,
   Gigabyte GO27Q24G, Samsung G7 C27G75T (+ TechSpot dla G7 i porównawczo M27Q3).
3. ~40 z 57 monitorów NIE ma żadnej recenzji laboratoryjnej w RTINGS/TFTCentral/TechSpot
   (regionalne SKU EU/PL). Dla nich uczciwy wynik = "brak niezależnych pomiarów" + spec producenta.
4. Wiele "podobnych" modeli to INNE panele (np. GO27Q24 QD-OLED ≠ GO27Q24G WOLED; X27U ≠ X27U Z1;
   27GX704A ≠ 27GX700A) — nie przenosić danych między nimi.

## PLAN INTEGRACJI (do wykonania w nowej sesji)
1. Dokończyć/odzyskać grupy 5–6 → `lab_group5.json`, `lab_group6.json`.
2. Fala 2 (6 agentów): specyfikacja deklarowana ze stron producentów, per monitor:
   panel/typ, Hz natywne/OC, deklarowany czas reakcji (oznaczyć "deklarowany"), jasność typ/peak,
   kontrast, certyfikat VESA DisplayHDR, gamut % (sRGB/DCI-P3), zakres VRR + certyfikaty
   (G-Sync Compatible / FreeSync tier), powłoka (matowa/glossy), krzywizna, porty (DP/HDMI wersje,
   USB-C PD), KVM, głośniki, VESA, ergonomia, gwarancja (burn-in dla OLED), nazwa funkcji BFI.
   Zapis: `mfr_group1..6.json`, pola z URL źródła; "BRAK" gdy brak.
3. Scalić lab + mfr → pole `audit:{...}` w każdym wpisie DATA[] w
   `scratchpad/monitors_1700_template.html` (dodać po `coverage:'…'`, przed `}`; NIE zmieniać
   prefiksu `{img:'KEY', name:'…', price:N` — routine `apply_price_updates.py` kotwiczy na nim).
4. UI: nowa sekcja w `buildMonitorDetailHTML` — "Audyt inżynieryjny": blok "Pomiary laboratoryjne"
   (tabela A–F + plakietka pokrycia + linki źródeł) i blok "Specyfikacja deklarowana przez
   producenta" (osobno, z adnotacją "deklaracja, nie pomiar"). Gdy brak pomiarów — jawny komunikat.
   Do `buildCompareTable` dodać wiersze: czas reakcji (zmierzony), input lag, dE, HDR peak,
   VRR flicker, text fringing, certyfikat HDR, zakres VRR, porty.
5. Styl tekstów: twarde metryki, bez "zapierający dech"; kontekst gamedev/simracing tam, gdzie
   dane to uzasadniają.
6. `python3 build_merged.py` → test lokalny (serve_test.py:8793) → publikacja:
   (a) Artifact: https://claude.ai/code/artifact/18421fe1-69f6-4fc6-bb69-5426785e8bea
   (b) GitHub Pages: skopiować `monitors_1700.html` → `grid-overdrive-repo/index.html`, commit, push
       (repo grzesko48/grid-overdrive; Routine `grid-overdrive-prices`
       trig_019oSfiWFF19AeSnxS7ZiCbe aktualizuje tylko ceny, codziennie 6:00 UTC).

## Stan strony przed tym zadaniem (nienaruszony)
- Artifact + GitHub Pages działają, ceny odświeżone 9.09.2026, Routine przetestowana (1 przebieg OK,
  poprawiony prompt: cena bazowa nie promocyjna, zaokrąglanie do najbliższej złotówki).
