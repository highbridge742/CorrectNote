# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only compact forms of the large public tables (memory usage "low").

2026-10-14 うにさん: 「低は 700MB 以下」「解析速度はとても遅くしてよい」.
The correction worker holds a few very large tables as Python sets and dicts:
the 778k-word list of seed_japanese/oddness (about 100MB) and corrector's
reading/cost tables (about 200MB). Every word is a separate Python object.

Here the same keys live in one string, sorted, with an offset array, and
lookups bisect over it. The answers are exactly the same (same keys, same
values, same container types); only the speed differs (about 12µs a lookup).
They are built without the Python objects ever existing: the word list is
streamed from its sorted source, and the cost tables come from a bundled
derived file (`seed_japanese_compact.bin.gz`, pinned like cost_index's).

Used only when the main process starts the worker with CN_COMPACT_TABLES=1
(memory usage low); every other tier keeps the ordinary dicts and sets.
"""
import gzip
import hashlib
import json
import os
import re
from array import array

ENV = 'CN_COMPACT_TABLES'
FILE_NAME = 'seed_japanese_compact.bin.gz'
# The bundled file (gzip bytes) and the cost source it is derived from.
SOURCE_SHA256 = 'bd9efabf65d326ad46de7757d5ed331a7424b450aa72786f2b629eedb578073e'
# Rebuilt with `python compact_tables.py build`; update this when it changes.
FILE_SHA256 = '818c3b8e3eec7096e8fb4b1942ebbdb6e5ba0d3905389a6e209a2f5c4891fda7'
_MAGIC = b'CNCOMPACT1\n'


def enabled():
    return os.environ.get(ENV) == '1'


class _Keys:
    """Sorted unique strings in one blob; positions found by bisection.

    Every key is preceded by the separator, so an empty key still counts."""
    __slots__ = ('_blob', '_starts', '_sep')

    def __init__(self, blob, sep):
        self._blob = blob
        self._sep = sep
        starts = array('I')
        for match in re.finditer(re.escape(sep), blob):
            starts.append(match.end())
        self._starts = starts

    @classmethod
    def of(cls, keys, sep='\x00'):
        return cls(''.join(sep + key for key in sorted(keys)), sep)

    def __len__(self):
        return len(self._starts)

    def key(self, index):
        start = self._starts[index]
        end = (self._starts[index + 1] - 1 if index + 1 < len(self._starts)
               else len(self._blob))
        return self._blob[start:end]

    def index(self, value):
        """Position of value, or -1."""
        if not isinstance(value, str) or self._sep in value:
            return -1
        low, high = 0, len(self._starts)
        while low < high:
            middle = (low + high) // 2
            if self.key(middle) < value:
                low = middle + 1
            else:
                high = middle
        if low < len(self._starts) and self.key(low) == value:
            return low
        return -1

    def __iter__(self):
        for index in range(len(self._starts)):
            yield self.key(index)

    def ordered(self):
        """True when the keys are strictly increasing (checked once)."""
        previous = None
        for key in self:
            if previous is not None and not previous < key:
                return False
            previous = key
        return True


class CompactWords:
    """A frozenset of strings answering `in`, len, bool and iteration."""
    __slots__ = ('_keys',)

    def __init__(self, keys):
        self._keys = keys

    @classmethod
    def of(cls, words):
        return cls(_Keys.of(words, '\n'))

    def __contains__(self, value):
        return self._keys.index(value) >= 0

    def __len__(self):
        return len(self._keys)

    def __bool__(self):
        return len(self._keys) > 0

    def __iter__(self):
        return iter(self._keys)


class CompactPairs:
    """A dict of str -> list of (int, str), as corrector's reading tables.

    `get` returns a new container equal to the original value."""
    __slots__ = ('_keys', '_values', '_value_starts', '_outer', '_inner')

    def __init__(self, keys, values, outer=list, inner=tuple):
        self._keys = keys
        self._values = values
        # Like the keys, every value is preceded by the separator.
        starts = array('I')
        for match in re.finditer('\x00', values):
            starts.append(match.end())
        self._value_starts = starts
        self._outer, self._inner = outer, inner

    @classmethod
    def of(cls, table):
        keys = _Keys.of(table)
        sample = next(iter(table.values()), [])
        outer = type(sample) if isinstance(sample, (list, tuple)) else list
        first = next(iter(sample), (0, ''))
        inner = type(first) if isinstance(first, (list, tuple)) else tuple
        values = ''.join('\x00' + '\x01'.join('%d\x02%s' % (int(cost), text)
                                              for cost, text in table[key])
                         for key in keys)
        return cls(keys, values, outer, inner)

    def _value(self, index):
        starts = self._value_starts
        start = starts[index]
        end = starts[index + 1] - 1 if index + 1 < len(starts) else len(self._values)
        text = self._values[start:end]
        if not text:
            return self._outer()
        out = []
        for item in text.split('\x01'):
            cost, value = item.split('\x02', 1)
            out.append(self._inner((int(cost), value)))
        return self._outer(out)

    def get(self, key, default=None):
        index = self._keys.index(key)
        return self._value(index) if index >= 0 else default

    def __getitem__(self, key):
        index = self._keys.index(key)
        if index < 0:
            raise KeyError(key)
        return self._value(index)

    def __contains__(self, key):
        return self._keys.index(key) >= 0

    def __len__(self):
        return len(self._keys)

    def __bool__(self):
        return len(self._keys) > 0

    def __iter__(self):
        return iter(self._keys)

    def items(self):
        for index, key in enumerate(self._keys):
            yield key, self._value(index)


class CompactCosts:
    """A dict of str -> int."""
    __slots__ = ('_keys', '_values')

    def __init__(self, keys, values):
        self._keys = keys
        self._values = values

    @classmethod
    def of(cls, table):
        keys = _Keys.of(table)
        return cls(keys, array('q', (int(table[key]) for key in keys)))

    def get(self, key, default=None):
        index = self._keys.index(key)
        return self._values[index] if index >= 0 else default

    def __getitem__(self, key):
        index = self._keys.index(key)
        if index < 0:
            raise KeyError(key)
        return self._values[index]

    def __contains__(self, key):
        return self._keys.index(key) >= 0

    def __len__(self):
        return len(self._keys)

    def __bool__(self):
        return len(self._keys) > 0

    def __iter__(self):
        return iter(self._keys)

    def items(self):
        for index, key in enumerate(self._keys):
            yield key, self._values[index]


class CompactLists:
    """A dict of str -> list of str (dict_index's reading/surface lists).

    `get` returns a new list equal to the original value. Items must not
    contain the separators (words never do); `of` raises ValueError otherwise
    so the caller keeps the ordinary dict."""
    __slots__ = ('_keys', '_values', '_value_starts')
    _EMPTY = '\x02'

    def __init__(self, keys, values):
        self._keys = keys
        self._values = values
        starts = array('I')
        for match in re.finditer('\x00', values):
            starts.append(match.end())
        self._value_starts = starts

    @classmethod
    def of(cls, table):
        keys = _Keys.of(table)
        parts = []
        for key in keys:
            items = list(table[key])
            if any(not isinstance(item, str) or '\x00' in item or '\x01' in item
                   or '\x02' in item for item in items):
                raise ValueError('compact list items must be plain strings')
            parts.append('\x00' + ('\x01'.join(items) if items else cls._EMPTY))
        return cls(keys, ''.join(parts))

    def _value(self, index):
        starts = self._value_starts
        start = starts[index]
        end = starts[index + 1] - 1 if index + 1 < len(starts) else len(self._values)
        text = self._values[start:end]
        if text == self._EMPTY:
            return []
        return text.split('\x01')

    def get(self, key, default=None):
        index = self._keys.index(key)
        return self._value(index) if index >= 0 else default

    def __getitem__(self, key):
        index = self._keys.index(key)
        if index < 0:
            raise KeyError(key)
        return self._value(index)

    def __contains__(self, key):
        return self._keys.index(key) >= 0

    def __len__(self):
        return len(self._keys)

    def __bool__(self):
        return len(self._keys) > 0

    def __iter__(self):
        return iter(self._keys)

    def keys(self):
        return iter(self._keys)

    def values(self):
        for index in range(len(self._keys)):
            yield self._value(index)

    def items(self):
        for index, key in enumerate(self._keys):
            yield key, self._value(index)


class CompactTuples:
    """A set of equal-length tuples of str (oddness' split pairs): `in`, len,
    iteration. Items must not contain the separator."""
    __slots__ = ('_keys', '_width')
    _SEP = '\x01'

    def __init__(self, keys, width):
        self._keys = keys
        self._width = width

    @classmethod
    def of(cls, pairs):
        joined = []
        width = None
        for pair in pairs:
            pair = tuple(pair)
            if width is None:
                width = len(pair)
            if (len(pair) != width or not pair
                    or any(not isinstance(item, str) or cls._SEP in item or '\x00' in item
                           for item in pair)):
                raise ValueError('compact tuples must be equal-length plain strings')
            joined.append(cls._SEP.join(pair))
        return cls(_Keys.of(joined), width or 0)

    def __contains__(self, value):
        if (not isinstance(value, tuple) or len(value) != self._width
                or any(not isinstance(item, str) for item in value)):
            return False
        return self._keys.index(self._SEP.join(value)) >= 0

    def __len__(self):
        return len(self._keys)

    def __bool__(self):
        return len(self._keys) > 0

    def __iter__(self):
        for key in self._keys:
            yield tuple(key.split(self._SEP))


def words_from_seed(path):
    """word_table.read_word_sets for a sorted, fully marked seed list.

    Returns (wide, narrow) as one shared CompactWords, or None when the
    source is not of that shape (the caller then reads it as before)."""
    with gzip.open(path, 'rt', encoding='utf-8') as source:
        text = source.read()
    text = text.rstrip('\n')
    if not text.startswith('*') or re.search(r'\n(?!\*)', text) or '\n\n' in text:
        return None
    keys = _Keys(('\n' + text).replace('\n*', '\n'), '\n')
    del text
    if not keys.ordered():
        return None
    words = CompactWords(keys)
    return words, words


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def build_cost_file(tables, out_path):
    """Write the three corrector tables (readings, costs, surfaces) compactly."""
    readings, costs, surfaces = (CompactPairs.of(tables[0]), CompactCosts.of(tables[1]),
                                 CompactPairs.of(tables[2]))
    parts = [readings._keys._blob.encode('utf-8'), readings._values.encode('utf-8'),
             costs._keys._blob.encode('utf-8'), costs._values.tobytes(),
             surfaces._keys._blob.encode('utf-8'), surfaces._values.encode('utf-8')]
    header = dict(schema=1, source_sha256=SOURCE_SHA256, sizes=[len(p) for p in parts],
                  readings=[readings._outer.__name__, readings._inner.__name__],
                  surfaces=[surfaces._outer.__name__, surfaces._inner.__name__],
                  cost_itemsize=costs._values.itemsize)
    raw = _MAGIC + json.dumps(header).encode('ascii') + b'\n' + b''.join(parts)
    with open(out_path, 'wb') as stream:
        stream.write(gzip.compress(raw, mtime=0))
    return _sha256(out_path)


_CONTAINERS = {'list': list, 'tuple': tuple}


def load_cost_tables(source_path, compact_path):
    """(readings, costs, surfaces) compact, or None when the files differ."""
    try:
        if FILE_SHA256 is None or _sha256(compact_path) != FILE_SHA256:
            return None
        if _sha256(source_path) != SOURCE_SHA256:
            return None
        with open(compact_path, 'rb') as stream:
            raw = gzip.decompress(stream.read())
        if not raw.startswith(_MAGIC):
            return None
        line_end = raw.index(b'\n', len(_MAGIC))
        header = json.loads(raw[len(_MAGIC):line_end].decode('ascii'))
        if header.get('schema') != 1 or header.get('source_sha256') != SOURCE_SHA256:
            return None
        position = line_end + 1
        parts = []
        for size in header['sizes']:
            parts.append(raw[position:position + size])
            position += size
        del raw
        costs = array('q')
        if costs.itemsize != header['cost_itemsize']:
            return None
        costs.frombytes(parts[3])
        outer, inner = (_CONTAINERS[name] for name in header['readings'])
        readings = CompactPairs(_Keys(parts[0].decode('utf-8'), '\x00'),
                                parts[1].decode('utf-8'), outer, inner)
        cost_table = CompactCosts(_Keys(parts[2].decode('utf-8'), '\x00'), costs)
        outer, inner = (_CONTAINERS[name] for name in header['surfaces'])
        surfaces = CompactPairs(_Keys(parts[4].decode('utf-8'), '\x00'),
                                parts[5].decode('utf-8'), outer, inner)
        return readings, cost_table, surfaces
    except (OSError, ValueError, KeyError, EOFError):
        return None


if __name__ == '__main__':
    # Rebuild the bundled file from the ordinary tables:
    #   python compact_tables.py build
    import sys
    if sys.argv[1:] == ['build']:
        import corrector
        corrector._table_readings_for_surface('')
        here = os.path.dirname(os.path.abspath(__file__))
        print(build_cost_file((corrector._TABLE_READINGS, corrector._TABLE_COST,
                               corrector._TABLE_SURFACES), os.path.join(here, FILE_NAME)))
