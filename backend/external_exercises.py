"""Generated catalog access. External media permission never enables a detector."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def bundle():
    return json.loads((Path(__file__).parent/'data/exercises_external.json').read_text(encoding='utf8'))


@lru_cache(maxsize=1)
def chinese_names():
    return json.loads((Path(__file__).parent/'data/exercise_names_zh.json').read_text(encoding='utf8'))


def display_name(entry_id, fallback):
    return chinese_names()['names'].get(entry_id, fallback)


def localize(entry):
    # Read-time localization also covers existing DB seeds, without overwriting
    # user edits, historical snapshots or the upstream English source identity.
    if entry.get('source_kind') != 'external_catalog':
        return entry
    name = display_name(entry['id'], entry['name'])
    if name != entry['name']:
        entry['aliases'] = list(dict.fromkeys([*entry.get('aliases', []), entry['name']]))
        entry['name'] = name
    if entry['id'] in chinese_names()['names']:
        entry['name_locale_version'] = chinese_names()['version']
    return entry


def legacy_overlay(entry):
    overlay=bundle()['legacy_bindings'].get(entry['id'])
    if overlay:
        entry['upstream_refs']=overlay['upstream_refs']
        entry['original_name']=overlay['original_name']
        if overlay.get('demo'):
            entry['demo']=overlay['demo']
    return entry
