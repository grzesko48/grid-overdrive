# Pakiet — trzy nowe źródła PC (Gamer-Zone.pl, Actina, NTT System)

Rozpoznanie zrobił Opus 5 (WebFetch na żywych stronach, nie zgadywanie). Wykonuje Sonnet 5, weryfikuje
wyłącznie Opus 5. **Ten pakiet NIE dotyka `monitors_1700_template.html`** — buduje i testuje wyłącznie
narzędzie zbierające. Dopisanie nowych zestawów do katalogu to osobny, kolejny krok, dopiero po tym, jak
zbieranie działa i przejdzie test na żywych stronach.

---

## Czwarty kandydat, którego NIE robimy — i dlaczego

**Mad Dog PurePC Edition** (Media Expert) kwalifikuje się merytorycznie najlepiej ze wszystkich — linia
współtworzona i testowana przez PurePC.pl, ceny ~4000/7000/10000 zł, DDR5 32GB 6000MHz. Ale sprzedaje ją
wyłącznie Media Expert, a ten sklep **już dziś zwraca 403 z chmury** (ten sam fakt, który wyklucza x-kom).
To nie jest moje uznanie — to ta sama zasada projektu, która obowiązuje od początku: nie obchodzimy
blokad. Zostaje opisana luka, nie próba obejścia.

---

## Stan wyjściowy — co sprawdziłem osobiście, nie przez podsumowanie modelu

