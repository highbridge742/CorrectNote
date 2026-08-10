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
カタカナ語と英単語の誤字補正（2026-08-10・うにさんの指定）。

これまで **カタカナ語は原則として補正対象外** だった。固有名詞・
俗語・専門語が多く、辞書に無い語を「知らない＝誤字」と扱うと
正しく書いたものを壊すため。英単語に至っては経路そのものが無かった。

うにさんの指定で方針が変わった:

    プセネタリウム（隣接キー）／プネラタリウム（順序）／
    プネタリウム（脱字）／ププラネタリウム（重複）／
    プラニネタリウム（余分な文字）／ぷらねたりうむ（ひらがな）
    …をすべて「プラネタリウム」に直す。これらは一例なので、
    **共通的に判定する**こと。

共通の性質は「長い外来語は、字面がとても特徴的」であること。
7〜8文字の並びのうち1文字違うだけの別語は、まず存在しない。
そこで、かな連続の補正で使っている**キー配置の距離**という
細かい模型はここでは使わず、**素直な編集距離**（挿入・削除・
置換・隣り合う2文字の入れ替え＝ダメラウ）で測る。

    - キー配置の距離は「押し間違えとは考えにくい」組み合わせを
      弾くための仕組み。短いかな語では必要だが、長い外来語では
      かえって取りこぼす（せ→ら は配列上ずっと遠い）。
    - 代わりに**長さで守る**。5文字未満は見ない。直すのは
      **1文字ぶんの違いまで**（allowed_edits の説明を参照）。
    - **迷ったら直さない**。同じ距離の候補が2つ以上あれば手を引く。
    - **形態素解析がすべて既知の語として読めた並びは触らない**
      （ショートカットキー＝ショートカット＋キー のような複合語を
      勝手に縮めないため。corrector.py 側の関門）。

「プラネ１リウム」「プラネタリウ［」のような、かなですらない
文字が紛れた形も、素直な編集距離なら**置換1回**として自然に
拾える（キーの位置に読み替える必要が無い）。

