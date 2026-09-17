# Plan naprawczy Grid Overdrive — do wykonania przez Sonnet 5, do weryfikacji przez Opus 5

Podstawa: audyt Rady Firmy z 17.09.2026 (działy ai / finanse / dataviz). **Wszystkie dziewięć ustaleń
zostało potwierdzonych niezależnym pomiarem narzędziowym** — nie ma tu hipotez do rozstrzygnięcia,
są zadania do wykonania.

Podział ról jest celowy: ten plan powstał na mocnym modelu, żeby wykonanie było mechaniczne, a kontrola
końcowa wróciła na mocny model. **Wykonawca nie ocenia, czy zadanie ma sens — wykonuje je i zgłasza wynik
testu odbioru.** Jeśli test odbioru nie przechodzi, wykonawca ZATRZYMUJE się i opisuje, co zobaczył;
nie improwizuje obejścia.

---

## Stan wyjściowy — sprawdź, zanim cokolwiek zmienisz

Plan powstał 17.09.2026 na konkretnym stanie plików. Jeśli poniższe liczby się nie zgadzają, ktoś
ruszył pliki po napisaniu planu — **zatrzymaj się i zgłoś to**, zamiast szukać kotwic na wyczucie.

```bash
cd /Users/grzegorzrybak/Claude/grid-overdrive && python3 - <<'PY'
t=open('monitors_1700_template.html',encoding='utf-8').read()
a=open('apply_price_updates.py',encoding='utf-8').read()
oczek=[("szablon: pełna fraza etykiety","Ostatnia weryfikacja cen: 17 września 2026 —",t,3),
       ("szablon: sama data","17 września 2026",t,4),
       ("szablon: deklaracja zmiennej","var PRICE_CHECK_LABEL",t,1),
       ("szablon: zdanie uszkodzone","Każda cena ma teraz widoczną etykietę „Ostatnia",t,1),
       ("szablon: deklaracja o cenie","podano najniższą potwierdzoną cenę",t,1),
       ("szablon: nota o Windows","Ceny poniżej liczone razem z Windows 11",t,1),
       ("szablon: metodyka PC","jeszcze niewykonana runda dla PC",t,1),
       ("szablon: karta statystyk","od 9518 zł z Windows",t,1),
       ("skrypt: regex zjadający prozę",'re.sub(r"Ostatnia weryfikacja cen: [^—]+—"',a,2)]
zle=[(n,o,s.count(f)) for n,f,s,o in oczek if s.count(f)!=o]
for n,o,j in zle: print(f"NIE ZGADZA SIĘ: {n} — oczekiwano {o}, jest {j}")
print("STAN WYJŚCIOWY ZGODNY Z PLANEM" if not zle else "STAN INNY NIŻ W PLANIE — ZATRZYMAJ SIĘ")
PY
```

Trzy z tych liczb warto rozumieć, bo to one są sednem usterki Z-01: pełna fraza etykiety stoi
w **trzech** miejscach (raz w prozie metodyki, dwa razy w interfejsie), a data jako taka w **czterech**
(te trzy plus deklaracja zmiennej). Regex z `apply_price_updates.py` trafia we wszystkie trzy — i o to
właśnie chodzi w tej naprawie. Po etapie 1 zostaje **jedno** wystąpienie daty: w deklaracji zmiennej.

## Zasady twarde (łamanie ich unieważnia cały przebieg)

1. **Edytujesz wyłącznie `monitors_1700_template.html`.** `index.html` i `artifact.html` są plikami
   wynikowymi — powstają z `python3 build_merged.py`. Ręczna edycja `index.html` zostanie nadpisana.
2. **Po każdym etapie uruchamiasz `python3 build_merged.py`** i sprawdzasz, że kończy się bez asercji.
3. **Nie uruchamiasz `apply_price_updates.py` z parametrem `--date`, dopóki nie skończysz zadania Z-01.**
   Do tego czasu ten skrypt niszczy tekst strony przy każdym wywołaniu.
