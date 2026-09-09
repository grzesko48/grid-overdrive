import re, json
from pc_data import PCS as OLD_PCS

NEW = json.load(open("pc_entries_hardpc_goblin.json", encoding="utf-8"))

# Earlier work in this session already sampled 7 Hard-PC + 3 GoblinPC products (plus RAM/
# storage variant experiments) into pc_data.py as a proof of concept. The fresh datasets
# below (all 405 Hard-PC 5-9k listings, all 3 GoblinPC models, verified RAM-upgrade prices)
# supersede those samples — drop them from the old list so products aren't counted twice.
def sourced_from_new_retailers(p):
    urls = p.get('urls') or {}
    return 'hardpc' in urls or 'goblinpc' in urls

OLD_KEPT = [dict(p) for p in OLD_PCS if not sourced_from_new_retailers(p)]
print(f"Old curated list: {len(OLD_PCS)} total, {len(OLD_KEPT)} kept after dropping Hard-PC/GoblinPC samples superseded by fresh data")

PCS = OLD_KEPT + [dict(p) for p in NEW]

GPU_TIER = {
    'NVIDIA GeForce RTX 5050 8GB': 1,
    'AMD Radeon RX 7600 8GB': 1,
    'AMD Radeon RX 9060 XT 8GB': 2,
    'NVIDIA GeForce RTX 5060 8GB': 3,
    'NVIDIA GeForce RTX 5060 Ti 8GB': 4, 'AMD Radeon RX 9060 XT 16GB': 4,
    'NVIDIA GeForce RTX 5060 Ti 16GB': 5, 'AMD Radeon RX 7700 XT 12GB': 5,
    'AMD Radeon RX 9070 16GB': 6, 'NVIDIA GeForce RTX 5070 12GB': 6,
    'AMD Radeon RX 9070 XT 16GB': 7,
    'NVIDIA GeForce RTX 5070 Ti 16GB': 8,
}
SINGLE_VRAM = {
    'RTX5050': '8GB', 'RTX5070': '12GB', 'RTX5070TI': '16GB', 'RTX5060': '8GB',
    'RX9070': '16GB', 'RX9070XT': '16GB', 'RX7600': '8GB', 'RX7700XT': '12GB',
}

def normalize_gpu(raw):
    s = (raw or "").strip()
    m = re.search(r'\b(RTX|RX)\s*(\d{4})\s*(Ti|TI|XT)?\b', s, re.I)
    if not m:
        return s
    is_amd = m.group(1).upper() == 'RX'
    num = m.group(2)
    suffix_raw = (m.group(3) or "").upper()
    suffix = ' Ti' if suffix_raw == 'TI' else (' XT' if suffix_raw == 'XT' else '')
    vram_m = re.search(r'(\d{1,2})\s*GB\b', s, re.I)
    vram = f"{vram_m.group(1)}GB" if vram_m else ""
    if not vram:
        key = ('RX' if is_amd else 'RTX') + num + suffix_raw
        vram = SINGLE_VRAM.get(key, "")
    brand = 'AMD Radeon' if is_amd else 'NVIDIA GeForce'
    series = 'RX' if is_amd else 'RTX'
    return f"{brand} {series} {num}{suffix}{(' '+vram) if vram else ''}".strip()

def gpu_tier(gpu):
    return GPU_TIER.get(normalize_gpu(gpu), 3)

def gpu_vram_gb(gpu):
    m = re.search(r'(\d{1,2})\s*GB\b', gpu or "", re.I)
    return int(m.group(1)) if m else 8

def cpu_tier(cpu):
    c = (cpu or "").lower()
    if '7800x3d' in c or '9800x3d' in c or '7500x3d' in c: return 8
    if 'ultra 9' in c or 'ultra 7 2' in c: return 7
    if 'ryzen 7 9700x' in c or '8745hx' in c or 'ultra 7' in c: return 6
    if 'ryzen 7' in c or 'i7' in c: return 5
    if '9600x' in c or '9500f' in c or 'ultra 5' in c: return 5
    if '7600x' in c: return 5
    if '7600' in c or '8400f' in c or '8700f' in c or '7500f' in c: return 4
    if 'i5-14400f' in c or 'i5 14400f' in c: return 4
    if 'i5-12400f' in c or 'i5 12400f' in c: return 3
    if '5700x' in c or '5800x' in c or '5600' in c: return 3
    return 3

