# -*- coding: utf-8 -*-
"""Exact public nominal indices; stale or absent data uses native derivation."""
from functools import lru_cache
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import sys

ENGINE_STAMP = '2026-10-04a'
DATA_SHA256 = 'cf36bbd00051fbf37d098980b59bce43e2e17251c9a6da2844ec89a6c33d9fb5'
CODE_SHA256 = {'familiar_nominal': '3185a36f3288c33f621269fbb00e2eb2491d74c8dcad80a3f26e6179473995a3', 'reading_segments': 'cf0ad8ea4ca59b358113617ea9e2059c48aed3f97f256c04e07c5cb19c190e2b', 'kango_tier': '5ce58ca278f6a5a0fe8d1c6de2263596d4055d4ee22ea66a88fa7a4a329515ed', 'semantic_roles': '360a9fbeaa20649d92201b5bc07ccf76d90c3a9e8723b1046a93c279bec4b123', 'general_words': 'e36ee04f4c8fcc30b2faf3170135281428ec810512c555b991d9724b40dbf4d0', 'morphology': 'f364957312edf834139be4b8a5ff1c9facad2287c2a3e1f3a0ae568b98d2f36c', 'seed_vocabulary': '3228f20e67a90f1b6f924d59c79b043cfc99483b34ddfb32ed84babf5c0822e0', 'seed_japanese': '274e1c4eaf12498ff4810f4fca5c357f3a03600dcd0bf6aacd5499b7ca46813b', 'corrector': 'c32c1460ac6c9fd1ccb6688b578936033866f0af90f1f7f6c1a929c675107bbd', 'cost_index': 'f328427c1de5a3c216d664eeb5f129fd0b39c1b82ab70639f45acf016edff539', 'word_table': '88e87bf0a5ba80acdb7e5b9bbfb79ea273c095d3ec09a1ea65edb52ec96b13f2', 'janome_import': 'df466875d26370074681c98325a1a3ea28ae997020d485ea8dd77d5c06e627c5'}
RESOURCE_SHA256 = {'seed_japanese.txt.gz': 'cf5b9c61a127c21c0eabd3d1335f4696c74fbf8f53f5ae711b1d4210b2f9e30a', 'seed_japanese_cost.txt.gz': 'bd9efabf65d326ad46de7757d5ed331a7424b450aa72786f2b629eedb578073e', 'seed_japanese_index.pickle.gz': 'f2cdc9478fa3f6140418aaacacd48800cc6da605a0999f04c519cf576038d1d2', 'seed_japanese_compounds.json.gz': '03056eed0f6fddd2a5b1eacf16fbcc96fa3020173a587fb8929eae4c9498cd6d', 'kango_tier.json': 'aa90d46febd4ecc24c8de7122eea09ad4af0bc3eb4957eb6277402f766b748c4'}


def _digest(path):
    with open(path, 'rb') as source:
        data = source.read()
    # Git changes text line endings between Windows and Unix checkouts.
    # Python and JSON interpret both forms identically; binary assets remain exact.
    if Path(path).suffix.lower() in ('.py', '.json'):
        data = data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def load():
    """Return exact public tables, or None when any bundled input is stale."""
    try:
        from analysis_cache import ENGINE_STAMP as current_engine
        if current_engine != ENGINE_STAMP:
            return None
        path = Path(__file__).with_name('nominal_public_indices.json.gz')
        packed = path.read_bytes()
        if hashlib.sha256(packed).hexdigest() != DATA_SHA256:
            return None
        if not getattr(sys, 'frozen', False):
            for name, expected in CODE_SHA256.items():
                spec = importlib.util.find_spec(name)
                if spec is None or not spec.origin or _digest(spec.origin) != expected:
                    return None
        if getattr(sys, 'frozen', False):
            resource_dir = Path(sys._MEIPASS)
        else:
            spec = importlib.util.find_spec('app')
            if spec is None or not spec.origin:
                return None
            resource_dir = Path(spec.origin).parent
        for name, expected in RESOURCE_SHA256.items():
            if _digest(resource_dir / name) != expected:
                return None
        saved = json.loads(gzip.decompress(packed))
        if (not isinstance(saved, dict) or saved.get('schema') != 1
                or saved.get('engine') != ENGINE_STAMP
                or set(saved) != {'schema','engine','families','seed','classified','explicit'}):
            return None
        return {
            'families': {rd:{key:tuple(faces) for key,faces in group.items()}
                         for rd,group in saved['families'].items()},
            'seed': {rd:tuple(faces) for rd,faces in saved['seed'].items()},
            'classified': {rd:tuple(faces) for rd,faces in saved['classified'].items()},
            'explicit': {rd:set(faces) for rd,faces in saved['explicit'].items()},
        }
    except (OSError, EOFError, ValueError, TypeError, KeyError,
            ImportError, AttributeError):
        return None


def available():
    return load() is not None