4. **Nie dotykasz:** katalogu `images/`, tablic `PDATA`/`DATA` w części liczbowej (ceny, `scores`,
   `longevityYears`), katalogu `recheck/`, plików `pc_audit/` i `audit/`. Ocen nie przeliczamy — zostały
   przeliczone 17.09 i są zgodne z danymi (zweryfikowane: 2880 wartości, 0 rozbieżności).
5. **Jeden commit na etap**, z komunikatem podanym przy etapie. Nie łącz etapów w jeden commit.
6. **Nie publikujesz artefaktu ani nie robisz `git push`.** Publikację wykonuje weryfikator po odbiorze.
7. Każdy tekst, który wstawiasz, jest po polsku, z polskimi cudzysłowami „ ", bez skrótów myślowych.

---

## ETAP 1 — automat przestaje niszczyć stronę (najpilniejsze)

### Z-01. Zdejmij regex, który zjada prozę
**Problem:** `apply_price_updates.py` podmienia datę wzorcem `Ostatnia weryfikacja cen: [^—]+—`,
który trafia w **trzy** miejsca dokumentu — dwa w interfejsie i jedno w akapicie metodyki. W prozie
wzorzec pożera wszystko aż do pierwszej pauzy, kasując fragment zdania. Dzieje się tak od **pierwszego
przebiegu bota 9.09.2026 (commit e215aa2)**, w każdym kolejnym.

**Plik:** `apply_price_updates.py`

Usuń **dwa** wiersze (jeden w bloku dla `args.html`, drugi w bloku szablonu) w tej postaci:
```python
html = re.sub(r"Ostatnia weryfikacja cen: [^—]+—", f"Ostatnia weryfikacja cen: {args.date} —", html)
```
```python
szablon = re.sub(r"Ostatnia weryfikacja cen: [^—]+—",
                 f"Ostatnia weryfikacja cen: {args.date} —", szablon)
```
Zostaw nietknięte podmiany na `var PRICE_CHECK_LABEL = '…';` — to jedyna kotwica, która ma działać.

Dopisz nad pozostałą podmianą komentarz:
```python
# Datę trzyma JEDNA zmienna. Wcześniej podmieniał ją regex szukający frazy „Ostatnia weryfikacja cen:"
# w całym dokumencie — trafiał też w akapit metodyki i przy każdym przebiegu ucinał tam fragment zdania
# (od 9.09.2026, commit e215aa2). Wzorzec kotwiczony na deklaracji zmiennej nie ma jak trafić w prozę.
```

**Test odbioru Z-01:** `grep -c 'Ostatnia weryfikacja cen: \[^—\]' apply_price_updates.py` → **0**.

---

### Z-02. Napraw zdanie zniszczone przez automat
**Plik:** `monitors_1700_template.html`

Znajdź (jest dokładnie jedno wystąpienie):
```
Każda cena ma teraz widoczną etykietę „Ostatnia weryfikacja cen: 17 września 2026 — to jest realne źródło prawdy o cenie w danej chwili.
```
Zamień na:
```
Każda cena ma teraz widoczną etykietę z datą ostatniej weryfikacji, a każdy link zawsze prowadzi do żywej, aktualnej strony produktu w sklepie — to jest realne źródło prawdy o cenie w danej chwili.
```
Odtworzony fragment (`, a każdy link zawsze prowadzi do żywej, aktualnej strony produktu w sklepie`)
pochodzi z commita `b659607` sprzed uszkodzenia — nie jest zmyślony. Data została z tego zdania usunięta
celowo: proza nie ma powtarzać liczby, która żyje w zmiennej.

**Test odbioru Z-02:** w `monitors_1700_template.html` fraza `Każda cena ma teraz widoczną etykietę`
występuje raz i **nie zawiera** ciągu `2026`.

---

