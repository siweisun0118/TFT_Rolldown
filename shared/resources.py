"""File containing all helper methods and misc. resources used by rolldown."""


# Standard libraries
import json
from pathlib import Path


# Local imports
from shared.rolldown_enums import LEVEL_ODDS
from shared.rolldown_classes import Trait, Unit


# region Helper Methods

# Helper method to sanity check rolling odds
def sanity_check_odds():
    """Make sure odds make sense."""
    assert all((sum(odds) == 100 for odds in LEVEL_ODDS.values())), "Error in level odds."

# Helper function to read input directory
def read_database(input_dir):
    """Read in units and traits."""
    # Read in units
    with open(Path(input_dir) / 'champions.json', encoding='utf-8') as champions_file:
        champions_list = json.loads(champions_file.read())

    # Read in traits
    with open(Path(input_dir) / 'traits.json', encoding='utf-8') as traits_file:
        traits_list = json.loads(traits_file.read())

    # Parse unit data
    champions = {}
    for champ in champions_list:
        # If champion has no traits, ignore it
        # Since it is a target dummy, voidspawn, tome, etc.
        if len(champ['traits']) < 1:
            continue

        # Add to champions list
        champions[champ['name']] = Unit(champ['cost'], champ['name'], \
            champ['traits'], champ['championId'])

    # Parse trait data
    traits = {}
    for trait in traits_list:
        # Extract trait breakpoints and styles from trait data
        breakpoints = []
        styles = []
        for b_p in trait['sets']:
            breakpoints.append(b_p['min'])
            styles.append(b_p['style'])

        # Add to traits list
        traits[trait['name']] = Trait(trait['name'], breakpoints, styles)

    return champions, traits


# Helper function to serialize custom classes
def serialize(obj):
    """Serialize the object by converting its contents to a string."""
    return obj.name

# endregion
