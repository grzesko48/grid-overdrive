#!/bin/bash
# Dzienne odświeżenie cen i dostępności Z KOMPUTERA WŁAŚCICIELA (x-kom odpowiada tylko stąd — z chmury 403).
#
# Działa w OSOBNYM klonie (~/Claude/grid-overdrive-bot), nigdy w katalogu roboczym: robi `git reset --hard`,
# więc nie wolno go odpalać tam, gdzie leży niezacommitowana praca. Chmurowa Rutyna (co 2 dni) robi swoje
# równolegle; oba źródła nanoszą te same wyliczane pliki, więc przy wyścigu na `push` skrypt bierze świeży
# stan z GitHuba i NANOSI TE SAME CENY JESZCZE RAZ (zebrane_ceny.json zostaje), zamiast scalać pliki ręcznie.
#
# Kody wyjścia: 0 ok (także „brak zmian"), 10 git, 11 testy, 12 zbieranie (pokrycie < 50%),
#               2 bramka zgodności cen, 13 test_ranking, 14 push nie wyszedł.
set -u
cd "$(dirname "$0")" || exit 10
export LC_ALL=en_US.UTF-8

git fetch -q origin main && git reset -q --hard origin/main || { echo "BŁĄD: git fetch/reset"; exit 10; }
python3 test_nanies.py >/dev/null 2>&1 && python3 test_ranking.py >/dev/null 2>&1 \
  || { echo "BŁĄD: testy kontrolne kodu nie przechodzą — nic nie zapisuję"; exit 11; }

python3 zbieraj_ceny.py --watki 6 > /tmp/lokalnie_zbieranie.log 2>&1
POKRYCIE=$(grep -o "POKRYCIE: [0-9]*/[0-9]* adresów ([0-9]*%)" /tmp/lokalnie_zbieranie.log | tail -1)
PROC=$(echo "$POKRYCIE" | grep -o "([0-9]*%)" | tr -d '()%')
echo "$POKRYCIE"
if [ -z "$PROC" ] || [ "$PROC" -lt 50 ]; then echo "BŁĄD: pokrycie poniżej 50% — nic nie zapisuję"; exit 12; fi
grep -E "^   (hardpc|morele|xkom|plugnplay|mediamarkt|goblinpc|mediaexpert|rtveuroagd) " /tmp/lokalnie_zbieranie.log

nanies() {
  python3 nanies_zmiany.py --dzis > /tmp/lokalnie_nanies.log 2>&1; rc=$?
  if [ $rc -eq 2 ]; then cat /tmp/lokalnie_nanies.log | grep -A30 "BRAMKA"; echo "BŁĄD: bramka zgodności cen"; exit 2; fi
  [ $rc -ne 0 ] && { tail -5 /tmp/lokalnie_nanies.log; echo "BŁĄD: nanies_zmiany rc=$rc"; exit 14; }
  return 0
}
nanies
grep -E "^(zmian cen|dostępność|ukryte|przywrócone|do przejrzenia|sklepy bez)" /tmp/lokalnie_nanies.log
python3 test_ranking.py >/dev/null 2>&1 || { echo "BŁĄD: test_ranking po nanoszeniu — nie commituję"; git checkout -q -- . ; exit 13; }

if git diff --quiet && [ -z "$(git status --porcelain)" ]; then echo "brak zmian do zapisania"; exit 0; fi
git config user.email "lokalny@grid-overdrive"; git config user.name "Grid Overdrive (lokalnie)"
git add index.html monitors_1700_template.html coverage_log.json raport_rano.json raport_katalogu.json raport_ocen.json 2>/dev/null
git commit -q -m "bot lokalny: odswiezenie cen i dostepnosci (x-kom z komputera wlasciciela)" || { echo "brak zmian po add"; exit 0; }
for proba in 1 2 3; do
  git push -q origin HEAD:main && { echo "push OK (próba $proba)"; exit 0; }
  echo "push odrzucony (wyścig z chmurą) — pobieram świeży stan i nanoszę te same ceny ponownie"
  git fetch -q origin main && git reset -q --hard origin/main || exit 10
  nanies
  git add index.html monitors_1700_template.html coverage_log.json raport_rano.json raport_katalogu.json raport_ocen.json 2>/dev/null
  git commit -q -m "bot lokalny: odswiezenie cen i dostepnosci (x-kom z komputera wlasciciela)" || { echo "po wyścigu brak zmian"; exit 0; }
done
echo "BŁĄD: push nie wyszedł po 3 próbach"; exit 14
