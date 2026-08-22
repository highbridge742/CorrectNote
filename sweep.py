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

"""実機のメモ全文（session.json）での総点検（実機と同じ nearby の作り）。"""
import json, sys
import corrector as C

from vocabulary import VocabularyStore, find_known_readings_flex
from context_vec import ContextVectorStore, build_nearby_words, extract_content_words
from dict_index import DictIndex
# 入力方式（項目48-BQ）。既定は settings の既定と同じ romaji。
_METHOD = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ('kana', 'romaji') else 'romaji'
from tests_mock import mock_tokenize

store = VocabularyStore(path='vocabulary.json')
cv = ContextVectorStore(path='context_vec.json')
di = DictIndex(cache_path='dict_index.json')
# ensure_built() を呼ばないと索引は空のまま（ready が False）。
# app.py は起動時に呼ぶので、これが無いと**実機より弱いエンジンで
# 総点検していた**ことになる（2026-08-10 に気付いた）。
di.ensure_built()
d = json.load(open('session.json'))
lines = d['tabs'][0]['text'].split('\n')

cache = {}
def words_of(i):
    if not (0 <= i < len(lines)):
        return []
    l = lines[i]
    if l not in cache:
        try:
            cache[l] = extract_content_words(mock_tokenize, l)
        except Exception:
            cache[l] = []
    return cache[l]

changed = 0
for i, line in enumerate(lines):
    nb = build_nearby_words(len(lines), i, words_of)
    try:
        r = C.correct_line(line, store, mock_tokenize, find_known_readings_flex,
                           input_method=_METHOD, context_vec=cv, dict_index=di,
                           nearby_words=nb, recent_words=())
    except Exception as e:
        print(f'{i+1}: ERROR {e!r} {line!r}')
        continue
    if r['changed']:
        changed += 1
        print(f'{i+1}: {line}')
        print(f'   => {r["corrected"]}')
print('changed lines:', changed)
