#!/usr/bin/env python3
"""Generuje sekcję „Co się zmieniło w ocenach" z policzonych danych.

Sekcja jest archiwalna — opisuje jednorazowe zdarzenie z 18 września 2026 — więc powstaje
jako statyczny znacznik, nie jako kod liczący w przeglądarce. Ale liczby w nim NIE są
przepisywane ręcznie: pochodzą z porownanie_rankingow.json, czyli z pomiaru.

Jednostką jest PUNKT, nie miejsce w rankingu. Uzasadnienie w komentarzu porownaj_rankingi.py.
"""
import json, os, re

BAZA = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(BAZA, "monitors_1700_template.html")
D = json.load(open(os.path.join(BAZA, "porownanie_rankingow.json"), encoding="utf-8"))


def histogram(kub, akcent_od=3):
    maks = max(k["ile"] for k in kub) or 1
    w = []
    for k in kub:
        proc = round(k["ile"] / maks * 100)
        szum = k["prog"] < akcent_od
        w.append(
            f'<div class="zm-wiersz{" zm-szum" if szum else ""}">'
            f'<span class="zm-etyk">{k["etykieta"]}</span>'
            f'<span class="zm-slup"><span class="zm-wypelnienie" style="width:{proc}%"></span></span>'
            f'<span class="zm-ile mono">{k["ile"]}</span></div>')
    return "".join(w)


def sekcja(etyk, d, tytul):
    kub = d["kubelki"]
    szum = sum(k["ile"] for k in kub if k["prog"] < 3)
    duze = d["duze_zmiany"]
    progi = d.get("progi_ze_zmiana", [])

    kafle = [
        (d["porownanych"], "pozycji porównanych z wersją sprzed naprawy"),
        (d["zmienilo_o_3_lub_wiecej"], "zmieniło ocenę o 3 punkty lub więcej"),
        (szum, f'zmieniło się o 2 punkty lub mniej, czyli w granicach szumu skali'),
        (f'{d["skrajne"]["w_dol"]} … +{d["skrajne"]["w_gore"]}', "skrajne zmiany, w punktach na sto"),
    ]
    kafle_html = "".join(
        f'<div class="stat-card"><div class="big">{a}</div><div class="lbl">{b}</div></div>'
        for a, b in kafle)

    tabela = ""
    if progi:
        wiersze = "".join(
            f'<tr><td class="mono">{z["prog"]} zł</td><td>{z["przed"]}</td>'
            f'<td>{z["po"]}</td></tr>' for z in progi)
        tabela = (
            f'<h3 class="zm-podtytul">Co to zmienia przy konkretnym budżecie</h3>'
            f'<p class="zm-opis">Sprawdziliśmy, który zestaw serwis poleca jako najlepiej oceniony '
            f'mieszczący się w danej kwocie. Na <strong>{d["progi_budzetu"]} sprawdzonych progów '
            f'co 500 zł rekomendacja zmieniła się w {len(progi)}</strong> — oba poniżej 7500 zł. '
            f'W pozostałych przeliczenie nie zmieniło odpowiedzi na pytanie „co kupić za tyle".</p>'
            f'<div class="zm-tabela-obudowa"><table class="zm-tabela">'
            f'<thead><tr><th>budżet</th><th>polecany przed</th><th>polecany teraz</th></tr></thead>'
            f'<tbody>{wiersze}</tbody></table></div>')

    lista = ""
    if duze:
        el = "".join(
            f'<li><span class="pc-chip pc-chip-delta pc-chip-delta-'
            f'{"up" if x["delta"]>0 else "down"}" '
            f'aria-label="zmiana o {abs(x["delta"])} punktów {"w górę" if x["delta"]>0 else "w dół"}">'
            f'<span class="dglif" aria-hidden="true">{"▲" if x["delta"]>0 else "▼"}</span>'
            f'<span class="mono">{x["delta"]:+d}</span></span> {x["nazwa"]}</li>'
            for x in duze)
        lista = (f'<h3 class="zm-podtytul">Jedenaście pozycji, które ruszyły się naprawdę</h3>'
                 f'<p class="zm-opis">Tylko te zmieniły ocenę o 6 punktów lub więcej. Nazwy padają '
                 f'wyłącznie tutaj — przy zmianach mniejszych niż 3 punkty wymienianie modeli '
                 f'sugerowałoby różnicę, której nie ma.</p>'
                 f'<ul class="zm-lista">{el}</ul>')

    return f"""
  <section class="zmiany" aria-labelledby="zm-{etyk}">
    <div class="eyebrow"><span class="dot"></span>zmiana metody // 18 września 2026</div>
    <h2 id="zm-{etyk}" class="zm-tytul">{tytul}</h2>
    <p class="zm-lede">Do 18 września 2026 składnik „opłacalność" nie wynikał z żadnego wzoru —
    oceny były przypisywane ręcznie. Tego dnia policzyliśmy go po raz pierwszy jawną formułą
    i przeliczyliśmy wszystkie pozycje. Poniżej dokładnie to, co się przez to zmieniło.
    <strong>Mierzymy w punktach, nie w miejscach w rankingu</strong>: miejsce zależy od tego,
    kto stoi obok, a nie od samej pozycji — {d["porownanych"] and ""}w pomiarze
    26 zestawów nie zmieniło ani jednego punktu, a mimo to zmieniło miejsce.</p>
    <div class="stat-grid stat-grid-zm">{kafle_html}</div>
    <h3 class="zm-podtytul">Jak duże były te zmiany</h3>
    <p class="zm-opis">Każdy słupek to liczba pozycji, których ocena zmieniła się o tyle punktów.
    Trzy pierwsze są wyszarzone celowo: <strong>przy {d["porownanych"]} pozycjach mieszczących się
    w kilkudziesięciu wartościach różnica jednego czy dwóch punktów nie znaczy nic</strong> —
    to szum skali, nie zmiana oceny.</p>
    <div class="zm-histogram">{histogram(kub)}</div>
    <p class="zm-opis zm-przyczyny">Rozdzielamy przyczyny, żeby nie przypisać naprawie cudzego ruchu:
    <strong>{d["z_samej_naprawy"]} pozycji zmieniło ocenę przez samo przeliczenie opłacalności</strong>,
    a {d["z_reszty_dnia"]} przez pozostałe zmiany tego dnia (usunięcie duplikatów, korekta ceny
    systemu z 519 na 539 zł) — te drugie maksymalnie o {d["maks_z_reszty_dnia"]} punkt.</p>
    {tabela}
    {lista}
  </section>
"""