### Z-03. Etykiety w interfejsie mają brać datę ze zmiennej
**Problem:** `var PRICE_CHECK_LABEL` jest zdefiniowana (linia ~1126), ale **nigdzie nieużywana** — obie
etykiety mają datę wpisaną na twardo, dlatego automat musiał ich szukać tekstem.

**Plik:** `monitors_1700_template.html`, dwa miejsca (~1143 dla monitorów, ~1994 dla PC).

W obu zamień fragment `Ostatnia weryfikacja cen: 17 września 2026 —` wewnątrz łańcucha JavaScriptu na
sklejenie ze zmienną: `Ostatnia weryfikacja cen: ' + PRICE_CHECK_LABEL + ' —`.

Przy okazji (to jest naprawa ustalenia **R-09**) rozszerz treść etykiety **monitorów** (~1143) tak, żeby
nie obiecywała jednakowej świeżości wszystkich cen:
```
Ostatnia weryfikacja cen: ' + PRICE_CHECK_LABEL + ' — x-kom i Morele sprawdzane codziennie automatycznie, pozostałe sklepy rzadziej i ręcznie; kliknięcie zawsze prowadzi do aktualnej, żywej ceny w sklepie.
```
Powód liczbowy: w danych jest 164 cen sklepowych monitorów, a automat obejmuje 50 z nich.

**Test odbioru Z-03:** ciąg `17 września 2026` występuje w szablonie **dokładnie raz** (w deklaracji
`PRICE_CHECK_LABEL`); `grep -c "PRICE_CHECK_LABEL" monitors_1700_template.html` → **3**.

---

### Z-04. Test regresji automatu (obowiązkowy, na kopii)
Wykonaj na kopii, nie na repozytorium:
```bash
cd /tmp && rm -rf go_test && cp -r /Users/grzegorzrybak/Claude/grid-overdrive go_test && cd go_test
echo '[]' > price_updates.json
python3 apply_price_updates.py price_updates.json --date "1 stycznia 2099"
```
Następnie sprawdź w `/tmp/go_test/index.html`:
- fraza `Każda cena ma teraz widoczną etykietę` jest **nienaruszona** i nie zawiera `2099`;
- `var PRICE_CHECK_LABEL = '1 stycznia 2099';` — podmienione;
- `git diff --stat` pokazuje zmianę wyłącznie w `index.html`, `monitors_1700_template.html`
  i `price_updates.json`.

**To jest najważniejszy test całego planu** — sprawdza dokładnie ten błąd, który przez osiem dni
nikt nie zauważył. Jeśli nie przechodzi, zatrzymaj się tutaj.

**Commit etapu 1:** `Napraw automat niszczący tekst strony przy podmianie daty`

---

## ETAP 2 — strona przestaje twierdzić nieprawdę

Wszystkie zadania tego etapu to zmiany w tekście. Zero ryzyka regresji, duży wpływ na wiarygodność.

