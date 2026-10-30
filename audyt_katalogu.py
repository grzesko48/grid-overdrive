#!/usr/bin/env python3
"""Audyt katalogu porównywarki PC względem stron sklepów.

Dla każdego wpisu PC w szablonie HTML pobiera stronę sklepu i porównuje pola
katalogu ze specyfikacją zwróconą przez adapter sklepu.
"""

import argparse
import importlib
import json
import os
import re
import sys

BAZA = os.path.dirname(os.path.abspath(__file__))
if BAZA not in sys.path:
    sys.path.insert(0, BAZA)

import nanies_zmiany
import ocena_pc
import zbieraj_ceny


def _wyciagnij_pole_str(seg, nazwa):
    """Wycina wartość pola tekstowego w cudzysłowach lub apostrofach z segmentu wpisu."""
    m = re.search(r'\b' + nazwa + r':\s*"([^"]*)"', seg)
    if m:
        return m.group(1)
    m = re.search(r"\b" + nazwa + r":\s*'([^']*)'", seg)
    if m:
        return m.group(1)
    return ""


def _wyciagnij_pole_int(seg, nazwa):
    """Wycina wartość liczbową pola z segmentu wpisu."""
    m = re.search(r'\b' + nazwa + r':\s*"?(\d+)"?', seg)
    return int(m.group(1)) if m else None


def _znajdz_segment(sz, start, granice_list):
    """Wyznacza granice segmentu pojedynczego wpisu w szablonie."""
    if start in granice_list:
        idx = granice_list.index(start)
        stop = granice_list[idx + 1] if idx + 1 < len(granice_list) else len(sz)
    else:
        import bisect
        idx = bisect.bisect_right(granice_list, start)
        stop = granice_list[idx] if idx < len(granice_list) else len(sz)
    return sz[start:stop]


