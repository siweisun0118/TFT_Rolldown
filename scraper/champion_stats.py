import json
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://mobalytics.gg"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    )
}


def extract_stat(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def parse_star_values(value):
    if not value:
        return None

    parts = [p.strip() for p in value.split("/")]

    return {
        "1": int(parts[0]),
        "2": int(parts[1]),
        "3": int(parts[2])
    }


def get_champion_list():
    url = "https://mobalytics.gg/tft/champions"

    html = requests.get(url).text

    # Champion links look like:
    # /tft/set17/champions/aurora

    champions = sorted(
        set(
            re.findall(
                r"/tft/set17/champions/([a-z0-9\-]+)",
                html,
                flags=re.IGNORECASE
            )
        )
    )

    if champions:
        return champions

    # Fallback list from current Set 17 page
    return [
        "aatrox","akali","aurelionsol","aurora","bard","belveth",
        "blitzcrank","briar","caitlyn","chogath","corki","diana",
        "ezreal","fiora","fizz","gnar","gragas","graves","gwen",
        "illaoi","jax","jhin","jinx","kaisa","karma","kindred",
        "leblanc","leona","lissandra","lulu","maokai","masteryi",
        "meepsie","milio","missfortune","mordekaiser","morgana",
        "nami","nasus","nunu","ornn","pantheon","poppy","pyke",
        "rammus","reksai","rhaast","riven","samira","shen","sona",
        "tahmkench","talon","teemo","the-mighty-mech",
        "twistedfate","urgot","veigar","vex","viktor",
        "xayah","zed","zoe"
    ]


def scrape_champion(slug):
    url = f"https://mobalytics.gg/tft/set17/champions/{slug}"

    print(f"Scraping {slug}")

    response = requests.get(url, headers=HEADERS)

    # if response.status_code != 200:
    #     print(f"Failed: {url}", response.text)
    #     return None

    text = BeautifulSoup(response.text, "html.parser").get_text(
        "\n",
        strip=True
    )

    health = extract_stat(
        r"Health\s+(\d+\s*/\s*\d+\s*/\s*\d+)",
        text
    )

    attack = extract_stat(
        r"Damage\s+(\d+\s*/\s*\d+\s*/\s*\d+)",
        text
    )

    if not attack:
        attack = extract_stat(
            r"Attack\s+(\d+\s*/\s*\d+\s*/\s*\d+)",
            text
        )

    armor = extract_stat(
        r"Armor\s+(\d+)",
        text
    )

    mr = extract_stat(
        r"MR\s+(\d+)",
        text
    )

    if not mr:
        mr = extract_stat(
            r"Magic resist\s+(\d+)",
            text
        )

    attack_speed = extract_stat(
        r"Speed\s+([0-9.]+)",
        text
    )

    if not attack_speed:
        attack_speed = extract_stat(
            r"Attack speed\s+([0-9.]+)",
            text
        )

    mana_match = re.search(
        r"Mana\s+(\d+)\s*/\s*(\d+)",
        text,
        re.IGNORECASE
    )

    starting_mana = None
    total_mana = None

    if mana_match:
        starting_mana = int(mana_match.group(1))
        total_mana = int(mana_match.group(2))
    else:
        start = extract_stat(
            r"Starting mana\s+(\d+)",
            text
        )

        total = extract_stat(
            r"\bMana\s+(\d+)",
            text
        )

        if start:
            starting_mana = int(start)

        if total:
            total_mana = int(total)

    range_value = extract_stat(
        r"Range\s+(\d+)",
        text
    )

    ability_name = None

    ability_section = re.search(
        r"Ability\s+([^\n]+)",
        text,
        re.IGNORECASE
    )

    if ability_section:
        ability_name = ability_section.group(1).strip()

    return {
        "Health": parse_star_values(health),
        "Attack Damage": parse_star_values(attack),
        "Armor": int(armor) if armor else None,
        "MR": int(mr) if mr else None,
        "Attack Speed": float(attack_speed)
        if attack_speed else None,
        "Starting Mana": starting_mana,
        "Total Mana": total_mana,
        "Range": int(range_value)
        if range_value else None,
        "Ability Name": ability_name
    }


def scrape():
    champions = get_champion_list()
    data = {}
    for champion in champions:
        try:
            stats = scrape_champion(champion)

            if stats:
                data[champion] = stats

            time.sleep(0.5)

        except Exception as e:
            print(f"{champion}: {e}")

    with open(
        "TFT_Set_17/champion_stats.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )

    print(
        f"Wrote set17_stats.json "
        f"({len(data)} champions)"
    )