### Z-05. Ranking PC opisany formułą, której nie używa (R-02)
Nagłówek „Ranking ogólny — PC" opisuje wagi `Podzespoły 28 + Opłacalność 32 + Wydajność 27 +
Kompletność 13` (pole `overall`), a widok sortuje po `scores.ultra` (perf 28 + longevity 30 + value 22 +
components 12 + features 8). **Sortowanie jest zamierzone — nieaktualny jest opis.**

W akapicie `lede` pod `<h2>Ranking ogólny — PC</h2>` zamień opis wag na:
```
Wynik ważony „Ultra": Wydajność (indeks mocy: 78% poziom GPU + 22% poziom CPU) 28% + Długowieczność (klasa karty, pamięć karty, ilość RAM) 30% + Opłacalność (cena z Windows za indeks mocy) 22% + Podzespoły (CPU, RAM DDR5, dysk) 12% + Kompletność (zasilacz, system, liczba sklepów) 8%, w skali 1–100. Ranking celowo stawia jakość grania i długowieczność ponad samą opłacalność.
```
**Test odbioru:** w szablonie pod nagłówkiem `Ranking ogólny — PC` nie występuje już ciąg `32%`,
a występuje `30%` i słowo `Długowieczność`.

### Z-06. Deklaracja o najniższej cenie niezgodna z danymi (R-04)
Strona deklaruje: „w karcie/tabeli podano najniższą potwierdzoną cenę wraz z tym sklepem". W 7 z 57
monitorów cena nagłówkowa jest **wyższa** od najniższej ceny w tym samym wpisie (do 110 zł —
AOC Q27G4ZR: 899 wobec 789). Nagłówek pokazuje cenę sklepu odświeżanego codziennie, nie minimum.

Zamień to zdanie na:
```
gdy model jest dostępny w kilku sklepach, w karcie podano cenę tego sklepu, który sprawdzamy codziennie automatycznie; pełną listę cen wraz z najtańszą ofertą podświetloną na zielono zobaczysz po rozwinięciu karty.
```
**Test odbioru:** ciąg `podano najniższą potwierdzoną cenę` nie występuje w szablonie.

### Z-07. Nota o cenie z Windows mówi odwrotnie, niż jest (R-07)
W 291 z 360 zestawów pole `prices{}` trzyma cenę **bez** systemu, a nota nad wierszami mówi
„Ceny poniżej liczone razem z Windows 11" i zaraz obok podaje „(bez systemu: X zł)" — tę samą kwotę,
która stoi w wierszach. Czytelnik widzi jedną liczbę opisaną dwoma sprzecznymi etykietami.

W funkcji budującej wiersze cen PC (~1993) zamień wyrażenie `osNote` na:
```javascript
var osNote = d.osPriceKind==='included' ? '' : (' Ceny w sklepach poniżej to kwoty bez systemu; w nagłówku karty podano cenę z doliczonym Windows 11 (+'+(d.price-d.priceBare)+' zł).');
```
**Test odbioru:** ciąg `Ceny poniżej liczone razem z Windows 11` nie występuje w szablonie.

### Z-08. Metodyka zaprzecza wykonanej pracy (R-05)
Akapit twierdzi, że ceny PC to „zweryfikowany stan na 8 września 2026" i że runda cenowa dla PC jest
„osobna, jeszcze niewykonana". 17.09 wykonano ją: usunięto 132 nieistniejące zestawy i zmieniono 271 cen.

Zamień ten fragment na opis stanu faktycznego:
```
ceny zestawów PC zweryfikowano 17 września 2026: przejrzano katalogi sklepów, usunięto 132 zestawy, których sklepy już nie mają, i naniesiono 271 nowych cen. Sekcja PC nie ma jeszcze automatycznego odświeżania dziennego — ceny sprawdzane są ręcznie, a każdy link prowadzi do żywej strony produktu.
```
**Test odbioru:** ciąg `jeszcze niewykonana runda dla PC` nie występuje; występuje `17 września 2026`
w akapicie o cenach PC.

### Z-09. Karta statystyk podaje cenę innego zestawu (R-03)
Karta mówi „RTX 5070 Ti — najmocniejsza karta — Hard-PC.pl, od 9518 zł z Windows". Kwota 9518 zł należy
do zestawu z **RX 9060 XT**. Najtańszy realny RTX 5070 Ti to **9718 zł**.

Przelicz **wszystkie cztery** karty statystyk sekcji PC z danych i popraw te, które się nie zgadzają:
```bash
cd /Users/grzegorzrybak/Claude/grid-overdrive && python3 - <<'PY'
import re
s=open('monitors_1700_template.html',encoding='utf-8').read()
pd=s[s.index("var PDATA = ["):s.index("var PC_BY_SLUG")]
rek=[]
for m in re.finditer(r'\{img:"[^"]+", name:"([^"]*)".*?gpu:"([^"]*)".*?price:(\d+), store:"([^"]*)"', pd):
    rek.append({"name":m.group(1),"gpu":m.group(2),"price":int(m.group(3)),"store":m.group(4)})