def clamp(v, lo=1, hi=100):
    return max(lo, min(hi, round(v)))

def ram_cap_gb(ram):
    m = re.search(r'(\d{1,3})\s*GB', ram or "")
    return int(m.group(1)) if m else 16

def ram_quality(ram):
    cap = ram_cap_gb(ram)
    mhz = 0
    m = re.search(r'(\d{4})\s*MH?z', ram or "", re.I)
    if m: mhz = int(m.group(1))
    q = 0
    q += 10 if cap >= 32 else 0
    q += 6 if mhz >= 6000 else (3 if mhz >= 5600 else 0)
    return q

def storage_quality(storage):
    s = storage or ""
    if '2TB' in s or '2.5TB' in s: return 8
    if '1TB' in s or '1000GB' in s: return 5
    if '512GB' in s: return 2
    if '500GB' in s: return 2
    return 0

def is_hdd(storage):
    return 'HDD' in (storage or "").upper() and 'SSD' not in (storage or "").upper()

for p in PCS:
    p['tier'] = gpu_tier(p['gpu'])
    p['ctier'] = cpu_tier(p['cpu'])
    p['power'] = p['tier'] * 0.78 + p['ctier'] * 0.22

min_p = min(x['power'] for x in PCS); max_p = max(x['power'] for x in PCS)
for p in PCS:
    p['perf'] = clamp(60 + (p['power'] - min_p) / (max_p - min_p) * 40) if max_p > min_p else 80
    p['components'] = clamp(58 + p['ctier'] * 4 + ram_quality(p['ram']) + storage_quality(p['storage']) - (15 if is_hdd(p['storage']) else 0))
    p['zpp'] = p['price'] / p['power']

zpps = [x['zpp'] for x in PCS]
minz, maxz = min(zpps), max(zpps)
for p in PCS:
    p['value'] = clamp(100 - (p['zpp'] - minz) / (maxz - minz) * 92) if maxz > minz else 80

# --- Longevity: how many more years of comfortable 1440p gaming this GPU/RAM combo buys.
# Calibrated so RTX 5070 (tier 6) sits ~1 year ahead of RTX 5060 (tier 3), per the brief's
# own example. VRAM and RAM capacity shift it further: an 8GB card or 16GB RAM ages faster
# as VRAM/RAM requirements creep up; a 16GB card or 32GB RAM buys real extra headroom.
for p in PCS:
    base_years = 1.0 + p['tier'] / 3.0
    vram = gpu_vram_gb(p['gpu'])
    vram_adj = -0.3 if vram <= 8 else (0.3 if vram >= 16 else 0.0)
    ram_adj = 0.15 if ram_cap_gb(p['ram']) >= 32 else -0.15
    p['longevity_years'] = round(base_years + vram_adj + ram_adj, 2)

ly = [x['longevity_years'] for x in PCS]
minl, maxl = min(ly), max(ly)
for p in PCS:
    p['longevity'] = clamp(1 + (p['longevity_years'] - minl) / (maxl - minl) * 99) if maxl > minl else 50

