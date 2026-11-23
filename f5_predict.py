# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""F5 の予測（2026-11-20 うにさん「F5の再変換を、カーソルの右側に文字がない時に実行すると、今は1つ前の単語を選択するが、
変更して、次に続く文字の候補を出す。この状態から再度F5を押したり、左キーを押せば左の単語がフォーカスされ、これまでと
同じ挙動をする。行頭まで遡った次はその前の行末を選ぶのもそのまま。一度範囲を動かしたら、予告の候補には切り替わらない。
一度再変換を閉じてまたひらけば予測は出る。」）。

枠組み（app.py の _f5_predict_open など）:
・本文・簡易入力で、カーソルの右（その行）に字が無い所で F5 を開くと「予測の状態」で開く（範囲は空・カーソルの位置）
・予測の状態から F5・左キー → 左の語（今の動き）。右キーは何もしない。一度範囲を動かしたら予測へは戻らない
・候補を選ぶと、カーソルの位置へその字を入れる（Undo 1回）。候補が無ければ今までどおり左の語

候補（2026-11-20 13:55Z・13:57Z うにさんの仕様）:
1. 文末になりそうな所（前が述語の終わり。形態素で見る）: ！ ？ ！？ … 、 。（タブに2バイトの字が無ければ ! ? !? ... .）。
   その行で開いたまま閉じていない括弧・引用符があれば、その閉じを先頭に
2. 行頭: 見出しの字（◆ ■ ● ▼ ※ 【 ・。2バイトの字が無いタブでは # * > + -）
3. 接続詞になりそうな所（文の終わり 。！？ の後・読点の後）: 前の文（前の行にあってもよい）から使えそうな接続詞
4. それ以外: 前の2字から次の1字を予測（同梱の文字3連 ngram_ja.TRIGRAMS・このアプリの文書から数えた表）し、上位7字まで、
   それぞれその字で始まる続き（同じ表で数字ずつ伸ばした短い句）
   ・IME の予測（確定せずに問い合わせる口）は、このアプリの IME の部品（IFELanguage）に無いので使っていない
