# Pakiet naprawczy 2 — konstrukcja oceny Ultra

Następnik `PLAN-NAPRAWCZY.md` (17.09), nie zamiennik. Tamten plan obejmował Z-01…Z-11
i został wykonany 18.09; zamknij go jednym zdaniem na górze tamtego pliku, zanim zaczniesz ten.

Wykonuje: Sonnet 5. Weryfikuje: **wyłącznie** Opus 5, niezależnie od raportu wykonawcy.
Podstawa: Rada FIRMA z 18.09.2026, działy `dataviz` + `biznes`, pomiary na 348 pozycjach widocznych.

---

## Stan wyjściowy — sprawdź, zanim cokolwiek zmienisz

Każdą z tych liczb odtworzono dwukrotnie (dział + zarząd). Jeśli któraś się nie zgadza, **stop** —
baza się zmieniła i cały pakiet trzeba przeliczyć od nowa.

| fakt | komenda kontrolna | oczekiwane |
|---|---|---|
| pozycji widocznych | parser `PDATA`, pomijając `ukryty:1` | 348 z 355 |
| `longevity` jest min-maxem na ŻYWEJ bazie | `longevity == round(1+(lata-1.22)/(3.78-1.22)*99)` | 348/348 |
| dolną kotwicę trzyma JEDNA pozycja | pozycje z `longevityYears:1.22` | 1 (Ryzen 5 7500F, RTX 5050 8GB) |
| usunięcie tej jednej pozycji | przeliczenie longevity na nowej kotwicy 1.52 | rusza 337/347 longevity, **332/347 ultra** |
| `value` zależy od składowanego `perf` | `przelicz_oceny.py:89` | `podstawa = cena / s["perf"]` |
| reguła zaokrąglenia nie jest zadeklarowana | suma ważona na ułamkach dokładnych | 11 pozycji równo na ,5; 10 do parzystej, 1 (61,5→61) łamie |
| brak bazy odniesienia | `git tag` | 0 tagów |
| narzędzie różnicowe ISTNIEJE | `porownaj_rankingi.py --przed X --po-naprawie Y` | działa, raportuje 4 liczby |
| kod 4 składników nie istnieje, ale reguła 2 z nich jest odtwarzalna | — | `perf` = f(gpu,cpu) 96 kombinacji 0 niejednoznacznych; `longevityYears` = f(gpu,ram) 42/0 |
| `components` nie działa kierunkowo | udział w wariancji | −0,1%, korelacja z `ultra` −0,013 |
| `features` to jedyny składnik niosący informację niezależną | VIF | 1,08 (pozostałe 3,8–4,2) |
| efektywna liczba składników | 1/Σp², podstawa udziałów NAZWANA | **2,89** na „sd × waga”, **2,07** na udziale w wariancji |

---

## Zasady twarde (złamanie unieważnia cały przebieg)

1. **Nie wolno nadpisywać składowanego pola `perf`.** `value` liczy się z `cena / perf`, więc każde
   przeskalowanie `perf` przesuwa opłacalność u wszystkich 348 pozycji naraz. Jeżeli kiedykolwiek
   normalizujesz `perf`, rób to w sumowaniu wag, nie w danych.
2. **Nie ruszaj wag, dopóki składniki nie mają kodu.** Ważenie liczb, których nikt nie umie odtworzyć,
   to mnożenie nieznanego przez znane.
3. **Nie rozdzielaj wagi usuwanego składnika.** Zawieszenie `components` na stałej 100 daje maks 2 pkt
   różnicy; rozdzielenie jego wagi 12% na resztę rusza 304/348 pozycji o ≥3 pkt i 7/11 progów.
4. Każdy etap = jeden commit = jeden `git revert`.
5. Po każdym etapie uruchom `porownaj_rankingi.py` wobec tagu bazowego i **zapisz wynik do raportu**.
   Mierz w PUNKTACH, nigdy w miejscach w rankingu (lekcja z 18.09).
6. Zero zmyślonych liczb. Brak danych = „BRAK".

---

## ETAP 0 — baza odniesienia (bez zgody, 0 zmian widocznych)

### Z-20. Tag bazowy
`git tag baza-2026-09-18` na bieżącym HEAD. W repozytorium nie ma ani jednego tagu, a 18.09 weszło
19 commitów — bez zamrożonej rewizji żadne zdanie „to nie zepsuło poprzedniego" nie jest sprawdzalne.

### Z-21. Raport bazowy
Zapisz `raport-bazowy.json`: dla każdej z 348 pozycji wszystkie 5 składników + `ultra` + cena.
To jest punkt odniesienia dla każdego kolejnego etapu.