| Fakt | Jak sprawdzone |
|---|---|
| Gamer-Zone.pl `robots.txt` nie blokuje stron produktowych | WebFetch bezpośrednio na `/robots.txt`, WooCommerce, sitemapa obecna |
| Gamer-Zone.pl **nie ma** JSON-LD na stronie produktu | WebFetch na żywej karcie produktu (Phantom X7), brak `<script type="application/ld+json">` |
| Gamer-Zone: 180–256 opinii (dwa różne agregatory Trusted Shops) | WebSearch, cytowane liczby z trstd.com i trustedshops.pl |
| Actina — ID marki na Morele.net = **8** | Zweryfikowane przez `site:morele.net Actina` — realne linki produktowe z tym ID w URL, NIE przez odgadnięcie wzorca (pierwsza próba WebFetch podała fałszywe „221" — odrzucone, bo nikt tego nie potwierdził na żywej stronie) |
| NTT System — ID marki na Morele.net = **102941** | Potwierdzone bezpośrednio na żywej stronie kategorii, z przykładowymi produktami i cenami |
| `sklep.ntt.pl/robots.txt` zwraca **403** | WebFetch bezpośrednio |
| `actina.pl/robots.txt` zwraca **404** (plik nie istnieje) | WebFetch bezpośrednio — brak pliku, nie jawne zezwolenie; nie jest to to samo co „otwarte" |

---

## Zasada nadrzędna

**Actina i NTT System NIE dostają nowego kodu zbierającego.** Sprzedawane są też na Morele.net, a Morele
już działa w `zbieraj_ceny.py` przez `z_jsonld()`. Zamiast stawiać zbieranie dla dwóch domen, z których
jedna aktywnie blokuje automat (`sklep.ntt.pl`, 403) a druga nie ma jawnego zezwolenia (`actina.pl`, brak
`robots.txt`) — rozszerzamy listę adresów Morele o te dwie marki. Zero nowego ryzyka prawnego, zero
nowego kodu parsującego.

**Gamer-Zone.pl dostaje nowy parser**, bo jest jedynym kandydatem w pełni otwartym technicznie
(`robots.txt` bez zastrzeżeń) i prawnie (własna domena, nie pośrednik).

---

## ETAP A — Actina i NTT System przez Morele.net (tanie, bez nowego ryzyka)

1. W `zbieraj_ceny.py` (albo w osobnym pliku wejściowym, jeśli adresy sklepów trzymane są gdzie indziej —
   sprawdź, skąd `main()` bierze listę URL-i do pobrania) dodaj adresy kategorii Morele dla obu marek:
   - Actina: `https://www.morele.net/kategoria/komputery-stacjonarne-672/,,,,,8,,,0,,,,/1/` (i kolejne
     strony `/2/`, `/3/`... jeśli wyników jest więcej niż jedna strona)
   - NTT System: `https://www.morele.net/kategoria/komputery-stacjonarne-672/,,,,,102941,,,0,,,,/1/`
     (analogicznie kolejne strony)
2. Z każdej strony kategorii wyciągnij linki do pojedynczych produktów (wzorzec URL Morele, sprawdź na
   żywo jak wygląda link produktowy — przykład: `/komputer-ntt-system-prodesk-sff-...-15943620/`).
3. Każdy link produktowy pobierz i przepuść przez **już istniejący** `z_jsonld()` — to ten sam mechanizm,
   który dziś działa dla reszty katalogu Morele. Nie pisz nowego ekstraktora.
4. **Filtr DDR5 + karta gamingowa jest KONIECZNY na tym kroku, nie później.** W wynikach kategorii NTT
   widziałem też biurowe SFF z Ryzen 5 3400G/8GB RAM/512GB — to nie są zestawy do gier objęte tym
   zestawieniem. Zastosuj te same kryteria wejścia, co dla reszty katalogu (DDR5, karta z listy
   `GPU_TIER`), zanim cokolwiek trafi do dalszego przetwarzania.
   **Próg cenowy — decyzja właściciela z 21.09.2026, ta sama co w `sprawdz_katalogi.py`:** od 5000 zł
   (bez systemu), do **10 000 zł Z DOLICZONYM WINDOWSEM** — nie 10 000 zł bez systemu. Morele w
   większości przypadków podaje jedną cenę zawierającą już Windows (`osPriceKind` bliżej `included`) —
   wtedy porównuj wprost tę cenę do sufitu 10 000 zł. Jeśli trafisz na ofertę bez systemu, dolicz
   aktualną dopłatę (sprawdź ją tak samo dynamicznie jak `sprawdz_katalogi.py` — z mediany istniejących
   wpisów tego sklepu, nie ze stałej wpisanej na sztywno) przed porównaniem do sufitu.
5. Zapisz wynik w takim samym formacie, jak reszta pobranych ofert (żeby `nanies_zmiany.py` mógł to
   przyjąć bez zmian).

**Test:** uruchom na żywo z `--limit 5` dla obu marek. Pokaż: ile produktów znaleziono w kategorii, ile
przeszło filtr DDR5+gaming, przykładową pobraną cenę i specyfikację jednego zestawu z każdej marki,
zweryfikowaną ręcznie (otwórz link, porównaj).

---

## ETAP B — nowy parser dla Gamer-Zone.pl

Strona **nie ma JSON-LD** — dane są w zwykłym HTML. Napisz nową funkcję `z_gamerzone(s)` w
`zbieraj_ceny.py`, analogiczną do `z_ceneo`/`z_mediamarkt` (każda z nich to osobny, udokumentowany
wyjątek od `z_jsonld`, z komentarzem dlaczego).

Sprawdzone na żywej stronie (karta produktu „Phantom X7"), użyj tego jako wzorca, ale **potwierdź sam na
kilku innych kartach** przed napisaniem sztywnego regexu — struktura mogła się różnić między produktami:
- Cena: widoczna jako „7 499,00 zł z VAT" w treści strony.
- Specyfikacja (procesor, karta, RAM, dysk, zasilacz, system) w czytelnym bloku tekstowym na stronie —
  znajdź dokładny selektor/wzorzec HTML (`class=` bloku specyfikacji), nie parsuj wolnego tekstu całej
  strony.
- **Konfigurator:** RAM opisany jako „16 GB DDR5 min. 5200 MHz (**domyślnie wybrana konfiguracja**)" —
  strona ma opcje wyboru komponentów, podobnie jak Hard-PC. Sprawdź, czy są dopłaty za warianty (podobny
  mechanizm do `opcje_konfiguratora()`, który już czyta `<option>... (+kwota zł)`) i czy da się to
  ponownie wykorzystać, czy Gamer-Zone koduje to inaczej (np. przez atrybuty `data-*` albo osobny JS).

### Krytyczna rzecz do rozstrzygnięcia: status licencji Windows

Karta „Phantom X7" mówi wprost: **„System operacyjny: Windows 11 Home (zainstalowany, nieaktywowany —
bez klucza)"**. To NIE jest to samo, co „Windows w cenie" u pozostałych sklepów w tym katalogu — tam
`osPriceKind='included'`/`'confirmed'` zakłada realną, działającą licencję. Zanim jakikolwiek zestaw
Gamer-Zone trafi do katalogu:
1. Sprawdź na kilku kartach produktów, czy to jest **stały wzorzec całego sklepu**, czy tylko tego
   jednego produktu.
2. Sprawdź, czy istnieje płatna opcja aktywowanego Windows w konfiguratorze (podobnie jak dopłaty za RAM)
   — jeśli tak, to PRAWDZIWA cena „z legalnym Windows" to cena bazowa + ta dopłata, nie sama cena bazowa.
3. **Nie nadawaj żadnemu zestawowi Gamer-Zone statusu `osPriceKind='included'` ani `'confirmed'`**, dopóki
   nie potwierdzisz, że cena obejmuje aktywowaną licencję. Domyślnie traktuj to jak `osPriceKind='unknown'`
   (dokładnie ten status, który Etap 1 tego pakietu przed chwilą naprawił na czterech innych wpisach) —
   chyba że znajdziesz jawną, płatną opcję aktywacji i wtedy policzysz cenę z nią.

To jest dokładnie ten sam błąd, którego unikamy od dwóch dni — nie wolno go wnieść do serwisu przez nowe
źródło danych.

**Test:** `z_gamerzone()` poprawnie wyciąga cenę i dostępność z co najmniej 5 różnych, ręcznie
sprawdzonych kart produktów (różne ceny, różne układy strony, jeśli się różnią). Żaden zebrany zestaw nie
ma `osPriceKind` sugerującego pewność co do Windows, dopóki nie ma na to dowodu z konfiguratora.

**Próg cenowy dla Gamer-Zone — ta sama zasada co w Etapie A (10 000 zł Z Windowsem, nie bez):** cena
pokazana na stronie (np. „7 499,00 zł") to cena z zainstalowanym, ale NIEAKTYWOWANYM systemem — nie
traktuj jej automatycznie jako „ceny z Windowsem" do porównania z sufitem. Najpierw rozstrzygnij punkt
wyżej (czy istnieje płatna aktywacja i ile kosztuje); dopiero cenę **z realną, działającą licencją**
porównuj do sufitu 10 000 zł. Jeśli aktywacji nie da się kupić w ogóle, opisz to w raporcie i zapytaj o
decyzję, zamiast przyjmować cenę bazową za ostateczną.

---

## Zasady twarde (te same co zawsze)

- Zero zmyślonych danych. Fakt „nie sprawdziłem" nigdy nie zamienia się w domyślną wartość.
- Respektuj `robots.txt`. Nie próbuj `sklep.ntt.pl` bezpośrednio — 403 już potwierdzone.
- Nie dotykaj `monitors_1700_template.html` w tym pakiecie — to etap PRZED dodaniem czegokolwiek do
  katalogu. Dodanie nowych zestawów do strony to osobne zadanie, po tym jak zbieranie jest sprawdzone.
- Filtr DDR5 + karta gamingowa na wejściu, nie na wyjściu — inaczej biurowe SFF trafią do dalszej obróbki.
- Adaptacyjne tempo per-host (klasa `Tempo`) i sprawdzenie `Regulamin` (robots.txt) — użyj mechanizmów już
  istniejących w `zbieraj_ceny.py`, nie pisz nowych od zera.

## Odbiór całości

1. Actina i NTT: pokazane żywe, poprawnie sparsowane oferty z Morele, przefiltrowane do DDR5+gaming.
2. Gamer-Zone: nowa funkcja parsująca, sprawdzona na ≥5 kartach, z rozstrzygniętym pytaniem o status
   licencji Windows — opisanym w raporcie, nie zgadniętym.
3. Zero zmian w `monitors_1700_template.html`/`index.html` — to zadanie kończy się na działającym
   narzędziu zbierającym, nie na nowych wpisach w katalogu.
