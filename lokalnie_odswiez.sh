#!/bin/bash
# Odświeżenie cen i dostępności (+ opcjonalnie dopisanie nowych produktów). Jeden skrypt dla trzech miejsc:
#   - komputer właściciela (zadanie dzienne, x-kom odpowiada tylko stąd),
#   - GitHub Actions (.github/workflows/ceny.yml),
#   - ręcznie.
#
# UWAGA: robi `git reset --hard origin/main` — odpalaj WYŁĄCZNIE w osobnym klonie (~/Claude/grid-overdrive-bot)
# albo na runnerze CI, nigdy w katalogu roboczym z niezacommitowaną pracą.
# NOWE=1 → przed zbieraniem cen dopisuje nowe zestawy PC (limit 25) i monitory (limit 10).
# Przy wyścigu na `push` (ktoś wypchnął w międzyczasie) bierze świeży stan i nanosi to samo jeszcze raz.
#
# Kody wyjścia: 0 ok (także „brak zmian"), 10 git, 11 testy, 12 pokrycie < 50%, 2 bramka zgodności cen,
#               13 test_ranking, 14 push/nanoszenie, 15 awaria dopisywania (dane zapisane, ale przebieg do zgłoszenia).
set -u
glowna() {
  cd "$(dirname "$0")" || exit 10
  export LC_ALL=C.UTF-8
  LOG=${TMPDIR:-/tmp}
  AWARIA=0

  przygotuj() {
    git fetch -q origin main && git reset -q --hard origin/main || { echo "BŁĄD: git fetch/reset"; exit 10; }
    if [ "${NOWE:-0}" = "1" ]; then
      python3 nowe_pc.py --dopisz --limit 25 > "$LOG/nowe_pc.log" 2>&1
      python3 nowe_monitory.py --dopisz --limit 10 > "$LOG/nowe_mon.log" 2>&1
      grep -hE "^DO DOPISANIA|^!!! UWAGA" "$LOG/nowe_pc.log" "$LOG/nowe_mon.log"
      if grep -q "^!!! UWAGA" "$LOG/nowe_pc.log" "$LOG/nowe_mon.log"; then AWARIA=1; fi
    fi
  }
  nanies() {
    python3 nanies_zmiany.py --dzis > "$LOG/nanies.log" 2>&1; rc=$?
    if [ $rc -eq 2 ]; then grep -A30 "BRAMKA" "$LOG/nanies.log"; echo "BŁĄD: bramka zgodności cen"; exit 2; fi
    if [ $rc -ne 0 ]; then tail -5 "$LOG/nanies.log"; echo "BŁĄD: nanies_zmiany rc=$rc"; exit 14; fi
  }
  zapisz() {
    git config user.email "bot@grid-overdrive"; git config user.name "Grid Overdrive Bot"
    git add index.html monitors_1700_template.html images/pcs.json images/monitors.json coverage_log.json \
        raport_rano.json raport_katalogu.json raport_ocen.json raport_nowe_pc.json raport_nowe_monitory.json \
        monitory_odrzucone.json 2>/dev/null
    git commit -q -m "bot: odswiezenie cen i dostepnosci ($(date +%F), ${ZRODLO:-lokalnie})"
  }

  przygotuj
  python3 test_nanies.py >/dev/null 2>&1 && python3 test_ranking.py >/dev/null 2>&1 \
    || { echo "BŁĄD: testy kontrolne kodu nie przechodzą — nic nie zapisuję"; exit 11; }

  python3 zbieraj_ceny.py --watki 6 > "$LOG/zbieranie.log" 2>&1
  POKRYCIE=$(grep -o "POKRYCIE: [0-9]*/[0-9]* adresów ([0-9]*%)" "$LOG/zbieranie.log" | tail -1)
  PROC=$(echo "$POKRYCIE" | grep -o "([0-9]*%)" | tr -d '()%')
  echo "$POKRYCIE"
  if [ -z "$PROC" ] || [ "$PROC" -lt 50 ]; then echo "BŁĄD: pokrycie poniżej 50% — nic nie zapisuję"; exit 12; fi
  grep -E "^   (hardpc|morele|xkom|plugnplay|mediamarkt|goblinpc|mediaexpert|rtveuroagd) " "$LOG/zbieranie.log"

  nanies
  grep -E "^(zmian cen|dostępność|ukryte|przywrócone|do przejrzenia|sklepy bez)" "$LOG/nanies.log"
  python3 test_ranking.py >/dev/null 2>&1 || { echo "BŁĄD: test_ranking po nanoszeniu — nie commituję"; git checkout -q -- . ; exit 13; }

  if [ -z "$(git status --porcelain)" ]; then echo "brak zmian do zapisania"; [ $AWARIA -eq 1 ] && exit 15; exit 0; fi
  zapisz || { echo "brak zmian po add"; exit 0; }
  for proba in 1 2 3; do
    if git push -q origin HEAD:main; then
      echo "push OK (próba $proba)"
      [ $AWARIA -eq 1 ] && { echo "!!! UWAGA: dopisywanie nowych produktów zgłosiło awarię — szczegóły wyżej"; exit 15; }
      exit 0
    fi
    echo "push odrzucony (wyścig) — pobieram świeży stan i nanoszę ponownie"
    przygotuj; nanies; zapisz || { echo "po wyścigu brak zmian"; exit 0; }
  done
  echo "BŁĄD: push nie wyszedł po 3 próbach"; exit 14
}
glowna "$@"
exit $?