**Odbiór:** `git tag` zwraca `baza-2026-09-18`; `raport-bazowy.json` ma 348 rekordów po 7 pól.

---

## ETAP 1 — metodyka przestaje twierdzić nieprawdę, jakościowo (0 zmian ocen)

Ten etap **nie publikuje żadnej liczby wpływu** — patrz ETAP 4 i uzasadnienie kolejności niżej.

### Z-22. „Waga" to współczynnik, nie udział wpływu
W opisie rankingu Ultra dopisz zdanie mówiące wprost, że podane procenty są współczynnikami wzoru,
a nie udziałami w tym, co faktycznie różnicuje oceny, i że te dwie wielkości nie są sobie równe.

### Z-23. Karta graficzna wchodzi dwoma kanałami
Dopisz, że `perf` jest funkcją pary (karta, procesor), a `longevityYears` funkcją pary (karta, RAM) —
więc karta graficzna steruje dwoma składnikami o łącznej wadze 58%. To jest konstrukcja, nie przypadek,
i czytelnik ma prawo o tym wiedzieć.

**Odbiór:** `porownaj_rankingi.py --przed baza-2026-09-18 --po-naprawie HEAD` → `zmienilo_ocene: 0`,
`progi_ze_zmiana: 0`. Jakakolwiek inna wartość = `git revert` i wróć.

---

## ETAP 2 — reguła zaokrąglenia i remisu trafia do kodu (1 pozycja, 1 punkt)

### Z-24. Zadeklaruj zaokrąglenie
11 pozycji wypada równo na ,5. Dziesięć zaokrąglono do parzystej, jedna (61,5 → 61) nie. Zapisz regułę
jawnie w `przelicz_oceny.py` i przelicz te 11 pozycji tą samą regułą.

### Z-25. Zamroź regułę remisu
`ultra` przyjmuje tylko 39 różnych wartości na 348 pozycji, więc 5,2% par ma identyczną ocenę. Sama
zmiana reguły remisu przestawia 6 z 11 progów budżetowych **bez żadnej zmiany wzoru**. Reguła remisu
(ocena → cena → nazwa) musi być w kodzie liczącym progi, nie tylko w kodzie wyświetlającym ranking.

**Odbiór:** `zmienilo_ocene` ≤ 1 wobec tagu bazowego; `progi_ze_zmiana: 0`; ponowne uruchomienie
`porownaj_rankingi.py` dwa razy pod rząd daje identyczne progi.

---

## ETAP 3 — longevity przestaje zależeć od tego, co jest akurat w bazie ⟵ DECYZJA D-B

**To jest ta sama usterka, którą 18.09 usunięto z `value`, tyle że w drugim składniku i niezauważona.**

Zamień min-max na progi bezwzględne, wzorem `PROGI` z `przelicz_oceny.py`.

| widełki | zmierzony skutek wobec bazy | rekomendacje budżetowe |
|---|---|---|
| **1,2 – 3,8 lat** | maks 1 pkt, 0 pozycji o ≥3 pkt | **0 z 11** |
| 1,0 – 4,0 lat | maks 3 pkt, 3 pozycje o ≥3 pkt | 5 z 11 |
| 1,0 – 4,5 lat | 185 pozycji o ≥3 pkt | — |

Rekomendacja zarządu: **1,2–3,8** — odrelatywnia składnik przy zerowej zmianie tego, co serwis poleca.

**Odbiór:** po etapie usunięcie dowolnej jednej pozycji zmienia longevity u **0/347** (dziś: 337/347).
To jest cały cel tego etapu i jedyna bramka, która go rozstrzyga.

---

## ETAP 4 — liczby wpływu trafiają na stronę ⟵ DECYZJA D-A, wymaga ETAPU 3

### Z-26. Skrypt liczący wpływ ląduje w repozytorium PRZED zdaniem na stronie
Opublikowanie liczby „realny wpływ 17,5%" bez kodu, który ją produkuje, powtarza dokładnie mechanizm
erratki o opłacalności. Skrypt najpierw, zdanie potem.

### Z-27. Publikacja
Obok wagi nominalnej podaj zmierzony wpływ, datę pomiaru i nazwę skryptu.

Istnieją trzy różne miary tego samego zjawiska i **dają trzy różne obrazy**:

| składnik | waga nominalna | wpływ „sd × waga" | udział w wariancji |
|---|---|---|---|
| Długowieczność | 30% | 49,5% | 64,4% |
| Opłacalność | 22% | 26,1% | 11,0% |
| Wydajność | 28% | 17,5% | 23,9% |
| Podzespoły | 12% | 4,1% | −0,1% |
| Kompletność | 8% | 2,8% | 0,8% |