記号の並べ方: 決めた並びのまま（2026-11-21 うにさん「自動で並べ替えはしないので、ボタンと判定は不要です」）。前は
日本語キーボードで打つ手間の多い順（EFFORT の表）に並べ替え、デバッグの窓に表を見るボタンがあった。今の並びは、その
手間の順で並べた形を既定の並びとして書いたもの（見える並びは変わらない。同じ手間の時に「このタブで使っている字を先に」
する判定は無くなった）。CN_F5_FIXED_ORDER=0 で前の形（手間で並べ替え・デバッグの窓のボタン）。
個人のファイル（charngram.json など）は読まない。CN_F5_PREDICT=0 で前の形。
"""
import os
import re

_PROVIDER = None

# 日本語キーボード（かな入力・ローマ字入力の IME）で打つ手間。大きいほど手間が多い＝候補の前へ。
#   1: 1キーで出る　2: Shift が要る　3: 変換が要る（短い読み）　4: 変換が要る（長い読み）・2字以上を Shift で
EFFORT = {
    # 文末（全角）
    '！': 2, '？': 2, '！？': 4, '…': 4, '、': 1, '。': 1,
    # 文末（半角）
    '!': 2, '?': 2, '!?': 4, '...': 3, '.': 1,
    # 閉じ（開いたまま閉じていない時だけ・いつも先頭）
    '」': 1, '』': 3, '）': 2, ')': 2, '"': 2, "'": 2, '】': 3, '］': 3, ']': 1,
    # 見出し（全角）
    '◆': 4, '■': 4, '●': 4, '▼': 4, '※': 3, '【': 3, '・': 1,
    # 見出し（半角）
    '#': 2, '*': 2, '>': 2, '+': 2, '-': 1,
}
# 文末（全角あり）の既定の並び（2026-11-20 15:30Z うにさんの指定: ！ ？ !? … 、 。・!? は半角の2字）。手間の点数で並べ替えず、
# この順のまま使う（ほかの組は手間の多い順）。CN_F5_END_ORDER=0 で前の形（全角の ！？・手間の順）
END_WIDE = ('！', '？', '!?', '…', '、', '。')
END_WIDE_OLD = ('！', '？', '！？', '…', '、', '。')
# 文末（全角あり）の既定（2026-11-21 14:26Z うにさん「文末のデフォルトを、画像の並びにする」・最後は「半角が前後にある」矢印）。
# ？ ！ … ～ !? 、 。 → ⇒ ␣⇒␣（半角空白＋⇒＋半角空白）。自分で並べた一覧（設定の f5_predict_lists）はそのまま
# （既定と同じ並びは設定に残さないので、保存が無い時と「戻す」の時にこの並びになる）。CN_F5_TAIL_DEFAULT2=0 で前の既定（END_WIDE）
# 文末（半角だけ）も（14:30Z うにさん「半角はこう。ピリオドの下はカンマ」）: ? ! !? ... . , & //。三点は今までの既定と
# 同じ字（半角のピリオド3つ '...'）のまま。CN_F5_TAIL_DEFAULT2=0 で前の既定（END_NARROW）
END_NARROW2 = ('?', '!', '!?', '...', '.', ',', '&', '//')
END_WIDE2 = ('？', '！', '…', '～', '!?', '、', '。', '→', '⇒', ' ⇒ ')
FIXED_ORDER = ('end_wide', 'head_wide')
END_NARROW = ('!?', '...', '!', '?', '.')          # 手間の順で並べた形（前は ('!', '?', '!?', '...', '.') を並べ替えていた）
# 行頭（全角あり）の既定の並び（2026-11-20 16:44Z うにさん「行頭の候補を画像のもので並べる」）。全角空白＋罫線の
# 3つ（└ ├ は細い罫線 U+2514・U+251C）は、箇条書きの下の段を打つ時のもの。手間の点数で並べ替えず、この順のまま使う。
# CN_F5_HEAD_ORDER=0 で前の形（◆ ■ ● ▼ ※ 【 ・ を手間の順・このタブで使っている字を先に）
# 2026-11-21 01:55Z うにさん「行頭カスタムのデフォルトを画像のものに変更」: ・ ※ ◆ ■ >（半角） ＞（全角） ○ ● ▼ と
# 罫線3つ（前と同じ 全角空白＋└・全角空白2つ＋└・全角空白＋├）。CN_F5_HEAD_DEFAULT2=0 で前の並び（HEAD_WIDE_1120）
HEAD_WIDE = ('・', '※', '◆', '■', '>', '＞', '○', '●', '▼', '\u3000└', '\u3000\u3000└', '\u3000├')
HEAD_WIDE_1120 = ('・', '※', '◆', '■', '●', '▼', '\u3000└', '\u3000\u3000└', '\u3000├')
HEAD_WIDE_OLD = ('◆', '■', '●', '▼', '※', '【', '・')
HEAD_NARROW = ('#', '*', '>', '+', '-')
CLOSERS = (('「', '」'), ('『', '』'), ('（', '）'), ('(', ')'), ('【', '】'), ('［', '］'), ('[', ']'))
QUOTES = ('"', "'")
NEXT_CHARS = 7          # 前の2字から出す次の字の数（うにさん「上位7つまで」）
PHRASE_MAX = 12         # 続きの句を伸ばす上限（字）。そのあと語の切れ目で切る

CONJ_DEFAULT = ('しかし', 'そして', 'また', 'ただし', 'つまり', 'なお', 'さらに', 'ところで', 'だから', '例えば')
CONJ_AFTER_COMMA = ('そして', 'しかし', 'また', 'つまり', 'ただし')


def enabled(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_F5_PREDICT') != '0'


def set_provider(fn):
    """候補を出す手続きを差し替える。fn(app, widget, row, col, before) → 候補の字の並び。None で既定（predict）に戻す。"""
    global _PROVIDER
    _PROVIDER = fn


def candidates(app, widget, row, col, before):
    fn = _PROVIDER or predict
    try:
        app._f5_custom_items = None         # 行頭・文末の候補（カスタム）の並び。predict が決める（回り込みの的）
        app._f5_close_items = None          # 閉じ括弧（記号だけでも自動の一覧から落とさない）
    except Exception:
        pass
    try:
        got = fn(app, widget, row, col, before) or ()
    except Exception:
        return []
    return [str(c) for c in dict.fromkeys(got) if c]


def at_line_start(widget):
    """カーソルが行頭か（右に字があっても行頭なら行頭の候補・2026-11-20 14:21Z うにさん）。"""
    try:
        return widget.get('insert linestart', 'insert') == ''
    except Exception:
        return False


def opens_here(widget):
    """予測で開く所: カーソルの右（その行）に字が無いか、カーソルが行頭。"""
    return right_is_empty(widget) or at_line_start(widget)


def right_is_empty(widget):
    """カーソルの右（その行の終わりまで）に字が無いか。"""
    try:
        return widget.get('insert', 'insert lineend') == ''
    except Exception:
        return False


# --- 行頭・文末の候補のカスタム（2026-11-20 14:21Z うにさん「オプションに行頭の候補をカスタム、文末の候補をカスタムを追加し、
# 別ウインドウで候補を編集可能とします。並べ替えもできる」）。設定 f5_predict_lists に {名前: [字]}。無ければ既定の並び
LIST_NAMES = ('head_wide', 'head_narrow', 'end_wide', 'end_narrow')
LIST_LABELS = {'head_wide': '行頭（全角あり）', 'head_narrow': '行頭（半角だけ）',
               'end_wide': '文末（全角あり）', 'end_narrow': '文末（半角だけ）'}
# カスタム候補は、出す時の IME の形で選ぶ（2026-11-21 16:52Z うにさん「予測カスタムは、IMEが全角モードの時は全角用のものを
# 出し、半角モードの時は半角のものを出すようにする。カスタム編集は、上のボタンを「全角時」「半角時」という名称に変える」）。
# 前はタブの字に全角があるかで選んでいた（has_wide）。IME の形が分からない時（Windows 以外など）は前の選び方。
# CN_PREDICT_CUSTOM_BY_IME=0 で前の形（ボタンの名前も前の形）
LIST_LABELS_BY_IME = {'head_wide': '全角時', 'head_narrow': '半角時', 'end_wide': '全角時', 'end_narrow': '半角時'}


def by_ime_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_PREDICT_CUSTOM_BY_IME') != '0'


def list_label(name):
    return (LIST_LABELS_BY_IME if by_ime_on() else LIST_LABELS)[name]


def wide_for(widget, whole):
    """全角の一覧を使うか: IME が全角で打つ形なら全角の一覧。分からなければタブの字に全角があるか（前の形）。"""
    if by_ime_on():
        try:
            import ime_watch
            got = ime_watch.wide_input(int(widget.winfo_id()))
        except Exception:
            got = None
        if got is not None:
            return got
    return has_wide(whole)


def fixed_order(environ=None):
    """既定の並びを手間で並べ替えない（2026-11-21）。CN_F5_FIXED_ORDER=0 で前の形。"""
    environ = os.environ if environ is None else environ
    return environ.get('CN_F5_FIXED_ORDER') != '0'


def head_order_new(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_F5_HEAD_ORDER') != '0'


def default_list(name):
    if name == 'end_wide' and os.environ.get('CN_F5_END_ORDER') == '0':
        return by_effort(list(END_WIDE_OLD))
    if name == 'head_wide' and not head_order_new():
        return by_effort(list(HEAD_WIDE_OLD))
    if name == 'head_wide' and os.environ.get('CN_F5_HEAD_DEFAULT2') == '0':
        return list(HEAD_WIDE_1120)
    tail2 = os.environ.get('CN_F5_TAIL_DEFAULT2') != '0'
    items = list({'head_wide': HEAD_WIDE, 'head_narrow': HEAD_NARROW,
                  'end_wide': END_WIDE2 if tail2 else END_WIDE,
                  'end_narrow': END_NARROW2 if tail2 else END_NARROW}[name])
    if tail2 and name == 'end_narrow':
        return items                      # 決めた並びのまま（14:30Z・手間の順に並べ替えない）
    return items if (name in FIXED_ORDER or fixed_order()) else by_effort(items)


def custom_list(app, name):
    """利用者が並べた候補（設定）。無い・空なら None。CN_F5_CUSTOM=0 で使わない。"""
    if os.environ.get('CN_F5_CUSTOM') == '0':
        return None
    try:
        lists = app.settings.get('f5_predict_lists') or {}
    except Exception:
        return None
    got = lists.get(name) if isinstance(lists, dict) else None
    got = [str(x) for x in got or () if isinstance(x, str) and x]
    return got or None


def by_effort(items, used=()):
    """打つ手間の多い順（EFFORT）。同じ手間なら、このタブで使っている字を先に、それも同じなら元の並び。"""
    used = list(used)
    return sorted(items, key=lambda c: (-EFFORT.get(c, 2), used.index(c) if c in used else len(used), items.index(c)))


def effort_text():
    """デバッグの窓に出す表。"""
    lines = ['F5 予測の記号の並べ方（日本語キーボードで打つ手間・大きいほど前）',
             '  1: 1キー　2: Shift が要る　3: 変換（短い読み）　4: 変換（長い読み）・2字以上を Shift で', '']
    for name, group in (('文末（全角）', END_WIDE), ('文末（半角）', END_NARROW), ('見出し（全角）', HEAD_WIDE),
                        ('見出し（半角）', HEAD_NARROW), ('閉じ（開いたままの時だけ・先頭）', tuple(c for _o, c in CLOSERS) + QUOTES)):
        shown = (default_list('end_wide') if group is END_WIDE else default_list('head_wide') if group is HEAD_WIDE
                 else by_effort(list(group)))     # 全角の文末・行頭は決めた順のまま
        lines.append('%s: %s' % (name, '  '.join('%s=%d' % (c, EFFORT.get(c, 2)) for c in shown)))
    return '\n'.join(lines)


# --- 場合を見分ける ----------------------------------------------------------------
# 予測で本文を読むのはカーソルの行の上下 AROUND_ROWS 行まで（2026-11-22 03:13Z うにさん「予測変換の名詞の数は、上下何行の
# 範囲から取っている？もし全体を見ているなら範囲を絞る」）。名詞は前から上下40行。前の文（previous_sentence）と、全角・半角の
# 一覧を選ぶ時の「タブに全角の字があるか」（IME の形が分からない時だけ使う）はタブ全体を読んでいた。CN_PREDICT_NEAR_ROWS=0 で前の形
def _near_on():
    return os.environ.get('CN_PREDICT_NEAR_ROWS') != '0'


def _near_start(widget, row=None):
    if not _near_on():
        return '1.0'
    if row is None:
        row = int(str(widget.index('insert')).split('.')[0])
    return '%d.0' % max(1, row - AROUND_ROWS)


def _near_end(widget, row):
    if not _near_on():
        return 'end-1c'
    return '%d.end' % (row + AROUND_ROWS)


def has_wide(text):
    """2バイトの字（ASCII の外の字）が1つでもあるか。"""
    return any(ord(ch) > 0x7f for ch in text or '')


_END_WORDS = ('です', 'ます', 'ました', 'でした', 'ません', 'ませんでした', 'た', 'だ', 'だった', 'ない', 'なかった',
              'でしょう', 'ましょう', 'よう', 'う', 'ね', 'よ', 'な', 'か', 'わ', 'ぞ', 'さ')


def ends_like_sentence(before):
    """前が述語の終わり（終止形・です/ます/た・終助詞）らしいか。形態素で見る。"""
    text = (before or '').rstrip()
    if not text or text[-1] in '。．.！？!?…、，,':
        return False
    try:
        from morphology import tokenize
        tokens = [t for t in tokenize(text) if (t.surface or '').strip()]
    except Exception:
        tokens = []
    if not tokens:
        return text.endswith(('です', 'ます', 'ました', 'でした', 'ません'))
    t = tokens[-1]
    pos, sub, form = t.pos or '', t.pos_sub or '', t.infl_form or ''
    if pos == '助詞':
        return sub.startswith('終助詞')
    if pos == '助動詞':
        return form.startswith('基本形') or t.surface in _END_WORDS
    if pos in ('動詞', '形容詞'):
        return form.startswith('基本形')
    return False


# 閉じ括弧を先頭に（2026-11-21 17:16Z うにさん「予測候補に閉じる括弧を先頭に出すと書いているが、出てこない。文の途中でも
# 文末でも、カーソルの右に文字がない時は閉じる括弧の候補を出す。これは前の行から続くものでも候補に出す。なので、行の末尾に
# 閉じる括弧がなくても、下の行で閉じている可能性もある。それも気を付ける」）。前は文末の時だけ・その行だけ・全角は全角の一覧の
# 時だけで、行の末尾の自動の候補では記号だけの項目として落ちていた。
# ・カーソルの右に字が無い時、どの候補の一覧（F5・行の末尾の自動・続けて出す予測・行頭）でも、開いたままの括弧の閉じを先頭に
#   （内側から外へ）
# ・開いた括弧は、上の行から数える（空の行まで・CLOSE_SCAN_ROWS 行まで）。カーソルより後（その行の右・下の行。同じく空の行まで・
#   CLOSE_SCAN_ROWS 行まで）で閉じているものは除く（入れ子は内側から対にする）
# CN_PREDICT_CLOSE_BRACKET=0 で前の形
CLOSE_PAIRS = CLOSERS + (('〔', '〕'), ('｛', '｝'), ('{', '}'), ('〈', '〉'), ('《', '》'), ('＜', '＞'), ('“', '”'),
                         # 2026-11-22 01:43Z うにさん「これの閉じる括弧に対応する」: < ≪ ‘ 〝（〝 は 〟 で閉じる・〞 も閉じに数える）
                         ('<', '>'), ('≪', '≫'), ('‘', '’'), ('〝', '〟'),
                         # 01:50Z うにさん「`'この2つが対になります」: ` を開き・' を閉じ（`…' の形）
                         ('`', "'"))
CLOSE_EXTRA = {'〞': '〝'}              # 対の閉じのほかに、閉じとして数える字
# ' は英語の it's などにも出るので、カーソルより左では閉じとして数えない（カーソルより後に ' があれば閉じているとだけ見る）
CLOSE_LEFT_SKIP = ("'",)
# 開きと閉じが同じ字（"）: カーソルより左（上の行から・同じ範囲）にある数が奇数で、カーソルより後にその字が無い時だけ閉じに
CLOSE_SAME = ('"',)
CLOSE_SCAN_ROWS = 40


def _opens_here(text, i):
    """text[i] を開きと見るか。半角の < は比べる記号（a < b・x<3）にも使うので、直後が空白や数字なら開きと見ない。"""
    if text[i] != '<':
        return True
    nxt = text[i + 1:i + 2]
    return not (nxt and (nxt.isspace() or nxt.isdigit()))


def close_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_PREDICT_CLOSE_BRACKET') != '0'


def _rows_until_blank(lines):
    out = []
    for line in lines:
        if not line.strip():
            break
        out.append(line)
    return out


def close_brackets(widget, before):
    """開いたままの括弧の閉じ（内側から外へ）。上の行から続くものも数え、カーソルより後で閉じているものは除く。"""
    opens = dict(CLOSE_PAIRS)
    closes = {c: o for o, c in CLOSE_PAIRS}
    closes.update(CLOSE_EXTRA)
    try:
        row = int(str(widget.index('insert')).split('.')[0])
        lo = max(1, row - CLOSE_SCAN_ROWS)
        above = str(widget.get('%d.0' % lo, '%d.0' % row)).split('\n')[:-1] if row > 1 else []
        last = int(str(widget.index('end-1c')).split('.')[0])
        hi = min(last, row + CLOSE_SCAN_ROWS)
        right = str(widget.get('insert', 'insert lineend'))
        below = str(widget.get('%d.0' % (row + 1), '%d.end' % hi)).split('\n') if row < last else []
    except Exception:
        above, right, below = [], '', []
    text = '\n'.join(reversed(_rows_until_blank(list(reversed(above)))))
    text = (text + '\n' if text else '') + (before or '')
    stack = []
    for i, ch in enumerate(text):
        if ch in opens and _opens_here(text, i):
            stack.append(ch)
        elif ch in closes and ch not in CLOSE_LEFT_SKIP:
            o = closes[ch]
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == o:
                    del stack[i]
                    break
    after = right + '\n' + '\n'.join(_rows_until_blank(below))
    same = [q for q in CLOSE_SAME if text.count(q) % 2 == 1 and q not in after]
    if not stack:
        return same
    later = []
    for i, ch in enumerate(after):
        if ch in opens and _opens_here(after, i):
            later.append(ch)
        elif ch in closes:
            o = closes[ch]
            if later and later[-1] == o:
                later.pop()
                continue
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == o:
                    del stack[i]                 # 下で閉じている
                    break
    return list(dict.fromkeys(same + [opens[o] for o in reversed(stack)]))


def unclosed(before):
    """その行で開いたまま閉じていない括弧・引用符の閉じ（内側から外へ）。"""
    stack = []
    pairs = dict(CLOSERS)
    closes = {c: o for o, c in CLOSERS}
    for ch in before or '':
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in closes and stack and stack[-1] == ch:
            stack.pop()
    out = list(reversed(stack))
    for q in QUOTES:
        if q == "'" and close_on():
            continue                      # ' は開きに数えない（it's など・01:50Z うにさん。` の閉じは close_brackets）
        if (before or '').count(q) % 2 == 1:
            out.insert(0, q)
    return out


def previous_sentence(widget, before):
    """カーソルの前の、1つ前の文（前の行にあってもよい・改行は文の途中で入る）。"""
    try:
        text = widget.get(_near_start(widget), 'insert')
    except Exception:
        text = before or ''
    text = text.rstrip()
    if text.endswith(('。', '！', '？', '!', '?', '．')):
        body = text[:-1]
    else:
        body = text
    cut = max(body.rfind(c) for c in '。！？!?．')
    return text[cut + 1:].replace('\n', '').strip()


def conjunctions(widget, before):
    """前の文の中身から使えそうな接続詞（並べ方は日本語としての尤もらしさで決めた・2026-11-20 判断）。"""
    tail = (before or '').rstrip()
    if tail.endswith(('、', '，', ',')):
        return list(CONJ_AFTER_COMMA)
    prev = previous_sentence(widget, before)
    first = []
    if prev.endswith(('？', '?')) or re.search(r'(ですか|ますか|のか|だろうか)[。]?$', prev):
        first += ['では', 'それとも', 'つまり', 'なぜなら']
    if re.search(r'(ので|から|ため)', prev):
        first += ['だから', 'そのため', 'したがって']
    if re.search(r'(たい|予定|つもり|しよう|ましょう)', prev):
        first += ['そこで', 'そのため', 'しかし']
    if re.search(r'(ない|ません|なかった|ませんでした)', prev):
        first += ['しかし', 'ところが', 'それでも']
    if re.search(r'(例|など|たとえ)', prev):
        first += ['例えば', 'つまり']
    return list(dict.fromkeys(first + list(CONJ_DEFAULT)))[:7]


# --- 前の2字から次の字 --------------------------------------------------------------
_NEXT = None
_NEXT1 = None


def _next_table():
    """前の2字 → [(回数, 次の字)]（多い順）。同梱の ngram_ja.TRIGRAMS から一度だけ作る（前の1字だけの表も）。"""
    global _NEXT, _NEXT1
    if _NEXT is None:
        try:
            from ngram_ja import TRIGRAMS
        except Exception:
            TRIGRAMS = {}
        table, one = {}, {}
        for tri, n in TRIGRAMS.items():
            if len(tri) == 3 and tri[2] not in '^$':
                table.setdefault(tri[:2], []).append((n, tri[2]))
                if tri[1] != '^':
                    got = one.setdefault(tri[1], {})
                    got[tri[2]] = got.get(tri[2], 0) + n
        for v in table.values():
            v.sort(key=lambda x: -x[0])
        _NEXT1 = {k: sorted(((n, c) for c, n in v.items()), key=lambda x: -x[0]) for k, v in one.items()}
        _NEXT = table
    return _NEXT


def _options(text):
    """次の字の候補（前の2字の表。無ければ前の1字の表）。"""
    got = _next_table().get(_key2(text))
    if not got and text:
        got = (_NEXT1 or {}).get(text[-1])
    return got or ()


def _key2(text):
    text = (text or '')[-2:]
    return '^' * (2 - len(text)) + text


def next_chars(before, limit=NEXT_CHARS):
    return [c for _n, c in _options(before)[:limit]]


def phrase(before, first, limit=PHRASE_MAX):
    """first で始まる続き: 同じ表でいちばん多い次の字を足していく（句読点で止める・同じ3連は二度使わない）。"""
    out = first
    seen = set()
    while len(out) < limit and out[-1] not in '。、！？':
        key = _key2(before + out)
        if key in seen:
            break
        seen.add(key)
        options = _options(before + out)
        if not options:
            break
        out += options[0][1]
    return _cut_at_word(out)


def _cut_at_word(text):
    """伸ばした句を語の切れ目で切る（最後の語は途中で切れていることが多いので落とす。句読点で終わればそのまま）。"""
    if not text or text[-1] in '。、！？':
        return text
    try:
        from morphology import tokenize
        ends = [t.end for t in tokenize(text)]
    except Exception:
        return text
    keep = [e for e in ends[:-1] if e > 0]
    return text[:keep[-1]] if keep else text


# --- IME の予測（2026-11-20 14:21Z うにさん「直前の文字をタイピングしたとして、IMEはその先の予測を出しています。それを
# 並べられませんか？また、２文字の次の確率の高い1もじをタイピングするとIMEは予測を出してきます。それも気になる」）。
# Windows の TSF の検索候補（ITfFnSearchCandidateProvider・ime_candidates.SearchCandidates）に読みを問い合わせる。読みを
# 打つ・確定する・キーを送ることはしない（問い合わせだけ。IME の学習にも残らない）。取れなければ表の候補。CN_F5_IME=0 で使わない
IME_EACH = 7
IME_MAX_LEN = 16       # 候補1つの長さの上限（字）
IME_TOTAL = 14         # (a)・(b) を合わせた数の上限


def _hira(text):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in text or '')


def _ime_query(reading):
    from ime_candidates import SearchCandidates
    with SearchCandidates() as search:
        if not getattr(search, 'available', False):
            return None
        return list(search.candidates(reading) or ())


class _OneSession:
    """F5 1回の問い合わせを、TSF の検索候補の1つの接続で済ませる（開くのに数十 ms かかる）。"""
    def __enter__(self):
        from ime_candidates import SearchCandidates
        self._search = SearchCandidates()
        self._inner = self._search.__enter__()
        return self

    def __exit__(self, *exc):
        return self._search.__exit__(*exc)

    def __call__(self, reading):
        search = self._inner
        if not getattr(search, 'available', False):
            return None
        return list(search.candidates(reading) or ())


def _open_query():
    """F5 1回分の問い合わせの口（試験はここを差し替える）。"""
    return _OneSession()


_SMALL = 'ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶー'


def plausible(rest):
    """IME が覚えた打ち損じらしい並びを除く（小さい字で始まる・濁点の結合の印・辞書に無い語を含む）。"""
    if not rest or rest[0] in _SMALL or any(c in rest for c in '\u3099\u309a\u309b\u309c'):
        return False
    if rest[-1] in 'ぁぃぅぇぉ':
        return False
    try:
        from morphology import tokenize
        tokens = tokenize(rest)
    except Exception:
        return True
    return all(getattr(t, 'has_reading', True) for t in tokens)


def _reading_of(text):
    if all('ぁ' <= c <= 'ゖ' or 'ァ' <= c <= 'ヶ' or c == 'ー' for c in text):
        return _hira(text)
    try:
        from morphology import tokenize
        got = ''.join((t.reading or '') if getattr(t, 'has_reading', True) else '' for t in tokenize(text))
    except Exception:
        got = ''
    return _hira(got)


def ime_predictions(before, query=None):
    """IME の予測から、カーソルの位置へ入れる字の並び。
    (a) 直前の語（形態素）の読みを打った時の予測: その語で始まる候補の、続きの部分
    (b) 前2字の次に多い1字（同梱の表）を打った時の予測: その字で始まる候補
    取れなければ None。"""
    if os.environ.get('CN_F5_IME') == '0':
        return None
    if query is None:
        try:
            with _open_query() as one:
                return ime_predictions(before, query=one)
        except Exception:
            return None
    out = []
    asked = False
    try:
        from morphology import tokenize
        tokens = [t for t in tokenize(before) if (t.surface or '').strip()]
    except Exception:
        tokens = []
    if tokens:
        last = tokens[-1]
        surface = last.surface
        reading = _reading_of(surface)
        if reading and not re.fullmatch(r'[\W\d_]+', surface):
            got = query(reading)
            if got is not None:
                asked = True
                rest = [c[len(surface):] for c in got if c.startswith(surface) and len(c) > len(surface)
                        and plausible(c[len(surface):])]
                out += rest[:IME_EACH]
    for ch in next_chars(before, 2):
        reading = _reading_of(ch)
        if not reading:
            continue
        got = query(reading)
        if got is None:
            continue
        asked = True
        out += [c for c in got if c.startswith(ch) and len(c) > 1 and plausible(c)][:IME_EACH]
    if not asked:
        return None
    # IME が覚えた長い並び（打ち損じの塊など）は出さない。全体は IME_TOTAL まで
    return list(dict.fromkeys(x for x in out if x and '\n' not in x and len(x) <= IME_MAX_LEN))[:IME_TOTAL]


# --- クリップボードと周りの名詞（2026-11-21 01:55Z うにさん「行頭の候補を入れたあとの候補は、クリップボードが文字列なら
# それを最初の候補に出し、次にタブ内の周囲で使われた数が多い名詞を出す」「行頭の候補にもクリップボードと周囲の名詞を、
# カスタムの下に並べる」）。
# ・クリップボードは読むだけ（書かない）。文字列の時だけ。改行を含む時は最初の空でない行、入れるのもその行（改行は
#   入れない）。CLIP_SHOW を超える長さは、一覧では頭だけ見せて「…」を付ける（入れるのは行まるごと）。CLIP_MAX を
#   超える行は出さない
# ・周りの名詞は、カーソルの行の上下 AROUND_ROWS 行で数えた数の多い順（同じ数なら近い行の順）・NOUNS 個まで。行ごとの
#   名詞は行の字をかぎに控えて（AROUND_MEMO 行まで）、打つたびに全部を数え直さない。予測の候補にだけ使い、補正には渡さない
# CN_F5_CLIP_NOUNS=0 で前の形
CLIP_SHOW = 24
CLIP_MAX = 200
AROUND_ROWS = 40
NOUNS = 5
AROUND_MEMO = 3000
_NOUN_MEMO = {}
_LABELS = {}


def clip_nouns_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_F5_CLIP_NOUNS') != '0'


def clipboard_text(app):
    """クリップボードの文字列（入れる形）か None。読むだけ。"""
    try:
        raw = app.root.clipboard_get()
    except Exception:
        return None
    if not isinstance(raw, str):
        return None
    for line in raw.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        if line.strip():
            text = line.strip()
            if len(text) > CLIP_MAX:
                return None
            _LABELS[text] = text if len(text) <= CLIP_SHOW else text[:CLIP_SHOW] + '…'
            return text
    return None


def label(text):
    """一覧に見せる形（長いクリップボードの字は頭だけ）。入れるのは text のまま。"""
    return _LABELS.get(text, text)


def _row_nouns(line):
    got = _NOUN_MEMO.get(line)
    if got is not None:
        return got
    out = []
    try:
        from morphology import tokenize
        for t in tokenize(line):
            s = (t.surface or '').strip()
            if t.pos == '名詞' and len(s) >= 2 and not s.isdigit() and any(ch.isalpha() for ch in s):
                out.append(s)
    except Exception:
        out = []
    if len(_NOUN_MEMO) >= AROUND_MEMO:
        _NOUN_MEMO.clear()
    _NOUN_MEMO[line] = out
    return out


def around_nouns(widget, row, limit=NOUNS, rows=AROUND_ROWS):
    """カーソルの行の上下で、使われた数の多い名詞（数の多い順・同じなら近い順）。"""
    try:
        last = int(str(widget.index('end-1c')).split('.')[0])
        lo, hi = max(1, row - rows), min(last, row + rows)
        lines = widget.get('%d.0' % lo, '%d.end' % hi).split('\n')
    except Exception:
        return []
    count, near = {}, {}
    for k, line in enumerate(lines):
        if not line.strip():
            continue
        r = lo + k
        for noun in _row_nouns(line):
            count[noun] = count.get(noun, 0) + 1
            near[noun] = min(near.get(noun, 10 ** 9), abs(r - row))
    return sorted(count, key=lambda n: (-count[n], near[n]))[:limit]


def clip_and_nouns(app, widget, row):
    out = []
    clip = clipboard_text(app)
    if clip:
        out.append(clip)
    out += [n for n in around_nouns(widget, row) if n not in out]
    return out


def _remember_custom(app, items):
    """この一覧の中のカスタム候補（行頭・文末の候補の並び）を控える（一番上で上キー → カスタム候補の一番下・14:39Z）。"""
    try:
        app._f5_custom_items = list(items)
    except Exception:
        pass


def _head_list(app, wide):
    name = 'head_wide' if wide else 'head_narrow'
    return custom_list(app, name) or default_list(name)


def no_conjunctions_on(environ=None):
    """予測に接続詞の一覧を出さない（2026-11-23 うにさん）。CN_PREDICT_NO_CONJUNCTIONS=0 で前の形。"""
    environ = os.environ if environ is None else environ
    return environ.get('CN_PREDICT_NO_CONJUNCTIONS') != '0'


def ends_sentence_here(before):
    """カーソルの前が文の終わり・読点か（接続詞を出していた所）。ここで予測が空でも、F5 を左の語の再変換にしない
    （2026-11-23 うにさん「句点のあとにF5を押すと、予測変換の候補が出ないで、句点の前の単語が再変換処理されている」）。"""
    if not no_conjunctions_on():
        return False
    stripped = (before or '').rstrip()
    return bool(stripped) and (stripped[-1:] in ('。', '！', '？', '!', '?', '．') or stripped.endswith(('、', '，')))


def after_head_mark_on(environ=None):
    """見出しの印の後はクリップボードと周りの名詞だけ（2026-11-23 うにさん）。CN_PREDICT_AFTER_HEAD_MARK=0 で前の形。"""
    environ = os.environ if environ is None else environ
    return environ.get('CN_PREDICT_AFTER_HEAD_MARK') != '0'


_HEAD_MARK = re.compile(r'^[ 	　]*(?:[0-9０-９]{1,3}[.．)）、]|[(（][0-9０-９]{1,3}[)）]|[^\w\s]{1,3})[ 	　]*$')


def looks_like_head_mark(before):
    """行の頭が見出しの印だけか（「・」「■」「1.」「(1)」「◎」など・前の空白も含めて）。"""
    return bool(before and before.strip() and _HEAD_MARK.match(before))


def after_head(app, before, wide):
    """行頭の候補だけを入れた後か（「・」「　└」など。前の空白も含めて行頭の候補と同じ）。"""
    if not before or not before.strip():
        return False
    heads = _head_list(app, wide)
    return before in heads or before.rstrip() in heads or before.strip() in [h.strip() for h in heads]


def predict(app, widget, row, col, before):
    """既定の候補（上の 1〜4）。カーソルの右に字が無ければ、開いたままの括弧の閉じを先頭に（CN_PREDICT_CLOSE_BRACKET）。"""
    got = list(_predict_core(app, widget, row, col, before) or ())
    # 行頭（左に字が無い・空白や記号だけ）には出さない（17:31Z うにさん「閉じ括弧は、行頭の予測には出さない」）
    import unicodedata
    at_head = not any(unicodedata.category(c)[0] in 'LN' for c in (before or ''))
    if close_on() and not at_head and right_is_empty(widget):
        closers = close_brackets(widget, before)
        if closers:
            try:
                app._f5_close_items = list(closers)        # 記号だけでも落とさない（CN_AUTO_NO_PUNCT_ITEMS の対象外）
            except Exception:
                pass
            got = list(dict.fromkeys(closers + got))
    return got


def en_after_on(environ=None):
    """英文の後では日本語の候補を出さない（2026-11-23 うにさん承認）。CN_PREDICT_EN_AFTER=0 で前の形。"""
    environ = os.environ if environ is None else environ
    return environ.get('CN_PREDICT_EN_AFTER') != '0'


def is_english(text):
    """ラテン文字の英文か: かな・漢字・全角の字を含まず、ASCII の英字が字の半分以上（2字以上）。"""
    text = (text or '').strip()
    if not text or has_wide(text):
        return False
    letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    shown = sum(1 for ch in text if not ch.isspace())
    return letters >= 2 and letters * 2 >= shown


def english_candidates(app, widget, row):
    """英文の後の候補: カスタムの半角時の一覧（無ければ既定）と、近くの行の英単語の名詞。"""
    heads = _head_list(app, False)
    _remember_custom(app, heads)
    nouns = [n for n in around_nouns(widget, row) if n.isascii()]
    return list(dict.fromkeys(list(heads) + nouns))


def _after_english(widget, before):
    """カーソルの前が英文の後か: 行頭、または「.」「!」「?」の後で、前の文（行頭なら上の行の最後の文）が英文。"""
    stripped = (before or '').rstrip()
    if stripped and stripped[-1:] not in ('.', '!', '?'):
        return False
    if not stripped:
        # 行頭: 上の行（空行は飛ばす・近くの行だけ）の最後の文
        try:
            row = int(str(widget.index('insert')).split('.')[0])
            lo = max(1, row - AROUND_ROWS)
            lines = widget.get('%d.0' % lo, '%d.0' % row).split('\n')
        except Exception:
            return False
        stripped = next((l.rstrip() for l in reversed(lines) if l.strip()), '')
        if not stripped:
            return False
    return is_english(_last_sentence(stripped))


def _last_sentence(text):
    """text（同じ行の字）の最後の文。終わりの「.」「!」「?」「。」などは含める。"""
    body = text.rstrip()
    end = len(body)
    while end and body[end - 1] in '.!?。！？．':
        end -= 1
    cut = max(body.rfind(c, 0, end) for c in '.!?。！？．')
    return body[cut + 1:].strip()


def _predict_core(app, widget, row, col, before):
    """既定の候補（上の 1〜4）。"""
    try:
        whole = widget.get(_near_start(widget, row), _near_end(widget, row))
    except Exception:
        whole = before or ''
    english = en_after_on() and _after_english(widget, before)
    if english and (before or '').strip():
        # 英文の「.」「!」「?」の後で、日本語の接続詞（しかし・そして…）や日本語の名詞を並べていた（2026-11-23 説明書担当の
        # 見つけ・うにさん承認）。日本語の文の後は今までと同じ
        return english_candidates(app, widget, row)
    wide = wide_for(widget, whole)      # IME の形で全角・半角の一覧を選ぶ（16:52Z・CN_PREDICT_CUSTOM_BY_IME）
    if clip_nouns_on():
        if not (before or '').strip():
            # 行頭: カスタム（無ければ既定）の下に、クリップボードと周りの名詞（01:55Z）。行頭の印の一覧は IME の形で
            # 選ぶまま（2026-11-21 の指定）。上の行が英文なら、日本語の名詞は足さない（英単語の名詞だけ）
            heads = _head_list(app, wide)
            _remember_custom(app, heads)
            extra = clip_and_nouns(app, widget, row)
            if english:
                clip = clipboard_text(app)
                extra = [n for n in extra if n == clip or n.isascii()]
            return list(dict.fromkeys(heads + extra))
        if after_head(app, before, wide) or (after_head_mark_on() and looks_like_head_mark(before)):
            # 行頭の候補を入れた後: クリップボード → 周りの名詞（01:55Z）。無ければ今までどおり
            # 2026-11-23 うにさん「文頭の見出しを付けたあとの、クリップボードや多い名詞の予測を出すように切り替える」:
            # 行頭の一覧に無い見出しの印（「1.」「(1)」「◎」など）の後も同じにし、無い時も接続詞・続きの字は出さない
            got = clip_and_nouns(app, widget, row)
            if got or after_head_mark_on():
                return got
    if not (before or '').strip():
        custom = custom_list(app, 'head_wide' if wide else 'head_narrow')
        if custom:
            return custom
        if wide and head_order_new():
            return default_list('head_wide')             # 決めた順のまま（16:44Z の指定）
        if not wide and fixed_order():
            return default_list('head_narrow')           # 決めた並びのまま（2026-11-21）
        used = [line.strip()[:1] for line in whole.split('\n') if line.strip()]
        heads = list((HEAD_WIDE_OLD if wide else HEAD_NARROW))
        return by_effort(heads, used)
    stripped = before.rstrip()
    if stripped[-1:] in ('。', '！', '？', '!', '?', '．') or stripped.endswith(('、', '，')):
        if no_conjunctions_on():
            # 2026-11-23 うにさん「予測候補の、しかし　そして　また　などの接続詞の候補は無しにする。ニュアンスを予想する
            # ことはできない」: 文の終わり・読点の後は、接続詞の代わりにクリップボード → 近くの行で多い名詞（見出しの印の
            # 後と同じ）。何も無い時は空（app は一覧を開かず、左の語の再変換にも行かない・ends_sentence_here）。
            # CN_PREDICT_NO_CONJUNCTIONS=0 で前の形
            return clip_and_nouns(app, widget, row)
        return conjunctions(widget, before)
    # 2バイトの字の無いタブ（英文など）: 形態素では見られないので、語（英数字）の後を文末になりそうな所とする
    # 文末の候補を出す所かは、タブの字で見る（英文のタブでは語の後を文末に）。どちらの一覧かは wide（IME の形・16:52Z）
    if ends_like_sentence(before) or (not has_wide(whole) and stripped[-1:].isalnum()):
        name = 'end_wide' if wide else 'end_narrow'
        ends = custom_list(app, name) or default_list(name)
        _remember_custom(app, ends)
        closers = [c for c in unclosed(before) if wide or ord(c) < 0x80]
        return list(dict.fromkeys(closers + ends))
    got = None
    try:
        got = ime_predictions(before)
    except Exception:
        got = None
    if got:
        return got
    return [phrase(before, c) for c in next_chars(before)]
