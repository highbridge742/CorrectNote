# -*- coding: utf-8 -*-
# CorrectNote — かな入力誤字補正メモ帳
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
from tests_mock import mock_tokenize

store = VocabularyStore(path='vocabulary.json')
cv = ContextVectorStore(path='context_vec.json')
di = DictIndex(cache_path='dict_index.json')
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
                           input_method='kana', context_vec=cv, dict_index=di,
                           nearby_words=nb, recent_words=())
    except Exception as e:
        print(f'{i+1}: ERROR {e!r} {line!r}')
        continue
    if r['changed']:
        changed += 1
        print(f'{i+1}: {line}')
        print(f'   => {r["corrected"]}')
print('changed lines:', changed)