def audytuj(sz, adaptery, pobierz, tolerancja_ceny=0.05, maks=None, sklepy=None) -> list[dict]:
    """Audytuje katalog PC względem danych ze sklepów."""
    wszystkie = zbieraj_ceny.wczytaj(sz)
    wpisy_pc = [p for p in wszystkie if p.get("rodzaj") == "pc"]
    
    if sklepy is None:
        if maks is not None:
            wpisy_pc = wpisy_pc[:int(maks)]
        sklepy_set = None
    else:
        sklepy_set = set(sklepy)

    granice_list = nanies_zmiany.granice(sz)
    wyniki = []

    for p in wpisy_pc:
        if sklepy_set is not None and maks is not None and len(wyniki) >= int(maks):
            break

        start = p.get("start", 0)
        seg = None
        nazwa = None
        katalog_cpu = None
        katalog_gpu = None
        katalog_ram = None
        katalog_storage = None
        katalog_psu = None
        katalog_price_bare = None

        urls = p.get("urls", {})
        for sklep, url in urls.items():
            if sklepy_set is not None and sklep not in sklepy_set:
                continue

            if sklepy_set is not None and maks is not None and len(wyniki) >= int(maks):
                break

            if seg is None:
                seg = _znajdz_segment(sz, start, granice_list)
                nazwa = p.get("name") or _wyciagnij_pole_str(seg, "name")
                katalog_cpu = _wyciagnij_pole_str(seg, "cpu")
                katalog_gpu = _wyciagnij_pole_str(seg, "gpu") or p.get("gpu", "")
                katalog_ram = _wyciagnij_pole_str(seg, "ram") or p.get("ram", "")
                katalog_storage = _wyciagnij_pole_str(seg, "storage")
                katalog_psu = _wyciagnij_pole_str(seg, "psu")
                katalog_price_bare = _wyciagnij_pole_int(seg, "priceBare") or p.get("priceBare")

            if sklep not in adaptery:
                wyniki.append({
                    "nazwa": nazwa,
                    "sklep": sklep,
                    "url": url,
                    "status": "brak_adaptera",
                    "roznice": [],
                })
                continue

            adapter = adaptery[sklep]

            try:
                kod_http, html = pobierz(url)
            except Exception as e:
                kod_http, html = None, str(e)

            if kod_http in (403, 429) or (kod_http is None and html == "robots"):
                wyniki.append({
                    "nazwa": nazwa,
                    "sklep": sklep,
                    "url": url,
                    "status": "zablokowany",
                    "roznice": [],
                })
                continue

            if kod_http != 200:
                wyniki.append({
                    "nazwa": nazwa,
                    "sklep": sklep,
                    "url": url,
                    "status": "nieodczytany",
                    "roznice": [],
                    "powod": f"Błąd HTTP {kod_http}: {html}",
                })
                continue

            try:
                dane_sklepu = adapter.odczytaj_pc(url, html)
            except ocena_pc.BrakDanych as e:
                wyniki.append({
                    "nazwa": nazwa,
                    "sklep": sklep,
                    "url": url,
                    "status": "nieodczytany",
                    "roznice": [],
                    "powod": str(e),
                })
                continue
            except Exception as e:
                wyniki.append({
                    "nazwa": nazwa,
                    "sklep": sklep,
                    "url": url,
                    "status": "nieodczytany",
                    "roznice": [],
                    "powod": str(e),
                })
                continue

            roznice = []

            # 1. GPU: ta sama klasa i ta sama pamięć
            gpu_kat = katalog_gpu
            gpu_skl = dane_sklepu.get("gpu", "")
            gpu_zgodne = True
            try:
                klasa_kat = ocena_pc.klasa_gpu(gpu_kat)
                pamiec_kat = ocena_pc.pamiec_gpu_gb(gpu_kat)
                klasa_skl = ocena_pc.klasa_gpu(gpu_skl)
                pamiec_skl = ocena_pc.pamiec_gpu_gb(gpu_skl)
                if klasa_kat != klasa_skl or pamiec_kat != pamiec_skl:
                    gpu_zgodne = False
            except ocena_pc.BrakDanych:
                gpu_zgodne = False
            except Exception:
                gpu_zgodne = False

            if not gpu_zgodne:
                roznice.append({
                    "pole": "gpu",
                    "katalog": gpu_kat,
                    "sklep": gpu_skl,
                })

            # 2. CPU: ta sama klasa
            cpu_kat = katalog_cpu
            cpu_skl = dane_sklepu.get("cpu", "")
            cpu_zgodne = True
            try:
                klasa_kat = ocena_pc.klasa_cpu(cpu_kat)
                klasa_skl = ocena_pc.klasa_cpu(cpu_skl)
                if klasa_kat != klasa_skl:
                    cpu_zgodne = False
            except ocena_pc.BrakDanych:
                cpu_zgodne = False
            except Exception:
                cpu_zgodne = False

            if not cpu_zgodne:
                roznice.append({
                    "pole": "cpu",
                    "katalog": cpu_kat,
                    "sklep": cpu_skl,
                })

            # 3. RAM: ta sama pojemność w GB i oba DDR5
            ram_kat = katalog_ram
            ram_skl = dane_sklepu.get("ram", "")
            ram_zgodne = True
            try:
                cap_kat = ocena_pc.pojemnosc_ram_gb(ram_kat)
                cap_skl = ocena_pc.pojemnosc_ram_gb(ram_skl)
                kat_ddr5 = "ddr5" in (ram_kat or "").lower()
                skl_ddr5 = "ddr5" in (ram_skl or "").lower()
                if cap_kat != cap_skl or not (kat_ddr5 and skl_ddr5):
                    ram_zgodne = False
            except ocena_pc.BrakDanych:
                ram_zgodne = False
            except Exception:
                ram_zgodne = False

            if not ram_zgodne:
                roznice.append({
                    "pole": "ram",
                    "katalog": ram_kat,
                    "sklep": ram_skl,
                })

            # 4. Storage: ta sama pojemność w GB
            storage_kat = katalog_storage
            storage_skl = dane_sklepu.get("storage", "")
            storage_zgodne = True
            try:
                cap_kat = ocena_pc.pojemnosc_dysku_gb(storage_kat)
                cap_skl = ocena_pc.pojemnosc_dysku_gb(storage_skl)
                if cap_kat != cap_skl:
                    storage_zgodne = False
            except ocena_pc.BrakDanych:
                storage_zgodne = False
            except Exception:
                storage_zgodne = False

            if not storage_zgodne:
                roznice.append({
                    "pole": "storage",
                    "katalog": storage_kat,
                    "sklep": storage_skl,
                })

            # 5. PSU: moc w W tylko gdy obie strony ją podają (regex (\d{3,4})\s*W)
            psu_kat = katalog_psu
            psu_skl = dane_sklepu.get("psu", "")
            m_kat = re.search(r"(\d{3,4})\s*W", psu_kat or "", re.I)
            m_skl = re.search(r"(\d{3,4})\s*W", psu_skl or "", re.I)
            if m_kat and m_skl:
                if int(m_kat.group(1)) != int(m_skl.group(1)):
                    roznice.append({
                        "pole": "psu",
                        "katalog": psu_kat,
                        "sklep": psu_skl,
                    })

            # 6. Cena: porównaj prices[sklep] z katalogu z cena_bazowa adaptera
            cena_kat = p.get("prices", {}).get(sklep)
            if cena_kat is None:
                cena_kat = katalog_price_bare if katalog_price_bare is not None else p.get("price")

            cena_skl = dane_sklepu.get("cena_bazowa")
            if cena_skl is None:
                cena_skl = dane_sklepu.get("cena")

            cena_zgodna = True
            if cena_kat is None or cena_skl is None:
                cena_zgodna = False
            else:
                try:
                    ck = float(cena_kat)
                except (ValueError, TypeError):
                    val = zbieraj_ceny._liczba(cena_kat)
                    ck = float(val) if val is not None else None

                try:
                    cs = float(cena_skl)
                except (ValueError, TypeError):
                    val = zbieraj_ceny._liczba(cena_skl)
                    cs = float(val) if val is not None else None

                if ck is None or cs is None:
                    cena_zgodna = False
                else:
                    if ck <= 0:
                        roznica_wzgl = 0.0 if cs <= 0 else 1.0
                    else:
                        roznica_wzgl = abs(ck - cs) / ck
                    if roznica_wzgl > tolerancja_ceny:
                        cena_zgodna = False

            if not cena_zgodna:
                roznice.append({
                    "pole": "cena",
                    "katalog": cena_kat,
                    "sklep": cena_skl,
                })

            status = "roznica" if len(roznice) > 0 else "zgodny"
            wyniki.append({
                "nazwa": nazwa,
                "sklep": sklep,
                "url": url,
                "status": status,
                "roznice": roznice,
            })

    return wyniki


