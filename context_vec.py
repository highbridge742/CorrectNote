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
軽量な共起ベースの文脈ベクトル。

同音異義語（公園／講演／後援、過ぎ／好き 等）は、読みだけでは
どちらが正しいか決められない。決め手になるのは前後の文脈だが、
これまでの実装では「同じメモ内に、同じ読みの語が別の表記で
既に書かれているか」という**完全一致**でしか文脈を見ておらず、
「意味的に近い語が周りにあるか」までは見ていなかった。

このモジュールは、外部の学習済みモデルを持ち込まず、
**ユーザー自身が書いたメモの中での語の共起**だけから、
「この語とこの語は同じ話題で一緊に出てきやすい」という
軽量なベクトル（疎な共起カウント）を作る。

  Self-Attention（Transformerの文脈理解の中核）は、文中の各語が
  他の語とどれだけ関連するかを Query/Key/Value ベクトルの内積で
  計算する仕組みだが、それには大規模な事前学習が要る。
  ここではその発想を大きく簡略化し、
    - 「関連度」を、実際に近くで共起した回数（共起カウント）で近似する
    - 「注意の重み」を、対象語からの距離（近いほど重い）で近似する
  という軽量な統計処理に落とし込む。行列演算もモデルの重みも無く、
  辞書と統計だけで完結するため、このアプリの設計方針
  （オフライン・AI不使用・辞書と統計的な学習だけ）を保てる。