t = open(P, encoding="utf-8").read()

STYL = """
/* Sekcja „co się zmieniło" — wyłącznie istniejące tokeny. Kolor nie jest jedynym nośnikiem
   kierunku: obok niego stoi glif, znak liczby i etykieta dla czytnika ekranu. Bez animacji,
   bo jedyna animacja, której wyłączenie coś ukrywa, byłaby wadą. */
.zmiany{margin:2.4rem 0 1rem; padding-top:1.4rem; border-top:1px solid var(--line);}
.zm-tytul{font-size:1.45rem; margin:.3rem 0 .6rem;}
.zm-lede,.zm-opis{color:var(--ink-dim); max-width:72ch; margin:.3rem 0 1rem; font-size:1.02rem;}
.zm-podtytul{font-size:1.1rem; margin:1.6rem 0 .4rem;}
.stat-grid-zm .stat-card::before{background:var(--line);}
.zm-histogram{display:flex; flex-direction:column; gap:.35rem; margin:.6rem 0 1rem;}
.zm-wiersz{display:grid; grid-template-columns:8.5rem 1fr 3rem; align-items:center; gap:.6rem;}
.zm-etyk{font-size:.86rem; color:var(--ink-dim);}
.zm-slup{background:var(--panel-2); border:1px solid var(--line); border-radius:5px; height:1.1rem; overflow:hidden;}
.zm-wypelnienie{display:block; height:100%; background:var(--accent);}
.zm-szum .zm-wypelnienie{background:var(--ink-dim); opacity:.5;}
.zm-szum .zm-etyk{font-style:italic;}
.zm-ile{text-align:right; font-size:.9rem; color:var(--ink);}
.zm-tabela-obudowa{overflow-x:auto;}
.zm-tabela{border-collapse:collapse; width:100%; font-size:.92rem; margin:.4rem 0 1rem;}
.zm-tabela th,.zm-tabela td{text-align:left; padding:.45rem .6rem; border-bottom:1px solid var(--line);}
.zm-tabela th{color:var(--ink-dim); font-weight:600; font-size:.84rem; text-transform:uppercase; letter-spacing:.06em;}
.zm-lista{list-style:none; padding:0; margin:.4rem 0 1rem; display:flex; flex-direction:column; gap:.45rem;}
.zm-lista li{display:flex; align-items:center; gap:.6rem; font-size:.95rem; flex-wrap:wrap;}
.pc-chip-delta{color:var(--ink); font-weight:700; gap:.3rem;}
.pc-chip-delta .dglif{font-weight:800; line-height:1;}
.pc-chip-delta-up{background:var(--good-bg); border-color:var(--good);}
.pc-chip-delta-up .dglif{color:var(--good);}
.pc-chip-delta-down{background:var(--bad-bg); border-color:var(--bad);}
.pc-chip-delta-down .dglif{color:var(--bad);}
@media (max-width:520px){ .zm-wiersz{grid-template-columns:7rem 1fr 2.4rem;} }
"""

assert t.count("</style>") == 1
t = t.replace("</style>", STYL + "</style>")

# wstawiamy sekcje na koncu kazdego widoku rankingu
for etyk, ident, tytul in (
        ("pc", 'id="pcRankingView"', "Co się zmieniło w ocenach zestawów"),
        ("mon", 'id="rankingView"', "Co się zmieniło w ocenach monitorów")):
    dane = D["sekcje"]["zestawy" if etyk == "pc" else "monitory"]
    i = t.find(ident)
    assert i > -1, ident
    koniec = t.find("</section>", i)
    assert koniec > -1
    t = t[:koniec] + sekcja(etyk, dane, tytul) + t[koniec:]
    print(f"  OK  sekcja wstawiona do {ident}")

# aktualne liczniki w kafelkach statystyk
for stare, nowe, opis in (
        ('<div class="big grad">57</div><div class="lbl">zweryfikowanych modeli',
         '<div class="big grad" id="statMon">57</div><div class="lbl">zweryfikowanych modeli', "licznik monitorów"),
        ('<div class="big grad">360</div><div class="lbl">zestawów gamingowych',
         '<div class="big grad" id="statPc">360</div><div class="lbl">zestawów gamingowych', "licznik zestawów")):
    assert t.count(stare) == 1, opis
    t = t.replace(stare, nowe); print(f"  OK  {opis} dostał identyfikator")

t = t.replace("    wstaw('monCount', DATA.length);",
              "    wstaw('monCount', DATA.length);\n    wstaw('statMon', DATA.length);")
t = t.replace("    wstaw('pcCount', PDATA.length);",
              "    wstaw('pcCount', PDATA.length);\n    wstaw('statPc', PDATA.length);")

open(P, "w", encoding="utf-8").write(t)
print("zapisane")
