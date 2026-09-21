# Pakiet naprawczy 3 — audyt drugiej fali (RAM, dysk, zasilacz, system, ceny)

Następnik `PAKIET-NAPRAWCZY-2.md` (etapy 0–4 zamknięte 20.09), nie zamiennik. Podstawa: workflow z 6
niezależnymi wymiarami audytu + adwersarialna weryfikacja + własna kontrola Opus, 20–21.09.2026, na
348 widocznych zestawach PC. **15 potwierdzonych znalezisk**, zero obalonych; trzy poprawione osobiście
po weryfikacji workflow (błędne przypisanie pliku, dwa zdublowane zgłoszenia scalone w jedno).

Wykonuje: Sonnet 5. Weryfikuje: **wyłącznie** Opus 5, niezależnie od raportu wykonawcy.

---

## Stan wyjściowy — sprawdź, zanim cokolwiek zmienisz

| Fakt | Jak sprawdzić | Wartość |
|---|---|---|
| Tag bazowy tego pakietu | `git tag` | `baza-2026-09-21-audyt2` |
| Pozycji widocznych | `raport_skladnikow.py` | 348 |
| Osobny plik na wymiar audytu | pełny raport | `/tmp/wszystkie_znaleziska.txt` (zarchiwizuj przed startem, może zniknąć z `/tmp`) |

**Zasada nadrzędna tego pakietu:** znaleziska dzielą się na dwie klasy. Klasa A to błędy **logiki/tekstu**
— nie dotykają pola `scores`, więc odbiór jest prosty: **zero zmienionych ocen**. Klasa B dotyka
`scores.components` (i pośrednio `overall`/`ultra`) — tu odbiór wymaga precyzyjnie policzonej,
nie zgadniętej zmiany. Rób klasę A w całości, zanim dotkniesz klasy B.

---

## Zasady twarde

1. **Nigdy nie edytuj `index.html` ani `artifact.html`.** Edytujesz `monitors_1700_template.html` i pliki
   `.py`, potem `python3 build_merged.py`.
2. **Nie nadpisuj** `raport-bazowy.json`, `raport-po-etapie-2/3/4.json`, `raport-po-mocy.json`.
3. **Zero zmyślonych danych.** Tam, gdzie prawdziwej wartości nie znamy (patrz Etap 3B), nie zgaduj —
   zostaw jawny komunikat o niewiedzy.
4. Każdy etap = jeden commit = jeden `git revert`.
5. Po każdym etapie: `python3 raport_skladnikow.py monitors_1700_template.html raport-po-etapie-N.md.json`
   i porównaj z poprzednim stanem pole po polu na wszystkich 348 pozycjach — nie tylko licz sumy.
6. Gdziekolwiek naprawiasz literówkę/niespójność tekstu, **sprawdź, czy ten sam wzorzec nie występuje
   gdzie indziej** (przykład z dzisiaj: dwa niezależne wymiary audytu znalazły dokładnie ten sam błąd
   cen Hard-PC z dwóch różnych stron — bo przyczyna jest jedna, w jednym skrypcie).

---

## ETAP 1 — logika i tekst, zero zmian w ocenach (rób w całości na raz)

### 1.1 Trzy miejsca renderowania kłamią o statusie „system nieznany"

Istnieje już poprawny wzorzec: `pcPriceSubText(d)` (linia ~2206) poprawnie rozróżnia
`included`/`confirmed`/`estimated`/`unknown` i dla `unknown` zwraca **tylko** „system nieznany", bez
słowa Windows. Komentarz projektanta nad nią (linie ~2200-2205) mówi to wprost: *„'unknown' (OS status
itself unconfirmed, so no bare-price comparison is shown at all)"*. Trzy inne miejsca to łamią:

