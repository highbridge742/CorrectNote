# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Immutable bundled word sets shared by readers of the same public source file."""
import gzip,os
from functools import lru_cache


def _read(path):
    marked=set();unmarked=set()
    pending=''
    with gzip.open(path,'rt',encoding='utf-8') as source:
        while True:
            block=source.read(262144)
            if not block:break
            lines=(pending+block).split('\n');pending=lines.pop()
            for word in lines:
                if not word:continue
                if word[0]=='*':marked.add(word[1:])
                else:unmarked.add(word)
    if pending:
        if pending[0]=='*':marked.add(pending[1:])
        else:unmarked.add(pending)
    if not marked:return frozenset(unmarked),frozenset()
    if unmarked<=marked:
        shared=frozenset(marked)
        return shared,shared
    return frozenset(marked|unmarked),frozenset(marked)


@lru_cache(maxsize=2)
def _cached(path,modified,size):
    return _read(path)


def read_word_sets(path):
    path=os.path.normcase(os.path.abspath(path))
    try:info=os.stat(path)
    except OSError:return _read(path)
    return _cached(path,info.st_mtime_ns,info.st_size)


_COMPOUND_SOURCE_SHA256 = 'cf5b9c61a127c21c0eabd3d1335f4696c74fbf8f53f5ae711b1d4210b2f9e30a'
_COMPOUND_INDEX_SHA256 = '03056eed0f6fddd2a5b1eacf16fbcc96fa3020173a587fb8929eae4c9498cd6d'


def read_compound_tables(source_path, index_path=None):
    """Exact public derived counts; absent or stale data uses the original loop."""
    import hashlib,json
    from collections import Counter
    if index_path is None:
        index_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'seed_japanese_compounds.json.gz')
    try:
        with open(index_path,'rb') as stream:packed=stream.read()
        if hashlib.sha256(packed).hexdigest()!=_COMPOUND_INDEX_SHA256:return None
        with open(source_path,'rb') as stream:
            if hashlib.sha256(stream.read()).hexdigest()!=_COMPOUND_SOURCE_SHA256:return None
        saved=json.loads(gzip.decompress(packed))
        if (not isinstance(saved,dict) or saved.get('schema')!=1
                or saved.get('source_sha256')!=_COMPOUND_SOURCE_SHA256):return None
        return Counter(saved['left']),Counter(saved['right']),set(map(tuple,saved['pairs']))
    except (OSError,EOFError,ValueError,TypeError,KeyError):
        return None
