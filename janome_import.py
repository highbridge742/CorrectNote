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
janome の内蔵辞書（IPAdic）から語彙を取り込む。

janome は辞書を sysdic/ 以下に Python モジュールとして持っている。
  entries_compact0.py 〜 9.py : 表記・品詞など
  entries_extra0.py   〜 9.py : 読みなど
これらを直接 import して語彙を取り出す。

内部構造は janome のバージョンによって変わりうるので、
取り出せなかった場合は learn_from_text（形態素解析の結果から学ぶ）を使う。
こちらは確実に動く。

    pip install janome
"""

import importlib
import os

try:
    from janome.tokenizer import Tokenizer
    HAS_JANOME = True
except Exception:
    HAS_JANOME = False

# janome の辞書を読む処理は、複数のスレッドから同時に走らせない。
# ここで作る Tokenizer は morphology.py のものとは別インスタンスだが、
# **辞書の実体（mmap で開いたファイル）は janome の中で共有されて
# いる**ので、同じ錠前で守る必要がある。
# 同時に読むと読み出しが崩れ、janome が sys.exit(1) を呼んで
# アプリごと終わる（詳しい説明は morphology.py の _TOKENIZE_LOCK）。
try:
    from morphology import janome_lock as _janome_lock
except Exception:
    import threading as _threading
    _fallback_lock = _threading.Lock()

    def _janome_lock():
        return _fallback_lock


# 取り込みの決まりごとの版（うにさんの指定・2026-08-11・D-1）。
#
# **下の取り込みの決まり（品詞・コスト上限・語数・枠の割合）を
# 変えたら、必ずこの数字を上げること。**
# 上げると、次の起動で「辞書を作り直しますか？」と一度だけ尋ねる
# （app.py の `_maybe_offer_data_update`）。上げ忘れると、
# 更新したのに古い決まりで取り込んだ語彙のまま使い続けることになる
# （うにさんの報告:「アップデートした際に辞書と索引が古いまま」）。
#
# 版を上げても**語を消すことはない**。足りないものを足すだけ。
# 2 に上げた（項目48-DX・2026-08-16）。**読みの取りかたが変わった**
# ので、既に取り込んである語彙には `がっこー` のような
# 「発音の形」の読みが残っている。作り直しで正しい読みが足される
# （足すだけなので、覚えた語は消えない）。
IMPORT_RECIPE_VERSION = 2

# 取り込む品詞
IMPORT_POS = ('名詞', '動詞', '形容詞', '副詞')

# 除外する品詞細分類
EXCLUDE_SUB_POS = (
    '代名詞', '数', '接尾', '接続詞的', '非自立',
    '特殊', 'ナイ形容詞語幹',
    '固有名詞',   # 地名・人名・作品名は原則除外
)

# 一般語のコスト上限（IPAdicでは値が小さいほど一般的）
# 日常のメモ書きで使う語に絞るため、かなり厳しめにする。
# 緩すぎると「帰農」「一応」のような硬い語・専門語まで拾ってしまい、
# 誤変換候補のノイズが増えて誤補正の原因になる。
GENERAL_COST_LIMIT = 4500

# 取り込む語数の上限。
# 2026-08-10 に 6000 → 16000。品詞が読めるようになって固有名詞が
# 落ちるようになり、同じ語数でも中身が濃くなったうえで、
# なお「補正」「スクロール」「貼り付け」のような日常語が
# 枠に入りきらなかったため。
DEFAULT_MAX_WORDS = 16000

# 品詞ごとの取り込み枠（上限に対する割合）。
#
# **コスト順にそのまま上から取ると、日常語が入らない。**
# IPAdic のコストは新聞のコーパス由来なので、上位が
# 「連盟・協会・研究所・貿易・五輪・国際線」のような語に偏る。
# 一方、メモ書きでよく使う「補正・入力・変換・設定・削除・
# スクロール」は、動作を表す 名詞/サ変接続 にまとまっている。
# 品詞ごとに枠を分けて、それぞれの中でコスト順に採る。
#
# (品詞, 品詞細分類, 割合)。品詞細分類が None ならその品詞の残り全部。
# 最後の (None, None) は、どの枠にも入らなかったものの受け皿。
IMPORT_QUOTA = (
    ('名詞', 'サ変接続', 0.22),        # 操作・動作の語（補正・入力・変換）
    ('名詞', '一般', 0.38),
    ('名詞', '形容動詞語幹', 0.08),
    ('動詞', None, 0.18),
    ('形容詞', None, 0.06),
    ('副詞', None, 0.05),
    (None, None, 0.03),
)

# 記号・スペース類。これを含む語は除外する
_SYMBOLS = set('・。、「」『』【】〔〕（）()[]{}〜~―—‐/\\＼｜|＆&＋+＝=')

# 2文字の漢字語のコスト上限（難読語・専門語を弾くための目安）。
# 「補正」4276・「入力」4460・「変換」4463・「設定」4467・「削除」4466・
# 「該当」4427 のような日常語がこの帯に入るため、以前の 3500 では
# 日常の熟語がごっそり落ちていた（2026-08-10）。
KANJI2_COST_LIMIT = 5600


def is_two_kanji_noun(surface, pos, sub_pos=None):
    """
    **漢字2字の名詞**か（項目48-OJ・2026-09-02）。

    `dict_index` が索引に入れる帯を決めるのに使う——**この族は
    `KANJI2_COST_LIMIT`（5600）まで索引に持つ**。`_should_exclude` の
    KANJI2 の門は「5600 を超える2字漢語を弾く」ためのものだったが、
    先に `GENERAL_COST_LIMIT`（4500）で切られて **4500〜5600 の帯には
    一度も届いていなかった**（項目48-OF）。課題5329・効率5462・
    単語5564・巨大4845 が**どこからも見つからない**のはそのせい。

    **語彙（`count`＝本人が使った回数）には入れない。** 2026-09-02 に
    測った——この族 12,482 語を語彙に入れると、**全部の道が
    「知っている語」として読む**ので readcheck の化けが +22、実機メモで
    `手動補正 → 主導性`・`各種補正 → 馘首性`・`動かしたら → 動かしたはら`
    （項目48-OJ の記録）。索引（世の中の語）に持ち、順位は
    `kango_tier`（AI の判断）で付ける。
    """
    if pos != '名詞':
        return False
    if sub_pos and sub_pos in EXCLUDE_SUB_POS:
        return False
    if not surface or len(surface) != 2:
        return False
    return all('一' <= c <= '鿿' for c in surface)


def is_okurigana_noun(surface, pos, sub_pos=None):
    """
    **漢字2つ以上＋送り仮名で終わる名詞**か（項目48-KG・2026-08-27）。

    `引き継ぎ` `組み合わせ` `読み込み` `締め切り` `呼び出し` の族
    ——動詞の名詞化。**形だけで決まる閉じた類**である。

    うにさんの指定（2026-08-27）:「**初期にあるべきです**」
    （`引き継ぎ` が初期語彙に無く、`引き月資料 ⇒ 引き継ぎ資料` が
      組めなかった）。

    ### 落ちていたのは門ではなく**枠**だった（実測）

        `引き継ぎ` のコストは 5575。`名詞:一般` の枠（38%＝6,080語）は
        **コスト 3,657 で尽きている**ので、`GENERAL_COST_LIMIT` を
        緩めても届かない。

    ### この族では**コスト順が有害**（実測）

        コスト順の上位 = 新聞の交ぜ書き
          投てき(4467) 抜てき 感ぷく 把そく 抽せん 愛がん 憂もん …
        `familiarity`（書籍の重み）を足すと**もっと悪くなる**
          投てき 397位 → **41位**／抜てき 406位 → **50位**

    ### **形で割れる**

        「漢字2つ以上＋送り仮名で終わる」に絞ると **4,493語**で、
        **交ぜ書きが1つも入らない**（交ぜ書きは漢字1字＋かな）:
          大好き 問い合わせ 組み合わせ 引き上げ 手渡し 持ち込み
          切り捨て 呼び出し 組み立て 割り込み 締め切り 売り上げ …

    ### だから**丸ごと入れる**（コスト順で切らない）

        族のコストは1,500位あたりから **5,622 で平坦**——IPAdic が
        頻度を持たない語の既定値なので、**そこから先を順位で切ることに
        意味が無い**。切るなら形で切る。

    ### 一度は壊した。**正の判定（項目48-KH）を先に入れて解けた**

    最初に測ったとき、**実機メモで 設計42 の的を壊した**:

        5:37  切り替え時に解析が走っていて → **切り返しに解析が走っていて**

    `切り返し`（きりかえし・実績1）が語彙に入ると、**芯の再構築**が
    読み `きりかええじ`（`替` の音訓 **かえ** と本文の送り仮名 `え` が
    繋がって え が二重になったもの）を「読めない」と見て、費用1.0で
    `きりかえし` に寄せていた。**正しい読みの側は自分で断れている**
    （`きりかえじ` では「読める並びを覆すほど自然にならない・差5044」）。

    うにさんの指摘（2026-08-27）——「**切り替え時、が自然な文字列と
    判定されないことが問題です。これを正しいとする分析をします**」。
    そこで **項目48-KH の正の判定**（名詞＋副詞可能の接尾＝
    できあがった形なので触らない）を先に入れた。**それで解けた。**

    ### 測った（きれいな写しどうし・同じ標本・2026-08-27）

        初期語彙 **16,287 → 17,090**（+803）
        readcheck kana 1831/1566/**87**  ← **どちらも同値**
        fpcheck 0／seedcheck 38/40・壊し0／probe_pairs 単独28・化け0
        **実機メモ memodiff 全行 差なし**（設計42 の的も残った）

        ※ 前に「直った +53／化けた −10」と書いたのは**標本の取り違え**。
          `exclude_kg.tsv` を渡した回と渡さない回を比べていた。
          readcheck の題材は語彙から作るので、**足した語を除く**
          ようにそろえないと数字は比べられない。
    """
    if pos != '名詞':
        return False
    if sub_pos and sub_pos in EXCLUDE_SUB_POS:
        return False
    if not surface or len(surface) < 3:
        return False
    if not ('一' <= surface[0] <= '鿿'):
        return False
    if not ('ぁ' <= surface[-1] <= 'ゟ'):
        return False
    if sum(1 for c in surface if '一' <= c <= '鿿') < 2:
        return False
    # **送り仮名を全部書く形だけ**（＝漢字が2つ続けて並ばない）。
    # 2026-08-27 に測って足した門。**省いた形を入れると壊れる**:
    #     切返し（＝切り返し）が入ると、設計42 の的
    #       `切り替え時二階席が走っていて ⇒ 切り替え時に解析が走っていて`
    #     が **`切返しに解析が走っていて`** に化けた
    #     仕上がり が入ると `単語のつあがり ⇒ 単語のつながり` が
    #     **`単語のしあがり`** に化けた
    # 省いた形（切返し・引継ぎ・払戻し・立上り）は新聞・法令の書き方で、
    # メモではふつう書かない。**送り仮名を書く形だけが、日常の書き方**。
    for i, c in enumerate(surface[:-1]):
        if '一' <= c <= '鿿' and '一' <= surface[i + 1] <= '鿿':
            return False
    return True


# 以前ここに置いていた地名の接尾語・地形の漢字の一覧
# （_LONG_PLACE_SUFFIXES / _SHORT_PLACE_SUFFIXES / _GEO_TAIL_KANJI）は
# 2026-08-10 に取り除いた。品詞が読めていなかったせいで固有名詞の
# 除外が効かず、その穴を表記のパターンで塞ごうとしたものだった。
# 品詞を extra 側から正しく取るようにしたので、役目を終えている
# （`_parse_extra_pos` と `_should_exclude` の説明を参照）。


def _should_exclude(surface, pos, sub_pos, sub_sub_pos, cost):
    """
    補正ツールに不要な語を除外する。

    除外対象:
      - 記号・句読点・スペースを含む語（フモ・ノー、ヤンキー・ドゥードル等）
      - カタカナ固有名詞（外国人名・地名・作品名）
      - 短すぎるカタカナ語（略語・省略形でノイズになりやすい）
      - 「〇〇事件」「〇〇号」等の事件名・法令名パターン
      - 国名・地名の接尾語で終わる語（sub_posの判定をすり抜けたもの）
      - コストが高い語（使用頻度が低い語）
    """
    # 記号・句読点を含む語は除外（「フモ・ノー」「ヤンキー・ドゥードル」等）
    if any(c in _SYMBOLS for c in surface):
        return True

    # ------------------------------------------------------------------
    # ここに以前あった手書きのふるいは、2026-08-10 に取り除いた。
    #
    #   - 地名の接尾語（山・川・谷・共和国・山脈…）で終わる語の除外
    #   - 「岩・鼻・瀬」など地形の漢字で終わる語の除外
    #   - カタカナ5文字以下の除外
    #   - 「〇〇事件」「〇〇号」の固有名詞パターン
    #
    # どれも「固有名詞を落とせていない」ことへの対症療法だった。
    # 本当の原因は品詞が読めていなかったこと（`_parse_extra_pos` の
    # 説明）で、品詞を正しく取れば `EXCLUDE_SUB_POS` の固有名詞除外が
    # 効き、「アボ鼻」「アナマ岩」「巽ノ瀬」は元から入らなくなる。
    #
    # 逆にこのふるいは日常語を巻き添えにしていた。とくにカタカナの
    # 長さ規則は向きが逆で、**ドラッグ・クリック・コピー・ファイル・
    # スクロール・ペーストが全滅**し、残るのは6文字以上の
    # 「ゲームセンター」「シマフクロウ」「パパパパパパーン」
    # ばかりだった（採用6000語の64%が6文字以上）。
    # ------------------------------------------------------------------

    # 2文字の漢字語でコストがやや高いものは難読語・専門語の可能性が高い
    if len(surface) == 2 and all('\u4e00' <= c <= '\u9fff' for c in surface):
        if cost > KANJI2_COST_LIMIT:
            return True

    # **形で選べる族は、コストで切らない**（項目48-KG。
    # `is_okurigana_noun` の説明に、なぜコスト順が使えないかを書いた）
    if is_okurigana_noun(surface, pos, sub_pos):
        return False

    # コストが高い語（使用頻度が低い）を除外
    if cost > GENERAL_COST_LIMIT:
        return True

    return False


def _quota_bucket(pos, sub_pos):
    """その語がどの枠に入るか。IMPORT_QUOTA の添字を返す。"""
    for i, (q_pos, q_sub, _share) in enumerate(IMPORT_QUOTA):
        if q_pos is None:
            return i                        # 受け皿
        if pos != q_pos:
            continue
        if q_sub is None or sub_pos == q_sub:
            return i
    return len(IMPORT_QUOTA) - 1


def _apply_quota(candidates, limit):
    """
    コスト順に並んだ候補から、**品詞ごとの枠**に従って採る。

    枠が余ったら（その品詞の候補が枠より少ないなど）、
    余りはコスト順の続きから埋める。上限ちょうどまで使いきる。

    candidates: (コスト, 表記, 読み, 品詞, 品詞細分類) をコスト昇順で
    """
    # **形で選べる族は枠の外で、丸ごと採る**（項目48-KG・2026-08-27）。
    # コスト順に意味が無い族なので、順位で切らない
    # （`is_okurigana_noun` の説明）。枠 `limit` は**コスト順で採る
    # ぶんの上限**であって、語彙全体の上限ではなくなった。
    picked = []
    taken = set()
    rest = []
    for c in candidates:
        if is_okurigana_noun(c[1], c[3], c[4]):
            picked.append(c)
            taken.add(id(c))
        else:
            rest.append(c)
    candidates = rest

    buckets = {}
    for c in candidates:
        buckets.setdefault(_quota_bucket(c[3], c[4]), []).append(c)

    # 形で採ったぶんは枠の外。ここから下は**コスト順で採るぶん**だけを
    # `limit` で数える（項目48-KG）。
    n_shape = len(picked)

    for i, (_p, _s, share) in enumerate(IMPORT_QUOTA):
        room = int(limit * share)
        for c in buckets.get(i, ())[:room]:
            picked.append(c)
            taken.add(id(c))

    # 枠を使いきれなかったぶんは、コスト順の続きで埋める
    if len(picked) - n_shape < limit:
        for c in candidates:
            if len(picked) - n_shape >= limit:
                break
            if id(c) not in taken:
                picked.append(c)
                taken.add(id(c))

    picked.sort(key=lambda c: c[0])
    return picked[:n_shape + limit]


def accept_entry(surface, pos, sub_pos, sub_sub_pos, cost):
    """
    辞書の1件を語彙に取り込んでよいか。

    取り込みの判断を1か所にまとめてある（取り込み本体と回帰テストの
    両方がここを通る）。順に、
      1. 品詞（名詞・動詞・形容詞・副詞だけ）
      2. 品詞細分類（**固有名詞**・代名詞・数・接尾…を除く）
      3. 表記とコストによる細かい除外（`_should_exclude`）
    を見る。

    **地名・人名は 2 で落ちる。** 品詞が読めていなかった頃は
    ここが素通りしていたため、「アボ鼻」「アナマ岩」のような
    岬・岩礁の固有名が大量に入っていた（2026-08-10）。

    品詞が取れないビルドに当たったときは、1・2 を素通りさせて
    3 だけで判断する（取りこぼすより、以前の挙動に戻すほうが安全）。
    """
    if pos and pos not in IMPORT_POS:
        return False
    if sub_pos and sub_pos in EXCLUDE_SUB_POS:
        return False
    return not _should_exclude(surface, pos, sub_pos, sub_sub_pos, cost)


def _guess_category(pos, sub_pos, surface):
    """janome の品詞からおおまかにカテゴリを決める。"""
    if sub_pos == '固有名詞':
        return 'その他'
    if pos in ('動詞', '形容詞'):
        return '日常会話'
    if surface and all('\u30a1' <= c <= '\u30f6' or c == 'ー'
                       for c in surface):
        return 'IT・PC操作'
    return 'その他'


def katakana_to_hiragana(text):
    out = []
    for ch in text:
        if '\u30a1' <= ch <= '\u30f6':
            out.append(chr(ord(ch) - 0x60))
        else:
            out.append(ch)
    return ''.join(out)


def _is_katakana_word(s):
    return bool(s) and all('\u30a1' <= c <= '\u30f6' or c == 'ー' for c in s)


# ============================================================
# 内蔵辞書からの取り込み
# ============================================================

def _find_data(module):
    """モジュールの中から辞書データ本体（最も大きなコンテナ）を探す。"""
    for name in ('DATA', 'entries', 'ENTRIES', 'data'):
        val = getattr(module, name, None)
        if val is not None:
            return val
    best, best_size = None, 0
    for name in dir(module):
        if name.startswith('__'):
            continue
        val = getattr(module, name)
        if isinstance(val, (dict, list, tuple)):
            try:
                size = len(val)
            except Exception:
                continue
            if size > best_size:
                best, best_size = val, size
    return best


def _iter_items(data):
    """dict でも list でも同じように (キー, 値) を返す。"""
    if isinstance(data, dict):
        for k, v in data.items():
            yield k, v
    else:
        for i, v in enumerate(data):
            yield i, v


def _get_item(data, key):
    try:
        if isinstance(data, dict):
            return data.get(key)
        return data[key]
    except Exception:
        return None


def _extract_strings(item):
    """入れ子になったタプル・リストから文字列だけを取り出す。"""
    out = []
    stack = [item]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str):
            out.append(cur)
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
    return out


def _parse_compact(item):
    """
    compact 側の1件から (表記, 品詞, 生起コスト) を取り出す。

    janome の内蔵辞書の並びは
      compact = (表記, 左文脈ID, 右文脈ID, 生起コスト)
      extra   = (品詞, 活用型, 活用形, 原形, 読み, 発音)
    で、**compact 側に品詞は入っていない**（文字列は表記だけ）。
    品詞は `_parse_extra_pos` が extra 側から取る。
    ここが戻す品詞は、並びの違うビルドに当たったときの保険。

    生起コストは「その語の使われやすさ」を表し、小さいほど一般的。
    語彙を絞り込むときの目安に使う。並びが分かっているときは
    **4番目**から取る。以前は数値の最大値を当てずっぽうで
    コストとみなしていたため、左右の文脈IDのほうが大きい語では
    コストではなくIDを読んでいた。
    """
    if (isinstance(item, (list, tuple)) and len(item) == 4
            and isinstance(item[0], str)
            and all(isinstance(n, int) for n in item[1:])):
        return item[0], '', item[3]

    surface, pos_full, cost = '', '', None
    stack = [item]
    strings = []
    numbers = []
    while stack:
        cur = stack.pop()
        if isinstance(cur, str):
            strings.append(cur)
        elif isinstance(cur, int):
            numbers.append(cur)
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)

    for s in strings:
        if ',' in s and not pos_full:
            pos_full = s
        elif not surface and s and ',' not in s:
            surface = s

    # 数値の中で最も大きいものが生起コストであることが多い
    # (left_id, right_id は品詞IDで数千まで、cost は数千〜数万)
    if numbers:
        cost = max(numbers)

    return surface, pos_full, cost


def _parse_extra(item):
    """
    extra 側の1件から**読み**（カタカナ）を取り出す。

    **1つめではなく2つめを採る**（項目48-DX・2026-08-16）。
    extra の並びは

        [発音, 読み, 原形, ..., 品詞]
        ['ガッコー', 'ガッコウ', '学校', '*', '*', '名詞,一般,*,*']
        ['トーチャク', 'トウチャク', '到着', ...]
        ['コーヒー',  'コーヒー',  'コーヒー', ...]   ← 外来語は同じ

    で、**1つめは発音**（長音が `ー` になっている）。
    ここで1つめを採っていたので、

        辞書の索引 10,554読みのうち **3,886（37%）が `ー` の形**
        うにさんの語彙 15,331読みのうち **3,006（20%）**

    が「打っても一致しない読み」になっていた。
    利用者は `がっこう` と打つので、`がっこー` の索引には当たらない。

    そのせいで:
      - 「索引にある語は触らない」（項目48-CF/48-CG）が
        **長音を含む語に効いていなかった**。学校・東京・到着・
        広告のような**よく使う語が守られていない**
      - 語彙にも `がっこー` が入り、打った `がっこう` と別物になる

    外来語は発音と読みが同じ（`コーヒー`）なので、2つめを採って
    困ることはない。2つめが無い版に当たっても1つめに落とす。
    """
    got = [s for s in _extract_strings(item)
           if s and s != '*' and _is_katakana_word(s)]
    if len(got) >= 2:
        return got[1]
    return got[0] if got else ''


def _parse_extra_pos(item):
    """
    extra 側の1件から品詞（「名詞,固有名詞,一般,*」の形）を取り出す。

    **品詞は compact ではなく extra に入っている**（2026-08-10 に判明）。
    以前は compact 側から「, を含む文字列」を品詞として探していたが、
    compact 側の文字列は表記だけなので **品詞は常に空**だった。
    そのため `IMPORT_POS`（名詞・動詞・形容詞・副詞に限る）も
    **固有名詞の除外もまったく効いていなかった**。

    実機の語彙・辞書索引に「アボ鼻」「アナマ岩」のような岬・岩礁の
    固有名が大量に入っていたのはこれが原因。辞書側には
    `名詞,固有名詞,一般` の印がちゃんと付いている。

    並びの違うビルドに当たっても壊れないよう、先頭が品詞らしく
    なければ、入れ子の中から「, を含む文字列」を探す形に落とす。
    """
    if isinstance(item, (list, tuple)) and item:
        head = item[0]
        if isinstance(head, str) and ',' in head:
            return head
    for s in _extract_strings(item):
        if ',' in s:
            return s
    return ''


def iter_janome_entries(min_len=2, max_len=12):
    """
    janome の内蔵辞書から語を順に返す。

    戻り値: (表記, 読み, 品詞, 品詞細分類, 品詞細分類2, 生起コスト)
    """
    if not HAS_JANOME:
        return

    for part in range(10):
        try:
            compact = importlib.import_module(
                f'janome.sysdic.entries_compact{part}')
            extra = importlib.import_module(
                f'janome.sysdic.entries_extra{part}')
        except Exception:
            continue

        compact_data = _find_data(compact)
        extra_data = _find_data(extra)
        if compact_data is None:
            continue

        for key, comp in _iter_items(compact_data):
            surface, pos_full, cost = _parse_compact(comp)
            if not surface or not (min_len <= len(surface) <= max_len):
                continue

            reading = ''
            extra_item = None
            if extra_data is not None:
                extra_item = _get_item(extra_data, key)
                reading = _parse_extra(extra_item)
                # **品詞は extra 側から取る**（_parse_extra_pos の説明）。
                if not pos_full:
                    pos_full = _parse_extra_pos(extra_item)
            if not reading:
                continue

            parts = pos_full.split(',') if pos_full else []
            pos = parts[0] if parts else ''
            sub_pos = parts[1] if len(parts) > 1 else ''
            sub_sub_pos = parts[2] if len(parts) > 2 else ''

            yield (surface, katakana_to_hiragana(reading),
                   pos, sub_pos, sub_sub_pos,
                   cost if cost is not None else 99999)


def import_from_janome(store, limit=DEFAULT_MAX_WORDS, min_len=2, max_len=12,
                       progress=None, only_new=False):
    """
    janome の辞書から、日常的に使う語を選んで取り込む。

    固有名詞（地名・人名・川名・岬名など）は原則除外する。
    コストが高い語（＝使用頻度が低い語）も除外する。
    上記フィルタ後、コストの低い順に上位 limit 語を採用する。

    only_new=True: **既にある語には触らない**（うにさんの指定・
        2026-08-11・D-1）。アプリを更新したあとの「取り込み直し」に
        使う。`store.add` は既にある語の使用回数を増やすので、
        そのまま呼び直すと**うにさんが実際に使っている語の回数が
        水増しされる**。回数は「使用実績」の判断材料そのもので、
        水増しすると補正の判断が狂う（プラネタリウムの回帰と
        同じ形。学び20「数えるものには、必ず二度数えない仕組みを
        付ける」）。

    戻り値: 足した語数。only_new=True では**新しく足したぶんだけ**。
    """
    if not HAS_JANOME:
        return 0

    known = set()
    if only_new:
        try:
            known = {(e.get('reading'), e.get('surface'))
                     for e in store.to_list()}
        except Exception:
            known = set()

    candidates = []
    seen = set()

    for surface, reading, pos, sub_pos, sub_sub_pos, cost in iter_janome_entries(
            min_len, max_len):
        if not accept_entry(surface, pos, sub_pos, sub_sub_pos, cost):
            continue

        key = (reading, surface)
        if key in seen:
            continue
        seen.add(key)
        candidates.append((cost, surface, reading, pos, sub_pos))

        if progress and len(candidates) % 20000 == 0:
            progress(len(candidates))

    # コストが小さい（＝使用頻度が高い）語を優先して採用する。
    # ただし**品詞ごとに枠を分ける**（IMPORT_QUOTA の説明を参照）。
    candidates.sort(key=lambda c: c[0])
    if limit:
        candidates = _apply_quota(candidates, limit)

    # **書籍での使われぶりを `world` として持たせる**
    # （うにさんの指定・2026-08-14・項目48-DA）:
    #
    #   「ある程度使うと快適になるのであれば、そのある程度を初期と
    #     するべきです。すべての日本語の頻度は均一ではない。
    #     日常使いやすいものを補正しやすく。書籍から学んだものを、
    #     初期としてよいかと。」
    #
    # `familiarity.json`（UniDic／BCCWJ＝**書籍を柱にしたコーパス**。
    # 項目48-AE でうにさんが「新聞ではなく書籍から」と指定された
    # もの）の「ずれ」を足すと
    #
    #     書籍での重さ = IPAdic のコスト ＋ ずれ
    #
    # になる。小さいほど**書籍でよく使われる語**。
    #
    # **`count` は1のまま。** 回数は「この人が使った回数」という
    # 意味を保つ（学び20）。世の中での重みは別の鍵 `world` に置く。
    # 配る値はうにさんの実データの分布に合わせる（実測 2026-08-14。
    # count>=20 が16% / >=5 が34% / >=2 が78%）。
    try:
        import familiarity as _fam
    except Exception:
        _fam = None

    def _book_cost(cost, surface):
        if _fam is None:
            return cost
        try:
            return cost + _fam.bias(surface)
        except Exception:
            return cost

    ranked = sorted(candidates, key=lambda c: _book_cost(c[0], c[1]))
    n = len(ranked) or 1
    world_of = {}
    for i, (cost, surface, reading, pos, sub_pos) in enumerate(ranked):
        p = i / n
        world_of[(reading, surface)] = (
            20 if p < 0.16 else 5 if p < 0.34 else 2 if p < 0.78 else 1)

    added = 0
    for cost, surface, reading, pos, sub_pos in candidates:
        if only_new and (reading, surface) in known:
            continue
        store.add(reading, surface, _guess_category(pos, sub_pos, surface),
                  world=world_of.get((reading, surface), 1))
        added += 1

    return added


# ============================================================
# 形態素解析の結果から学ぶ（内部構造に依存しない確実な方法）
# ============================================================

def learn_from_text(store, text, category_hint=None):
    """
    文章を形態素解析して、そこに出てくる語を語彙として覚える。

    janome の内部構造に依存しないので確実に動く。
    ユーザーが実際に書いた文章から学ぶため、
    その人がよく使う語ほど強く記憶される。

    戻り値: 覚えた語の数
    """
    if not HAS_JANOME or not text:
        return 0

    t = Tokenizer()
    added = 0
    seen = set()

    # janome は辞書の mmap が壊れると `sys.exit` を呼ぶ。これは
    # SystemExit で、`except Exception` では捕まらない（学び16）。
    # ここは打鍵の3秒後に after() から呼ばれるので、素通りさせると
    # **無言でアプリが消える**（検証レポート 3-B）。
    try:
        with _janome_lock():
            tokens = list(t.tokenize(text))
    except SystemExit:
        return 0
    except Exception:
        return 0

    for token in tokens:
        parts = token.part_of_speech.split(',')
        pos = parts[0] if parts else ''
        sub_pos = parts[1] if len(parts) > 1 else ''

        if pos not in IMPORT_POS:
            continue
        if sub_pos in EXCLUDE_SUB_POS:
            continue

        surface = token.surface
        if len(surface) < 2:
            continue

        # 動詞・形容詞は基本形（辞書に載る形）だけを覚える。
        # 活用の途中の形（分から・使え・生き）まで語彙に入れると、
        # それが「使用実績のある語」として補正の当て先になり、
        # 「ひらから」→「ひわから」（分から）のような、正しいかなを
        # 活用の断片へ書き換える誤爆の温床になる（実機・2026-08-09。
        # count の水増しと重なって大量の誤検知を生んだ）。
        if pos in ('動詞', '形容詞'):
            base = getattr(token, 'base_form', surface)
            infl = getattr(token, 'infl_form', '') or ''
            # 連用形（打ち・入れ・出し）は名詞としても働く正当な形
            # なので学習してよい。それ以外の活用の途中の形だけ除く。
            # ※当初は基本形だけに絞ったが、「打ち」まで学習されなく
            #   なり、かな打ち（1-D の語の組）が直らなくなった
            #   （実機・2026-08-09）。
            if (base and base != '*' and base != surface
                    and '連用' not in infl):
                continue

        # phonetic は長音符を使う（ニューリョク）ので、
        # かなとの照合には reading（ニュウリョク）を使う
        reading = getattr(token, 'reading', '*')
        if not reading or reading == '*':
            continue
        reading = katakana_to_hiragana(reading)

        # 自動学習は「ユーザーが書いた語＝正しい語」という前提に立つが、
        # メモには誤変換された語も含まれている。
        # 誤変換語を学習してしまうと、その語が「使用実績のある正しい語」
        # とみなされ、以後その誤変換を直せなくなる
        # （「文字を治す」の「治す」を覚えてしまい、
        #   「直す」に補正できなくなる、という現象が起きていた）。
        #
        # そこで、同じ読みに複数の表記がありうる語
        # （＝変換ミスが起こりうる語）は自動学習の対象から外す。
        # ユーザーが明示的に「語彙を追加」した語や、
        # 辞書から取り込んだ語だけを信頼する。
        existing = store.lookup(reading)
        if existing and not any(e['surface'] == surface for e in existing):
            # 同じ読みで別の表記が既に知られている＝同音異義語がある。
            # どちらが意図された表記かは判断できないので学習しない。
            continue

        # 同じ文章の中に同じ語が何度出てきても、使用実績としては
        # 1回とだけ数える。これをしないと、編集のたびに全文を
        # 学習し直す場面で使用回数が際限なく増えていき、
        # 「よく使う語」の判断が壊れてしまう。
        key = (reading, surface)
        if key in seen:
            continue
        seen.add(key)

        category = category_hint or _guess_category(pos, sub_pos, surface)
        store.add(reading, surface, category)
        added += 1

    return added


def repair_conjugated_fragments(store):
    """
    語彙に紛れ込んだ「活用の途中の形」の使用実績を取り消す。

    過去の自動学習は、編集が落ち着くたびにメモ全文を学習し直して
    使用回数(count)を水増ししていた（2026-08-09 に「新しく書かれた
    行だけ学習する」へ修正）。その名残で「分から」「使え」「生き」の
    ような活用の断片が count>=2 の「使用実績のある語」になっており、
    正しいかなを断片へ書き換える誤爆（ひらから→ひわから 等）の
    温床になっている。

    janome で表記そのものを解析し、**1語の動詞・形容詞で、かつ
    基本形と違う形**（＝活用の途中の形）だけ count を 1（実績なし）へ
    戻す。語そのものは消さない（クリック候補としては残る）。
    名詞や基本形（巻き込む・使う）には触らない。

    一回きりの手入れとして呼ぶこと（実施の印は settings 側で持つ）。
    戻り値: 実績を取り消した件数。janome が無ければ 0。
    """
    if not HAS_JANOME:
        return 0
    t = Tokenizer()
    fixed = 0
    for entry in store.to_list():
        if entry.get('count', 0) < 2:
            continue
        surface = entry.get('surface') or ''
        if len(surface) < 2:
            continue
        try:
            with _janome_lock():
                toks = list(t.tokenize(surface))
        except SystemExit:
            # janome の `sys.exit` は Exception ではないので、
            # これを書かないと素通りする（学び16・検証レポート 3-B）。
            # ここは起動処理から呼ばれるため、素通りすると
            # **無言で起動に失敗する**。
            return fixed
        except Exception:
            continue
        if len(toks) != 1 or toks[0].surface != surface:
            continue
        pos = toks[0].part_of_speech.split(',')[0]
        if pos not in ('動詞', '形容詞'):
            continue
        base = getattr(toks[0], 'base_form', surface)
        infl = getattr(toks[0], 'infl_form', '') or ''
        # 連用形（打ち・入れ・出し）は名詞としても働く正当な形なので
        # 実績を残す。取り消すのは 未然形・仮定形・命令形 など、
        # 単語として立たない活用の途中の形だけ（分から・使え・書け）。
        # ※当初は基本形以外を全て取り消したため「打ち」の実績が
        #   消え、かな打ち（1-D）が直らなくなった（実機・2026-08-09）。
        if (base and base != '*' and base != surface
                and '連用' not in infl):
            entry['count'] = 1
            fixed += 1
    if fixed:
        store._invalidate_cache()
    return fixed


def learn_from_file(store, path):
    """テキストファイルを読んで語彙を覚える。"""
    text = None
    for enc in ('utf-8', 'cp932', 'utf-16'):
        try:
            with open(path, encoding=enc) as f:
                text = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            return 0
    if text is None:
        return 0
    return learn_from_text(store, text)


if __name__ == '__main__':
    if not HAS_JANOME:
        print('janome がインストールされていません。pip install janome')
        raise SystemExit(1)

    print('janome の内蔵辞書を調べています...')
    total = kept = 0
    samples = []
    for surface, reading, pos, sub_pos, sub_sub_pos, cost in iter_janome_entries():
        total += 1
        if pos and pos not in IMPORT_POS:
            continue
        if sub_pos in EXCLUDE_SUB_POS:
            continue
        if _should_exclude(surface, pos, sub_pos, sub_sub_pos, cost):
            continue
        kept += 1
        if len(samples) < 20:
            samples.append((surface, reading, pos, sub_pos, cost))

    print(f'辞書の総数: {total} 語 / 絞り込み後: {kept} 語')
    print(f'取り込むのは上位 {DEFAULT_MAX_WORDS} 語')
    if samples:
        print('\nサンプル:')
        for s, r, p, sp, c in samples:
            print(f'  {s:12s} {r:14s} {p}/{sp}  コスト:{c}')
    else:
        print('取り出せませんでした。「文章から学習」をお使いください。')