- **`buildPcPriceRows`, zmienna `osNote`** (linia ~2313): `d.osPriceKind==='included' ? '' : (...)` —
  dla `unknown` pisze „cenę z doliczonym Windows 11 (+0 zł)", co jest fałszywe i bez sensu logicznego
  (dopłata 0 zł). Dodaj osobną gałąź dla `unknown`, która zamiast tego wypisuje pole `d.osPriceNote`
  (istnieje w danych dla tych wpisów, ale dziś nigdzie nie jest czytane — sprawdź `grep -c osPriceNote`
  w kodzie renderującym, powinno wynosić 0 przed twoją zmianą).
- **`renderPcRanking`** (linia ~2538): `d.price+' zł z Windows'+(d.osPriceKind!=='included'?' (bez
  systemu: '+d.priceBare+' zł)':'')` — słowo „z Windows" jest twarde dla wszystkich wpisów. Zamień na
  wywołanie `pcPriceSubText(d)` albo równoważną logikę z gałęzią dla `unknown`.
- **`renderPcPerfRanking`** (widok „Największa moc", linia ~2566): to samo, w gorszej wersji — pisze
  „zł z Windows" bezwarunkowo, bez nawet nawiasu. Napraw tą samą metodą.
- **`renderPcTable`** (linia ~2505): komórka „Cena bez systemu" ma tylko warunek na `included`;
  `confirmed`/`estimated`/`unknown` trafiają w tę samą gałąź i pokazują goły `priceBare`. Dodaj
  rozróżnienie: dla `unknown` pokaż tekst sygnalizujący brak potwierdzenia (np. „? zł" albo etykietę),
  dla `estimated` oznacz jako szacunek.

Dotyczy 4 z 348 widocznych wpisów: NITROPC Pack Gold v2, NITROPC Extreme Bronze v2, NITROPC Extreme
Gold v2, NITROPC Extremo (plus 1 ukryty, idx 18) — wszystkie `osPriceKind==='unknown'`.

**Test:** otwórz kartę każdego z 4 zestawów w widoku Ranking Ultra, Ranking „Największa moc" i Tabeli —
żadne miejsce nie ma prawa napisać „z Windows" ani pokazać liczby jako potwierdzonej ceny bez systemu.

### 1.2 Plakietka „8 GB VRAM — mało na 1440p" ma własny, niepełny regex

`vram8Chip(d)` (linia ~2288) parsuje surowe `d.gpu` swoim `/(\d{1,2})\s*GB/` zamiast korzystać z
`normalizeGpu()`/`GPU_SINGLE_VRAM`, których używa reszta kodu (m.in. do liczenia `longevityYears`).
Dla 2 wpisów (Lenovo LOQ Tower 26ADR10 z RTX 5050, MSI MAG Infinite S3 z RTX 5060) — kart z JEDNĄ znaną
wersją pamięci, więc serwis **wie**, że to 8 GB — plakietka się nie pojawia.

Napraw: `vram8Chip` ma najpierw spróbować wyciągnąć GB ze znormalizowanej nazwy (`normalizeGpu(d.gpu)`,
tak jak robi to `GPU_SINGLE_VRAM`), a dopiero gdy się nie da — z surowego `d.gpu` jak dziś.

**Test:** obie karty (Lenovo LOQ Tower 26ADR10, MSI MAG Infinite S3) mają pokazywać plakietkę.

### 1.3 Filtr RAM „16 GB" łapie zestawy z 32 GB

`d.ram.indexOf(ramF+'GB')===-1` (funkcja filtrująca listę PC, ~linia 2771) dopasowuje po podłańcuchu.
2 wpisy GoblinPC („Goblin", „Kobold") mają `ram="32GB DDR5 (2x16GB, Dual Channel)"` — adnotacja liczby
modułów zawiera „16GB", więc trafiają jednocześnie pod filtr 16 i pod filtr 32.

Napraw: filtr ma czytać **wiodącą liczbę** pola `ram` (pierwszy `/^(\d+)\s*GB/` na początku stringa), nie
szukać podłańcucha gdziekolwiek w nim. Sprawdź przy okazji `parseInt(d.ram,10)` używany do sortowania
tabeli (~linia 2493) — działa poprawnie, bo liczba wiodąca jest zawsze na początku, ale upewnij się, że
naprawa filtra jest spójna z tą samą zasadą „licz liczbę wiodącą".

**Test:** po naprawie filtr „16 GB" i filtr „32 GB" mają być **rozłączne** — żaden z 348 wpisów nie może
pasować do obu jednocześnie. Sprawdź to programowo (Python), nie tylko na dwóch znanych przykładach.

### 1.4 Etykieta sklepu „PlugNPlay.pl" niezgodna z prawdziwą domeną

`PSTORE_LABELS` (linia ~2279): `plugnplay:'PlugNPlay.pl'`, ale pole `store` i realny URL wszystkich 36
wpisów to `plugnplay.sklep.pl`. Jedyna niezgodna pozycja w całym słowniku (pozostałe 5 sklepów zgadzają
się z polem `store`). Zmień na `plugnplay:'PlugNPlay.sklep.pl'`.

**Test:** `grep` na zbudowanym `index.html` — zero wystąpień gołego „PlugNPlay.pl" (bez „.sklep").

### 1.5 Tekst metodyki zamyka listę kart na 7 modelach — dane mają 3 więcej

Akapit „Pamięć karty, DLSS i FSR" (linie ~727-733) wylicza zamkniętą listę 7 modeli (RTX 5050/5060/5060
Ti/5070, RX 9060 XT/9070/9070 XT) i na tej podstawie tłumaczy brak kolumny DLSS/FSR. W danych są też
RTX 5070 Ti, RX 7600, RX 7700 XT — 4 widoczne wpisy. Dopisz te trzy modele do wyliczanki. Jeżeli nie masz
potwierdzonych danych o pełnym wsparciu FSR 4.1 na RDNA3 (RX 7600/7700 XT) — napisz to wprost jako
zastrzeżenie, nie milcz.

