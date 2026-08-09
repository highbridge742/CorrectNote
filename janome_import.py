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

try:
    from janome.tokenizer import Tokenizer
    HAS_JANOME = True
except Exception:
    HAS_JANOME = False


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

# 取り込む語数の上限。厳選する方針にしたため大幅に減らす。
DEFAULT_MAX_WORDS = 6000

# 記号・スペース類。これを含む語は除外する
_SYMBOLS = set('・。、「」『』【】〔〕（）()[]{}〜~―—‐/\\＼｜|＆&＋+＝=')

# 国名・地名の接尾語パターン。固有名詞のsub_pos判定をすり抜けても
# これらで終わる語は地名の可能性が非常に高いため除外する。
#
# 実機の janome では辞書エントリから品詞が取れないビルドがあり
# （診断で品詞が全件空文字だった）、sub_pos == '固有名詞' の判定が
# まったく効かないことがある。そのため品詞に頼らず、
# **表記のパターンだけで**地名を弾けるようにしておく必要がある
# （実機で「地名のようなものが多すぎる」と報告された）。

# それ自体が地名以外にほぼ使われない接尾語。語の長さを問わず弾く。
_LONG_PLACE_SUFFIXES = (
    '共和国', '王国', '連邦', '半島', '諸島', '海峡', '山脈',
    '神社', '街道', '丁目', '原野',
)

# 一般語にも現れうる短い接尾語。
# 「山」「谷間」のような一般語を巻き込まないよう、
# 3文字以上の語（＝前に固有の部分が付いた形）にだけ適用する。
# 地形・小地名に使われる漢字。これで終わる語は地名の可能性が高い。
# 実機の辞書索引に「アナマ岩」「アボ鼻」「ウノ瀬」「カナデ鼻」等が
# 大量に含まれていた（岬・岩礁・浜の固有名）。
_GEO_TAIL_KANJI = (
    '岩', '鼻', '瀬', '碆', '根', '崎', '岬', '浜', '磯', '礁',
    '滝', '森', '平', '原', '峠', '沢', '谷', '尾', '沼', '池',
    '海', '灘', '湾', '浦', '洲', '嶽', '岳', '峰', '塚', '窪',
    '網', '立神', '場', '前',
)

