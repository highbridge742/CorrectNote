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

"""
ユーザーが手動で選び直した語の記憶。

同音異義語（公園／講演／後援）は、読みだけでは決められない。
決め手になるのは前後の語であり、それは書いた本人しか知らない。
そこで選び直しを記録するときに、**前後の語もセットで**覚える。

  「明日の | こうえん | に行く」で「公園」を選んだ
  → 次から同じ並びが出たら「公園」を出す
  → 「大学で | こうえん | をする」は別の記録になり、混ざらない

文脈が一致しない場合でも、その語について過去に選ばれた表記が
1つしかなければそれを使う（弱い一致）。
文脈ごとに毎回選び直させるのは煩わしいためだが、
強い一致（前後とも一致）を必ず優先するので、
一度使い分けを教えれば混同しない。

保存形式 (choices.json):
    [{"original": "こうえん", "chosen": "公園", "reading": "こうえん",
      "prev": "明日の", "next": "に行く", "count": 1, "updated": ...}, ...]
"""

import json
import os
import time

# 文脈として意味を持たない語。これらを前後の語として記録しても
# 区別に役立たないので、文脈なしとして扱う。
_TRIVIAL_CONTEXT = {'', ' ', '　', '、', '。', '，', '．',
                    '「', '」', '（', '）', '\n', '\t'}


def _norm(word):
    """文脈語を正規化する。区別に使えないものは空にする。"""
    if word is None:
        return ''
    if not isinstance(word, str):
        return ''
    word = word.strip()
    if word in _TRIVIAL_CONTEXT:
        return ''
    return word


def _is_valid_word(value):
    """
    記録として受け付けられる語か。

    過去に、`halfwidth_to_kana` が返す3つ組
    （文字列, 変換できた数, 対象数）を文字列と思い込んで候補に
    並べてしまう不具合があった（SPEC.md 22）。その時期に
    選び直された記録は、JSON では配列として保存されるため、
    読み戻すと **リスト** のまま入ってくる。
    そのまま使うと、行の組み立て（units.build_line_units）が
    文字列の連結で落ち、**アプリが起動できなくなる**
    （実機で TypeError: sequence item 0: expected str instance,
      list found として発生）。

    壊れた記録のせいで起動できないのが一番困るので、
    ここで弾いて無かったことにする（その語の選び直しが
    1件消えるだけで、他への影響は無い）。
    """
    return isinstance(value, str) and bool(value)


class ChoiceStore:
    """
    手動で選び直した語を、前後の語とセットで覚える。

    同じ語・同じ文脈で選び直した場合は上書きする
    （あとから選び直せる、という要件のため）。
    """

    def __init__(self, path=None):
        self.path = path
        # original -> [記録, ...]
        self._by_original = {}
        if path and os.path.exists(path):
            self.load()

    # ------------------------------------------------------------
    # 記録する
    # ------------------------------------------------------------
    def record(self, original, chosen, reading=None, prev=None, next=None):
        """
        選び直しを覚える。同じ語・同じ文脈なら上書きする。

        戻り値: 新規に覚えたなら True、既存の更新なら False
        """
        if not _is_valid_word(original) or not _is_valid_word(chosen):
            return False
        if reading is not None and not isinstance(reading, str):
            reading = None
        prev, next = _norm(prev), _norm(next)
        records = self._by_original.setdefault(original, [])
        for rec in records:
            if rec.get('prev', '') == prev and rec.get('next', '') == next:
                # 同じ文脈での選び直し: 上書きして使用回数を増やす
                rec['chosen'] = chosen
                rec['reading'] = reading or rec.get('reading')
                rec['count'] = rec.get('count', 1) + 1
                rec['updated'] = time.time()
                return False
        records.append({
            'original': original,
            'chosen': chosen,
            'reading': reading,
            'prev': prev,
            'next': next,
            'count': 1,
            'updated': time.time(),
        })
        return True

    def forget(self, original, prev=None, next=None):
        """特定の文脈での選び直しを取り消す。"""
        prev, next = _norm(prev), _norm(next)
        records = self._by_original.get(original)
        if not records:
            return False
        for i, rec in enumerate(records):
            if rec.get('prev', '') == prev and rec.get('next', '') == next:
                records.pop(i)
                if not records:
                    self._by_original.pop(original, None)
                return True
        return False

    def forget_all(self, original):
        """その語の選び直しを全て取り消す。"""
        return self._by_original.pop(original, None) is not None

    def forget_record(self, rec):
        """一覧から選んだ記録を1件消す。"""
        return self.forget(rec.get('original'), rec.get('prev'),
                           rec.get('next'))

    # ------------------------------------------------------------
    # 引き当てる
    # ------------------------------------------------------------
    def lookup(self, original, prev=None, next=None):
        """
        この語をこの文脈で、ユーザーは何に選び直したか。

        一致の強い順に見る:
          1. 前後とも一致    最も信頼できる
          2. 片側だけ一致
          3. 文脈なしで記録されたもの
          4. その語の選び直しが1通りしかない（弱い一致）

        ただし1文字の語は、弱い一致では引き当てない。
        「し」のような1文字は文章のあらゆる場所に現れるため、
        文脈の裏付けなしに置き換えると無関係な箇所まで巻き添えになる。

        戻り値: 選ばれた表記。無ければ None。
        """
        records = self._by_original.get(original)
        if not records:
            return None
        prev, next = _norm(prev), _norm(next)

        best = None
        best_rank = -1
        for rec in records:
            rp, rn = rec.get('prev', ''), rec.get('next', '')
            if rp == prev and rn == next:
                rank = 4
            elif rp and rp == prev:
                rank = 3
            elif rn and rn == next:
                rank = 2
            elif not rp and not rn:
                rank = 1
            else:
                continue
            # 同じ強さなら使用回数の多いほうを採る
            if rank > best_rank or (rank == best_rank and best is not None
                                    and rec.get('count', 1)
                                    > best.get('count', 1)):
                best, best_rank = rec, rank

        if best is not None:
            # 1文字の語は、前後どちらかが一致する記録だけを信用する
            if len(original) <= 1 and best_rank < 2:
                return None
            return best['chosen']

        # どの文脈にも当てはまらないが、その語の選び直しが
        # 1通りしかないなら、それを使う。
        # 文脈が違うたびに選び直させるのは煩わしいため。
        if len(original) <= 1:
            return None
        chosen = {r['chosen'] for r in records}
        if len(chosen) == 1:
            return records[0]['chosen']
        return None

    def originals(self):
        """記録されている元の語（引き当ての走査に使う）。"""
        return list(self._by_original.keys())

    def has(self, original):
        return original in self._by_original

    def all_records(self):
        out = []
        for records in self._by_original.values():
            out.extend(records)
        out.sort(key=lambda r: r.get('updated', 0), reverse=True)
        return out

    def __len__(self):
        return sum(len(v) for v in self._by_original.values())

    # ------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------
    def save(self, path=None):
        path = path or self.path
        if not path:
            return
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.all_records(), f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    def load(self, path=None):
        path = path or self.path
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            # 壊れていても起動は止めない
            return
        self._by_original.clear()
        for rec in data:
            if not isinstance(rec, dict):
                continue
            original = rec.get('original')
            # 壊れた記録（表記が文字列でないもの）は読み飛ばす。
            # 詳しい経緯は _is_valid_word の説明を参照。
            if not _is_valid_word(original) or \
                    not _is_valid_word(rec.get('chosen')):
                continue
            rec['prev'] = _norm(rec.get('prev'))
            rec['next'] = _norm(rec.get('next'))
            self._by_original.setdefault(original, []).append(rec)
