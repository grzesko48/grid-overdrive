"""Adapter Morele.net (monitory): cienka nakładka na nowe_monitory.py, żeby ta sama ścieżka
naboru obsługiwała wszystkie sklepy jednakowo. Komputery z Morele: zrodla/morele_pc.py."""
import html as htmllib
import nowe_monitory as nm
from ocena_pc import BrakDanych
import zbieraj_ceny

SKLEP = "morele"
LOKALNIE = False
SKLEP_UWAGI = "monitory: kategoria WQHD z facetami 240–500 Hz (nowe_monitory.lista_morele)"


def lista_monitorow(pobierz, maks_stron=6):
    adres = nm.LISTA.format(filtry=nm.FILTR_WQHD, strona="")
    if not zbieraj_ceny.REGULAMIN.wolno(adres):
        return []
    return sorted(nm.lista_morele(maks_stron))


def odczytaj_monitor(url, html):
    d = nm.odczytaj(url, html)
    o = nm.produkt(html)
    mpn = htmllib.unescape(str(o.get("mpn") or "")).strip()
    d["kod_modelu"] = mpn if mpn else None
    return d


def lista_pc(pobierz, maks_stron=6):
    return []


def odczytaj_pc(url, html):
    raise BrakDanych("komputery z Morele obsługuje zrodla/morele_pc.py")
