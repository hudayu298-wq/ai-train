"""Everyday browsing selection; source identities and historical references survive."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def policy():
    return json.loads((Path(__file__).parent / 'data/exercise_selection.json').read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def selected_ids():
    return frozenset(key for group in policy()['groups'].values() for key in group)


def visible(entry):
    # User-maintained entries are deliberate additions, even without demo media.
    return entry.get('source_kind') == 'user' or entry['id'] in selected_ids()


def referenced_ids(value):
    """Find exact exercise IDs in owner-scoped plans/records, never by name."""
    if isinstance(value, dict):
        found = {value['exercise_id']} if isinstance(value.get('exercise_id'), str) else set()
        for item in value.values():
            found.update(referenced_ids(item))
        return found
    if isinstance(value, list):
        return set().union(*(referenced_ids(item) for item in value)) if value else set()
    return set()