print("zestawow:", len(rek))
naj=min(rek,key=lambda r:r["price"]); print("najtanszy:", naj["price"], naj["name"][:60], "|", naj["gpu"])
ti=[r for r in rek if "5070 Ti" in r["gpu"] or "5070 TI" in r["gpu"].upper()]
print("RTX 5070 Ti:", len(ti), "| najtanszy:", min(ti,key=lambda r:r["price"]) if ti else "brak")
print("sklepow:", len({r["store"] for r in rek}))
PY
```
Wstaw wyniki do kart. **Test odbioru:** liczby w czterech kartach zgadzają się z wyjściem tego skryptu.

**Commit etapu 2:** `Popraw zdania i liczby, które strona podawała niezgodnie z danymi`

---

## ETAP 3 — widoczność degradacji automatu (R-06)

**Ustalenie:** automat zebrał 49/50 cen w pierwszym przebiegu (9.09), potem załamał się do 7/50 (10.09)
i wraca powoli — 12, 17, 19, 19, 21, 22, 20. Czyli pokrywa **14–44%** własnej listy, a nikt tego nie
widzi, bo commit wygląda tak samo przy 7 i przy 49 pozycjach.

Nie naprawiamy tu przyczyny — jest po stronie Routine w chmurze, poza tym repozytorium. **Naprawiamy
niewidzialność.**

### Z-10. Dziennik pokrycia
W `apply_price_updates.py`, po wyliczeniu `changed`/`unchanged`, dopisz zapis do `coverage_log.json`
(twórz plik, jeśli nie istnieje; dopisuj jeden wpis na przebieg):
```json
{"data": "<--date albo dzisiejsza>", "zebranych": <len(updates)>, "oczekiwanych": <len(auto_list)>,
 "pokrycie_proc": <procent>, "zmienionych": <len(changed)>, "brakujace_klucze": [<klucze z listy bez wpisu>]}
