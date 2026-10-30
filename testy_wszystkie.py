#!/usr/bin/env python3
"""Uruchamianie wszystkich test_*.py z katalogu."""

import argparse
import os
import subprocess
import sys
import time


def parsuj_argumenty():
    parser = argparse.ArgumentParser(
        description="Uruchamia po kolei wszystkie pliki test_*.py z katalogu."
    )
    parser.add_argument(
        "--katalog",
        default=os.path.dirname(os.path.abspath(__file__)),
        help="Katalog z testami (domyślnie katalog skryptu)",
    )
    parser.add_argument(
        "--szukaj",
        dest="szukaj",
        default=None,
        help="Uruchamia tylko testy, których nazwa zawiera podany tekst",
    )
    return parser.parse_args()


def pobierz_pliki_testowe(katalog, szukaj=None):
    if not os.path.isdir(katalog):
        return []
    pliki = []
    for f in sorted(os.listdir(katalog)):
        if f.startswith("test_") and f.endswith(".py"):
            if szukaj is not None and szukaj not in f:
                continue
            pliki.append(f)
    return pliki


def uruchom_test(katalog, plik_nazwa, limit_czasu=600):
    sciezka = os.path.join(katalog, plik_nazwa)
    start_czas = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, plik_nazwa],
            cwd=katalog,
            capture_output=True,
            text=True,
            timeout=limit_czasu,
        )
        czas = time.time() - start_czas
        wyjscie = (proc.stdout or "") + (proc.stderr or "")
        zaliczony = proc.returncode == 0
        adnotacja = None
    except subprocess.TimeoutExpired as exc:
        czas = time.time() - start_czas
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        wyjscie = stdout + stderr
        zaliczony = False
        adnotacja = "timeout"

    linie = [linia for linia in wyjscie.splitlines() if linia.strip()]
    if adnotacja == "timeout":
        ostatnia_linia = "timeout"
    else:
        ostatnia_linia = linie[-1] if linie else ""

    if len(ostatnia_linia) > 80:
        ostatnia_linia = ostatnia_linia[:80]

    return {
        "nazwa": plik_nazwa[:-3],
        "plik": plik_nazwa,
        "zaliczony": zaliczony,
        "czas": czas,
        "ostatnia_linia": ostatnia_linia,
        "linie_wyjscia": linie,
    }


def main():
    args = parsuj_argumenty()
    katalog = os.path.abspath(args.katalog)
    pliki = pobierz_pliki_testowe(katalog, args.szukaj)

    wyniki = []
    for f in pliki:
        wynik = uruchom_test(katalog, f, limit_czasu=600)
        wyniki.append(wynik)

    # Wypisz tabelę
    for w in wyniki:
        status = "OK" if w["zaliczony"] else "BŁĄD"
        print(f"{w['nazwa']} | {status} | {w['czas']:.2f} s | {w['ostatnia_linia']}")

    zaliczonych = sum(1 for w in wyniki if w["zaliczony"])
    lacznie = len(wyniki)

    print(f"ZALICZONE: {zaliczonych}/{lacznie}")

    niezaliczone = [w for w in wyniki if not w["zaliczony"]]
    if niezaliczone:
        for w in niezaliczone:
            print(f"\n--- Ostatnie linie dla {w['nazwa']} ---")
            ostatnie_8 = w["linie_wyjscia"][-8:] if w["linie_wyjscia"] else []
            for l in ostatnie_8:
                print(l)

    if lacznie > 0 and zaliczonych == lacznie:
        sys.exit(0)
    elif lacznie == 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