英単語も考え方は同じ。ただし**英単語の辞書は持っていない**ので、
相手は「このアプリが覚えた英単語」だけになる（janome の辞書に
Planetarium のような語は入っていない）。覚えるのは
`learn_english_words` で、ユーザーが正しく書いた語をそのまま拾う。
外部の辞書もモデルも持ち込まない、という設計方針は変えない。
"""

import re

# ------------------------------------------------------------
# 文字種の判定
# ------------------------------------------------------------

# 「ー」（長音）と小書きのカタカナも1文字として数える
_KATAKANA_RE = re.compile('[ァ-ヶー]')

# カタカナの並びに紛れうる「かなではない文字」。
# かな入力で隣のキーを押してしまうと、数字や括弧が入る
# （プラネ１リウム・プラネタリウ［）。全角・半角の両方を見る。
_STRAY_RE = re.compile('[!-~！-～]')


def is_katakana_char(ch):
    return bool(_KATAKANA_RE.match(ch))


def katakana_to_hiragana(text):
    out = []
    for ch in text:
        if 'ァ' <= ch <= 'ヶ':
            out.append(chr(ord(ch) - 0x60))
        else:
            out.append(ch)
    return ''.join(out)


def hiragana_to_katakana(text):
    out = []
    for ch in text:
        if 'ぁ' <= ch <= 'ゖ':
            out.append(chr(ord(ch) + 0x60))
        else:
            out.append(ch)
    return ''.join(out)


def is_all_katakana(text):
    """すべてカタカナ（長音・中黒を含む）か。"""
    if not text:
        return False
    return all(is_katakana_char(c) or c == '・' for c in text)


# ------------------------------------------------------------
# 編集距離（ダメラウ・レーベンシュタイン）
# ------------------------------------------------------------

def edit_distance(a, b, limit=None):
    """
    a を b にするのに必要な操作の回数。

    挿入・削除・置換に加えて、**隣り合う2文字の入れ替え**も
    1回として数える（プネラタリウム＝ら と ね の入れ替え）。

    limit を渡すと、その回数を超えた時点で打ち切って limit + 1 を
    返す（4516 語との総当たりを速くするため）。
    """
    n, m = len(a), len(b)
    if limit is not None and abs(n - m) > limit:
        return limit + 1
    if not n:
        return m
    if not m:
        return n
    prev2 = None
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            v = min(prev[j] + 1,          # 削除
                    cur[j - 1] + 1,       # 挿入
                    prev[j - 1] + cost)   # 置換
            if (i > 1 and j > 1 and prev2 is not None
                    and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]):
                v = min(v, prev2[j - 2] + 1)   # 入れ替え
            cur[j] = v
        if limit is not None and min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[m]


def allowed_edits(length):
    """
    何回まで直してよいか。**常に1回**。

    最初は「8文字以上なら2回」にしていたが、実機のメモで総点検
    （sweep）したところ、2回を許すと正しく書けている語が次々に
    壊れた（2026-08-10）:

        タッチスクリーン → バックスクリーン
        チェックボックス → ブラックボックス
        アンインストール → インストール
        タブショートカット → ショートカット

    外来語は「同じ長さで2文字だけ違う別語」がいくらでもある。
    1回に絞れば、うにさんが挙げた例（隣接キー・順序の入れ替え・
    脱字・重複・余分な1文字）はすべて1回で説明が付くので、
    取りこぼしも起きない。
    """
    return 1


MIN_LENGTH = 5


# ------------------------------------------------------------
# カタカナ語
# ------------------------------------------------------------

def _katakana_vocabulary(store, min_count=2):
    """
    語彙のうち「表記がすべてカタカナ」の語。

    戻り値: {読み: 表記}。同じ読みに複数あれば、使用回数の多いほう。
    結果はストアに控える（語彙の件数が変わったら作り直す）。
    """
    try:
        size = len(store._by_reading)
    except Exception:
        size = -1
    cached = getattr(store, '_katakana_vocab_cache', None)
    if cached is not None and cached[0] == (size, min_count):
        return cached[1]

    out = {}
    best_count = {}
    try:
        entries = store.to_list()
    except Exception:
        entries = []
    for e in entries:
        surface = e.get('surface') or ''
        reading = e.get('reading') or ''
        count = e.get('count', 0)
        if count < min_count or not reading:
            continue
        if not is_all_katakana(surface):
            continue
        if count > best_count.get(reading, -1):
            best_count[reading] = count
            out[reading] = surface
    try:
        store._katakana_vocab_cache = ((size, min_count), out)
    except Exception:
        pass
    return out


def _has_non_katakana_surface(store, reading):
    """その読みに、カタカナ以外の表記も登録されているか。"""
    try:
        for e in store.lookup(reading):
            if not is_all_katakana(e.get('surface') or ''):
                return True
    except Exception:
        return True     # 分からないときは「ある」側に倒して触らない
    return False


def fix_katakana_word(word, store, known_word=False):
    """
    カタカナの並び1つを、語彙にある外来語へ直す。

    word: 元のテキストのままの並び（カタカナ以外が紛れていてもよい）
    known_word: 形態素解析がこの並びを「辞書にある1語」として
        読めたか。読めたなら正しい語なので触らない。

    戻り値: 直した表記（カタカナ）。直さないなら None。
    """
    if known_word or not word:
        return None
    typed = katakana_to_hiragana(word)
    if len(typed) < MIN_LENGTH:
        return None

    vocab = _katakana_vocabulary(store)
    if not vocab:
        return None

    # 読みがそのまま語彙にあるなら、それは正しく書けている。
    # （表記の違い＝ひらがなで書いた場合の直しは、
    #   katakana_for_hiragana の受け持ち。）
    if typed in vocab:
        surface = vocab[typed]
        return surface if surface != word else None

    budget = allowed_edits(len(typed))
    best = None          # (距離, 読み)
    second = None
    _no_bar = typed.replace('ー', '')
    for reading, surface in vocab.items():
        if abs(len(reading) - len(typed)) > budget:
            continue
        # 長音「ー」の有無だけが違う相手は、誤字ではなく**表記のゆれ**。
        # どちらも正しい書き方なので直さない
        # （ダイアログ／ダイアローグ、コンピュータ／コンピューター。
        #   実機のメモで「ダイアログ」が「ダイアローグ」に
        #   書き換えられた・2026-08-10）。
        # かな連続の探索にも同じ考えの関門がある
        # （find_similar_readings の「ーの位置は動かさない」）。
        if reading.replace('ー', '') == _no_bar:
            continue
        d = edit_distance(typed, reading, limit=budget)
        if d > budget:
            continue
        if best is None or d < best[0]:
            second = best
            best = (d, reading)
        elif second is None or d < second[0]:
            second = (d, reading)
    if best is None:
        return None
    # 同じ距離で並んだら、どちらとも決められないので手を引く。
    if second is not None and second[0] == best[0]:
        return None
    surface = vocab[best[1]]
    return surface if surface != word else None


def is_known_compound(parts, store):
    """
    複数の**ユーザーが実際に使っている外来語**がつながった形か。

    「ショートカットキー」＝ショートカット＋キー、
    「タッチスクリーン」＝タッチ＋スクリーン のような複合語を、
    1文字違いの別語に縮めてしまわないための関門
    （実機のメモで縮められた・2026-08-10）。

    **janome の辞書に載っているだけでは根拠にしない。**
    「プラモタリウム」は janome だと プラモ＋タリウム と読めて
    しまうが、どちらもうにさんが使っている語ではない。
    ここでは「語彙ストアに使用実績がある語」だけを数える。
    """
    if len(parts) < 2:
        return False
    vocab = _katakana_vocabulary(store)
    for p in parts:
        if not is_all_katakana(p):
            return False
        if katakana_to_hiragana(p) not in vocab:
            return False
    return True


def katakana_for_hiragana(reading, store, min_length=MIN_LENGTH):
    """
    ひらがなで書かれた外来語を、カタカナの表記に直す。

    「ぷらねたりうむ」→「プラネタリウム」。うにさんの指定
    （カタカナが適した単語はカタカナに補正する）。

    「ひらがなで打たれたものはひらがなのまま」という原則の例外なので、
    根拠が揃ったときだけ行う:
      - 5文字以上（短い語は、たまたま同じ読みの和語がある）。
        min_length で緩められる。**別の関門で既に根拠が揃っている
        場合だけ**（濁点のキーの打ち間違いから完全一致で辿り着いた
        「どらっぐ」など）4文字まで下げてよい。
      - その読みの表記が**カタカナのものしか無い**
        （漢字やひらがなの表記もあるなら、外来語だと言い切れない）
      - 使用回数が2回以上（辞書から取り込んだだけの語に寄せない）

    戻り値: カタカナの表記。直さないなら None。
    """
    if not reading or len(reading) < min_length:
        return None
    if not all('ぁ' <= c <= 'ゖ' or c == 'ー' for c in reading):
        return None
    vocab = _katakana_vocabulary(store)
    surface = vocab.get(reading)
    if not surface:
        return None
    if _has_non_katakana_surface(store, reading):
        return None
    return surface


def is_stray(ch):
    """カタカナの並びに紛れうる「かなではない1文字」か。"""
    return bool(ch) and bool(_STRAY_RE.match(ch))


def find_katakana_runs(line, min_katakana=4):
    """
    カタカナの並びを取り出す。

    紛れてよいのは **カタカナに前後を挟まれた1文字だけ**
    （プラネ１リウム の「１」）。末尾にくっついた文字は含めない。

    以前は末尾の1文字も含めていたが、実機のメモで総点検したところ、
    日本語の文に普通に出てくる区切り文字を巻き込んで消していた
    （2026-08-10）:

        （東京上野キャンパス） → 閉じ括弧が消える
        ファイル/編集         → スラッシュが消える
        文脈ベクトル=0.02s    → 等号が消える
        カタカナ+漢字         → プラスが消える

    「プラネタリウ［」のように**末尾に紛れた形**は、
    呼び出し側が「その1文字を除いた部分が既に正しい語かどうか」を
    確かめたうえで、改めて1文字足して試す（corrector.py）。
    キャンパス は正しい語なので触られず、プラネタリウ は
    正しい語ではないので直る、という切り分けになる。

    戻り値: [(開始, 終了, 並び), ...]
    """
    runs = []
    n = len(line)
    i = 0
    while i < n:
        if not is_katakana_char(line[i]):
            i += 1
            continue
        j = i
        strays = 0
        while j < n:
            ch = line[j]
            if is_katakana_char(ch):
                j += 1
                continue
            # 紛れた1文字は、**次の文字もカタカナ**のときだけ認める
            if (strays == 0 and is_stray(ch)
                    and j + 1 < n and is_katakana_char(line[j + 1])):
                strays += 1
                j += 1
                continue
            break
        run = line[i:j]
        if sum(1 for c in run if is_katakana_char(c)) >= min_katakana:
            runs.append((i, j, run))
        i = max(j, i + 1)
    return runs


def is_known_katakana(word, store):
    """その並びが、そのまま語彙にある外来語か（＝正しく書けている）。"""
    if not word:
        return False
    return katakana_to_hiragana(word) in _katakana_vocabulary(store)


# ------------------------------------------------------------
# 英単語
# ------------------------------------------------------------

# 英単語として覚える・直す対象。数字混じり（Python3・v1）は
# 対象にしない（版番号や識別子は誤字ではないため）。
_ENGLISH_RE = re.compile(r'[A-Za-z]+')

# 英単語であることを示す読みの前置き。
# 語彙ストアは「読み→表記」の入れ物なので、英単語も同じ形で
# 入れる。かなの読みと混ざらないよう、前置きを付けて区別する。
ENGLISH_PREFIX = 'en:'

# 英単語を覚える・直すときの最短の長さ。
# 短い語は「1文字違いの別の語」が多すぎる（form/from・there/three）。
# うにさんの例（Planetarium 系）は10文字以上なので、
# 安全側に倒して6文字からにする。
MIN_ENGLISH_LENGTH = 6


def english_reading(word):
    """英単語を語彙ストアに入れるときの読み（小文字に揃える）。"""
    return ENGLISH_PREFIX + word.lower()


def learn_english_words(text, store, category='英語'):
    """
    文章に出てくる英単語を覚える。

    **英単語の辞書は持っていない**ので、直す相手は「ユーザーが
    正しく書いた語」だけになる。外部の辞書やモデルを持ち込まない
    という方針のため、ここは避けられない。裏を返せば、一度でも
    正しく書いた語はそれ以降ずっと直せるようになる。

    覚えるのは5文字以上の英字だけの並び。数字や記号が混ざったもの
    （Python3・v1.0・md5）は、誤字ではなく識別子のことが多いので
    覚えない。

    戻り値: 覚えた語の数
    """
    if not text:
        return 0
    added = 0
    for m in _ENGLISH_RE.finditer(text):
        word = m.group(0)
        if len(word) < MIN_ENGLISH_LENGTH:
            continue
        # 前後に数字や記号がくっついている（Python3・utf8）なら
        # 識別子とみなして覚えない
        s, e = m.start(), m.end()
        if s > 0 and (text[s - 1].isdigit() or text[s - 1] in '._-@/'):
            continue
        if e < len(text) and (text[e].isdigit() or text[e] in '._-@/'):
            continue
        # **打ち間違いを覚えない。**
        # 覚えてしまうと「知っている語＝正しい」と見なして
        # 二度と直せなくなる（実機で Pplanetarium が覚えられ、
        # Planetarium に直らなくなった・2026-08-10）。
        # 既に知っている語の1文字違いなら、それは誤字なので覚えない。
        # 日本語側の「誤変換語を覚えない」（学び2）と同じ考え方。
        try:
            if fix_english_word(word, store):
                continue
        except Exception:
            pass
        try:
            store.add(english_reading(word), word, category)
            added += 1
        except Exception:
            pass
    return added


def relearn_english_from_texts(texts, store):
    """
    メモ全文から英単語を覚え直す（起動時に一度）。

    **多く書かれている形から先に覚える。** 少ないほうは
    「多いほうの打ち間違い」として自動的に弾かれる
    （learn_english_words の中の関門）。順番に頼らない形にして
    おかないと、誤字がメモの先に出てきた場合に誤字のほうを
    覚えてしまう。

    覚え直す前に、**覚えている英単語をいったん全部捨てる**。
    ここが自己修復になっている: 以前の版は誤字も覚えてしまって
    いたので、そのまま残すと「知っている語＝正しい」と見なされて
    永遠に直らない（実機で Pplanetarium が直らなかった・
    2026-08-10）。使用回数の少ないものだけを捨てる形も試したが、
    誤字が2回以上覚えられていると残ってしまい、直らないままだった。

    全部捨ててよいのは、**英単語の記録がメモから作り直せる**から。
    かなの語彙と違って、外から取り込んだ辞書も、長い時間をかけて
    育てた実績も持っていない（持ちようがない）。捨てて拾い直す
    ほうが、汚れが残るより確実。

    戻り値: 覚えた語の数
    """
    from collections import Counter
    counts = Counter()
    for text in texts:
        if not text:
            continue
        for m in _ENGLISH_RE.finditer(text):
            word = m.group(0)
            if len(word) < MIN_ENGLISH_LENGTH:
                continue
            s, e = m.start(), m.end()
            if s > 0 and (text[s - 1].isdigit() or text[s - 1] in '._-@/'):
                continue
            if e < len(text) and (text[e].isdigit() or text[e] in '._-@/'):
                continue
            counts[word] += 1

    # 覚えている英単語をいったん全部捨てる（上の説明を参照）
    try:
        stale = [e for e in store.to_list()
                 if (e.get('reading') or '').startswith(ENGLISH_PREFIX)]
        for e in stale:
            store.remove(e['reading'], e['surface'])
    except Exception:
        pass
    try:
        store._english_vocab_cache = None
    except Exception:
        pass

    added = 0
    for word, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        try:
            if fix_english_word(word, store):
                continue
        except Exception:
            pass
        try:
            store.add(english_reading(word), word, '英語')
            store._english_vocab_cache = None
            added += 1
        except Exception:
            pass
    return added


def _english_vocabulary(store, min_count=1):
    """
    覚えている英単語。戻り値: {小文字の語: 表記}

    同じ語を大文字小文字ちがいで覚えていたら、使用回数の多いほうを
    採る（Planetarium と planetarium が両方あるとき）。
    """
    try:
        size = len(store._by_reading)
    except Exception:
        size = -1
    cached = getattr(store, '_english_vocab_cache', None)
    if cached is not None and cached[0] == (size, min_count):
        return cached[1]

    out = {}
    best = {}
    try:
        entries = store.to_list()
    except Exception:
        entries = []
    for e in entries:
        reading = e.get('reading') or ''
        if not reading.startswith(ENGLISH_PREFIX):
            continue
        if e.get('count', 0) < min_count:
            continue
        key = reading[len(ENGLISH_PREFIX):]
        if e.get('count', 0) > best.get(key, -1):
            best[key] = e.get('count', 0)
            out[key] = e.get('surface') or ''
    try:
        store._english_vocab_cache = ((size, min_count), out)
    except Exception:
        pass
    return out


def _english_count(store, key):
    """その英単語を何回書いたか（覚えていなければ 0）。"""
    try:
        return max((e.get('count', 0)
                    for e in store.lookup(ENGLISH_PREFIX + key)),
                   default=0)
    except Exception:
        return 0


def fix_english_word(word, store):
    """
    英単語1つを、覚えている語へ直す。

    カタカナ語と同じ考え方（素直な編集距離・長さで守る・
    迷ったら直さない）。大文字小文字の違いは誤字と見なさない
    （小文字に揃えてから比べ、直すときは覚えている表記を使う）。

    戻り値: 直した表記。直さないなら None。
    """
    if not word or len(word) < MIN_ENGLISH_LENGTH:
        return None
    if not word.isalpha():
        return None
    vocab = _english_vocabulary(store)
    if not vocab:
        return None
    key = word.lower()
    own = _english_count(store, key)
    if own >= 2:
        return None         # 何度も書いている語＝正しい
    # 一度しか見ていない語は、**もっとよく書いている1文字違いの語**が
    # あれば、そちらの打ち間違いとみなす。誤字を先に覚えてしまった
    # ときの逃げ道（覚える側でも弾いているが、順番によっては
    # 誤字のほうが先に入りうる）。
    _override = own == 1

    budget = allowed_edits(len(key))
    best = None
    second = None
    for known, surface in vocab.items():
        if known == key:
            continue
        if abs(len(known) - len(key)) > budget:
            continue
        if _override and _english_count(store, known) < 3:
            continue        # 「よく書いている語」だけが上書きできる
        d = edit_distance(key, known, limit=budget)
        if d > budget:
            continue
        if best is None or d < best[0]:
            second = best
            best = (d, known)
        elif second is None or d < second[0]:
            second = (d, known)
    if best is None:
        return None
    if second is not None and second[0] == best[0]:
        return None
    surface = vocab[best[1]]
    return surface if surface != word else None


def find_english_runs(line, min_len=MIN_ENGLISH_LENGTH):
    """
    英字だけの並びを取り出す。

    前後に数字や記号（. _ - @ /）がくっついているものは、
    識別子・版番号・URL とみなして対象にしない。

    戻り値: [(開始, 終了, 並び), ...]
    """
    runs = []
    for m in _ENGLISH_RE.finditer(line):
        word = m.group(0)
        if len(word) < min_len:
            continue
        s, e = m.start(), m.end()
        if s > 0 and (line[s - 1].isdigit() or line[s - 1] in '._-@/'):
            continue
        if e < len(line) and (line[e].isdigit() or line[e] in '._-@/'):
            continue
        runs.append((s, e, word))
    return runs
