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

import functools
import heapq
import json
import math
import os
import time
from collections import defaultdict

from kana_layout import nearby_candidates
try:
    from kana_layout import ALL_KANA as _ALL_KANA
except Exception:      # pragma: no cover
    _ALL_KANA = ()


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
        self._trie = None                # 読みの木（項目48-GB）
        # **語彙が変わった回数**（項目48-BT）。外の控えは、これを
        # 見分けに使う。件数では足りない——**語が増えなくても
        # 使用回数は変わる**（回数が敷居に届いた瞬間・同じ読みの
        # 表記が入れ替わった瞬間が、件数の変わらない変化）。
        self._revision = 0
        # **語の顔ぶれが変わった回数**（項目48-BV）。上とは別に持つ。
        # 使用回数で答えが変わらない控え（文脈語彙）は、こちらを見る。
        # `revision` を見せると**打鍵のたびに作り直す**ことになり、
        # 1000行のタブで毎回0.6秒かかる（そのための控えなのに）。
        self._shape_revision = 0
        if path and os.path.exists(path):
            self.load()

    def revision(self):
        """
        語彙が変わった回数（外の控えの見分け用・項目48-BT）。

        **使用回数が増えただけでも進む。** 回数で答えが変わる控え
        （直し先の一覧など）はこちらを見ること。
        """
        return getattr(self, '_revision', 0)

    def shape_revision(self):
        """
        **語の顔ぶれ**が変わった回数（項目48-BV）。

        足した・消した・分類が変わった、のときだけ進む。
        **使用回数が増えただけでは進まない。**
        読み・表記・分類しか見ない控えはこちらを見ること
        （打鍵のたびに作り直さずに済む）。
        """
        return getattr(self, '_shape_revision', 0)

    def _invalidate_cache(self):
        """語彙が変わったときにキャッシュを破棄する。"""
        self._revision = getattr(self, '_revision', 0) + 1
        self._shape_revision = getattr(self, '_shape_revision', 0) + 1
        self._readings_cache = None
        self._surfaces_cache = None
        self._prefixes_cache = None
        self._next_chars_cache = None
        self._surface_to_reading = None
        self._surface_index = None
        self._trie = None

    def reading_trie(self):
        """
        **読みを1本の木にまとめたもの**（項目48-GB）。

        同じ頭を持つ読みは木の上で1本にまとまる。
        `find_similar_readings` はこれを降りながら距離を測るので、
        「あ行から始まる相手」を何千件も個別に見なくて済む。

        作るのに約 35ms。**語彙が変わったときだけ**作り直す
        （`_invalidate_cache`。使用回数が増えただけでは作り直さない）。
        """
        if getattr(self, '_trie', None) is None:
            self._trie = _ReadingTrie(self._by_reading.keys())
        return self._trie

    # ---------------- 記録 ----------------

    def add(self, reading, surface, category='その他', world=0):
        """
        語彙を1件記録する。既にあれば使用回数を増やす。

        world: **世の中での使われぶり**（項目48-DA）。
            辞書から取り込むときに、書籍での頻度から与える。
            `count`（＝**この人が使った回数**）とは**別の持ち物**に
            する。片方の数で両方を表すと、

                見える／見えない … `count >= 2` の壁
                どれが勝つか     … 回数の大小

            の2つの役目が絡まり、**回数を配ると壁が中途半端に開く**
            （よく使う語だけ見えて、正解が下位にいると見えない）。
            分けておけば、**見える範囲は広く・順位は書籍の頻度で**
            が同時に成り立つ。

            **既にある語には触らない**（学び20）。
        """
        if not reading or not surface:
            return
        entry = self._by_reading[reading].get(surface)
        if entry:
            entry['count'] += 1
            entry['last_seen'] = time.time()
            if category != 'その他' and entry.get('category') != category:
                entry['category'] = category
                # 分類は**顔ぶれ**の側（項目48-BV）。文脈語彙は
                # 分類を持って回るので、変わったら作り直させる。
                self._shape_revision = getattr(
                    self, '_shape_revision', 0) + 1
            # **件数は変わらないが、中身は変わった**（項目48-BT）。
            # ここを数えないと、回数が敷居に届いた語がその場では
            # 直し先に入らない（`cachecheck.py` で見つけた）。
            self._revision = getattr(self, '_revision', 0) + 1
        else:
            entry = {
                'reading': reading,
                'surface': surface,
                'count': 1,
                'last_seen': time.time(),
                'category': category,
            }
            if world:
                # **`count` は増やさない。** 世の中での重みは別の鍵。
                # **1 でも書く。** 「辞書から取り込んだ語である」
                # という印そのものが、見える／見えないの判断に要る
                # （項目48-DA）。
                entry['world'] = int(world)
            self._by_reading[reading][surface] = entry
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

    # 同音異義語で選ばれなかった表記を、どれだけ残すか。
    # うにさんの指定（2026-08-10）:「同音異義語で選ばれなかった
    # 場合は評価値を大きく減らしてください」。
    DEMOTE_FACTOR = 0.2

    def demote_homophones(self, reading, chosen, factor=None):
        """
        同じ読みで**選ばれなかった**表記の使用実績を大きく下げる。

        ユーザーが同音異義語の中から1つを選び直したということは、
        「その読みで欲しいのはこれで、他ではない」という、いちばん
        はっきりした意思表示になる。それでも他の表記が高い実績を
        持ったままだと、次に同じ読みを書いたときにまた競り勝って
        しまう（実機で「単語」と「玉子」が競った件と同じ形）。

        **消しはしない**（1回ぶんは残す）。語彙を勝手に消さない
        という方針を守りつつ、判断材料としての重みだけ落とす。
        また使えば `add` で戻る。

        戻り値: 下げた件数。
        """
        if not reading:
            return 0
        f = self.DEMOTE_FACTOR if factor is None else factor
        entries = self._by_reading.get(reading)
        if not entries:
            return 0
        n = 0
        for surface, entry in entries.items():
            if surface == chosen:
                continue
            old = entry.get('count', 0)
            new = max(1, int(old * f))
            if new < old:
                entry['count'] = new
                n += 1
        if n:
            self._invalidate_cache()
        return n

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

        **いまは誰も使っていない**（項目48-GE）。
        `_find_known_readings_flex_uncached` がこれを引いていたが、
        `reading_trie()` の節をたどる形にしたので要らなくなった。
        呼ばれなければ作られない（13万件の集合を作らずに済む）。
        新しく使う前に、木で足りないかを考えること。
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

        **いまは誰も使っていない**（項目48-GE）。書いてあるとおり
        「トライ木と同じ役割」だったので、本物の木（`reading_trie`）
        に置き換えた。**集合を返すので、並ぶ順が起動ごとに変わる**
        （`PYTHONHASHSEED` に依る）という難点もあった。
        木の子は読みを並べ直してから作るので、順が動かない。
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

    **語彙側の位置は「読みの木の節」で持つ**（項目48-GE）。
    以前は**前方一致の文字列そのもの**を持ち、進むたびに
    `prefix + 字` を作って「その文字列が前方一致の集合に在るか」を
    引いていた。**それは木を、文字列で書いたものだった**
    （元の書き置きにも「トライ木と同じ役割」と書いてある）。
    48-GB で本物の木を作ったので、そちらに乗せ替える。

        prefix + 字 が前方一致集合に在るか   →  children[節].get(字)
        store.next_chars(prefix)            →  children[節] の中身
        prefix が読みとして在るか             →  word[節] is not None

    文字列を作らない・数え直さないので**答えは変わらず**、
    `all_prefixes`（13万件の集合）も要らなくなる。
    **IMEの予測変換が前方一致に木を使うのと同じ形**である。

    戻り値: [(復元された読み, 訂正コスト, 訂正した文字数), ...] コストの低い順
    """
    if not typed:
        return []

    known = store.all_readings()
    if not known:
        return []
    trie = store.reading_trie()
    children = trie.children
    word = trie.word

    # 状態: (読みの木の節, 消費した入力の位置) -> (費用, 訂正数)
    beam = {(0, 0): (0.0, 0)}
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
        for (node, pos), (cost, edits) in beam.items():
            if word[node] is not None and pos >= n:
                _relax((node, pos), cost, edits)
                continue
            kids = children[node]

            # --- 通常の1文字対応（一致 or 置換） ---
            if pos < n:
                ch = typed[pos]
                for cand_char, d in nearby_candidates(ch, max_dist=max_dist):
                    nxt = kids.get(cand_char)
                    if nxt is None:
                        continue
                    new_edits = edits + (0 if cand_char == ch else 1)
                    _relax((nxt, pos + 1), cost + d, new_edits)
                    progressed = True

            # --- 脱字: 入力に無い1文字を語彙側が持っている（挿入で補う） ---
            # 語彙側だけ1文字進める（＝入力側の脱字を補う）。
            # 全かなを試すと遅すぎるので、**その節から実際に伸びている
            # 字だけ**を候補にする（＝木の子。以前は
            # `store.next_chars(prefix)` が同じ表を字で引いていた）。
            for nxt in kids.values():
                _relax((nxt, pos), cost + SKIP_COST, edits + 1)
                progressed = True

            # --- 重複打鍵: 入力側だけ1文字進める（＝入力の余分な1文字を捨てる） ---
            if pos < n:
                _relax((node, pos + 1), cost + SKIP_COST, edits + 1)
                progressed = True

            # --- 入れ替わり: 隣り合う2文字の順序を入れ替えて対応させる ---
            if pos + 1 < n:
                ch1, ch2 = typed[pos], typed[pos + 1]
                mid = kids.get(ch2)
                if mid is not None:
                    nxt = children[mid].get(ch1)
                    if nxt is not None:
                        new_edits = edits + (0 if ch1 == ch2 else 1)
                        _relax((nxt, pos + 2), cost + TRANSPOSE_COST,
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
    for (node, pos), (cost, edits) in beam.items():
        prefix = word[node]
        if prefix is not None and pos >= n:
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


# 文脈語彙の行ごとの控えを、何行ぶんまで持つか。
# タブを行き来しても解析し直さずに済む程度に大きく取る
# （実機のタブは最大1000行ほど。全タブぶん持っても軽い）。
_CTX_CACHE_LIMIT = 8000


def build_context_vocab_cached(all_lines, store, cache, attested_out=None):
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
    **語の顔ぶれが変わったら**控えを捨てて作り直す。
    使われなくなった行の控えは呼び出しの最後に落とす
    （消えた行の控えが溜まり続けないように）。

    見分けは `store.shape_revision()`（項目48-BV）。**語数では
    足りない**——起動のたびに英単語を捨てて拾い直すので、
    **消した数と足した数が同じなら語数は動かない**。それで
    「消したはずの語が文脈語彙に残る」が起きていた
    （`cachecheck.py` で見つけた）。

    **`revision()` のほうを見てはいけない。** あちらは使用回数が
    増えただけでも進むので、**打鍵のたびに全行を解析し直す**
    ことになる（1000行で毎回0.6秒。控えの意味が無くなる）。
    ここが見ているのは読み・表記・分類だけで、回数は見ていない。
    """
    from morphology import tokenize, HAS_JANOME
    if not HAS_JANOME:
        return {}

    try:
        store_size = store.shape_revision()
    except Exception:
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

    def _extract_all(line):
        """
        **メモに実際に書かれている**（読み, 表記）を全部集める。

        `_extract` と違い、語彙にあるかどうかを問わない。
        選び直しの候補づくりに使う（うにさんの指摘・2026-08-11:
        「『ひらがな』をドラッグしても候補に『平仮名』が無い」。
        `平仮名` は janome の辞書にあるがコストが高く索引に
        入らず、自動学習も「同じ読みに別表記が既にある語は
        覚えない」規則で覚えられないため、どこからも出てこない）。
        候補は選び直しの材料でしかないので、自動補正より広く取る。
        """
        out = []
        for tok in tokenize(line):
            if tok.is_skippable or len(tok.surface) < 2:
                continue
            if not tok.has_reading or not tok.reading:
                continue
            if tok.surface == tok.reading:
                continue        # かなそのままは候補にならない
            out.append((tok.reading, tok.surface))
        return out

    context = {}
    seen = {'_store_size'}
    want_attested = attested_out is not None
    for line in all_lines:
        if not line.strip():
            continue
        got = cache.get(line)
        if got is None or (want_attested and len(got) < 2):
            got = (_extract(line), _extract_all(line))
            cache[line] = got
        elif not isinstance(got, tuple):
            got = (got, [])
            cache[line] = got
        seen.add(line)
        for reading, val in got[0]:
            context[reading] = val
        if want_attested:
            for reading, surface in got[1]:
                bucket = attested_out.setdefault(reading, [])
                if surface not in bucket:
                    bucket.append(surface)
    # 使われなくなった行の控えを落とす。ただし**毎回は落とさない**。
    # 落としてしまうと、タブを切り替えるたびに相手のタブの控えが
    # 消え、戻ったときに全行を解析し直すことになる
    # （1000行のタブで 0.7 秒。うにさんから「タブ切り替え時に
    # とても待たされます」の指摘・2026-08-11）。
    # 行の文字列を鍵にしているので、別のタブの行が残っていても
    # 誤って使われることは無い。溜まりすぎたときだけ掃除する。
    if len(cache) > _CTX_CACHE_LIMIT:
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