_SHORT_PLACE_SUFFIXES = (
    '県', '府', '都', '市', '区', '町', '村', '郡',
    '山', '川', '湖', '島', '岬', '峠', '崎', '浜', '沢', '谷',
    '駅', '寺', '城', '港', '橋', '峰', '岳', '街',
)


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

    # 国名・地名パターン（固有名詞判定をすり抜けたものを追加で弾く）
    #
    # 「山」「川」「谷」などの1文字の語尾は、そのままだと
    # 「山」「谷間」のような一般語まで巻き込む。地名として現れるのは
    # 「○○山」「○○川」のように前に固有の部分が付いた形なので、
    # **3文字以上の語**に限って適用する。
    # 「共和国」「山脈」のような、それ自体が地名以外にほぼ使われない
    # 長い接尾語は、語の長さを問わず弾いてよい。
    if surface.endswith(_LONG_PLACE_SUFFIXES):
        return True
    if len(surface) >= 3 and surface.endswith(_SHORT_PLACE_SUFFIXES):
        return True

    # カタカナ語の追加フィルタ
    is_all_kata = all('\u30a1' <= c <= '\u30f6' or c == 'ー' for c in surface)
    if is_all_kata:
        # カタカナ語は略語・専門用語・固有名詞が非常に多いため、
        # 日常語として使う機会の少ない語まで拾わないよう長めの語も除外する。
        # （「イチロー」「デ杯」「ニタリクジラ」等）
        if len(surface) <= 5:
            return True
        # カタカナ固有名詞は除外（外国人名・地名・作品名）
        if sub_pos == '固有名詞':
            return True

    # カタカナ＋漢字の混在は、地名・小地名の可能性が非常に高い。
    #
    # 実機の辞書索引に「アナマ岩」「アボ鼻」「ウノ瀬」「カナデ鼻」の
    # ような語が大量に含まれていた（実機で「岩・鼻などが多く、
    # カタカナ+漢字のものはよく目につく」と報告された）。
    # これらは岬・岩礁・浜の固有名で、日常のメモ書きにはまず現れない。
    #
    # 一方で「コピー機」「メモ帳」「カタカナ表記」のような
    # 実用的な複合語も同じ形をしているため、
    # **地形・地名に使われる漢字で終わる場合だけ**を弾く。
    _has_kata = any('\u30a1' <= c <= '\u30f6' for c in surface)
    _has_kanji = any('\u4e00' <= c <= '\u9fff' for c in surface)
    if _has_kata and _has_kanji and surface.endswith(_GEO_TAIL_KANJI):
        return True

    # 地形を表す漢字で終わる3文字以上の語も、地名の可能性が高い。
    # 「エンロク泣セ岩」のようにカタカナを含まないものも拾う。
    if len(surface) >= 3 and surface.endswith(_GEO_TAIL_KANJI):
        # ただし、その漢字だけで一般語として成立するもの
        # （「火山岩」「石灰岩」等）まで巻き込まないよう、
        # 全部が漢字の語は対象外にする。
        if not all('\u4e00' <= c <= '\u9fff' for c in surface):
            return True

    # 漢字語の追加フィルタ
    is_all_kanji = all('\u4e00' <= c <= '\u9fff' for c in surface)
    if is_all_kanji:
        # 2文字の漢字語でコストがやや高いものは難読語・専門語の可能性が高い
        if len(surface) == 2 and cost > 3500:
            return True

    # 「〇〇事件」「〇〇号」等のパターンは補正には不要
    if surface.endswith(('事件', '事故', '条約', '法案', '法律',
                          '号', '式', '型')):
        if sub_pos == '固有名詞':
            return True

    # コストが高い語（使用頻度が低い）を除外
    if cost > GENERAL_COST_LIMIT:
        return True

    return False


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

    生起コストは「その語の使われやすさ」を表し、小さいほど一般的。
    語彙を絞り込むときの目安に使う。
    """
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
    """extra 側の1件から読み（カタカナ）を取り出す。"""
    for s in _extract_strings(item):
        if s and s != '*' and _is_katakana_word(s):
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

            parts = pos_full.split(',') if pos_full else []
            pos = parts[0] if parts else ''
            sub_pos = parts[1] if len(parts) > 1 else ''
            sub_sub_pos = parts[2] if len(parts) > 2 else ''

            reading = ''
            if extra_data is not None:
                reading = _parse_extra(_get_item(extra_data, key))
            if not reading:
                continue

            yield (surface, katakana_to_hiragana(reading),
                   pos, sub_pos, sub_sub_pos,
                   cost if cost is not None else 99999)


def import_from_janome(store, limit=DEFAULT_MAX_WORDS, min_len=2, max_len=12,
                       progress=None):
    """
    janome の辞書から、日常的に使う語を選んで取り込む。

    固有名詞（地名・人名・川名・岬名など）は原則除外する。
    コストが高い語（＝使用頻度が低い語）も除外する。
    上記フィルタ後、コストの低い順に上位 limit 語を採用する。
    """
    if not HAS_JANOME:
        return 0

    candidates = []
    seen = set()

    for surface, reading, pos, sub_pos, sub_sub_pos, cost in iter_janome_entries(
            min_len, max_len):
        if pos and pos not in IMPORT_POS:
            continue
        if sub_pos in EXCLUDE_SUB_POS:
            continue
        if _should_exclude(surface, pos, sub_pos, sub_sub_pos, cost):
            continue

        key = (reading, surface)
        if key in seen:
            continue
        seen.add(key)
        candidates.append((cost, surface, reading, pos, sub_pos))

        if progress and len(candidates) % 20000 == 0:
            progress(len(candidates))

    # コストが小さい（＝使用頻度が高い）語を優先して採用する
    candidates.sort(key=lambda c: c[0])
    if limit:
        candidates = candidates[:limit]

    added = 0
    for cost, surface, reading, pos, sub_pos in candidates:
        store.add(reading, surface, _guess_category(pos, sub_pos, surface))
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

    for token in t.tokenize(text):
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
            toks = list(t.tokenize(surface))
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
