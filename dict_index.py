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
janome 内蔵辞書の読み索引。

語の選び直しの候補は、当初は個人語彙（vocabulary.json）だけから
作っていた。しかし個人語彙は「本人が使った語」しか持たないため、
「ひらがな」をドラッグしても「平仮名」が候補に出ない、という
不足が実機で確認された。

そこで janome の内蔵辞書（数十万語）全体を、
  読み  -> 表記の一覧   （ひらがな -> 平仮名, 片仮名...）
  表記  -> 読みの一覧   （時 -> とき, じ）
の両方向で引ける索引にする。「時ッ層」のように漢字が
別の読みで誤変換された場合、表記→読みの逆引きで
「じ」という読みも試せるようになる。

索引の構築には辞書全体の走査が必要で数秒かかるため、
初回に構築したら JSON に保存し、次回からはそれを読み込む。

このモジュールは候補づくり（candidates.py）専用であり、
補正エンジンの判断には使わない（判断経路を増やさないため）。
"""

import json
import os

try:
    from janome_import import (iter_janome_entries, HAS_JANOME,
                               _should_exclude, EXCLUDE_SUB_POS)
except Exception:
    HAS_JANOME = False
    EXCLUDE_SUB_POS = ()

    def iter_janome_entries(min_len=1, max_len=8):
        return iter(())

    def _should_exclude(surface, pos, sub_pos, sub_sub_pos, cost):
        return False

# 索引に入れる品詞。候補として意味を持つ内容語だけに絞る。
# 名詞:接尾 も入れる（「時=じ」「層=そう」のような単漢字の読みは
# 接尾語として辞書に載っていることが多いため）。
#
# ただし実機の janome では辞書エントリから品詞が取れないビルドが
# あることが確認されている（診断で品詞が全件空文字だった）。
# 品詞での絞り込みだけに頼ると、そのようなビルドでは索引が
# 丸ごと空になるか、逆に何も絞り込めず地名・人名・難語まで
# 全部入ってしまう（実機で報告された症状）。
# そこで品詞が取れている場合の絞り込みに加え、
# 語彙取り込み機能（janome_import.py）が使っている
# _should_exclude（コスト・表記パターンによる除外。
# 固有名詞の地名接尾語・カタカナ固有名詞・記号混じり・
# 高コスト＝低頻度の語を弾く）を必ず併用する。
# これは品詞の有無に関係なく効くので、上のような環境でも機能する。
_TARGET_POS = ('名詞', '動詞', '形容詞', '副詞')
_EXCLUDE_SUB = ('数',) + EXCLUDE_SUB_POS

# 1つの読みに対して覚える表記の数。コストの低い（一般的な）順。
_MAX_SURFACES = 10
# 1つの表記に対して覚える読みの数。
_MAX_READINGS = 5

# 索引専用のコスト上限。語彙取り込み機能（GENERAL_COST_LIMIT=4500）より
# さらに厳しくする。「殺伐たる」「ただならぬ」「さしたる」のような
# 文語調の連体詞・形容表現はコストが 4300〜4900 あたりに集中しており、
# 4500 では素通りしてしまうことが実機の診断で分かった
# （地名・人名・難語が多すぎるという報告の主因）。
# 索引は候補を「たくさん見せる」場ではなく、
# 日常的に見て分かる語だけに絞るべきなので、取り込みより絞り込む。
_INDEX_COST_LIMIT = 4000


def _should_prune(surface, pos, sub_pos, sub_sub_pos, cost):
    """候補索引に入れるかどうかの判定。地名・人名・難語をまとめて弾く。"""
    if _should_exclude(surface, pos, sub_pos, sub_sub_pos, cost):
        return True
    if cost is not None and cost > _INDEX_COST_LIMIT:
        return True
    return False


# キャッシュの形式が変わったら数字を上げる（古い索引を作り直させる）
CACHE_VERSION = 3
# 索引として最低限あるべき読みの数。これを下回るものは
# 作りかけ・壊れた索引とみなして作り直す。
# （空の索引が保存されると、候補が一切出ないのに
#   「索引はある」と扱われて原因が分からなくなるため）
_MIN_READINGS = 5000


def _is_kana(s):
    return all('\u3041' <= c <= '\u3096' or c == 'ー' for c in s)


class DictIndex:
    """
    janome 辞書の読み索引。初回構築＋キャッシュ。

    janome が無い環境ではすべて空を返す（候補が減るだけで壊れない）。
    """

    def __init__(self, cache_path=None):
        self.cache_path = cache_path
        self._by_reading = None    # reading -> [surface, ...]
        self._by_surface = None    # surface -> [reading, ...]

    @property
    def ready(self):
        return self._by_reading is not None

    def ensure_built(self, progress=None):
        """
        索引を使える状態にする。キャッシュがあれば読み込み、
        無ければ辞書を走査して構築・保存する。

        戻り値: 使えるようになったら True
        """
        if self.ready:
            return True
        if self._load_cache():
            return True
        if not HAS_JANOME:
            # janome が無ければ空索引として動く
            self._by_reading, self._by_surface = {}, {}
            return False
        self._build(progress)
        self._save_cache()
        return True

    # ------------------------------------------------------------
    # 引く
    # ------------------------------------------------------------
    def surfaces_for_reading(self, reading, limit=_MAX_SURFACES):
        """この読みを持つ表記の一覧（一般的な語から順に）。"""
        if not self.ready or not reading:
            return []
        return list(self._by_reading.get(reading, ()))[:limit]

    def readings_for_surface(self, surface, limit=_MAX_READINGS):
        """この表記が持ちうる読みの一覧（時 -> とき, じ）。"""
        if not self.ready or not surface:
            return []
        return list(self._by_surface.get(surface, ()))[:limit]

    # ------------------------------------------------------------
    # 構築
    # ------------------------------------------------------------
    def _build(self, progress=None):
        # (コスト, 表記) を読みごとに集め、最後にコスト順で切り詰める。
        #
        # 品詞での絞り込みは「品詞が取れている場合だけ」行う。
        # janome のバージョンによっては辞書エントリから品詞を
        # 取り出せず、全件が空になることがある（実機の診断で判明）。
        # そのようなビルドでは品詞フィルタが無力化されるため、
        # 代わりに _should_exclude（語彙取り込み機能と共通の、
        # コストと表記パターンによる除外）を必ず併用する。
        # これにより、品詞が取れない環境でも地名・人名・難語を弾ける。
        by_reading = {}
        by_surface = {}
        n = 0
        for surface, reading, pos, sub_pos, sub_sub_pos, cost in \
                iter_janome_entries(min_len=1, max_len=8):
            if pos and pos not in _TARGET_POS:
                continue
            if sub_pos and sub_pos in _EXCLUDE_SUB:
                continue
            if not reading or not _is_kana(reading):
                continue
            if _should_prune(surface, pos, sub_pos, sub_sub_pos, cost):
                continue
            by_reading.setdefault(reading, []).append((cost, surface))
            # 表記からの逆引きは、ドラッグ範囲に現れる短い語
            # （時・層・売っ など）にしか使わない。
            # 全ての表記を持つとキャッシュが極端に大きくなるため絞る。
            if len(surface) <= 4:
                by_surface.setdefault(surface, []).append((cost, reading))
            n += 1
            if progress and n % 50000 == 0:
                progress(n)

        def _dedup_sorted(pairs, limit):
            pairs.sort()
            out, seen = [], set()
            for _cost, v in pairs:
                if v in seen:
                    continue
                seen.add(v)
                out.append(v)
                if len(out) >= limit:
                    break
            return out

        self._by_reading = {r: _dedup_sorted(v, _MAX_SURFACES)
                            for r, v in by_reading.items()}
        self._by_surface = {s: _dedup_sorted(v, _MAX_READINGS)
                            for s, v in by_surface.items()}

    # ------------------------------------------------------------
    # キャッシュ
    # ------------------------------------------------------------
    def _save_cache(self):
        if not self.cache_path:
            return
        # 中身の乏しい索引は保存しない。保存してしまうと
        # 次回もそれを読み込んで、候補が出ない状態が固定される。
        if len(self._by_reading or {}) < _MIN_READINGS:
            return
        try:
            tmp = self.cache_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'version': CACHE_VERSION,
                           'by_reading': self._by_reading,
                           'by_surface': self._by_surface},
                          f, ensure_ascii=False)
            os.replace(tmp, self.cache_path)
        except Exception:
            pass    # キャッシュできなくても動作には支障がない

    def _load_cache(self):
        if not self.cache_path or not os.path.exists(self.cache_path):
            return False
        try:
            with open(self.cache_path, encoding='utf-8') as f:
                data = json.load(f)
            if data.get('version') != CACHE_VERSION:
                return False        # 古い形式は作り直す
            by_reading = data['by_reading']
            by_surface = data['by_surface']
            # 空・極端に小さい索引は壊れているとみなして作り直す
            if len(by_reading) < _MIN_READINGS:
                return False
            self._by_reading = by_reading
            self._by_surface = by_surface
            return True
        except Exception:
            return False

    def stats(self):
        """索引の状態（診断用）。"""
        return {
            'ready': self.ready,
            'readings': len(self._by_reading or {}),
            'surfaces': len(self._by_surface or {}),
            'has_janome': HAS_JANOME,
            'cache_path': self.cache_path,
        }