# **隣どうしの入れ替え**（順序違い）。SPEC の「誤打の種類」に
# 挙がっている3つのうちの1つ（項目48-CU）。
#
# 入れ替えを**1回の訂正**として数えないと、正解に届かない:
#     やすぎら（やすらぎ の入れ替え）
#       やすらぎ … 置換2回（ら↔ぎ）＝ 訂正2回
#       やすぎる … 置換1回（ら→る）＝ **訂正1回**
#     並べる順が (訂正の回数, 費用, …) なので、
#     **回数の少ない間違った答えが必ず勝つ**。
#
# 費用は「連打の削除(0.6)」より高く、「遠い置換(2.4)」「押し忘れ
# (2.6)」より安い。指の順番が入れ替わるのはよくある誤打だが、
# 何もしないよりは高くしておく。
#
# **場所で費用を変える**（うにさんの指定・2026-08-13・項目48-CV）:
#
#   「順序違いは、さいしょのもじは正しい確率がかなり高く、
#     なんなら順序の対象外としてもかまいません。
#     ただし濁点か半濁点のキーよりも前に2文字めが割り込む
#     ケースはあります。プラネタリウムでもその例はありました。
#     また最後の文字も正しい確率は高いです。ただし間違ってる
#     こともあるので対象外とはしません。
#     最初の文字と最後の文字を固定したとすると、その中間の文字が
#     入れ替わっていても人間は正しい順序に置き換えて読むことは
#     容易いです。」
#
# **両端に触れない入れ替えだけを安くする。** 3つの種のうち
# 中間どうしの入れ替えが、人にとっていちばん読み替えが容易い側。
#
#   実測（うにさんの語彙600語・種3つ・種を3回振り直して確認）:
#       中間の費用 1.8 → 1.4 で
#         seed 7   直った 82→84 / 化けた 16→15
#         seed 21  直った 79→83 / 化けた  7→ 6
#         seed 33  直った 91→92 / 化けた  8→ 8
#       **3回とも同じ向き**。小さいが揺れではない。
#
# **語頭を対象外にするのは、測って入れなかった**（学び19）。
# うにさんは「対象外としてもかまいません」と言われたが、実測では
#       語頭の入れ替えを切る   直った 116→77 / 化けた 20→**31**
#       語頭を高くする(2.4)    直った 116→103 / 化けた 20→21
# と**どちらも悪くなる**。直す道を塞ぐと「そのまま」になるのでは
# なく、**別の直しが選ばれて化ける**ため。他の5種の成績は
# 1件も動かなかった（＝語頭の候補は他の判断に干渉していない）。
# 語頭がめったに間違わないのは**材料の作り方**の話として正しく、
# `readcheck.py` は順序違いを語頭・中間・語末に分けて測る。
#
# 濁点・半濁点が語頭に絡む割り込み（フ→ア→゜ ＝ プラネタリウム）は、
# DP の手前の `normalize_marks(swap_across=True)`（項目48-AO）が
# 別経路で拾うので、ここでは扱わない。
_SWAP_COST_MID = 1.4        # 両端に触れない入れ替え
_SWAP_COST_TAIL = 1.8       # 語末を巻き込む
_SWAP_COST_HEAD = 1.8       # 語頭を巻き込む（切らない。上の実測）

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