```
Dopisz też do wyjścia skryptu linię czytelną dla człowieka:
`POKRYCIE: <zebranych>/<oczekiwanych> (<proc>%)`.

**Test odbioru Z-10:** uruchomienie na kopii (jak w Z-04) tworzy `coverage_log.json` z jednym wpisem,
w którym `oczekiwanych` = 50.

**Commit etapu 3:** `Dopisz dziennik pokrycia, żeby spadek skuteczności automatu był widoczny`

---

## ETAP 4 — status magazynowy (R-08), tylko jeśli etapy 1–3 przeszły

Dwa monitory są wyprzedane w Morele (`Acer Nitro XZ273UX2bmiiprx`, `Gigabyte GS27Q X`), a ich cena
wygląda na kupowalną. Schemat danych nie ma gdzie zapisać dostępności.

### Z-11. Pole i plakietka
1. W obu wpisach `DATA` dodaj pole `soldout:['morele']`.
2. W funkcji budującej wiersze cen monitorów: gdy klucz sklepu jest w `d.soldout`, dopisz do wiersza
   `<span class="punavail">chwilowo niedostępne</span>` i **wyklucz ten sklep z wyliczania najtańszej
   oferty** (`minPrice`).
3. Klasa `.punavail` już istnieje w arkuszu stylów — nie dodawaj nowej.

**Test odbioru Z-11:** w zbudowanym `index.html` oba modele mają `soldout`, a podświetlenie „najtańsza"
nie wskazuje na Morele w żadnym z nich.

**Commit etapu 4:** `Oznacz oferty wyprzedane i wyklucz je z wyboru najtańszej ceny`

---

## ETAP 5 — przebudowa i raport

```bash
cd /Users/grzegorzrybak/Claude/grid-overdrive && python3 build_merged.py
```
Następnie napisz **RAPORT WYKONANIA** (w odpowiedzi, nie w pliku) w formacie:

| Zadanie | Status | Test odbioru | Co zobaczyłem |
|---|---|---|---|
| Z-01 … Z-11 | ZROBIONE / ZATRZYMANE | PRZESZEDŁ / NIE | jedno zdanie |

Do tego: lista commitów (`git log --oneline`) i wynik `git status --short`.
**Nie publikuj i nie wypychaj zmian.**

---

## PROTOKÓŁ WERYFIKACJI (wykonuje Opus 5, niezależnie od raportu wykonawcy)

Weryfikacja nie polega na przeczytaniu raportu. Każdy punkt ma dać **liczbę albo wartość logiczną**
wyprowadzoną z plików, nie z relacji wykonawcy.

**W1. Test regresji automatu — najważniejszy.** Na świeżej kopii repozytorium uruchomić
`apply_price_updates.py --date "1 stycznia 2099"` z pustą listą i sprawdzić, że akapit
`Każda cena ma teraz widoczną etykietę` jest znak w znak taki sam przed i po. Porównanie sumą SHA
fragmentu, nie okiem.

**W2. Jedna data w źródle.** `grep -c "17 września 2026" monitors_1700_template.html` → 1.
Ciąg `Ostatnia weryfikacja cen: [^—]+` nie występuje w `apply_price_updates.py`.

**W3. Zdania kontra dane — przeliczyć od zera, nie ufać wykonawcy.**
- cztery karty statystyk PC kontra `PDATA` (najtańszy, najmocniejsza karta, liczba zestawów, liczba sklepów);
- opis wag rankingu PC kontra wzór faktycznie użyty w `renderPcRanking`;
- brak w szablonie ciągów: `podano najniższą potwierdzoną cenę`, `Ceny poniżej liczone razem z Windows 11`,
  `jeszcze niewykonana runda dla PC`.

**W4. Niczego nie zepsuto po drodze.** Po przebudowie: `DATA` = 57 pozycji, `PDATA` = 360,
suma `scores.ultra` identyczna jak przed zmianami (oceny miały zostać nietknięte), obrazy = 62 + 150.

**W5. Strona żyje.** Serwer lokalny, `document.compatMode === 'CSS1Compat'`, zero błędów w konsoli,
liczniki pokazują 57 i 360, ranking PC się renderuje.

**W6. Kontrola zakresu zmian.** `git diff b_przed..HEAD --stat` — zmienione mają być wyłącznie:
`monitors_1700_template.html`, `apply_price_updates.py`, `index.html`, `artifact.html`,
`coverage_log.json`. Każdy inny plik w diffie = zawrót.

**W7. Kontrola na cudzą robotę.** Wyszukać w zmienionym tekście zdania, które twierdzą coś, czego
dane nie potwierdzają — tak samo jak robiła to Rada. Naprawa, która wprowadza nowe twierdzenie bez
pokrycia, jest gorsza od usterki, którą naprawiała.

Dopiero po komplecie W1–W7: `git push` i publikacja `artifact.html` pod istniejący adres artefaktu
(**nie** `index.html` — ten ma własny szkielet i zagnieździłby się w szkielecie platformy).

---

## Czego NIE robić

- Nie przeliczać ocen ani nie ruszać `scores` — zweryfikowane, 0 rozbieżności na 2880 wartościach.
- Nie zmieniać semantyki ceny nagłówkowej monitorów na minimum z `prices{}` — automat nadpisuje to pole
  codziennie ceną sklepu domowego i zmiana rozjedzie się przy najbliższym przebiegu. Naprawiamy **opis**,
  nie mechanizm.
- Nie usuwać 4 pozycji, przy których Media Expert i RTV zniknęły z ofert Ceneo — brak oferty na
  porównywarce to za słaby dowód, żeby skasować cenę.
- Nie próbować naprawiać przyczyny spadku pokrycia automatu — leży w konfiguracji Routine w chmurze
  claude.ai, której z sesji nie widać ani nie da się edytować.
- Nie dodawać nowych funkcji strony. To jest przebieg naprawczy.
