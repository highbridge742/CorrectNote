# -*- coding: utf-8 -*-
"""Exact public nominal indices; stale or absent data uses native derivation."""
from functools import lru_cache
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import sys

ENGINE_STAMP = '2026-10-09ab'
DATA_SHA256 = '07a78de1cbaa90f0d6a71f998d8ffd270e5c25bd290e8298c90083f556173b2f'
CODE_SHA256 = {'familiar_nominal': '3185a36f3288c33f621269fbb00e2eb2491d74c8dcad80a3f26e6179473995a3', 'reading_segments': '5c371751dfc228512bbbaad229c4b5e4ec014b6368d90aecfccfbb9f0c72ba9b', 'kango_tier': 'c39495d6e357811cdd4e600a42971c7aa0ed2ec33a0f5a965b30673e82d46dc8', 'semantic_roles': 'f17fc65fc84017999b4b8db7913804cc6ce8c533f074ec92fff0f4ee3c6c86ae', 'general_words': '60742f422a162ae48fe16e109f1cb44113b24d98447f2e86160f95a2c33c954e', 'morphology': '932fb1d41f814ffb33ca2a3254d6da4c9f576e74f7fe99d0f06d4e4372ca728a', 'seed_vocabulary': '3228f20e67a90f1b6f924d59c79b043cfc99483b34ddfb32ed84babf5c0822e0', 'seed_japanese': '274e1c4eaf12498ff4810f4fca5c357f3a03600dcd0bf6aacd5499b7ca46813b', 'corrector': '0830030186474d9e2c1704ec1a8d698f8ea2cb9c427199f961d48d9501cf8704', 'cost_index': 'f328427c1de5a3c216d664eeb5f129fd0b39c1b82ab70639f45acf016edff539', 'word_table': '88e87bf0a5ba80acdb7e5b9bbfb79ea273c095d3ec09a1ea65edb52ec96b13f2', 'janome_import': 'c7b494dd0b10bc62f7b42a41f67593654fa1e716d19801bdeecb97c09b902085'}
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