@functools.lru_cache(maxsize=None)
def _sub_cost(a, b):
    """
    1文字を別の文字に取り違えた費用。

    **文字2つだけで決まる純粋な計算**なので、まるごと控える。
    1000行のタブの解析では26万回呼ばれ、しかも毎回
    `from kana_layout import ...` を通っていた（2026-08-11）。
    """
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


def weighted_edit_distance(typed, target, limit=None):
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

    limit: これ以上になると分かった時点で打ち切ってよい額。
        DP の各段の最小値は、そこから先で減ることが無い
        （どの操作も費用が0以上）ので、段の最小が limit に届いたら
        止めてよい。**返す額は limit ちょうど**なので、
        呼び出し側は必ず捨てる。None なら最後まで計算する
        （テストや他の用途のため、ふるまいを変えない）。

        1000行のタブの解析では、この関数が1行あたり8000回近く
        呼ばれる。その大半は「遠すぎて候補にならない」相手なので、
        打ち切りがそのまま効く（2026-08-11・うにさんから
        「1000行あると待ち時間が長い」の指摘）。
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
    prev2 = None        # 2つ前の段。**入れ替え**を見るのに要る
    # 1つ前の段の最小。打ち切りの判断に要る（項目48-GB。下を見ること）。
    prev_row_min = 0.0
    for i in range(1, n + 1):
        dc = _del_cost(i - 1)
        cur = [(prev[0][0] + dc, prev[0][1] + 1)]
        ch = typed[i - 1]
        row_min = cur[0][0]
        for j in range(1, m + 1):
            # 削除・挿入・置換の3通り。min(リスト) を組み立てず
            # その場で比べる（この2行の中が全体でいちばん回数の多い
            # 場所で、タプルのリストを作るだけで時間を食っていた）。
            # 同額のときは「削除→挿入→置換」の順で先に見つけたものを
            # 採る。min(options) と同じ並びなので結果は変わらない。
            best = (prev[j][0] + dc, prev[j][1] + 1)
            ins = (cur[j - 1][0] + _GAP_COST, cur[j - 1][1] + 1)
            if ins < best:
                best = ins
            sc = _sub_cost(ch, target[j - 1])
            sub = (prev[j - 1][0] + sc,
                   prev[j - 1][1] + (0 if sc == 0.0 else 1))
            if sub < best:
                best = sub
            # **隣どうしの入れ替え**（項目48-CU）。
            # typed の2文字が、target では逆順に並んでいるとき。
            # 置換2回ではなく**1回の訂正**として数える。
            if (prev2 is not None and j > 1
                    and ch == target[j - 2]
                    and typed[i - 2] == target[j - 1]
                    and ch != typed[i - 2]):
                # 入れ替えた2文字は typed の (i-2, i-1)。
                # **場所で費用が変わる**（項目48-CV）。
                if i - 2 == 0:
                    _sw = _SWAP_COST_HEAD        # 語頭を巻き込む
                elif i - 1 == n - 1:
                    _sw = _SWAP_COST_TAIL        # 語末を巻き込む
                else:
                    _sw = _SWAP_COST_MID         # 中間どうし
                if _sw is not None:
                    tr = (prev2[j - 2][0] + _sw, prev2[j - 2][1] + 1)
                    if tr < best:
                        best = tr
            cur.append(best)
            if best[0] < row_min:
                row_min = best[0]
        # **打ち切りは、2段つづけて届かないときだけ**（項目48-GB）。
        #
        # 「どの操作も費用が0以上だから、段の最小が limit に届いたら
        #   止めてよい」は、**入れ替え（項目48-CU）を入れた時点で
        #   成り立たなくなっていた**。入れ替えは `prev2`（2つ前の段）
        #   から来るので、**1つの段を飛び越える**。飛ばされた段の
        #   最小が高くても、答えは安いことがある。
        #
        # 実際に取りこぼしていた（2026-08-19・`probe_trie` で発見）:
        #
        #     だいぶんじ → だいあじん   本当は 4.20 なのに 4.50 で打ち切り
        #                              （末尾 んじ ↔ じん が入れ替え）
        #     てんかした → はなしかた   本当は 4.20 なのに 4.50 で打ち切り
        #
        # 経路は1歩で 0・1・2 段しか進めないので、**2段つづけて
        # 届かなければ、もう届かない**。そこで初めて止める。
        if limit is not None and row_min >= limit \
                and prev_row_min >= limit:
            return (limit, n + m)
        prev_row_min = row_min
        prev2 = prev
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


