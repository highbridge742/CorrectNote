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
語彙ストアと、誤打かな列から既知の読みを探す探索。

オンラインAIを使わずに補正を行うため、
「ユーザーが過去に使った語彙」を辞書として持ち、
誤打かな列の候補組み合わせの中から既知の読みに一致するものを探す。

このモジュールは「材料」だけを提供する。
外から使うのは次の3つだけ:

    VocabularyStore            語彙の記録・引き当て
    find_known_readings_flex   誤打された読みから既知の読みを探す
    build_context_vocab        同じメモ内の正しい表記を集める

**「直すかどうか」の判断はここでは一切行わない。**
判断は corrector.py の1経路に集約してある。

かつてこのファイルには補正の判断そのもの（correct / correct_line /
find_homophone_replacements / find_particle_replacements など）が
入っており、corrector.py と合わせて補正経路が並列に存在していた。
片方に安全策を入れても別の経路が同じ誤りを通してしまい、
正しい日本語を壊す誤補正が頻発したため、判断は corrector.py へ
一本化した（SPEC.md「過去の失敗と学び」1）。
使われなくなった旧経路は 2026-08 に削除済み。
ここに補正の判断を書き戻さないこと。
"""

import json
import math
import os
import time
from collections import defaultdict

from kana_layout import nearby_candidates


class VocabularyStore:
    """
    ユーザー固有の語彙を記録する。

    各エントリ:
        reading  : 読み（ひらがな）  例: もじにゅうりょく
        surface  : 表記             例: 文字入力
        count    : 使用回数
        last_seen: 最終使用時刻(epoch秒)
        category : カテゴリ
    """

    def __init__(self, path=None):
        self.path = path
        # reading -> {surface -> entry}
        self._by_reading = defaultdict(dict)
        # キャッシュ（語彙が変わったら None にリセット）
        self._readings_cache = None      # set of all readings
        self._surfaces_cache = None      # set of all surfaces
        self._prefixes_cache = None      # set of all reading prefixes
        self._next_chars_cache = None    # 前方一致文字列 -> 次の1文字の集合
        self._surface_to_reading = None  # surface -> reading の逆引きdict
        self._surface_index = None       # 先頭文字 -> [(reading, surface, entry)] のインデックス
        if path and os.path.exists(path):
            self.load()

    def _invalidate_cache(self):
        """語彙が変わったときにキャッシュを破棄する。"""
        self._readings_cache = None
        self._surfaces_cache = None
        self._prefixes_cache = None
        self._next_chars_cache = None
        self._surface_to_reading = None
        self._surface_index = None

    # ---------------- 記録 ----------------

    def add(self, reading, surface, category='その他'):
        """語彙を1件記録する。既にあれば使用回数を増やす。"""
        if not reading or not surface:
            return
        entry = self._by_reading[reading].get(surface)
        if entry:
            entry['count'] += 1
            entry['last_seen'] = time.time()
            if category != 'その他':
                entry['category'] = category
        else:
            self._by_reading[reading][surface] = {
                'reading': reading,
                'surface': surface,
                'count': 1,
                'last_seen': time.time(),
                'category': category,
            }
            self._invalidate_cache()

    def remove(self, reading, surface):
        """
        語彙を1件削除する（語彙の整理用）。

        検証の貼り付けの繰り返しなどで、誤った学習
        （たいしゅー→大衆、こうない→行内 等）が使用実績を持って
        居座ることがある。関門で実害は防いでいるが、判断材料を
        きれいに保ちたいときに、この経路で消せるようにする。

        戻り値: 消せたら True。
        """
        entries = self._by_reading.get(reading)
        if not entries or surface not in entries:
            return False
        del entries[surface]
        if not entries:
            del self._by_reading[reading]
        self._invalidate_cache()
        return True

    # ---------------- 検索 ----------------

    def lookup(self, reading):
        """読みが完全一致する語を、スコアの高い順に返す。"""
        entries = list(self._by_reading.get(reading, {}).values())
        entries.sort(key=lambda e: self.score(e), reverse=True)
        return entries

    def reading_of(self, surface):
        """
        表記から読みを引く（逆引き）。

        「文字入リュク」のように IME が部分的に変換した文字列を
        かなに戻して照合するために使う。
        """
        if self._surface_to_reading is None:
            self._build_surface_index()
        return self._surface_to_reading.get(surface)

    def _build_surface_index(self):
        """表記→読みの逆引き辞書を構築する。"""
        index = {}
        for reading, surfaces in self._by_reading.items():
            for surface, entry in surfaces.items():
                # 同じ表記に複数の読みがある場合は使用頻度の高いものを採用
                if surface not in index:
                    index[surface] = (reading, self.score(entry))
                else:
                    _, cur_score = index[surface]
                    s = self.score(entry)
                    if s > cur_score:
                        index[surface] = (reading, s)
        # 読みだけを返すように整理
        self._surface_to_reading = {s: r for s, (r, _) in index.items()}

    def all_surfaces(self):
        """登録されている表記の集合（キャッシュ）"""
        if self._surfaces_cache is None:
            out = set()
            for surfaces in self._by_reading.values():
                out.update(surfaces.keys())
            self._surfaces_cache = out
        return self._surfaces_cache

    def has_reading(self, reading):
        return reading in self._by_reading and len(self._by_reading[reading]) > 0

    def all_readings(self):
        """登録されている読みの集合（キャッシュ）"""
        if self._readings_cache is None:
            self._readings_cache = set(self._by_reading.keys())
        return self._readings_cache

    def all_prefixes(self):
        """
        全ての読みの前方一致集合（キャッシュ）。

        ビームサーチでの枝刈りに使う。
        33万語があっても一度だけ計算して使い回す。
        """
        if self._prefixes_cache is None:
            prefixes = set()
            for r in self._by_reading.keys():
                for i in range(1, len(r) + 1):
                    prefixes.add(r[:i])
            self._prefixes_cache = prefixes
        return self._prefixes_cache

    def next_chars(self, prefix):
        """
        ある読みの前方一致文字列 prefix の直後に続きうる文字の集合を返す。

        「脱字（1文字押し忘れ）」を補うビームサーチで、
        全てのかな文字を試すと遅すぎるため、
        実際に語彙の読みとして存在する続きの文字だけに絞り込む。

        全読みから作った「前方一致文字列 → 次の1文字の集合」の表を
        一度だけ構築してキャッシュする（トライ木と同じ役割）。
        """
        if self._next_chars_cache is None:
            table = defaultdict(set)
            for r in self._by_reading.keys():
                for i in range(len(r)):
                    table[r[:i]].add(r[i])
            self._next_chars_cache = table
        return self._next_chars_cache.get(prefix, ())

    def iter_surfaces_starting_with(self, prefix, max_len_diff=3):
        """
        表記が prefix と先頭文字が同じ語を返す。

        _match_by_surface での全件走査を避けるための高速化。
        先頭文字でグループ化したインデックスを使い、比較件数を削減する。
        """
        if not prefix:
            return
        if self._surface_index is None:
            self._build_surface_index_by_char()
        first = prefix[0]
        target_len = len(prefix)
        for reading, surface, entry in self._surface_index.get(first, []):
            if abs(len(surface) - target_len) <= max_len_diff:
                yield reading, surface, entry

    def _build_surface_index_by_char(self):
        """表記の先頭文字でグループ化したインデックスを構築する。"""
        index = defaultdict(list)
        for reading, surfaces in self._by_reading.items():
            for surface, entry in surfaces.items():
                if surface:
                    index[surface[0]].append((reading, surface, entry))
        self._surface_index = dict(index)

    @staticmethod
    def score(entry):
        """
        語彙の有力さ。
        よく使う語ほど高く、最近使った語ほど高い。
        """
        count_part = math.log(entry['count'] + 1)
        elapsed_days = (time.time() - entry['last_seen']) / 86400.0
        # 半減期を7日とした減衰
        recency_part = 0.5 ** (elapsed_days / 7.0)
        return count_part * (0.3 + 0.7 * recency_part)

    # ---------------- 永続化 ----------------

    def to_list(self):
        out = []
        for surfaces in self._by_reading.values():
            out.extend(surfaces.values())
        return out

    def save(self, path=None):
        target = path or self.path
        if not target:
            return
        with open(target, 'w', encoding='utf-8') as f:
            json.dump(self.to_list(), f, ensure_ascii=False, indent=2)

    def load(self, path=None):
        target = path or self.path
        if not target or not os.path.exists(target):
            return
        with open(target, encoding='utf-8') as f:
            data = json.load(f)
        self._by_reading.clear()
        for e in data:
            self._by_reading[e['reading']][e['surface']] = e
        self._invalidate_cache()


# ============================================================
# 誤打かな列の復元
# ============================================================

_FLEX_CACHE = {}
_FLEX_CACHE_LIMIT = 4000


def find_known_readings_flex(typed, store, max_dist=1.6, max_edits=2,
                             beam_width=600):
    """
    誤打された可能性のあるかな列 typed について、
    語彙ストアに存在する読みへ復元できる候補を探す。

    この探索は語彙全体を相手にした幅優先探索で、語彙が育つほど
    重くなる（実機の7000語超で1回あたり10ミリ秒近くかかり、
    行数の多いメモでは起動時の全行解析だけで10秒を超えていた）。
    同じ読みに対する探索は語彙が変わらない限り同じ結果になるので、
    結果を控えて使い回す。

    （キャッシュ本体は _find_known_readings_flex_uncached。
      語彙の件数を鍵に含めることで、語を覚えたあとは
      自動的に作り直される。）
    """
    try:
        vocab_size = len(store._by_reading)
    except Exception:
        vocab_size = -1
    key = (typed, vocab_size, max_dist, max_edits, beam_width)
    cached = _FLEX_CACHE.get(key)
    if cached is not None:
        return cached

    result = _find_known_readings_flex_uncached(
        typed, store, max_dist=max_dist, max_edits=max_edits,
        beam_width=beam_width)

    if len(_FLEX_CACHE) >= _FLEX_CACHE_LIMIT:
        _FLEX_CACHE.clear()
    _FLEX_CACHE[key] = result
    return result


def _find_known_readings_flex_uncached(typed, store, max_dist=1.6,
                                       max_edits=2, beam_width=600):
    """
    誤打された可能性のあるかな列 typed について、
    語彙ストアに存在する読みへ復元できる候補を探す。

    find_known_readings は「1文字を別の文字に置き換える」誤り
    （隣接キーの押し間違い）しか扱えない。
    しかし実際の誤打には他の種類もある:
      - 置換: 隣のキーを押してしまった（従来対応）
      - 脱字: 1文字押し忘れた（読みが1文字短い）
      - 重複: 同じキーを2回押してしまった（読みが1文字長い）
      - 入れ替わり: 隣り合う2文字の順番を間違えた
        （例:「たごん」→「たんご」）

    ここでは (語彙側の読みの位置, 入力側の位置) の2次元状態を
    ビームサーチで進めることで、この4種類をまとめて扱う。
    語彙が33万語規模でも動くよう、前方一致キャッシュで枝刈りする。

    戻り値: [(復元された読み, 訂正コスト, 訂正した文字数), ...] コストの低い順
    """
    if not typed:
        return []

    known = store.all_readings()
    if not known:
        return []
    prefixes = store.all_prefixes()

    # 状態: (語彙側で確定した読みの文字列, 消費した入力の位置, 訂正数)
    # 語彙側の文字列は必ず prefixes に含まれるものだけを残す（枝刈り）。
    beam = {('', 0): (0.0, 0)}   # (prefix, typed_pos) -> (cost, edits)
    n = len(typed)

    # 1文字の脱字・重複を許すコスト（隣接キー押し間違いと同程度に扱う）
    SKIP_COST = 1.1
    TRANSPOSE_COST = 0.6   # 入れ替わりは1回の訂正として扱う（人間には起きやすいため）

    for _ in range(n + max(2, n // 2) + 1):
        # 十分な反復回数（挿入によって語彙側が入力より長くなる分の余裕を持たせる）
        next_beam = {}

        def _relax(key, cost, edits):
            if edits > max_edits:
                return
            cur = next_beam.get(key)
            if cur is None or cost < cur[0]:
                next_beam[key] = (cost, edits)

        progressed = False
        for (prefix, pos), (cost, edits) in beam.items():
            if prefix in known and pos >= n:
                _relax((prefix, pos), cost, edits)
                continue

            # --- 通常の1文字対応（一致 or 置換） ---
            if pos < n:
                ch = typed[pos]
                for cand_char, d in nearby_candidates(ch, max_dist=max_dist):
                    new_prefix = prefix + cand_char
                    if new_prefix not in prefixes:
                        continue
                    new_edits = edits + (0 if cand_char == ch else 1)
                    _relax((new_prefix, pos + 1), cost + d, new_edits)
                    progressed = True

            # --- 脱字: 入力に無い1文字を語彙側が持っている（挿入で補う） ---
            # 語彙側だけ1文字進める（＝入力側の脱字を補う）。
            # 全かなを試すと遅すぎるので、実際にこのprefixの続きとして
            # 語彙に存在する文字だけを候補にする（トライ木的な絞り込み）。
            for cand_char in store.next_chars(prefix):
                new_prefix = prefix + cand_char
                if new_prefix not in prefixes:
                    continue
                _relax((new_prefix, pos), cost + SKIP_COST, edits + 1)
                progressed = True

            # --- 重複打鍵: 入力側だけ1文字進める（＝入力の余分な1文字を捨てる） ---
            if pos < n:
                _relax((prefix, pos + 1), cost + SKIP_COST, edits + 1)
                progressed = True

            # --- 入れ替わり: 隣り合う2文字の順序を入れ替えて対応させる ---
            if pos + 1 < n:
                ch1, ch2 = typed[pos], typed[pos + 1]
                new_prefix = prefix + ch2 + ch1
                if new_prefix in prefixes:
                    new_edits = edits + (0 if ch1 == ch2 else 1)
                    _relax((new_prefix, pos + 2), cost + TRANSPOSE_COST,
                          new_edits)
                    progressed = True

        if not next_beam:
            break
        # コストの低い順に上位だけ残す
        beam = dict(sorted(next_beam.items(), key=lambda kv: kv[1][0])[:beam_width])
        if not progressed:
            break

    # 長音「ー」の位置は動かさない（find_similar_readings と同じ。
    # ーが動く・消える訂正は別の語への化けにしかならない）。
    _bar_pos = tuple(i for i, c in enumerate(typed) if c == 'ー')
    results = []
    for (prefix, pos), (cost, edits) in beam.items():
        if prefix in known and pos >= n:
            if tuple(i for i, c in enumerate(prefix)
                     if c == 'ー') != _bar_pos:
                continue
            # 拗音・促音を開くだけの候補は作らない（にゃん→にやん）
            if _flattens_small_kana(typed, prefix):
                continue
            results.append((prefix, cost, edits))
    results.sort(key=lambda x: x[1])
    return results


def build_context_vocab(all_lines, store):
    """
    メモ全体から「正しく書かれた語」を抽出して文脈語彙を作る。

    「単語のつながり」と正しく書かれた行があれば、
    「たんぎ」「タン具」等もそこに合わせて補正できる。

    戻り値: {読み: (表記, カテゴリ)} の辞書
    """
    context = {}
    from morphology import tokenize, HAS_JANOME
    if not HAS_JANOME:
        return context

    for line in all_lines:
        if not line.strip():
            continue
        for tok in tokenize(line):
            if tok.is_skippable:
                continue
            if len(tok.surface) < 2:
                continue
            if not tok.has_reading or not tok.reading:
                continue
            # 語彙ストアに読みがある語のみ（正しく書けた語として信頼する）
            if not store.has_reading(tok.reading):
                continue

            # 実際にメモに書かれている表記そのものを文脈として採用する。
            # ここで語彙ストアの最有力表記に置き換えてしまうと、
            # 「同じメモの中でこう書けている」という情報が失われ、
            # 文脈に合わせるという目的を果たせなくなる。
            entries = store.lookup(tok.reading)
            entry = next((e for e in entries if e['surface'] == tok.surface), None)
            if entry is None:
                # 書かれている表記が語彙に無い＝それ自体が誤変換かもしれない。
                # これを文脈として採用すると、誤りを基準にしてしまうので使わない。
                # また、ここで語彙ストアの最有力表記を代わりに入れてしまうと
                # 「以下」→「異化」のように、文脈と無関係な書き換えを
                # 文脈由来だと誤認してしまうため、何も記録しない。
                continue
            context[tok.reading] = (tok.surface, entry['category'])
    return context


def build_context_vocab_cached(all_lines, store, cache):
    """
    build_context_vocab の差分版。行ごとの抽出結果を控えて使い回す。

    文脈語彙は解析のたび（実質、打鍵が落ち着くたび）に作り直される。
    毎回メモ全文を形態素解析すると、行数が増えるほど1打鍵ごとの
    反応が重くなる（実機で「入力から画面反映までが長い」と報告
    された・2026-08-08）。1回の打鍵で変わる行は普通1〜2行しか
    ないので、**行の文字列を鍵に**抽出結果を控えておき、
    変わっていない行は解析し直さない。

    cache は呼び出し側が持ち続ける辞書:
        {'_store_size': int, 行の文字列: [(読み, (表記, 分類)), ...]}
    語彙ストアが育つと同じ行でも抽出結果が変わりうるため、
    ストアの語数が変わったら控えを捨てて作り直す。
    使われなくなった行の控えは呼び出しの最後に落とす
    （消えた行の控えが溜まり続けないように）。
    """
    from morphology import tokenize, HAS_JANOME
    if not HAS_JANOME:
        return {}

    try:
        store_size = len(store.to_list())
    except Exception:
        store_size = -1
    if cache.get('_store_size') != store_size:
        cache.clear()
        cache['_store_size'] = store_size

    def _extract(line):
        out = []
        for tok in tokenize(line):
            if tok.is_skippable:
                continue
            if len(tok.surface) < 2:
                continue
            if not tok.has_reading or not tok.reading:
                continue
            if not store.has_reading(tok.reading):
                continue
            entries = store.lookup(tok.reading)
            entry = next((e for e in entries
                          if e['surface'] == tok.surface), None)
            if entry is None:
                continue
            out.append((tok.reading, (tok.surface, entry['category'])))
        return out

    context = {}
    seen = {'_store_size'}
    for line in all_lines:
        if not line.strip():
            continue
        got = cache.get(line)
        if got is None:
            got = _extract(line)
            cache[line] = got
        seen.add(line)
        for reading, val in got:
            context[reading] = val
    for key in [k for k in cache if k not in seen]:
        del cache[key]
    return context


# ============================================================
# 語彙の読みを総当たりで照合する探索（配列上の遠い取り違えも拾う）
# ============================================================
# find_known_readings_flex は「隣接キーの押し間違い」を前提にした
# 探索なので、キー配列上で遠い取り違え（「たんご」を「たんほ」）は
# 候補にすら上がらない。ご＝こ＋濁点、ほ＝数字段の右寄りで、
# 物理的に離れているためである。
#
# しかし実機からは「たんほの繋がり」「たんごのちながり」のような、
# **配列とは無関係な取り違え**も直してほしいと指定された
# （方針: 「ひらがなに直し、隣接キーや脱字などを考慮して再構築する」）。
#
# そこで、語彙の読みを長さで絞ってから重み付き編集距離で総当たりする
# 経路を別に用意する。隣接キーの誤打は安く、それ以外の取り違えは
# 高く数えるので、両方を同じ物差しの上に並べられる
# （＝「隣を押した」ほうが常に優先され、遠い取り違えは
#   他に説明が付かないときだけ採られる）。
#
# 使いどころは限定する。呼び出し側（corrector.py）が
# 「単語として成立していないと分かっている窓」にだけ使うこと。
# 正しい語に対して使うと、何にでも似た語が見つかってしまう。

# 隣接キーで説明が付かない取り違えの費用。
# 隣接キー1回（1.0前後）よりはっきり高くし、脱字・重複とも
# 並べられる値にする。
_FAR_SUBSTITUTION_COST = 2.4
# 脱字（1文字押し忘れ）・余分な打鍵（1文字多い）の費用。
#
# **隣接キーの誤打より高くする。** 打ち間違いのうち、
# 「キーを1つ余分に押した／押し忘れた」は、「隣のキーを押した」より
# 起こりにくい。安くすると、単に1文字削っただけの **短い語** が
# 常に最有力になってしまう（実機で「たんほ」→「たん」、
# 「つあがり」→「あがり」という切り詰めが起きた。
# 語彙が育つほど短い語が増えるので、この歪みは使うほど悪化する）。
#
# 連打（_REPEAT_GAP_COST）だけは例外として安いままにする。
# 同じキーを続けて打つのは実際によくある誤りで、
# しかも「たああんご」のように削るべき文字が明らかだから。
_GAP_COST = 2.6
# 直前・直後と同じ文字が余分に入っている場合の費用。
# 「たああんご」のように同じキーを続けて打ってしまう連打は
# 打ち間違いの中でも起きやすいので、安く数える。
_REPEAT_GAP_COST = 0.6

_SIM_CACHE = {}
_SIM_CACHE_LIMIT = 4000

# 文字ごとの「最低これだけは掛かる」費用（下界の材料）。
# その文字を置換するなら最も近いキーへの距離、削除するなら
# 連打の削除費用（_REPEAT_GAP_COST）が最低額。安いほうを採る。
_CHAR_FLOOR = None


def _char_floor_costs():
    global _CHAR_FLOOR
    if _CHAR_FLOOR is not None:
        return _CHAR_FLOOR
    table = {}
    try:
        from kana_layout import KANA_POSITIONS, kana_key_distance
        kanas = list(KANA_POSITIONS)
        for a in kanas:
            best = _REPEAT_GAP_COST
            for b in kanas:
                if a == b:
                    continue
                d = kana_key_distance(a, b)
                if d and d < best:
                    best = d
            table[a] = min(best, _REPEAT_GAP_COST)
    except Exception:
        pass
    _CHAR_FLOOR = table
    return table


def _sub_cost(a, b):
    """1文字を別の文字に取り違えた費用。"""
    if a == b:
        return 0.0
    try:
        from kana_layout import kana_key_distance, FAR
        d = kana_key_distance(a, b)
    except Exception:
        return _FAR_SUBSTITUTION_COST
    if d >= FAR:
        return _FAR_SUBSTITUTION_COST
    return min(d, _FAR_SUBSTITUTION_COST)


def weighted_edit_distance(typed, target):
    """
    2つのかな列の隔たりを (費用, 訂正の回数) で返す。

    費用は「その打ち間違いの起こりやすさ」を表す。
      - 隣のキーを押した      安い（kana_layout の距離そのまま）
      - 配列上で遠い取り違え  高い（_FAR_SUBSTITUTION_COST）
      - 押し忘れ・余分な打鍵  中くらい（_GAP_COST）
      - 同じキーの連打        安い（_REPEAT_GAP_COST）

    訂正の回数も併せて返すのは、費用が同じでも
    **触る箇所が少ないほうがありそう**だから。
    「たんほ」に対して「たんご」（1箇所）と「でんわ」（2箇所）は
    費用が偶然同じになるが、選ぶべきは前者である。

    費用が同じ経路が複数あるときは、訂正の回数が少ないほうを採る。
    """
    n, m = len(typed), len(target)
    if n == 0:
        return (m * _GAP_COST, m)
    if m == 0:
        return (n * _GAP_COST, n)

    def _del_cost(i):
        """typed[i] が余分だった場合の費用（連打なら安い）。"""
        ch = typed[i]
        if (i > 0 and typed[i - 1] == ch) or \
                (i + 1 < n and typed[i + 1] == ch):
            return _REPEAT_GAP_COST
        return _GAP_COST

    # (費用, 訂正回数) を並べて持つ。費用を主、回数を従で最小化する。
    prev = [(0.0, 0)]
    for j in range(1, m + 1):
        prev.append((prev[j - 1][0] + _GAP_COST, prev[j - 1][1] + 1))
    for i in range(1, n + 1):
        cur = [(prev[0][0] + _del_cost(i - 1), prev[0][1] + 1)]
        ch = typed[i - 1]
        for j in range(1, m + 1):
            options = [
                (prev[j][0] + _del_cost(i - 1), prev[j][1] + 1),
                (cur[j - 1][0] + _GAP_COST, cur[j - 1][1] + 1),
            ]
            sc = _sub_cost(ch, target[j - 1])
            options.append((prev[j - 1][0] + sc,
                            prev[j - 1][1] + (0 if sc == 0.0 else 1)))
            cur.append(min(options))
        prev = cur
    return prev[m]


_SMALL_TO_LARGE = str.maketrans('ぁぃぅぇぉゃゅょっ', 'あいうえおやゆよつ')
# 開いてはいけない小書き（拗音・小書き母音）。促音「っ」は含めない:
# 活用形の語幹引き当て（売っ→うっ→うつ→打つ）で っ→つ の読み替えが
# 必要になるため。
_SMALL_KANA_SET = set('ぁぃぅぇぉゃゅょ')


def _flattens_small_kana(typed, reading):
    """訂正で拗音・小書き母音が減るか。

    「にゃん」→「にやん」（ゅ→ゆ 等のシフト違い）だけでなく、
    「きゅっ」→「きやっ」（ゅ→や。隣のキーの大書きに化ける）も
    実機で報告された。小書きは意図して打たないと出ない字であり、
    それが減る（開かれる・別の大書きに置き換わる）訂正は
    別の語への化けにしかならない（2026-08-08）。
    逆方向（しゆうせい→しゅうせい。小書きが増える＝シフトの
    押し忘れの訂正）はよくある誤打なので許す。
    """
    if typed == reading:
        return False
    # 長さが変わる訂正（かんじょ→かんじ。小書きの削除）は対象外。
    # クリック候補の「取り違えの引き当て」で必要になる形のため、
    # ここで縛るのは「同じ長さのまま小書きが減る」置換だけにする。
    if len(typed) != len(reading):
        return False
    t_small = sum(1 for c in typed if c in _SMALL_KANA_SET)
    r_small = sum(1 for c in reading if c in _SMALL_KANA_SET)
    return r_small < t_small


def find_similar_readings(typed, store, max_cost=4.0, max_len_diff=3,
                          limit=6, min_count=2):
    """
    語彙の読みの中から、typed に近いものを近い順に返す。

    並べる順は **(訂正の回数, 費用, 語の長さの逆順)**。
    触る箇所が少ないものを先に、同じなら起こりやすい誤りを先に、
    それも同じなら長い語を先にする（短い語は偶然似やすいため）。

    max_cost: これを超える相手は候補にしない
    max_len_diff: 長さがこれ以上違う相手は最初から見ない（速さのため）
    min_count: 覚えた回数がこれ未満の語は候補にしない
        （辞書から取り込んだだけの珍しい語に引き寄せられないよう、
          既定では「実際に使われた語」に限る）

    戻り値: [(読み, 費用, 訂正の回数), ...]  typed 自身は含めない
    """
    if not typed:
        return []
    try:
        vocab_size = len(store._by_reading)
    except Exception:
        vocab_size = -1
    key = (typed, vocab_size, max_cost, max_len_diff, limit, min_count)
    cached = _SIM_CACHE.get(key)
    if cached is not None:
        return cached

    out = []
    n = len(typed)
    try:
        readings = store.all_readings()
    except Exception:
        readings = ()
    # 高速化のための安全な足切り。
    # 編集距離のDPは1件あたりの計算が重く、語彙7000件超の総当たりは
    # 1回で数十ミリ秒かかる（起動時の全行解析が数秒固まる主因）。
    # DPの前に「どんな並べ方をしても、これ以上は安くならない」
    # 下界を見積もり、しきい値を超えるものはDPを省く。
    #
    # 相手に無い文字（重複込みの共通部分から溢れた文字）は、
    # 置換（その文字から最も近いキーへの距離が最低額）か削除
    # （連打なら 0.6 が最低額）のどちらかが必ず掛かる。
    # 文字ごとの最低額（_char_floor_cost）を足し合わせたものが下界。
    # 下界なので取りこぼしは起きない（真の費用は必ずこれ以上）。
    typed_set = set(typed)
    # 読み側の各文字について「typed のどの文字に置き換えるとしても、
    # 最低これだけ掛かる」費用（typed の全文字への置換費用の最小）を
    # その場で求めて控える。typed に無い文字は、
    #   - 置換で説明するなら、その最小の置換費用
    #   - 挿入で説明するなら _GAP_COST
    # の安いほうが必ず掛かる。読み全体でこの合計に届かないことは
    # 無い（＝安全な下界）ので、しきい値を超える読みは
    # 重いDPを実行せずに捨てられる。
    # typed に含まれる文字は費用0とみなす（一致できるかもしれない
    # ため。実際より安く見積もる方向の誤差しか無い）。
    dmin_cache = {}

    def _dmin(c):
        v = dmin_cache.get(c)
        if v is None:
            v = min(min(_sub_cost(t, c) for t in typed_set), _GAP_COST)
            dmin_cache[c] = v
        return v

    # 長音「ー」の位置は動かさない。ーは伸ばして書いた話し言葉の
    # 印であることが多く、ーが動く・消える訂正は別の語への
    # 化け（もしもーし→もしーと、みかーん→みかん）にしかならない
    # （2026-08-08、セリフの検証で合意）。
    _bar_pos = tuple(i for i, c in enumerate(typed) if c == 'ー')

    for reading in readings:
        if reading == typed:
            continue
        if tuple(i for i, c in enumerate(reading)
                 if c == 'ー') != _bar_pos:
            continue
        # 拗音・促音を開くだけの候補は作らない（にゃん→にやん）
        if _flattens_small_kana(typed, reading):
            continue
        # 促音・小書きで終わる読みは活用の断片（つよかっ・打っ 等。
        # 自動学習が拾ってしまった語幹）。独立した語として当てると
        # 「つよかった」→「つよかっ」のような破壊になるので、
        # 再構築の候補には出さない（クリックの候補づくりは
        # 別経路なので影響しない）。
        if reading[-1] in 'っゃゅょぁぃぅぇぉ':
            continue
        m = len(reading)
        if abs(m - n) > max_len_diff:
            continue
        lower = 0.0
        for c in reading:
            if c not in typed_set:
                lower += _dmin(c)
                if lower >= max_cost:
                    break
        if lower >= max_cost:
            continue
        cost, edits = weighted_edit_distance(typed, reading)
        if cost >= max_cost:
            continue
        if min_count > 0:
            try:
                if not any(e['count'] >= min_count
                           for e in store.lookup(reading)):
                    continue
            except Exception:
                continue
        out.append((reading, cost, edits))
    # 費用も編集回数も長さも並ぶ読み同士の順序を、読みの文字列で
    # 確定させる。all_readings() は集合で、並び順が起動ごとに変わる
    # （ハッシュのランダム化）。ここで順序を固定しないと、拮抗した
    # 候補のどれが「最有力」かが起動ごとに揺れ、同じメモでも
    # 起動のたびに補正結果が変わりうる（総点検で 実在/実害 が
    # 入れ替わるのを確認。2026-08-08）。
    out.sort(key=lambda rce: (rce[2], rce[1], -len(rce[0]), rce[0]))
    out = out[:limit]

    if len(_SIM_CACHE) >= _SIM_CACHE_LIMIT:
        _SIM_CACHE.clear()
    _SIM_CACHE[key] = out
    return out
