#!/usr/bin/env python3
"""
Wczytuje price_updates.json (lista {key, new_price}) i nanosi zmiany na index.html:
- headline `price:` dla wpisu o danym `img:'<key>'`
- odpowiadający klucz w `prices:{...}` (store_key z check_list_auto.json)
- datę w PRICE_CHECK_LABEL i w treści strony (jeśli podano dzisiejszą datę)

Nie zgaduje niczego: wpis bez odpowiadającego `key` w index.html jest pomijany
i zgłaszany jako błąd (exit 1), żeby routine nie commitował cichej pomyłki.

Użycie:
  python3 apply_price_updates.py price_updates.json [--date "DD miesiąca RRRR"]
"""
import json, os, re, sys, argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("updates_file")
    ap.add_argument("--date", default=None, help='np. "12 września 2026" — aktualizuje etykietę "ostatnia weryfikacja"')
    ap.add_argument("--html", default="index.html")
    args = ap.parse_args()

    with open(args.updates_file, encoding="utf-8") as f:
        updates = json.load(f)
    with open("check_list_auto.json", encoding="utf-8") as f:
        auto_list = json.load(f)
    by_key = {e["key"]: e for e in auto_list}

    with open(args.html, encoding="utf-8") as f:
        html = f.read()

    changed = []
    unchanged = []
    errors = []

    for u in updates:
        key = u.get("key")
        new_price = u.get("new_price")
        if key is None or new_price is None:
            errors.append(f"wpis bez key/new_price: {u}")
            continue
        entry = by_key.get(key)
        if not entry:
            errors.append(f"klucz nieznany w check_list_auto.json: {key}")
            continue
        store_key = entry["store_key"]

        # headline price dla tego wpisu (kotwiczone przez unikalny img:'<key>')
        pattern_head = re.compile(r"(\{img:'" + re.escape(key) + r"', name:'[^']*', price:)(\d+)")
        m = pattern_head.search(html)
        if not m:
            errors.append(f"nie znaleziono wpisu img:'{key}' w {args.html}")
            continue
        old_price = int(m.group(2))

        if old_price == new_price:
            unchanged.append(key)
            continue

        html = pattern_head.sub(lambda mm: mm.group(1) + str(new_price), html, count=1)

        # odpowiadający klucz w prices:{...} tego samego wpisu — szukamy w tym samym
        # fragmencie (od pozycji dopasowania nagłówka do najbliższego '},\n    {img:' albo końca)
        entry_start = m.start()
        entry_end = html.find("},\n    {img:", entry_start)
        if entry_end == -1:
            entry_end = entry_start + 4000
        segment = html[entry_start:entry_end]
        prices_pattern = re.compile(r"(prices:\{[^}]*?\b" + re.escape(store_key) + r":)(\d+)")
        pm = prices_pattern.search(segment)
        if pm:
            new_segment = prices_pattern.sub(lambda mm: mm.group(1) + str(new_price), segment, count=1)
            html = html[:entry_start] + new_segment + html[entry_end:]

        changed.append({"key": key, "name": entry["name"], "old": old_price, "new": new_price})

    if args.date:
        html = re.sub(r"Ostatnia weryfikacja cen: [^—]+—", f"Ostatnia weryfikacja cen: {args.date} —", html)
        html = re.sub(r"var PRICE_CHECK_LABEL = '[^']*';", f"var PRICE_CHECK_LABEL = '{args.date}';", html)

    with open(args.html, "w", encoding="utf-8") as f:
        f.write(html)

    # Te same ceny nanosimy na szablon — źródło, z którego buduje się stronę.
    # Wcześniej ceny szły wyłącznie do index.html, więc szablon zostawał w tyle (AOC Q27G4ZR:
    # 789 zł w szablonie wobec 899 zł na stronie) i każda przebudowa cofała tydzień pracy
    # Routine. Kotwica regexowa jest ta sama, bo dane siedzą w szablonie — poza szablonem
    # są tylko obrazy. Robimy to tutaj, a nie w konfiguracji Routine, bo Routine woła ten
    # skrypt bez zmian i nie da się jej edytować z sesji.
    szablon_plik = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "monitors_1700_template.html")
    szablon_zmian = 0
    if os.path.exists(szablon_plik) and os.path.abspath(szablon_plik) != os.path.abspath(args.html):
        with open(szablon_plik, encoding="utf-8") as f:
            szablon = f.read()
        for c in changed:
            wzor = re.compile(r"(\{img:'" + re.escape(c["key"]) + r"', name:'[^']*', price:)(\d+)")
            szablon, n = wzor.subn(lambda mm: mm.group(1) + str(c["new"]), szablon, count=1)
            szablon_zmian += n
        if args.date:
            szablon = re.sub(r"Ostatnia weryfikacja cen: [^—]+—",
                             f"Ostatnia weryfikacja cen: {args.date} —", szablon)
            szablon = re.sub(r"var PRICE_CHECK_LABEL = '[^']*';",
                             f"var PRICE_CHECK_LABEL = '{args.date}';", szablon)
        with open(szablon_plik, "w", encoding="utf-8") as f:
            f.write(szablon)
        if changed and szablon_zmian != len(changed):
            errors.append(f"szablon: naniesiono {szablon_zmian} z {len(changed)} zmian "
                          f"— szablon rozjechał się z index.html")

    print(json.dumps({
        "changed": changed,
        "unchanged_count": len(unchanged),
        "template_synced": szablon_zmian,
        "errors": errors
    }, ensure_ascii=False, indent=1))

    if errors:
        sys.exit(1)

if __name__ == "__main__":
    main()