# **まだ育っていない語彙か**の見分け（項目48-CX）。
#
# 「使われた読み」が全体に占める割合で見る。実測（2026-08-14）:
#
#     ダウンロードしただけ   14,551 読み中 **373（2.6%）**
#     うにさんの語彙         15,331 読み中 **11,941（77.9%）**
#
# **30倍の開き**がある。どこで切っても同じなので、真ん中の広い
# ところ（1割）に置く。**細かい差を読む場所ではない**（学び50）。
# 語彙が育つにつれて自動的に「育った」側へ移る。
_YOUNG_RATIO = 0.10


def store_is_young(store):
    """
    **使った跡がほとんど無い＝ダウンロードしただけの状態か。**

    初期状態では辞書から取り込んだ語の使用回数が全部1なので、
    「実際に使われた語だけを候補にする」という既定
    （`find_similar_readings` の `min_count=2`）が
    **候補の97%を捨ててしまう**。そこだけ緩めるための見分け。

    数え直しは語彙が変わったときだけ（`revision()` を鍵にする）。
    """
    try:
        rev = store.revision()
    except Exception:
        rev = None
    cached = getattr(store, '_young_cache', None)
    if cached is not None and cached[0] == rev:
        return cached[1]
    total = used = 0
    try:
        for surfaces in store._by_reading.values():
            total += 1
            for e in surfaces.values():
                if (e.get('count') or 0) >= 2:
                    used += 1
                    break
    except Exception:
        return False
    young = bool(total) and (used / total) < _YOUNG_RATIO
    try:
        store._young_cache = (rev, young)
    except Exception:
        pass
    return young