Wybór jednej bez powiedzenia, że pozostałe istnieją, powtarza ten sam błąd na wyższym poziomie.

**Odbiór:** `zmienilo_ocene: 0`; skrypt w repo odtwarza opublikowane liczby przy każdym uruchomieniu.

---

## ETAP 5 — martwe składniki, BEZ ruszania wag ⟵ wymaga definicji od właściciela

- `features`: moda 71 u 213 pozycji (61%), ale VIF 1,08 — **jedyny składnik niosący informację
  niezależną od pozostałych**. Nie usuwać. Zawieszenie na stałej 71 kosztuje maks 2 pkt, 0 pozycji
  o ≥3 pkt, 0 z 11 progów.
- `components`: moda 100 u 113 pozycji (32%), udział w wariancji −0,1%, korelacja z `ultra` −0,013 —
  ma rozrzut i nie robi nic kierunkowo, bo znosi go korelacja −0,54 z `value`.

Przebudowa wymaga definicji, której w repozytorium nie ma (`features` nie jest funkcją pary
(RAM, dysk) — 10 z 27 kombinacji niejednoznacznych). Do czasu decyzji: zawieszenie z jawnym
komunikatem na stronie, nigdy cicha zmiana wagi.

---

## ETAP 6 — NIE TERAZ

Rozdzielenie karty graficznej między `perf` a `longevity` oraz rekalibracja wag. Wariant naiwny daje
Spearman 0,9031 i 335 z 348 pozycji zmienionych o ≥3 pkt. Nie wolno tego wykonać, dopóki nie istnieje
zamrożony zestaw par ocenionych ręcznie przez właściciela **przed** zobaczeniem wyniku nowego wzoru
(minimum 16 z 23 par przy H0 = 0,50, α = 0,05, moc 0,80).

---

## Czego NIE robić

- **Nie normalizować rozrzutów przez z-score ani min-max.** To wprowadziłoby zależność od żywej bazy
  do WSZYSTKICH składników: usunięcie jednej pozycji rusza 16/347 ocen w wariancie z-score wobec
  0/347 w dzisiejszym wzorze liniowym. Byłoby to rozlanie usterki, nie jej naprawa.
- **Nie ustawiać wag tak, żeby wpływ równał się deklaracji.** Da się dokładnie, ale wychodzą wagi
  Podzespoły 41,6% / Kompletność 18,6% / Opłacalność 16,1% / Wydajność 15,7% / Długowieczność 8,1%.
  Nikt takich wag nie zadeklaruje i nikt ich nie obroni.
- **Nie scalać `perf` z `longevity`.** Rozróżnienie „szybki dziś" vs „starczy na lata" jest realne
  (5060 Ti 16 GB vs 5070 8 GB to dokładnie ta różnica) i czytelnik go potrzebuje.
- **Nie usuwać `features` ani `components`** — patrz ETAP 5.

---

## Protokół weryfikacji (wykonuje Opus 5, niezależnie od raportu wykonawcy)

| # | bramka | dziś | próg |
|---|---|---|---|
| G1 | składników odtwarzalnych jawnym kodem | 1/5 | ≥ 3/5 po etapie 3 |
| G2 | pozycji, u których kod odtwarza opublikowane `ultra` | 347/348 | 348/348, reguła w kodzie |
| G3 | stabilność bazy: usunięcie 1 pozycji zmienia ocenę innym | 332/347 | **0/347** po etapie 3 |
| G4 | luka deklaracja − zmierzony wpływ | 34,4 p.p. | ≤ 10 p.p. albo obie liczby obok siebie |
| G5 | efektywna liczba składników 1/Σp² | 2,89 „sd × waga” / 2,07 wariancja | ≥ 3,0 na nazwanej podstawie albo zmiana deklaracji |
| G6 | skutek dla czytelnika, w PUNKTACH i progach | — | budżet zmiany zadeklarowany per etap, przekroczenie = stop |
| G7 | powtarzalność: dwa przebiegi dają ten sam wynik | — | identyczny |

**Granica uczciwości tego protokołu:** G1–G7 dowodzą, że wzór jest odtwarzalny, stabilny i zgodny
z własną deklaracją. **Żadna z nich nie dowodzi, że serwis poleca lepszy sprzęt.** Do zdania
„jest trafniej" potrzebny jest zewnętrzny punkt odniesienia, którego w repozytorium nie ma.
Do tego czasu wolno mówić wyłącznie „jest zgodniej z deklaracją".