for p in PCS:
    psu_w = 0
    m = re.search(r'(\d{3,4})W', p['psu'] or "")
    if m: psu_w = int(m.group(1))
    feat = 58.0
    if psu_w >= 750: feat += 12
    elif psu_w >= 600: feat += 6
    elif psu_w == 0: feat -= 6
    if '80+ gold' in (p['psu'] or "").lower(): feat += 7
    elif '80+ bronze' in (p['psu'] or "").lower() or 'cybenetics bronze' in (p['psu'] or "").lower(): feat += 3
    if p['os'] and 'windows' in p['os'].lower(): feat += 7
    if len(p['prices']) >= 2: feat += 6
    p['features'] = clamp(feat)
    p['overall'] = clamp(p['components']*0.28 + p['value']*0.32 + p['perf']*0.27 + p['features']*0.13)
    # Ultra ranking: quality-of-play + longevity weighted above raw value, per the brief
    # ("najważniejsza jest jakość grania i długowieczność"). Storage/features stay minor.
    p['ultra'] = clamp(p['perf']*0.28 + p['longevity']*0.30 + p['value']*0.22 + p['components']*0.12 + p['features']*0.08)
    p['n_stores'] = len(p['prices'])

    pros = []
    if p.get('isCustom'):
        pros.append(f"Wariant custom: RAM podniesiony do 32GB za dopłatą {p.get('ramUpgradeCost','?')} zł względem wersji bazowej ({p.get('baseRam','16GB')}) — realny wzrost trwałości platformy.")
    if p['tier'] >= 6:
        pros.append(f"Karta {p['gpu']} — wydajność wystarczająca do gier w 1440p w wysokich ustawieniach.")
    elif p['tier'] >= 4:
        pros.append(f"Karta {p['gpu']} — solidna wydajność 1080p/1440p w większości gier.")
    if p['ctier'] >= 6:
        pros.append(f"Procesor {p['cpu']} — jeden z mocniejszych w tym zestawieniu.")
    if p['longevity'] >= 75:
        pros.append(f"Wysoka długowieczność (szac. ~{p['longevity_years']:.1f} roku komfortowej gry w 1440p) — dobry wybór na dłuższą metę.")
    if p['value'] >= 82:
        pros.append("Jeden z najlepszych stosunków ceny do wydajności całego zestawu (GPU + CPU) w zestawieniu.")
    if ram_cap_gb(p['ram']) >= 32 and not p.get('isCustom'):
        pros.append(f"{p['ram']} — komfortowy zapas na kolejne lata i multitasking.")
    if re.search(r'6000\s*MH?z', p['ram'] or "", re.I):
        pros.append("Szybka pamięć DDR5-6000 — realny plus w grach z platformą AM5/nowszym Intelem.")
    if p['os'] and 'windows' in p['os'].lower():
        pros.append("System Windows 11 w cenie — gotowy do pracy po rozpakowaniu.")
    if p['price'] == min(x['price'] for x in PCS):
        pros.append("Najniższa cena w całym zestawieniu.")
    if len(pros) < 2:
        pros.append(f"Spełnia kryteria zestawienia: {p['gpu']}, {p['ram']}, w cenie {p['price']} zł.")
    p['pros'] = pros[:3]

    cons = []
    if p['n_stores'] <= 1:
        cons.append("Potwierdzona dostępność tylko w 1 sklepie z tych sprawdzonych.")
    if ram_cap_gb(p['ram']) < 32 and not p.get('isCustom'):
        if p.get('ramUpgradeCost'):
            cons.append(f"{p['ram']} — w sklepie dostępna opcja podniesienia do 32GB za {p['ramUpgradeCost']} zł (patrz wariant custom w rankingu).")
        else:
            cons.append(f"{p['ram']} — wystarczające dziś, ale bez dużego zapasu na przyszłość.")
    if psu_w and psu_w < 550:
        cons.append(f"Zasilacz {psu_w}W — ograniczony zapas mocy na ewentualny upgrade karty graficznej.")
    if not p['os'] or 'brak' in (p['os'] or '').lower():
        cons.append("Bez systemu operacyjnego w cenie — Windows trzeba dokupić osobno.")
    if '500GB' in (p['storage'] or '') or '512GB' in (p['storage'] or ''):
        cons.append("Dysk 500-512 GB — komfortowe na start, ale szybko zapełnione przy kilku dużych grach.")
    if is_hdd(p['storage']):
        cons.append("W zestawie dysk HDD — zauważalnie wolniejsze wczytywanie gier niż na SSD NVMe.")
    if p['tier'] <= 2:
        cons.append(f"Karta {p['gpu']} — segment budżetowy, krótszy realny okres komfortowej gry w wysokich ustawieniach 1440p.")
    if not cons:
        cons.append("Brak wyróżniających się wad poza typowymi ograniczeniami tej klasy cenowej.")
    p['cons'] = cons[:2]

print("TOTAL PCS:", len(PCS))
print("customs:", sum(1 for p in PCS if p.get('isCustom')))
print("Hard-PC:", sum(1 for p in PCS if p['store']=='Hard-PC.pl'))
print("GoblinPC:", sum(1 for p in PCS if p['store']=='GoblinPC.pl'))
print("Other (existing curated):", sum(1 for p in PCS if p['store'] not in ('Hard-PC.pl','GoblinPC.pl')))

print("\nTop 10 by ultra score:")
for p in sorted(PCS, key=lambda p: -p['ultra'])[:10]:
    print(f"  ultra={p['ultra']:>3} overall={p['overall']:>3} perf={p['perf']:>3} longevity={p['longevity']:>3}({p['longevity_years']}y) value={p['value']:>3}  {p['price']:>5}zl  {p['name'][:70]}")

json.dump(PCS, open("pcs_final.json", "w"), ensure_ascii=False, indent=1)