# ============================================================
# 読みの木（トライ）と、木を降りる探索（項目48-GB）
# ============================================================
# うにさんの問い（2026-08-19）:
#
# > 「あらゆる補正後の文字列を、語のリストと一致するかを判定して
# >   いる認識でよいか？」
#
# 半分そうで、半分は逆だった。**作る側**（変形を作って辞書を引く）は
# 速く、**走る側**（22,714 件を1件ずつ見る）が全体の 78% を食って
# いた（項目48-GA）。うにさんの指示「よいです。続けて」を受けて、
# 走る側を**木を降りる形**に置き換えた。
#
# **答えは変えない。** `weighted_edit_distance` の漸化式そのままを、
# 木の上でたどる。同じ頭を持つ読みは木の上で1本にまとまるので、
# 「あ行から始まる相手」を何千件も個別に見なくて済む。
#
#     読み 22,714 件 → 木の節 47,914（作るのに約 35ms）
#
# **確かめかた**: `probe_trie.py` が、実機メモで実際に呼ばれた
# 問い合わせを両方に通して**1件ずつ突き合わせる**。
# `CN_TRIE=0` で今までの総当たりに戻せる（比べるため）。
_USE_TRIE = (os.environ.get('CN_TRIE', '1') != '0')


class _ReadingTrie:
    """
    語彙の読みを1本の木にまとめたもの。

    `children[node]` は {次の1文字: 次の節}。
    `word[node]` はその節で終わる読み（終わらないなら None）。

    **並べ直してから作る**（`sorted`）。集合の列挙順に頼ると
    起動ごとに節の番号が変わる（項目48-DR の再発防止）。
    """

    __slots__ = ('children', 'word', 'alphabet', 'minrem', 'maxrem')

    def __init__(self, readings):
        self.children = [{}]
        self.word = [None]
        children = self.children
        word = self.word
        for r in sorted(readings):
            node = 0
            for ch in r:
                nxt = children[node].get(ch)
                if nxt is None:
                    nxt = len(children)
                    children.append({})
                    word.append(None)
                    children[node][ch] = nxt
                node = nxt
            word[node] = r
        # **木に出てくる字を、木自身から集める**（項目48-GC）。
        # 以前は `kana_layout.ALL_KANA` で置き換え表を作っていたが、
        # 語彙には ALL_KANA に無い字（を・ゐ・ゎ・`en:` の英字）が
        # 混じっていて、**その字を含む読みに置き換えで辿り着けなかった**。
        #
        #     おつーじて → をつーじて   走る側は 2.4 で見つける
        #                              木は見つけられなかった
        #
        # 木の側が黙って取りこぼす形だったので、木自身の字で表を作る。
        alpha = set()
        for d in children:
            alpha.update(d)
        self.alphabet = tuple(sorted(alpha))
        # **節ごとの「残りの丈」**（項目48-GC）。
        # minrem[節] = その節から下にある語の、いちばん短い残りの長さ。
        # maxrem[節] = いちばん長い残りの長さ。探索の見込み（下界）に使う。
        NN = len(children)
        INF = 1 << 30
        minrem = [INF] * NN
        maxrem = [-1] * NN
        order = []
        st = [0]
        while st:
            v = st.pop()
            order.append(v)
            st.extend(children[v].values())
        for v in reversed(order):          # 子が先に決まる順
            mn = 0 if word[v] is not None else INF
            mx = 0 if word[v] is not None else -1
            for nx in children[v].values():
                a = minrem[nx] + 1
                if a < mn:
                    mn = a
                b = maxrem[nx] + 1
                if b > mx:
                    mx = b
            minrem[v] = mn
            maxrem[v] = mx
        self.minrem = minrem
        self.maxrem = maxrem