def podsumuj(wyniki: list[dict]) -> dict:
    """Zwraca słownik liczników statusów (tylko statusy, które wystąpiły)."""
    liczniki = {}
    for w in wyniki:
        st = w.get("status")
        if st is not None:
            liczniki[st] = liczniki.get(st, 0) + 1
    return liczniki


def pobierz_adapter_z_modulu(mod):
    """Zwraca instancję lub obiekt adaptera z zaimportowanego modułu."""
    if hasattr(mod, "odczytaj_pc"):
        return mod
    for name in ("Adapter", "Ad", "Zrodlo"):
        if hasattr(mod, name):
            obj = getattr(mod, name)
            if isinstance(obj, type):
                return obj()
            return obj
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if isinstance(attr, type) and hasattr(attr, "odczytaj_pc"):
            return attr()
        if hasattr(attr, "odczytaj_pc") and hasattr(attr, "SKLEP"):
            return attr
    return mod


def zaladuj_adaptery(klucze):
    """Dynamicznie ładuje moduły adapterów z pakietu zrodla.<klucz>."""
    adaptery = {}
    for k in klucze:
        try:
            mod = importlib.import_module("zrodla." + k)
            adapter = pobierz_adapter_z_modulu(mod)
            adaptery[k] = adapter
        except (ImportError, ModuleNotFoundError):
            pass
    return adaptery


