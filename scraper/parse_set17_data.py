#!/usr/bin/env python3
"""
TFT Champion Scraper for MetaTFT
Scrapes champion stats, traits, roles, and abilities from
https://data.metatft.com/lookups/TFTSet17_latest_en_us.json - the same static data
MetaTFT's own unit pages (e.g. https://www.metatft.com/units/Jhin) render client-side.

This is plain Riot game data behind a CDN, not behind any bot-detection challenge
(unlike mobalytics.gg, which sits behind a Cloudflare managed JS challenge), so no
Selenium/browser automation is needed at all - a single `requests.get` returns
everything for the whole roster.

Caveat: this file can occasionally lag a very recent balance patch for an individual
champion (confirmed once, for Aatrox, whose ability here didn't match the live site).
It self-corrects once the CDN cache refreshes; --redo re-pulls it fresh.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    from .token_resolver import resolve_ability_scaling_text, resolve_ability_text
except ImportError:
    # Run directly as a script (`python scraper/parse_set17_data.py`) rather than
    # imported as part of the `scraper` package.
    from token_resolver import resolve_ability_scaling_text, resolve_ability_text

REPO_ROOT = Path(__file__).resolve().parent.parent
ABILITIES_DIR = REPO_ROOT / "TFT_Set_17" / "abilities"
CHAMPION_STATS_PATH = REPO_ROOT / "TFT_Set_17" / "champion_stats.json"

LOOKUP_URL = "https://data.metatft.com/lookups/TFTSet17_latest_en_us.json"

# Real playable champions vs. PvE monsters/hero-augment variants/UI placeholders that
# also show up in the `units` list (e.g. "Cosmic Bruiser", "Apex Primordian", item
# anvils): apiName is "TFT17_<Champion>" with no "PVE"/"Enemy_"/"FakeUnit" marker,
# has at least one real trait, has stats, and costs 1-5.
NON_CHAMPION_API_MARKERS = ('PVE', 'Enemy_', 'FakeUnit')


def normalize_name(name: str) -> str:
    """Normalize a champion name for comparison (e.g. "Cho'Gath" -> "chogath")."""
    return re.sub(r'[^a-z0-9]', '', name.lower())


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


class TFTScraper:
    def __init__(self):
        self.champions_data = {}

    def fetch_lookup(self) -> Optional[Dict[str, Any]]:
        try:
            response = requests.get(LOOKUP_URL, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching {LOOKUP_URL}: {e}")
            return None

    def is_real_champion(self, unit: Dict[str, Any]) -> bool:
        api_name = unit.get('apiName', '')
        if not api_name.startswith('TFT17_'):
            return False
        if any(marker in api_name for marker in NON_CHAMPION_API_MARKERS):
            return False
        if not unit.get('traits'):
            return False
        if not unit.get('stats', {}).get('hp'):
            return False
        if not (1 <= unit.get('cost', 0) <= 5):
            return False
        return True

    def download_ability_icon(self, icon_asset_path: str, slug: str) -> Optional[str]:
        """Download an ability's icon (via Community Dragon) to TFT_Set_17/abilities/."""
        if not icon_asset_path or not slug:
            return None

        url = 'https://raw.communitydragon.org/latest/game/' + icon_asset_path.lower().replace('.tex', '.png')
        ABILITIES_DIR.mkdir(parents=True, exist_ok=True)
        dest = ABILITIES_DIR / f"{slug}.png"

        if not dest.exists():
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                dest.write_bytes(response.content)
            except requests.RequestException as e:
                print(f"    Failed to download ability icon {url}: {e}")
                return None

        return str(dest.relative_to(REPO_ROOT)).replace('\\', '/')

    def extract_champion(self, unit: Dict[str, Any], roles: Dict[str, Any]) -> Dict[str, Any]:
        """Build the champion_stats.json entry for one unit's metatft data."""
        stats: Dict[str, Any] = {}
        unit_stats = unit.get('stats', {})

        if unit_stats.get('hp') is not None:
            stats['hp'] = int(unit_stats['hp'])
        if unit_stats.get('damage') is not None:
            stats['damage'] = int(unit_stats['damage'])
        if unit_stats.get('magicResist') is not None:
            stats['mr'] = float(unit_stats['magicResist'])
        if unit_stats.get('armor') is not None:
            stats['armor'] = float(unit_stats['armor'])
        if unit_stats.get('attackSpeed') is not None:
            stats['speed'] = float(unit_stats['attackSpeed'])
        if unit_stats.get('initialMana') is not None and unit_stats.get('mana') is not None:
            stats['mana'] = f"{unit_stats['initialMana']} / {unit_stats['mana']}"
        if unit.get('cost') is not None:
            stats['cost'] = int(unit['cost'])
        if unit_stats.get('range') is not None:
            stats['range'] = int(unit_stats['range'])

        if unit.get('traits'):
            stats['traits'] = list(unit['traits'])

        role_key = unit.get('role')
        role = roles.get(role_key) if role_key else None
        if role and role.get('name'):
            stats['role'] = role['name']

        ability = unit.get('ability') or {}
        if ability.get('name'):
            stats['ability'] = ability['name']

        if ability.get('desc'):
            base_hp = unit_stats.get('hp')
            champion_name = unit.get('name')
            resolved = resolve_ability_text(ability, base_hp=base_hp, champion_name=champion_name)
            stats['ability_description'] = resolved.text

            scaling = resolve_ability_scaling_text(ability, base_hp=base_hp, champion_name=champion_name)
            stats['ability_description_scaling'] = scaling.text

        if ability.get('icon') and ability.get('name'):
            icon_path = self.download_ability_icon(ability['icon'], slugify(ability['name']))
            if icon_path:
                stats['ability_icon'] = icon_path

        return stats

    def scrape_all(self) -> Dict[str, Dict[str, Any]]:
        """Scrape every Set 17 champion's data from the metatft lookup file."""
        already_scraped = {
            normalize_name(name) for name, data in self.champions_data.items() if data
        }

        print("Fetching champion data...")
        lookup = self.fetch_lookup()
        if not lookup:
            print("Failed to fetch champion data.")
            return self.champions_data

        roles = lookup.get('roles', {})
        champions = [u for u in lookup.get('units', []) if self.is_real_champion(u)]
        champions.sort(key=lambda u: u['name'])

        if not champions:
            print("No champions found in the lookup data.")
            return self.champions_data

        print(f"Found {len(champions)} champions. Extracting...")

        for i, unit in enumerate(champions, 1):
            name = unit['name'].strip()
            print(f"[{i}/{len(champions)}] {name}...", end=' ')

            if normalize_name(name) in already_scraped:
                print("skipped (already scraped)")
                continue

            stats = self.extract_champion(unit, roles)
            self.champions_data[name] = stats
            already_scraped.add(normalize_name(name))
            print("✓")

        return self.champions_data

    def load_existing_data(self, filename: Path = CHAMPION_STATS_PATH):
        """Load previously scraped data so scrape_all can resume and skip completed champions."""
        if not filename.exists():
            return
        with open(filename, 'r', encoding='utf-8') as f:
            self.champions_data = json.load(f)

    def save_to_json(self, filename: Path = CHAMPION_STATS_PATH):
        """Save scraped data to JSON file."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.champions_data, f, indent=2, ensure_ascii=False)
        print(f"\nData saved to {filename}")
        print(f"Total champions scraped: {len(self.champions_data)}")


def main():
    parser = argparse.ArgumentParser(description="Scrape TFT champion stats from MetaTFT.")
    parser.add_argument(
        '--redo', action='store_true',
        help="Re-scrape every champion from scratch, ignoring any existing champion_stats.json. "
             "By default the scraper resumes and skips champions that already have data."
    )
    args = parser.parse_args()

    scraper = TFTScraper()

    if args.redo:
        print("Redoing full scrape (ignoring existing champion_stats.json).")
    else:
        scraper.load_existing_data()
        if scraper.champions_data:
            print(f"Resuming: {len(scraper.champions_data)} champions already scraped will be skipped.")

    try:
        scraper.scrape_all()
        scraper.save_to_json()
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
        if scraper.champions_data:
            scraper.save_to_json()
    except Exception as e:
        print(f"Error during scraping: {e}")
        if scraper.champions_data:
            scraper.save_to_json()


if __name__ == "__main__":
    main()