def _trie_costs(typed, store, max_cost, max_len_diff):
    """
    木を降りて、**敷居に届く読みとその費用**を全部返す。

    `{読み: (費用, 訂正の回数)}`。
    `weighted_edit_distance` が持つ4つの手だけを使う:

        置き換え   打った1字を、節の子の字に対応させる
        脱字       節の子の字を、打たずに補う（挿入）
        余分       打った1字を捨てる（削除。連打なら安い）
        入れ替え   隣り合う2字を逆順で対応させる

    費用の安い順に取り出す（ダイクストラ）ので、どの状態にも
    **いちばん安い行き方で1度だけ**着く。費用が同じときは
    訂正の回数が少ないほうを採る——`weighted_edit_distance` が
    `(費用, 回数)` の組を最小化するのと同じ。

    **先の見込み（項目48-GC）**: ある節から下にある語の丈は
    `minrem`／`maxrem` で分かっている。打ち残した字の数と丈が
    食い違えば、その差だけ「押し忘れ」か「余分」が**必ず**掛かる。
    いま掛かっている額にその分を足して敷居に届くなら、
    **その先には答えが無い**ので、進まない。
    見込みは必ず控えめ（下界）なので**取りこぼしは起きない**。
    取り出す節が1回 3,936 → 1,103 に減った。
    """
    trie = store.reading_trie()
    children = trie.children
    word = trie.word
    minrem = trie.minrem
    maxrem = trie.maxrem
    NN = len(children)
    n = len(typed)
    max_depth = n + max_len_diff

    # 打った字ごとの費用表。`_sub_cost` を輪の中で呼ばずに済む。
    # **木に出てくる字すべて**で作る（項目48-GC）。`_ALL_KANA` で
    # 作っていたときは、を・ゐ・ゎ を含む読みへ置き換えで辿り着け
    # なかった（走る側は辿り着けるので、両者が食い違っていた）。
    alphabet = trie.alphabet
    subrow = {}
    for ch in set(typed):
        row = {}
        for k in alphabet:
            c = _sub_cost(ch, k)
            if c < max_cost:
                row[k] = c
        subrow[ch] = row

    del_cost = []
    for i in range(n):
        ch = typed[i]
        if (i > 0 and typed[i - 1] == ch) or \
                (i + 1 < n and typed[i + 1] == ch):
            del_cost.append(_REPEAT_GAP_COST)
        else:
            del_cost.append(_GAP_COST)
    # i 文字目から先で、いちばん安い「余分」の額。
    # 見込み（下界）で「あと何回は必ず捨てる」に掛ける。
    sufmin = [_GAP_COST] * (n + 2)
    _m = _GAP_COST
    for i in range(n - 1, -1, -1):
        if del_cost[i] < _m:
            _m = del_cost[i]
        sufmin[i] = _m

    best = {0: (0.0, 0)}
    heap = [(0.0, 0, 0, 0, 0)]      # (費用, 訂正数, 打った側の位置, 節, 深さ)
    found = {}
    push = heapq.heappush
    pop = heapq.heappop
    while heap:
        cost, edits, i, node, dep = pop(heap)
        if best.get(i * NN + node) != (cost, edits):
            continue                # もっと安い行き方で既に着いている
        if i == n:
            w = word[node]
            if w is not None:
                found[w] = (cost, edits)
        kids = children[node]
        rem = n - i                     # まだ打ち残している字の数
        if kids and dep < max_depth:
            ins_c = cost + _GAP_COST
            ins_e = edits + 1
            ins_ok = ins_c < max_cost
            row = subrow[typed[i]] if i < n else None
            base = (i + 1) * NN
            sm0 = sufmin[i]
            sm1 = sufmin[i + 1]
            rem1 = rem - 1
            for ch, nx in kids.items():
                mn = minrem[nx]
                if ins_ok:
                    # 見込み: この子の下の語の丈と、打ち残しの差
                    if mn > rem:
                        h = ins_c + (mn - rem) * _GAP_COST
                    else:
                        mx = maxrem[nx]
                        h = ins_c + (rem - mx) * sm0 if rem > mx else ins_c
                    if h < max_cost:
                        key = i * NN + nx
                        cur = best.get(key)
                        if cur is None or (ins_c, ins_e) < cur:
                            best[key] = (ins_c, ins_e)
                            push(heap, (ins_c, ins_e, i, nx, dep + 1))
                if row is not None:
                    sc = row.get(ch)
                    if sc is None:
                        continue
                    c2 = cost + sc
                    if c2 >= max_cost:
                        continue
                    if mn > rem1:
                        if c2 + (mn - rem1) * _GAP_COST >= max_cost:
                            continue
                    else:
                        mx = maxrem[nx]
                        if rem1 > mx and \
                                c2 + (rem1 - mx) * sm1 >= max_cost:
                            continue
                    e2 = edits if sc == 0.0 else edits + 1
                    key = base + nx
                    cur = best.get(key)
                    if cur is None or (c2, e2) < cur:
                        best[key] = (c2, e2)
                        push(heap, (c2, e2, i + 1, nx, dep + 1))
        if i >= n:
            continue
        c2 = cost + del_cost[i]
        if c2 < max_cost:
            rem1 = rem - 1
            mn = minrem[node]
            if mn > rem1:
                h = c2 + (mn - rem1) * _GAP_COST
            else:
                mx = maxrem[node]
                h = c2 + (rem1 - mx) * sufmin[i + 1] if rem1 > mx else c2
            if h < max_cost:
                key = (i + 1) * NN + node
                cur = best.get(key)
                e2 = edits + 1
                if cur is None or (c2, e2) < cur:
                    best[key] = (c2, e2)
                    push(heap, (c2, e2, i + 1, node, dep))
        if i + 1 < n and typed[i] != typed[i + 1] and dep + 2 <= max_depth:
            mid = kids.get(typed[i + 1])
            if mid is not None:
                gnd = children[mid].get(typed[i])
                if gnd is not None:
                    if i == 0:
                        sw = _SWAP_COST_HEAD
                    elif i + 1 == n - 1:
                        sw = _SWAP_COST_TAIL
                    else:
                        sw = _SWAP_COST_MID
                    if sw is not None:
                        c2 = cost + sw
                        if c2 < max_cost:
                            rem2 = rem - 2
                            mn = minrem[gnd]
                            if mn > rem2:
                                h = c2 + (mn - rem2) * _GAP_COST
                            else:
                                mx = maxrem[gnd]
                                h = (c2 + (rem2 - mx) * sufmin[i + 2]
                                     if rem2 > mx else c2)
                            if h < max_cost:
                                e2 = edits + 1
                                key = (i + 2) * NN + gnd
                                cur = best.get(key)
                                if cur is None or (c2, e2) < cur:
                                    best[key] = (c2, e2)
                                    push(heap,
                                         (c2, e2, i + 2, gnd, dep + 2))
    return found


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

    **「1文字違いは隣のキーのときだけ」の門はここには置かない**
    （項目48-FX）。ここで候補ごと落とすと、**拮抗の裁定に使う
    相手まで消えて**、それまで拮抗で止まっていた別の直しが
    独り勝ちしてしまう（実機メモで `たんほの` が `たんぼの` に
    化けた）。門は `rebuild_window_core` が**決めた答え**に掛ける。

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
    #
    # **個数まで見る形にしても、DPは1回も減らなかった**
    # （2026-08-12 に実測。161,354 → 161,354）。生き残る読みは
    # 文字の**個数まで**typed と噛み合っているので、集合で見る
    # いまの形で足りている。**同じ道をもう一度通らないこと。**
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
    _has_bar = bool(_bar_pos)

    # **安い判定から順に置く。** 語彙は15000件を超えており、この
    # ループは1行の解析で20回以上回る。以前は長さの比較（いちばん
    # 安い）が最後にあり、その手前で全件に対して
    # 「ーの位置のタプルを作る」「小書きを開くだけかを調べる」を
    # やっていた（2026-08-11・うにさんから「1000行あると待ち時間が
    # 長い」の指摘）。並べ替えただけで、ふるまいは変えていない。
    _min_len = n - max_len_diff
    _max_len = n + max_len_diff
    # 打たれた側の小書き（拗音・小書き母音）の数。**輪の外で1回だけ**
    # 数える（項目48-GA。下の関門の説明を見ること）。
    _t_small = 0
    for _c in typed:
        if _c in _SMALL_KANA_SET:
            _t_small += 1
    # **木を降りて費用まで出しておく**（項目48-GB）。
    # 出せたら、下の輪は「関門を掛けるだけ」になる
    # （下界の見積もりも本計算も、もう要らない）。
    _known = None
    if _USE_TRIE:
        try:
            _known = _trie_costs(typed, store, max_cost, max_len_diff)
            readings = _known
        except Exception:
            _known = None
    for reading in readings:
        m = len(reading)
        if m < _min_len or m > _max_len:
            continue
        if reading == typed:
            continue
        # 長音「ー」の位置は動かさない。typed に ー が無いときは
        # 「相手にも ー が無い」だけを見ればよく、タプルを作らずに済む
        # （こちらが大多数）。
        if _has_bar:
            if tuple(i for i, c in enumerate(reading)
                     if c == 'ー') != _bar_pos:
                continue
        elif 'ー' in reading:
            continue
        # 促音・小書きで終わる読みは活用の断片（つよかっ・打っ 等。
        # 自動学習が拾ってしまった語幹）。独立した語として当てると
        # 「つよかった」→「つよかっ」のような破壊になるので、
        # 再構築の候補には出さない（クリックの候補づくりは
        # 別経路なので影響しない）。この判定は文字1つを見るだけ
        # なので、_flattens_small_kana より先に置く。
        # **拗音（ゃゅょ）は外した**（項目48-GK）。`corrector.py` の
        # `_FRAGMENT_TAILS` と同じ理由——拗音で終わる読みは
        # 辞書・解除・削除・場所・後者・神社…と**普通の語が 534件**。
        # ここで落としていたので、直し先としてまるごと見えなかった。
        if reading[-1] in 'っぁぃぅぇぉ':
            continue
        # 拗音・促音を開くだけの候補は作らない（にゃん→にやん）
        #
        # **下界の見積もりを先に置く形も試したが、差が無かった**
        # （2026-08-12 に実測。候補 619,855 のうち下界で落ちるのは
        # 74% なので、この判定を1/4に減らせる計算だったが、
        # 977行で 8.18秒 対 8.16秒＝誤差の範囲）。
        # **効かない入れ替えを核に残さない。同じ道を通らないこと。**
        #
        # **打たれた側に小書きが1つも無ければ、この関門は決して
        # 働かない**（項目48-GA）。`_flattens_small_kana` は
        # 「小書きが**減る**訂正か」を見るので、元が 0 個なら
        # `r_small < 0` になることは無い。それでも 17,000 回
        # 呼ばれていて、`probe_scan` で **1件も捨てずに 5ms** を
        # 使っていた。数えるのは輪の外で1回でよい（`_t_small`）。
        # **答えは1つも変わらない**（同じ判定を書き写しただけ）。
        if _t_small and len(reading) == n:
            if sum(1 for c in reading
                   if c in _SMALL_KANA_SET) < _t_small:
                continue
        # **木が費用まで出しているなら、下界も本計算も飛ばす**
        # （項目48-GB）。下の下界2つは「本計算をしないで済ませる」
        # ための見積もりなので、費用が既にあるなら要らない。
        if _known is not None:
            cost, edits = _known[reading]
            if cost >= max_cost:
                continue
            if min_count > 0:
                try:
                    if not any((e.get('count', 0) or 0) >= min_count
                               or (e.get('world', 0) or 0) >= 1
                               for e in store.lookup(reading)):
                        continue
                except Exception:
                    continue
            out.append((reading, cost, edits))
            continue
        lower = 0.0
        for c in reading:
            if c not in typed_set:
                lower += _dmin(c)
                if lower >= max_cost:
                    break
        if lower >= max_cost:
            continue
        # **逆向きの下界も見る**（項目48-FT・設計20・2026-08-19）。
        #
        # 上の下界は「**相手の字のうち、こちらに無いもの**」しか
        # 数えていない。**こちらの字のうち、相手に無いもの**も、
        # 置換か挿入で必ず費用が掛かる。どちらも正しい下界なので
        # **大きいほう**を採ってよい（和ではなく max。和にすると
        # 同じ1手を二重に数えて、正しい候補まで落としかねない）。
        #
        # **これがいちばん効いた。** 実測（実機の語彙・60行）:
        #     重み付き編集距離の呼び出し **921,408 → 86,046 回（−91%）**
        #     1行あたり **249ms → 159ms**
        #
        # 過去の高速化の試み（下界を先に置く／文字の個数まで見る）も、
        # 今回まず試した削除近傍の索引（SymSpell）も、どれも
        # **候補を絞る**話だった。実際に重かったのは
        # **距離の計算そのもの**で、そこへ届く数を減らすのが効いた。
        #
        # **答えは変わらない**（下界なので、落とすのは
        # 「どうやっても敷居に届かない」相手だけ）。
        # 1,540通りの問い合わせで**差 0 件**を確かめてある。
        r_set = set(reading)
        back = 0.0
        for _i, c in enumerate(typed):
            if c not in r_set:
                # **落とすときの最低額は、連打かどうかで変わる**
                # （`weighted_edit_distance._del_cost` と同じ規則）。
                # ここを `_GAP_COST` に決め打ちしたら、
                # `おおげさ` `しゃんんりあ` のように**連打を含む読み**で
                # 正しい候補を落とした（7,200組中 **97組**がずれた。
                # 2026-08-19 に実測して直した）。
                # **下界は、いちばん安い道を見落とさないこと。**
                if ((_i > 0 and typed[_i - 1] == c)
                        or (_i + 1 < n and typed[_i + 1] == c)):
                    best = _REPEAT_GAP_COST
                else:
                    best = _GAP_COST
                for t in r_set:
                    x = _sub_cost(c, t)
                    if x < best:
                        best = x
                        if best <= 0.0:
                            break
                back += best
                if back >= max_cost:
                    break
        if back >= max_cost:
            continue
        cost, edits = weighted_edit_distance(typed, reading, limit=max_cost)
        if cost >= max_cost:
            continue
        if min_count > 0:
            try:
                # **見えるかどうかは「この人が使った回数」か
                #   「世の中での使われぶり」のどちらかで足りる**
                #   （項目48-DA）。
                # 辞書から取り込んだ語は、使ったことが無くても
                # **書籍でよく使う語なら候補にする**。
                # うにさんの指定（2026-08-14）:
                #   「ある程度使うと快適になるのであれば、その
                #     ある程度を初期とするべきです。すべての
                #     日本語の頻度は均一ではない。日常使いやすい
                #     ものを補正しやすく。」
                # **辞書から取り込んだ語は、使ったことが無くても見える**
                # （`world` が付いている＝辞書由来）。
                # 実測（初期状態・同じ材料2,300件・2026-08-14）:
                #     見える範囲を狭めると**両方悪くなる**
                #       上位34%だけ  直った 292 / 化けた 93
                #       上位78%      直った 374 / 化けた 75
                #       ぜんぶ       ← いちばん広い（下で測る）
                #   正解が見えないまま誤りだけが見える「半開き」が
                #   いちばん悪い。**見える範囲は広く、順位で決める。**
                if not any((e.get('count', 0) or 0) >= min_count
                           or (e.get('world', 0) or 0) >= 1
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
    # **同じ費用・同じ訂正回数なら、書籍でよく使う語を先にする**
    # （うにさんの指定・2026-08-14・項目48-CZ）:
    #
    #   「すべての日本語の頻度は均一ではない。
    #     日常使いやすいものを補正しやすく。
    #     書籍から学んだものを、初期としてよいかと。」
    #
    # `familiarity.json` は UniDic／BCCWJ（**書籍を柱にした
    # コーパス**。項目48-AE でうにさんが「新聞ではなく書籍から」と
    # 指定されたもの）から作った「馴染みの薄さ」の表。
    # **大きいほど馴染みが薄い。** 小さいものを先にする。
    #
    # **順位づけにしか使わない。** 候補から外しはしない
    # （表に無い語は 0＝いちばん馴染みがある扱いになるので、
    #   外す方向に使うと表に載っていない語を全部殺してしまう）。
    # 費用と訂正回数が決めたあとの、**最後の並べ替え**だけ。
    def _familiar(reading):
        try:
            import familiarity as _f
            best = None
            for e in store.lookup(reading):
                v = _f.bias(e.get('surface') or '')
                if best is None or v < best:
                    best = v
            return best if best is not None else 0
        except Exception:
            return 0

    out.sort(key=lambda rce: (rce[2], rce[1], _familiar(rce[0]),
                              -len(rce[0]), rce[0]))
    out = out[:limit]

    if len(_SIM_CACHE) >= _SIM_CACHE_LIMIT:
        _SIM_CACHE.clear()
    _SIM_CACHE[key] = out
    return out