def pobierz_cli(url):
    """Pobiera stronę sklepu z uwzględnieniem zasad robots.txt."""
    try:
        if not zbieraj_ceny.REGULAMIN.wolno(url):
            return None, "robots"
    except Exception:
        pass
    return zbieraj_ceny.pobierz(url)


def wypisz_tabele_i_podsumowanie(wyniki):
    """Wypisuje tabelę rozbieżności (maks 40 linii) oraz podsumowanie statusów."""
    linie = []
    for w in wyniki:
        nazwa = w.get("nazwa", "")
        sklep = w.get("sklep", "")
        status = w.get("status", "")
        roznice = w.get("roznice", [])
        if status == "roznica":
            for r in roznice:
                linie.append(
                    f"{nazwa[:30]:<30} | {sklep:<12} | {r['pole']:<8} | kat: {r['katalog']} | skl: {r['sklep']}"
                )
        elif status in ("nieodczytany", "zablokowany", "brak_adaptera"):
            powod = w.get("powod", "-")
            linie.append(
                f"{nazwa[:30]:<30} | {sklep:<12} | {status:<14} | powód: {powod}"
            )

    print("=" * 80)
    print("TABELA ROZBIEŻNOŚCI:")
    if not linie:
        print("  Brak rozbieżności (wszystkie pozycje zgodne).")
    else:
        for linia in linie[:40]:
            print(" ", linia)
        if len(linie) > 40:
            print(f"  ... oraz {len(linie) - 40} kolejnych rozbieżności (ucięto do 40 linii)")
    print("=" * 80)

    podsum = podsumuj(wyniki)
    print("PODSUMOWANIE STATUSÓW:")
    for st, ile in podsum.items():
        print(f"  {st}: {ile}")
    print("=" * 80)


def parsuj_argumenty():
    domyslny_szablon = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "monitors_1700_template.html"
    )
    parser = argparse.ArgumentParser(
        description="Audyt katalogu zestawów PC względem stron sklepów."
    )
    parser.add_argument(
        "--szablon",
        default=domyslny_szablon,
        help="Ścieżka do szablonu HTML (domyślnie monitors_1700_template.html obok skryptu)",
    )
    parser.add_argument(
        "--sklepy",
        default=None,
        help="Lista kluczy sklepów oddzielonych przecinkami",
    )
    parser.add_argument(
        "--maks",
        type=int,
        default=None,
        help="Najwyżej tyle wpisów PC do audytu",
    )
    parser.add_argument(
        "--wyjscie",
        default="audyt_katalogu.json",
        help="Plik JSON z wynikami (domyślnie audyt_katalogu.json)",
    )
    return parser.parse_args()


def main():
    args = parsuj_argumenty()

    if not os.path.exists(args.szablon):
        print(f"BŁĄD: Szablon {args.szablon} nie istnieje.", file=sys.stderr)
        sys.exit(2)

    try:
        with open(args.szablon, "r", encoding="utf-8") as f:
            sz = f.read()
    except Exception as e:
        print(f"BŁĄD: Nie można odczytać szablonu {args.szablon}: {e}", file=sys.stderr)
        sys.exit(2)

    wpisy_pc = [p for p in zbieraj_ceny.wczytaj(sz) if p.get("rodzaj") == "pc"]
    if args.sklepy:
        sklepy_filtr = [k.strip() for k in args.sklepy.split(",") if k.strip()]
        klucze = sklepy_filtr
    else:
        sklepy_filtr = None
        klucze = sorted({sklep for p in wpisy_pc for sklep in p.get("urls", {})})

    adaptery = zaladuj_adaptery(klucze)
    wyniki = audytuj(sz, adaptery, pobierz_cli, maks=args.maks, sklepy=sklepy_filtr)

    try:
        with open(args.wyjscie, "w", encoding="utf-8") as f:
            json.dump(wyniki, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"OSTRZEŻENIE: Nie można zapisać {args.wyjscie}: {e}", file=sys.stderr)

    wypisz_tabele_i_podsumowanie(wyniki)
    sys.exit(0)


if __name__ == "__main__":
    main()