**Test:** zdanie wymienia wszystkie modele kart faktycznie obecne w widocznych 348 wpisach — sprawdź to
programowo (lista unikalnych `gpu` znormalizowanych vs lista w tekście).

### 1.6 Plakietka zasilacza „brak danych" renderuje się goła

5 wpisów ma `psu:"brak danych"`. W przeciwieństwie do `os` i `storage`, to pole nie ma żadnej dedykowanej
obsługi — chip na karcie i wiersz w panelu szczegółów wypisują dosłownie ikonę błyskawicy + „brak danych".
Zastosuj już istniejący wzorzec `isBrak()`/klasa `.punavail` (użyty w liniach ~1322-1324, ~1509) do pola
`psu` w obu miejscach renderowania (chip na karcie, wiersz specyfikacji w panelu).

**Test:** wszystkie 5 kart pokazują plakietkę zasilacza w tym samym stylu, co braki `os`/`storage`.

### 1.7 Plakietka dysku „brak danych" bywa ucięta

Tekst „SSD (pojemność brak w danych producenta)" (5 wpisów) jest szerszy niż najmniejsza dopuszczalna
karta w siatce (`minmax(340px,1fr)`) i `overflow:hidden` obcina domykający nawias. Skróć tekst plakietki
(np. „SSD (pojemność brak)") **zachowując pełne zdanie** w tytule/`title` atrybutu dla czytelników, którzy
najadą kursorem, albo dodaj `white-space:normal` + odpowiedni `line-height` w miejscu tej konkretnej
plakietki, żeby się zawijała zamiast ucinać.

**Test:** przy szerokości karty 340px (najmniejszej z siatki) tekst jest w całości czytelny — bez utraty
ostatniego znaku.

### 1.8 Filtr GPU pokazuje fantomowy trzeci wariant „RTX 5060 Ti"

Lista `<select>` filtra GPU (~linia 2715) budowana jest z `normalizeGpu()` bez etykiety „(pamięć
niepodana)", którą kod już dokłada w tabeli „Według podzespołów" (~linia 2616). Dla 1 wpisu (SMX
Battlestation M6A, `gpu` bez GB) filtr pokazuje osobną, trzecią pozycję obok „...8GB" i „...16GB".
Zastosuj tę samą etykietę przy budowie `<select>`.

**Uwaga:** jest już zlecone osobne zadanie ustalenia prawdziwej pamięci karty w tym konkretnym zestawie
(SMX Battlestation M6A) — gdy ono się rozstrzygnie, ten jeden wpis przestanie być problemem sam z siebie.
Napraw mimo to kod filtra, bo usterka jest ogólna i wróci przy każdym kolejnym niepełnym zapisie karty.

**Test:** filtr GPU nie ma pozycji bez GB, chyba że dla niej faktycznie brak jednoznacznej wersji pamięci
— a wtedy ma nosić etykietę „(pamięć niepodana)", nie wyglądać jak osobny model.

### 1.9 Jeden wpis kłamie o systemie w sekcji Wady

NITROPC Extremo (`osPriceKind==='unknown'`, `os==='brak danych'`) ma w `cons` zdanie „Bez systemu
operacyjnego w cenie — Windows trzeba dokupić osobno." — stanowcze twierdzenie tam, gdzie serwis sam nie
wie. Pozostałe 4 wpisy o tym samym statusie nie mają żadnego zdania o OS w `pros`/`cons` — to jest
odosobniony wyjątek. Usuń to zdanie z `cons` tego jednego wpisu (idx 25).

**Test:** żaden wpis z `osPriceKind==='unknown'` nie ma w `pros`/`cons` twierdzenia o obecności/braku
systemu.

**Odbiór całego Etapu 1:** `raport_skladnikow.py` wobec `baza-2026-09-21-audyt2` → **0 zmienionych ocen**
na wszystkich 348 pozycjach. Jeśli cokolwiek w `scores` się poruszyło — któraś z „bezpiecznych" zmian
dotknęła czegoś więcej niż tekst/logikę wyświetlania. Zatrzymaj się i zgłoś.

---

## ETAP 2 — ceny w tekście „Zalety", zero zmian w ocenach

### 2.1 Pięć zestawów Hard-PC.pl cytuje starą cenę w `pros[]`

Bullet „Spełnia kryteria zestawienia: ..., w cenie X zł" dla 5 wpisów (idx 29, 31, 33, 35, 37) liczy X
starą dopłatą za Windows (519 zł zamiast aktualnych 539 zł) — jest o 20 zł niższy niż `price` w nagłówku
tej samej karty. Popraw tekst tych 5 bulletów na aktualną wartość `price`.

### 2.2 Zabezpiecz przed powrotem tego błędu

Przyczyna: `nanies_zmiany.py` patchuje wyłącznie pola liczbowe (`price`/`priceBare`), nigdy tekst
`pros[]`/`cons[]`/`osPriceNote`. Każda kolejna zmiana stawki odtworzy ten błąd. Zrób jedno z dwóch —
wybierz to, co mniej ryzykowne do wdrożenia teraz:
  (a) w `nanies_zmiany.py` dodaj krok, który po zmianie ceny przeszukuje `pros[]` danego wpisu wzorcem
      `w cenie \d+ zł` i podmienia liczbę na aktualne `price`;
  (b) NIE zmieniaj generatora teraz, tylko dopisz do `PAKIET-NAPRAWCZY-3.md` w sekcji „Czego nie
      zrobiono" ostrzeżenie, że to się powtórzy, i zostaw to jako osobną pozycję do zaplanowania.
Rekomendacja: (a), bo koszt jest mały, a błąd bez tego wróci przy najbliższej zmianie ceny automatem.

### 2.3 Osobna, niewidoczna niespójność — dokumentacyjnie

Pole `osPriceNote` (nigdy nierenderowane na stronie — sprawdź `grep -c osPriceNote` w kodzie render,
poza etapem 1.1 gdzie je *dodajesz* do jednej gałęzi) dla 284 z 286 potwierdzonych ofert Hard-PC.pl
zapisuje „519 zł", podczas gdy realna dopłata w `price-priceBare` wynosi 539 zł u tych samych wpisów.
Skoro w etapie 1.1 zaczynasz czytać `osPriceNote` na stronie (dla `unknown`), upewnij się, że TA
niespójność nie dotyczy wpisów, których dotyczy 1.1 (nie dotyczy — to rozłączne zbiory: 1.1 to
`unknown`, to jest `confirmed`). Dla porządku danych zaktualizuj tekst `osPriceNote` tych 284 wpisów na
„539 zł", żeby pole było spójne samo ze sobą, nawet jeśli dziś nigdzie indziej nie jest czytane.

**Odbiór Etapu 2:** `raport_skladnikow.py` → 0 zmienionych ocen. Zmienia się wyłącznie tekst.

---

## ETAP 3 — dotyka `scores.components`, wymaga Twojej zgody

### 3A. „1000GB" i „1TB" to ta sama pojemność, ale dostają różny wynik

Usterka pochodzi z martwego, jednorazowego skryptu `recheck/aktualizuj_pc.py` (17.09, pisał bezpośrednio
do szablonu; dziś nie da się go uruchomić — jego dane wejściowe to zamrożone zrzuty z tamtego dnia).
Jego `storage_quality()` konwertuje „N TB" na `N*1024` GB, ale bierze „N GB" dosłownie — więc „1000GB"
(1000 < próg 1024) ląduje w niższym koszyku niż „1TB" (1024 ≥ próg), mimo identycznej fizycznej
pojemności. **To nie jest usterka `pc_audit/build_all_pcs.py`** — sprawdziłem osobno, ta wersja funkcji
traktuje oba zapisy identycznie. Nie mylić plików.

Zmierzone: 13 wpisów ze storage=„1000GB SSD"; w 11 z nich istnieje bliźniak (ten sam cpu+gpu+ram) z
„1TB SSD" o `components` wyższym o dokładnie 4 punkty; w pozostałych 2 (idx 256, 264) `components` jest
już przycięte do sufitu 100 w obu wariantach, więc naprawa nic tam nie zmieni.

**Napisz mały, jednorazowy skrypt** (nowy plik, np. `normalizuj_1000gb.py` — NIE wołaj martwych skryptów
z `pc_audit/`/`recheck/`, one mają nieaktualne stawki i inne błędy):
1. Zamień tekst `storage` z „1000GB SSD" na „1TB SSD" dla tych 13 wpisów — to jest fizycznie ta sama
   pojemność, zero ryzyka w warstwie danych.
2. Dla każdego z tych 13 wpisów podnieś `scores.components` o **+4**, przycięte do 100 (czyli
   `min(100, components+4)`) — wielkość +4 wzięta z realnie zmierzonej różnicy do bliźniaków z „1TB",
   nie z rekonstrukcji formuły.
3. Uruchom `python3 przelicz_oceny.py`, żeby przeliczyć `overall`/`ultra` na nowo z poprawionym
   `components` (te pola już są liczone jawnym wzorem w tym skrypcie — patrz `WZORY`).
4. `python3 build_merged.py`.

**Test:** po zmianie żaden wpis nie ma już `storage=="1000GB SSD"`; wszystkie dawne pary „1000GB vs 1TB"
mają teraz identyczny `components` (sprawdź programowo na wszystkich 13); `przelicz_oceny.py` nie
zgłasza par sprzecznych; `porownaj_rankingi.py --przed baza-2026-09-21-audyt2 --po-naprawie HEAD` — podaj
dokładną liczbę zmienionych ocen (oczekiwana: dokładnie tyle, ile wpisów faktycznie miało bliźniaka, z
uwzględnieniem propagacji do `overall`/`ultra`) i dokładną liczbę przestawionych progów budżetowych z 11.
**Jeśli przestawi się więcej niż 2 z 11 progów — zatrzymaj się i zgłoś, nie publikuj.**

### 3B. Pięć wpisów z „brak danych" o dysku ma wynik identyczny jak 500 GB

Tu **nie znamy** prawdziwej pojemności — inaczej niż w 3A, to nie jest kwestia zapisu tej samej liczby,
tylko realny brak danych. Naprawa NIE polega na poprawieniu wyniku (nie mamy podstawy, żeby wiedzieć, o
ile go poprawić) — polega na przestaniu udawać precyzję, której nie ma.

1. **NIE zgaduj i nie zmieniaj `scores.components`** dla tych 5 wpisów w tym pakiecie.
2. W panelu szczegółów, tuż przy wierszu „Podzespoły: X/100" dla tych 5 wpisów, dodaj jedno zdanie
   (podobnie jak przy plakietkach `isBrak`): „Ocena obejmuje założenie o pojemności dysku, której sklep
   nie podaje — traktuj ten wynik jako przybliżony." Znajdź te 5 wpisów po `storage === "SSD (pojemność
   brak w danych producenta)"`.
3. Zgłoś (nie wykonuj) osobne zadanie: ustalenie realnej pojemności tych 5 dysków ze stron sklepów —
   dokładnie tym samym trybem, co zlecone wcześniej zadanie dla karty graficznej SMX Battlestation M6A.
   Wypisz w raporcie kierownika listę tych 5 zestawów z ich `urls`, żeby dało się to zlecić.

**Odbiór 3B:** `scores` się nie zmienia; na stronie pojawia się jawne zastrzeżenie przy dokładnie tych 5
kartach; żadna inna karta go nie ma.

---

## Czego NIE robić

- **Nie uruchamiaj `pc_audit/build_all_pcs.py` ani `recheck/aktualizuj_pc.py`.** Oba są martwe (brak
  zależności / zamrożone dane z 17.09), obie mają inne, nieaktualne stawki dopłaty za Windows (519 zł),
  i próba ich odpalenia nadpisze poprawki z Pakietu 2 tego samego dnia.
- **Nie zgaduj pojemności dysku dla 5 wpisów z Etapu 3B.** To dokładnie ten błąd, który ten pakiet ma
  usunąć — podstawienie cichej wartości tam, gdzie jej nie znamy.
- **Nie licz od nowa całego `components`.** Nie mamy dla niego kodu źródłowego (patrz Pakiet 2, Etap 5) —
  ruszasz go wyłącznie w Etapie 3A, i to precyzyjnie zmierzoną, punktową korektą, nie przebudową wzoru.
- **Nie łącz Etapu 1/2 z Etapem 3 w jeden commit.** Etap 3 wymaga osobnej zgody i osobnego progu
  wycofania (patrz bramka 2/11 wyżej).

---

## Protokół weryfikacji (wykonuje Opus 5, niezależnie od raportu wykonawcy)

| # | Bramka | Próg |
|---|---|---|
| W1 | Etap 1: zmienionych ocen wobec `baza-2026-09-21-audyt2` | 0 |
| W2 | Etap 1.1: żaden z 4 wpisów `unknown` nie pokazuje słowa „Windows" w żadnym z 4 widoków sekcji PC | potwierdzone w każdym widoku osobno |
| W3 | Etap 1.3: filtry RAM „16"/„32" rozłączne na wszystkich 348 wpisach | 0 wpisów w obu naraz, 0 wpisów w żadnym |
| W4 | Etap 2: zmienionych ocen | 0 |
| W5 | Etap 3A: liczba wpisów `storage=="1000GB SSD"` po zmianie | 0 |
| W6 | Etap 3A: par (dawne 1000GB, jego bliźniak 1TB) z różnym `components` | 0 |
| W7 | Etap 3A: przestawionych progów budżetowych z 11 | ≤ 2, inaczej stop |
| W8 | Etap 3B: wpisów z jawnym zastrzeżeniem o pojemności dysku | dokładnie 5, i tylko tych 5 |