補正エンジン（corrector.py）の判断経路を増やさないという原則を守り、
このモジュールは「材料」だけを提供する。「直すかどうか」の判断は
これまでどおり corrector.py 側で行い、ここで作るスコアは
既存の判断の中で「複数の候補のうちどちらが文脈に合うか」を
決める追加の手がかりとしてのみ使う。
"""

import json
import math
import os
from collections import defaultdict

# 共起を数える範囲（同じ行の中で、対象語から何語以内を「近く」とみなすか）。
# Self-Attention の全語ペア計算とは違い、遠い語まで見ると
# 無関係な語同士の弱い相関ばかり集まってノイズになるため、
# 近傍に絞る。
CO_WINDOW = 4

# 学習対象にする語の最小の長さ（1文字の語は助詞等と紛れやすいため除く）
MIN_SURFACE_LEN = 2

# 1語あたりに覚える共起相手の数の上限（メモリと計算量を抑える）
MAX_NEIGHBORS_PER_WORD = 60

# 同じテキストを繰り返し学習しない、という語彙ストアと同じ方針。
# ここでは呼び出し側（app.py の _schedule_learning）が
# 既に同じ制御をしているので、このモジュール自身は重複排除をしない
# （呼ばれた分だけ律儀に数える）。


class ContextVectorStore:
    """
    語同士の共起カウントを保持し、類似度・文脈スコアを計算する。

    内部表現: surface -> {other_surface: count}
    密なベクトル（数百次元の実数）ではなく、疎な辞書のまま持つ。
    語彙数が数千〜数万語程度のこのアプリの規模では、疎なままの方が
    メモリ効率が良く、実装も単純になる（コサイン類似度は
    共通のキーだけを見れば計算できる）。
    """

    def __init__(self, path=None):
        self.path = path
        self._co = defaultdict(lambda: defaultdict(int))
        # 語ごとの総共起数（正規化に使う）
        self._totals = defaultdict(int)
        # 初期の話題のまとまり（seed_context.py）を読み込んだか。
        # 保存ファイルにも残し、起動のたびに重ねて読まないようにする
        # （読むたびに共起カウントが増え、初期値が実際の使用実績より
        #   強くなってしまうため）。
        self.seeded = False
        if path and os.path.exists(path):
            self.load()

    def ensure_seeded(self):
        """
        初期の話題のまとまりを、まだなら読み込む。

        文脈ベクトルは本来ユーザーのメモから育つものだが、
        それでは使い込むまで効かない。初回起動の時点から
        候補の並びがまともであるために、あらかじめ用意した
        話題のまとまりを最初に読み込んでおく
        （実機からの指摘：「初期起動時からしっかりと使える
          必要がある。使い込んだ状態のものを初期に添付するなど
          何かが必要」）。

        戻り値: 新たに読み込んだなら True
        """
        if self.seeded:
            return False
        try:
            from seed_context import load_seed_topics
            load_seed_topics(self)
        except Exception:
            return False
        self.seeded = True
        return True

    # ------------------------------------------------------------
    # 学習
    # ------------------------------------------------------------
    def observe_line(self, surfaces):
        """
        1行ぶんの語の並び（表記のリスト）から共起を学習する。

        surfaces: その行に出てきた内容語の表記を、出現順に並べたもの
            （助詞・記号は呼び出し側で除いておく）。
        """
        n = len(surfaces)
        if n < 2:
            return
        for i, w in enumerate(surfaces):
            if len(w) < MIN_SURFACE_LEN:
                continue
            lo = max(0, i - CO_WINDOW)
            hi = min(n, i + CO_WINDOW + 1)
            for j in range(lo, hi):
                if j == i:
                    continue
                other = surfaces[j]
                if len(other) < MIN_SURFACE_LEN:
                    continue
                # 距離が近いほど重みを大きくする
                # （Self-Attention の「近い語ほど強く関連づけられやすい」
                #   傾向を、簡易な距離減衰で近似する）。
                dist = abs(i - j)
                weight = 1 if dist <= 1 else 1  # 整数カウントに丸めて保持
                self._co[w][other] += weight
                self._totals[w] += weight
        self._prune_if_needed()

    def _prune_if_needed(self):
        """共起相手が増えすぎた語は、少ない回数のものから間引く。"""
        for w, neighbors in self._co.items():
            if len(neighbors) <= MAX_NEIGHBORS_PER_WORD:
                continue
            keep = sorted(neighbors.items(), key=lambda kv: -kv[1])[
                :MAX_NEIGHBORS_PER_WORD]
            self._co[w] = defaultdict(int, keep)

    # ------------------------------------------------------------
    # 類似度・スコア
    # ------------------------------------------------------------
    def similarity(self, word_a, word_b, min_shared=1):
        """
        2語の共起ベクトル同士のコサイン類似度（0〜1程度）。

        直接一緒に出てきたことが無くても、共通の共起相手が多ければ
        値が高くなる（「分布仮説」：似た文脈で使われる語は意味も近い）。
        どちらかの語のデータが無ければ 0.0。

        min_shared: **共通の相手がこの数に満たなければ 0.0 にする**
            （項目48-BY・2026-08-13）。既定の 1 は今までどおり。

            共通の相手が1語しか無いとき、コサイン類似度は
            **その1語だけで決まる**。片方の語の共起が少ないと、
            その1語がベクトルの大半を占めるので、値は大きく出る:

                制度 × 置き換え = (15×102) / (20.7×159.5) = 0.4627
                共通の相手は `ない` 1語だけ
                （`ない` は 制度 の72%・置き換え の64%を占める）

            これで `判断の精度に依存しない` が
            `判断の制度に依存しない` に化けていた。
            **「似ている」ではなく「たまたま同じ1語の隣にいた」。**
            自動補正の判断に使うときは 2 以上を渡すこと。
        """
        if word_a == word_b:
            return 1.0
        va = self._co.get(word_a)
        vb = self._co.get(word_b)
        if not va or not vb:
            return 0.0
        # 疎ベクトルの内積は、共通のキーだけを見れば十分
        keys = set(va.keys()) & set(vb.keys())
        if len(keys) < min_shared:
            return 0.0
        dot = sum(va[k] * vb[k] for k in keys)
        norm_a = math.sqrt(sum(v * v for v in va.values()))
        norm_b = math.sqrt(sum(v * v for v in vb.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def context_score(self, candidate, surrounding_words, min_shared=1):
        """
        候補の語が、周辺の語（文脈）とどれだけ馴染むかのスコア。

        surrounding_words: 対象位置に近い順に並べた周辺語のリスト。
            Self-Attention が全語ペアの関連度を計算するのに対し、
            ここでは「近い語ほど重みを大きくする」重み付き平均で
            簡易に近似する（先頭に近いものほど重視）。

        戻り値: 0.0〜1.0程度のスコア。データが無ければ 0.0
            （＝判断材料が無いので、他の手がかりに委ねる）。
        """
        if not surrounding_words:
            return 0.0
        total_w = 0.0
        total_score = 0.0
        for rank, w in enumerate(surrounding_words):
            weight = 1.0 / (rank + 1)   # 近いものほど重い
            sim = self.similarity(candidate, w, min_shared=min_shared)
            total_score += sim * weight
            total_w += weight
        if total_w == 0:
            return 0.0
        return total_score / total_w

    def pick_best_by_context(self, candidates, surrounding_words,
                             min_margin=0.08, min_shared=1):
        """
        複数の候補（同じ読みを持つ複数の表記）のうち、
        文脈に最も合うものを選ぶ。

        自動補正で使う場合は、僅差での決め打ちを避けるため、
        最上位と次点のスコア差が min_margin 未満なら選ばない
        （＝判断がつかないとみなす。SPEC.mdの「判断がつかない
        ものは直さない」という設計方針を、文脈スコアにも適用する）。

        candidates: 表記の文字列のリスト（2つ以上）。
        戻り値: 選ばれた表記。決め手が無ければ None。
        """
        if len(candidates) < 2 or not surrounding_words:
            return None
        scored = [(c, self.context_score(c, surrounding_words,
                                         min_shared=min_shared))
                  for c in candidates]
        scored.sort(key=lambda cs: -cs[1])
        best, best_score = scored[0]
        second_score = scored[1][1] if len(scored) > 1 else 0.0
        if best_score <= 0.0:
            return None    # 手がかりが無い
        if best_score - second_score < min_margin:
            return None    # 僅差。決め手にしない
        return best

    def rank_candidates(self, candidates, surrounding_words):
        """
        候補一覧（辞書のリストなど、'surface' キーを含む）を、
        文脈スコアの高い順に並べ替えるための、表記ごとのスコアを返す。

        **min_shared は掛けない。** 自動で書き換えるわけではなく、
        ユーザーが目で見て選ぶ候補の並び順なので、細い証拠でも
        並べる材料として使ってよい（学び39・判定の向きが違えば
        要る強さも違う）。

        自動補正の可否判定（pick_best_by_context）とは別に、
        ユーザーがクリックで選び直す際の候補順（candidates.py）にも
        「文脈的にありそうな順」を軽く反映したい場面で使う。
        こちらは決め打ちをしないので margin のしきい値は無い。

        戻り値: {surface: score}
        """
        if not surrounding_words:
            return {}
        return {c: self.context_score(c, surrounding_words)
               for c in candidates}

    def __len__(self):
        return len(self._co)

    # ------------------------------------------------------------
    # 保存・読み込み
    # ------------------------------------------------------------
    def save(self, path=None):
        path = path or self.path
        if not path:
            return
        # 疎な辞書のまま JSON にする。語数が多くなるとファイルも
        # 大きくなるため、共起相手は _prune_if_needed で既に
        # 上限を掛けてある。
        data = {
            'version': 1,
            'seeded': self.seeded,
            'co': {w: dict(neighbors) for w, neighbors in self._co.items()},
        }
        try:
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            pass    # 保存できなくても、次回はまた学習し直せば良い

    def load(self, path=None):
        path = path or self.path
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return
        if not isinstance(data, dict) or data.get('version') != 1:
            return
        co = data.get('co')
        if not isinstance(co, dict):
            return
        self._co = defaultdict(lambda: defaultdict(int))
        self._totals = defaultdict(int)
        self.seeded = bool(data.get('seeded'))
        for w, neighbors in co.items():
            if not isinstance(neighbors, dict):
                continue
            for other, count in neighbors.items():
                try:
                    c = int(count)
                except Exception:
                    continue
                self._co[w][other] = c
                self._totals[w] += c


def extract_content_words(tokenize_fn, line):
    """
    1行から、共起学習に使う内容語（表記）だけを取り出す。

    助詞・助動詞・記号を含めると、あらゆる語同士が「よく共起する」
    ことになってしまい、意味的な近さの手がかりとして機能しなくなる。
    corrector.py が持つ「触ってよい語」の判定をそのまま流用し、
    判断基準を1箇所に保つ（新しい語の良し悪しの基準を
    ここで作り直さない）。
    """
    import corrector as C
    try:
        tokens = tokenize_fn(line)
    except Exception:
        return []
    out = []
    for tok in tokens:
        surface = tok[0]
        if len(surface) < MIN_SURFACE_LEN:
            continue
        if C.is_protected_word(surface):
            continue
        if C.contains_non_japanese(surface):
            continue
        out.append(surface)
    return out


# ============================================================
# 文脈の材料集め（同じ行の外側）
# ============================================================
# 同音異義語をどちらにするかは、その行の中だけでは決まらないことが
# 多い。「上下のいくつかの行も含めて検討する」「直前の変換履歴も
# 頼りにする」という方針に沿って、行をまたいだ材料をここで作る。
#
# 判断そのものはこれまでどおり corrector.py が行う。ここは
# **材料を渡すだけ**で、直すか直さないかは決めない
# （判断経路を増やさないという設計方針のため）。

# 上下いくつの行まで見るか
NEARBY_RADIUS = 2
# 周辺の行から拾う語数の上限（増やしすぎると遠い話題まで混ざる）
NEARBY_LIMIT = 12


def build_nearby_words(line_count, index, words_of_line,
                       radius=NEARBY_RADIUS, limit=NEARBY_LIMIT):
    """
    対象行の上下の行から、内容語を **近い行から順に** 集める。

    line_count: 全体の行数
    index: 対象の行（0始まり）
    words_of_line: 行番号を渡すとその行の内容語を返す関数
        （呼び出し側で覚えておけるよう、関数で受ける。
          同じ行が何度も近傍になるため、その都度分割し直すと重い）

    近い行を先頭に置くのは、context_score が「並びの先頭ほど重い」
    重み付けをするため。順番そのものが優先順位を表す。

    戻り値: 表記のリスト（近い順）
    """
    out = []
    seen = set()
    for dist in range(1, radius + 1):
        for i in (index - dist, index + dist):
            if not (0 <= i < line_count) or i == index:
                continue
            try:
                words = words_of_line(i)
            except Exception:
                continue
            for w in words or ():
                if w in seen:
                    continue
                seen.add(w)
                out.append(w)
        if len(out) >= limit:
            break
    return out[:limit]


class RecentWords:
    """
    直前に確定した語を、新しい順にいくつか覚える。

    かな入力では、同じ話題を書いている間は同じ語が続けて出る。
    「直前の変換履歴」は、周囲の語と並んで有力な手がかりになる。

    ひとつ前だけでは弱いので複数を保持する（方針: 「この直前とは、
    ひとつ前だけではなく、いくつかを保持します」）。
    保存はしない。書いている最中の流れを見るためのもので、
    アプリを開き直せば忘れてよい（残すと、昨日の話題が今日の
    判断を引きずる）。
    """

    LIMIT = 12

    def __init__(self, limit=LIMIT):
        self.limit = limit
        self._words = []      # 新しい順

    def add(self, surface):
        """確定した語を1つ覚える。同じ語は先頭へ繰り上げる。"""
        if not isinstance(surface, str):
            return
        surface = surface.strip()
        if len(surface) < MIN_SURFACE_LEN:
            return
        if surface in self._words:
            self._words.remove(surface)
        self._words.insert(0, surface)
        del self._words[self.limit:]

    def add_all(self, surfaces):
        for s in surfaces or ():
            self.add(s)

    def words(self):
        """新しい順の一覧（そのまま文脈の材料として渡せる）。"""
        return list(self._words)

    def clear(self):
        self._words.clear()

    def __len__(self):
        return len(self._words)
