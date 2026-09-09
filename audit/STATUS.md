# Audyt inżynieryjny monitorów — ZAKOŃCZONY (9.09.2026)

Zadanie z persony TFTCentral/RTINGS/Monitors Unboxed (patrz PERSONA_PROTOKOL.md) jest
w pełni zintegrowane ze stroną i opublikowane.

## Co zrobiono
- Research laboratoryjny (pomiary niezależne) dla wszystkich 57 monitorów: `lab_group1-6.json`.
- Research specyfikacji deklarowanej przez producentów dla wszystkich 57 monitorów: `mfr_group1-6.json`.
- Scalenie obu warstw w pole `audit:{lab:{...}, mfr:{...}}` każdego wpisu DATA[] w
  `monitors_1700_template.html` (skrypt `merge_audit.py` — UWAGA: ten skrypt miał błąd
  podwajania przecinka po insercji, powodujący 56 "dziur" w tablicy DATA i wywalającą się
  interakcję na całej stronie; błąd naprawiony ręcznie w szablonie, skrypt NIE został
  poprawiony w repo — nie uruchamiać go ponownie bez naprawy linii
  `new_line = prefix + insertion + closing + (comma if comma else "") + "\n"` →
  `closing` już zawiera przecinek, więc `(comma if comma else "")` trzeba usunąć).
- Nowa sekcja UI w `buildMonitorDetailHTML`: "Audyt inżynieryjny — pomiary laboratoryjne"
  (z plakietką pokrycia recenzjami) + "Specyfikacja deklarowana przez producenta" (z jawną
  adnotacją, że to deklaracja, nie pomiar). Pola "BRAK" renderują się jako "brak danych".
- Nowe wiersze w `buildCompareTable`: czas odpowiedzi (zmierzony), input lag (zmierzony),
  Delta E, HDR peak (zmierzony), migotanie VRR, text fringing, certyfikat HDR (producent),
  zakres VRR (producent), złącza (producent).

## Dwa poboczne błędy naprawione przy okazji (były w szablonie już wcześniej)
1. Brak `<meta charset="utf-8">` w pliku źródłowym — powodował mojibake dla polskich
   znaków na GitHub Pages (Artifact ma własny wrapper z charset, więc tam nie było widać).
   Dodano na początku pliku.
2. `slugify()` miał w regexie DOSŁOWNE znaki diakrytyczne zamiast escape'ów `̀-ͯ`
   — po poprawnym odczycie UTF-8 (patrz punkt 1) rzucało to `SyntaxError` i wywalało
   CAŁĄ interaktywność strony (klik w kartę, porównywarka, widok szczegółów) na produkcji.
   Naprawione na `̀-ͯ`.

## Stan publikacji (9.09.2026)
- Artifact: https://claude.ai/code/artifact/18421fe1-69f6-4fc6-bb69-5426785e8bea — zaktualizowany.
- GitHub Pages: https://grzesko48.github.io/grid-overdrive/ — zaktualizowany (commit bc0a1ec).
- Zweryfikowane w przeglądarce: 0 błędów w konsoli, sekcja audytu renderuje się poprawnie
  z prawdziwymi danymi (sprawdzone na Philips Evnia 27M2N3501PA/00), tabela porównawcza
  pokazuje nowe wiersze.

## Znane ograniczenia (uczciwie, zgodnie z Konstytucją Prawdy)
- RTINGS od 2026 blokuje niemal wszystkie liczby za paywallem — dla wielu modeli dostępny
  jest tylko werdykt opisowy, nie liczba.
- ~30-40% z 57 monitorów nie ma ŻADNEJ niezależnej recenzji laboratoryjnej (regionalne SKU
  EU/PL) — dla nich pole audytu pokazuje uczciwie "brak danych", nie zmyśloną liczbę.
- Część danych producenta pochodzi z regionalnych wariantów strony (np. AOC Islandia/Estonia
  zamiast US) gdy globalna strona nie miała danego SKU — oznaczone w `notes` każdego wpisu.
