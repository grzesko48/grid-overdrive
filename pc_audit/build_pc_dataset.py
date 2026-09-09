import csv, json, re, hashlib

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
    single_vram = {
        'RTX5050': '8GB', 'RTX5070': '12GB', 'RTX5070TI': '16GB', 'RTX5060': '8GB',
        'RX9070': '16GB', 'RX9070XT': '16GB', 'RX7600': '8GB', 'RX7700XT': '12GB',
    }
    if not vram:
        key = ('RX' if is_amd else 'RTX') + num + suffix_raw
        vram = single_vram.get(key, "")
    brand = 'AMD Radeon' if is_amd else 'NVIDIA GeForce'
    series = 'RX' if is_amd else 'RTX'
    return f"{brand} {series} {num}{suffix}{(' '+vram) if vram else ''}".strip()

def img_key_hash(url):
    return f"pcimg_hpc_{hashlib.md5(url.encode()).hexdigest()[:10]}"

url_to_imgkey = json.load(open("pc_url_to_imgkey.json"))
ram_lookup = json.load(open("pc_ram_lookup.json"))

with open("hardpc_final.csv", encoding="utf-8") as f:
    all_hardpc_rows = list(csv.DictReader(f))
seen_urls = set()
hardpc_rows = []
for r in all_hardpc_rows:
    if r['url'] in seen_urls:
        continue
    seen_urls.add(r['url'])
    hardpc_rows.append(r)
print(f"Hard-PC rows: {len(all_hardpc_rows)} total, {len(hardpc_rows)} after de-duplicating by URL")

goblin_rows = json.load(open("goblinpc_catalog.json"))

entries = []
custom_count = 0
seen_names = {}

def dedup_name(name):
    n = seen_names.get(name, 0)
    seen_names[name] = n + 1
    if n == 0:
        return name
    return f"{name} ({n+1})"

for r in hardpc_rows:
    img_url = r['image_url']
    img_key = url_to_imgkey.get(img_url)
    if not img_key:
        continue
    gpu = normalize_gpu(r['gpu'])
    ram_raw = r['ram']  # e.g. "16GB DDR5"
    storage = r['storage'] or "SSD (pojemność brak w danych producenta)"
    name = dedup_name(r['name'])
    base = dict(
        img=img_key, name=name, cpu=r['cpu'], gpu=gpu, ram=ram_raw,
        storage=storage, psu=r['psu'], os='brak (bez systemu)',
        price=int(float(r['price_pln'])), store='Hard-PC.pl',
        prices={'hardpc': int(float(r['price_pln']))},
        urls={'hardpc': r['url']},
    )
    entries.append(base)

    lk = ram_lookup.get(r['url'])
    if lk and isinstance(lk.get('ram_upgrade_32gb_price'), (int, float)) and '16GB' in ram_raw:
        upgrade_price = lk['ram_upgrade_32gb_price']
        custom_price = base['price'] + int(round(upgrade_price))
        ram_type = 'DDR5' if 'DDR5' in ram_raw else ('DDR4' if 'DDR4' in ram_raw else '')
        custom = dict(
            img=img_key, name=dedup_name(name + ' (custom: 32GB RAM)'),
            cpu=r['cpu'], gpu=gpu, ram=f'32GB {ram_type}'.strip(),
            storage=storage, psu=r['psu'], os='brak (bez systemu)',
            price=custom_price, store='Hard-PC.pl',
            prices={'hardpc': custom_price}, urls={'hardpc': r['url']},
            isCustom=True, customLabel=f'+ RAM 32GB (+{int(round(upgrade_price))} zł)',
            baseName=name, baseRam=ram_raw, ramUpgradeCost=int(round(upgrade_price)),
        )
        entries.append(custom)
        custom_count += 1

for g in goblin_rows:
    img_key = url_to_imgkey.get(g['image_url'])
    if not img_key:
        continue
    gpu = normalize_gpu(g['gpu'])
    name = dedup_name(g['name'] + ' (GoblinPC)')
    price = int(round(float(g['price'])))
    base = dict(
        img=img_key, name=name, cpu=g['cpu'], gpu=gpu, ram=g['ram'],
        storage=g['storage'], psu=g['psu'], os=g['os'],
        price=price, store='GoblinPC.pl',
        prices={'goblinpc': price}, urls={'goblinpc': g['url']},
    )
    entries.append(base)
    up = g.get('ram_upgrade_32gb_price')
    if isinstance(up, (int, float)) and '16GB' in g['ram']:
        custom_price = price + int(round(up))
        custom = dict(
            img=img_key, name=dedup_name(name.replace(' (GoblinPC)', '') + ' (custom: 32GB RAM) (GoblinPC)'),
            cpu=g['cpu'], gpu=gpu, ram='32GB DDR5', storage=g['storage'], psu=g['psu'], os=g['os'],
            price=custom_price, store='GoblinPC.pl',
            prices={'goblinpc': custom_price}, urls={'goblinpc': g['url']},
            isCustom=True, customLabel=f'+ RAM 32GB (+{int(round(up))} zł)',
            baseName=name, baseRam=g['ram'], ramUpgradeCost=int(round(up)),
        )
        entries.append(custom)
        custom_count += 1

print(f"Hard-PC + GoblinPC entries built: {len(entries)} (of which {custom_count} are 'custom 32GB RAM' variants)")
json.dump(entries, open("pc_entries_hardpc_goblin.json", "w"), ensure_ascii=False, indent=1)
