import json
import os
from bs4 import BeautifulSoup
import urllib.request
from pathlib import Path


def _extract_apollo_cache(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')

    for script in soup.find_all('script'):
        if script.string and '__PRELOADED_STATE__' in script.string:
            raw = script.string.split('window.__PRELOADED_STATE__=', 1)[1]
            depth = 0
            end = 0
            for i, c in enumerate(raw):
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            data = json.loads(raw[:end])
            return data['tftState']['apollo']['static']

    return {}


COLOR_TO_STYLE = {
    'bronze': 1,
    'silver': 2,
    'gold': 3,
    'platinum': 3,
    'legendary': 4,
}


def parse_champions():
    cache = _extract_apollo_cache('Set_17_Champions.txt')

    synergy_id_to_name = {}
    for key, val in cache.items():
        if key.startswith('SynergiesV1:'):
            flat_ref = val.get('flatData', {}).get('__ref', '')
            flat_data = cache.get(flat_ref, {})
            slug = flat_data.get('slug', '')
            if slug.endswith('-1'):
                continue
            name = flat_data.get('name', '').strip()
            if name:
                synergy_id_to_name[key] = name

    champions_data = []
    for key, val in cache.items():
        if not key.startswith('ChampionsV1DataFlatDto:'):
            continue
        if val.get('gameSet') != 'set17':
            continue

        name = val['name']
        cost = val['cost']
        slug = val['slug']

        traits = []
        for syn_ref in val.get('synergies', []):
            ref_key = syn_ref.get('__ref', '')
            trait_name = synergy_id_to_name.get(ref_key, '')
            if trait_name:
                traits.append(trait_name)

        champion_id = f"TFT17_{slug.replace('-', '').title().replace(' ', '')}"

        champions_data.append({
            "championId": champion_id,
            "cost": cost,
            "name": name,
            "traits": traits,
            "_slug": slug,
        })

    champions_data.sort(key=lambda c: c['name'])
    return champions_data


def parse_traits():
    cache = _extract_apollo_cache('Set_17_Synergies.txt')

    traits_data = []
    for key, val in cache.items():
        if not key.startswith('SynergiesV1DataFlatDto:'):
            continue
        if val.get('gameSet') != 'set17':
            continue
        name = val.get('name', '').strip()
        if not name:
            continue
        slug = val.get('slug', '')
        if '-1' in slug:
            continue

        bonuses = val.get('bonuses', [])
        if not bonuses:
            continue

        sets = []
        needed_values = [b['needed'] for b in bonuses]
        for i, bonus in enumerate(bonuses):
            needed = bonus['needed']
            color = bonus.get('color', 'bronze')
            style = COLOR_TO_STYLE.get(color, 1)

            if i + 1 < len(needed_values):
                max_val = needed_values[i + 1] - 1
            else:
                max_val = 25000

            sets.append({
                "min": needed,
                "max": max_val,
                "style": style,
            })

        traits_data.append({"name": name, "sets": sets, "_slug": slug})

    traits_data.sort(key=lambda t: t['name'])
    return traits_data


def _download(url, output_path):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/120.0.0.0 Safari/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    with open(output_path, 'wb') as f:
        f.write(data)


def download_champion_images(champions_data, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for champion in champions_data:
        name = champion['name']
        slug = champion.get('_slug', name.lower().replace(' ', '').replace("'", '').replace('-', ''))
        img_url = f"https://cdn.mobalytics.gg/assets/tft/images/champions/thumbnail/set17/{slug}.jpg?v=5"

        output_path = os.path.join(output_dir, f"{name}.png")

        if os.path.exists(output_path):
            print(f"Already exists: {name}")
            continue

        try:
            _download(img_url, output_path)
            print(f"Downloaded: {name}")
        except Exception as e:
            print(f"Failed to download {name} from {img_url}: {e}")


def download_trait_images(traits_data, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for trait in traits_data:
        name = trait['name']
        slug = trait.get('_slug', name.lower().replace(' ', '-').replace("'", ''))
        img_url = f"https://cdn.mobalytics.gg/assets/common/icons/tft-synergies-set17/24-{slug}.svg?v=5"

        output_path = os.path.join(output_dir, f"{name}.png")

        if os.path.exists(output_path):
            print(f"Already exists: {name}")
            continue

        try:
            _download(img_url, output_path)
            print(f"Downloaded: {name}")
        except Exception as e:
            print(f"Failed to download {name} from {img_url}: {e}")


def main():
    print("Parsing Set 17 champions...")
    champions = parse_champions()

    print("Parsing Set 17 traits...")
    traits = parse_traits()

    os.makedirs('TFT_Set_17', exist_ok=True)

    champions_out = [{k: v for k, v in c.items() if not k.startswith('_')} for c in champions]
    with open('TFT_Set_17/champions.json', 'w', encoding='utf-8') as f:
        json.dump(champions_out, f, indent=4, ensure_ascii=False)
    print(f"Saved {len(champions_out)} champions to champions.json")

    traits_out = [{k: v for k, v in t.items() if not k.startswith('_')} for t in traits]
    with open('TFT_Set_17/traits.json', 'w', encoding='utf-8') as f:
        json.dump(traits_out, f, indent=4, ensure_ascii=False)
    print(f"Saved {len(traits_out)} traits to traits.json")

    print("\nDownloading champion images...")
    download_champion_images(champions, 'TFT_Set_17/champions')

    print("\nDownloading trait images...")
    download_trait_images(traits, 'TFT_Set_17/traits')

    print("\nDone!")


if __name__ == '__main__':
    main()
