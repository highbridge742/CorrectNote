# -*- coding: utf-8 -*-
"""Exact public nominal indices; stale or absent data uses native derivation."""
from functools import lru_cache
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import sys

ENGINE_STAMP = '2026-10-10al'
DATA_SHA256 = 'b0e5fe590b5b50c480858e181c407947886662c8d89062d2e4ab0cf3a3de20ec'
CODE_SHA256 = {'familiar_nominal': '3185a36f3288c33f621269fbb00e2eb2491d74c8dcad80a3f26e6179473995a3', 'reading_segments': '0d0dc0ed5120bdf1221726fe8512fc3f13ed0268c28246ccbb2a649d72a5d6ef', 'kango_tier': 'c39495d6e357811cdd4e600a42971c7aa0ed2ec33a0f5a965b30673e82d46dc8', 'semantic_roles': 'c50ea435f5f376879c5e1838b79255b262f8e37b4bf04614ad3c767a5b0e6bc9', 'general_words': '60742f422a162ae48fe16e109f1cb44113b24d98447f2e86160f95a2c33c954e', 'morphology': '382058086d9e70aa1f2d3797440f3657fff94a54aead1258352c95b9ddaccc02', 'seed_vocabulary': '3228f20e67a90f1b6f924d59c79b043cfc99483b34ddfb32ed84babf5c0822e0', 'seed_japanese': '1c0f83000c8c1121bbbad39868a9395c1c0a71647dd7ccc62e47696122da7f41', 'corrector': 'bd1b80ece7f6e150f0cd6a0a01189711f5929c5a9d57955807689449d347d2fc', 'cost_index': '5f11681f91ff86e12a2997d8d04208ae8ce2fc1cd207dc9794f18c8688de0adc', 'word_table': 'b774501292795779c70341c8925e72dd7a229646803453621139f3ede98a1e4d', 'janome_import': '515164215ed712aab0d7d53de6b53268d92794919965bdc0ae2324c8e11daa18'}
RESOURCE_SHA256 = {'seed_japanese.txt.gz': 'cf5b9c61a127c21c0eabd3d1335f4696c74fbf8f53f5ae711b1d4210b2f9e30a', 'seed_japanese_cost.txt.gz': 'bd9efabf65d326ad46de7757d5ed331a7424b450aa72786f2b629eedb578073e', 'seed_japanese_index.pickle.gz': 'f2cdc9478fa3f6140418aaacacd48800cc6da605a0999f04c519cf576038d1d2', 'seed_japanese_compounds.json.gz': '03056eed0f6fddd2a5b1eacf16fbcc96fa3020173a587fb8929eae4c9498cd6d', 'kango_tier.json': 'e184094f089811b38b6f3177abae6c625b1027909aabe558b393e0f29602c6ee'}


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
