"""
画面の表示言語（Language メニュー・2026-10-26・うにさんの指定）。

    「メニューのこのアプリについての左に、Languageを追加する。
     アプリ全体の言語が切替わる」
    「日本向け設定は隠さない。言語を変えた場合は、項目をインデントし、
     末尾に日本のIME用の設定と書く」

**作りの要点**: 画面の文字を書いている所（数百か所）を1つずつ直すのではなく、
tkinter が Tk へ文字を渡す出入り口で訳す。

- 渡すとき: `Misc._options`（ウィジェットを作る・configure・メニューの
  add/entryconfigure・Canvas の文字の全部がここを通る）で text/label/
  accelerator を訳す。窓の題（wm_title）・messagebox・ファイルの窓も同じ。
- 読むとき: cget / entrycget / wm_title() は**元の日本語**を返す。
  アプリの中には `status.cget('text').startswith('解析中…')` のように
  画面の文字を読んで比べる所があるので、読む側には日本語のまま見せる。
- 訳は ui_lang_en.py の表（日本語 → 英語）。`{0}` の入った行は型として
  扱い、実行時の値（数・ファイル名）をはめ込む。表に無い文字は日本語のまま
  （壊れない・訳が足りないだけ）。
- 日本語（'ja'）のときは何もしない（出入り口は素通り）。

**利用者の書いた文字は訳さない**: 単語帳のボタンのように、本人の語が
text に入る所は `ui_lang.raw(文字)` で包む。包んだウィジェットは、
言語を切り替えたときの訳し直しからも外す。
"""

import re
import tkinter
from collections import OrderedDict

LANGUAGES = (('ja', '日本語'), ('en', 'English'))
DEFAULT_LANGUAGE = 'ja'

# 日本の IME 用の設定（うにさんの指定: 言語を変えたら、字下げして末尾に書く）
IME_NOTE = {'en': '(Japanese IME setting)'}
IME_INDENT = '    '

_TEXT_KEYS = ('text', 'label', 'accelerator')
_JA = re.compile(r'[぀-ヿ㐀-鿿！-～　-〿]')

_lang = DEFAULT_LANGUAGE
_installed = False
_tables = {}            # 言語 → 表（ui_lang_en.TABLE を遅れて読む）
_cache = OrderedDict()  # 訳の控え（日本語 → 訳）
_reverse = OrderedDict()  # 画面に出した訳 → 元の日本語
_CACHE_MAX = 4096
_REVERSE_MAX = 20000


class Raw(str):
    """訳さない文字（本人の語・ファイル名など）。"""
    __slots__ = ()


def raw(text):
    return Raw(text)


def language():
    return _lang


def is_japanese():
    return _lang == 'ja'


# ------------------------------------------------------------
# 表
# ------------------------------------------------------------

class _Table:
    def __init__(self, exact, ime_only):
        self.exact = {}
        self.patterns = {}      # 型の頭の1字 → [(正規表現, 訳の型)]
        self.free_patterns = []  # 頭が {0} で始まる型
        self.prefixes = []      # 「開けませんでした:」のように後ろに値が続く行
        self.ime_only = frozenset(ime_only)
        self.terms = {}
        for ja, en in exact.items():
            if not en:
                continue
            if re.search(r'\{\d+\}', ja):
                self._add_pattern(ja, en)
            else:
                self.exact[ja] = en
                if ja.rstrip()[-1:] in (':', '：', '\n'):
                    self.prefixes.append((ja, en))
        self.prefixes.sort(key=lambda p: -len(p[0]))
        # 型は字の多いものから当てる（「セット{0}」が「セット{0}に登録した単語を…」より先に当たって
        # 「Set 2に登録した…」になっていた・2026-10-26）
        for group in list(self.patterns.values()) + [self.free_patterns]:
            group.sort(key=lambda p: -len(re.sub(r'\(\?P<g\d+>\.\+\?\)', '', p[0].pattern)))

    def _add_pattern(self, ja, en):
        parts = re.split(r'(\{\d+\})', ja)
        rx = ''
        for p in parts:
            m = re.fullmatch(r'\{(\d+)\}', p)
            rx += '(?P<g%s>.+?)' % m.group(1) if m else re.escape(p)
        try:
            compiled = re.compile(rx + r'\Z', re.S)
        except re.error:
            return
        head = parts[0][:1]
        if head:
            self.patterns.setdefault(head, []).append((compiled, en))
        else:
            self.free_patterns.append((compiled, en))


def _table(lang):
    t = _tables.get(lang)
    if t is None and lang == 'en':
        try:
            import ui_lang_en as mod
            t = _Table(mod.TABLE, getattr(mod, 'IME_ONLY', ()))
            t.terms = {ja: (mod.TABLE.get(ja) or ja)
                       for ja in getattr(mod, 'TERMS', ()) if mod.TABLE.get(ja)}
        except Exception:
            t = _Table({}, ())
        _tables[lang] = t
    return t


# ------------------------------------------------------------
# 訳す
# ------------------------------------------------------------

def _remember(out, src):
    if out != src:
        _reverse[out] = src
        _reverse.move_to_end(out)
        if len(_reverse) > _REVERSE_MAX:
            _reverse.popitem(last=False)


def _fill(table, rx, en, s):
    m = rx.match(s)
    if not m:
        return None
    vals = {}
    for name, v in m.groupdict().items():
        # はめ込む値が画面の語（品詞の名前など）なら、それも訳す
        vals[name[1:]] = table.exact.get(v, v)
    try:
        return re.sub(r'\{(\d+)\}', lambda mm: vals.get(mm.group(1), mm.group(0)), en)
    except Exception:
        return None


def _core(table, s, free=True):
    hit = table.exact.get(s)
    if hit is not None:
        return hit
    for rx, en in table.patterns.get(s[:1], ()):
        out = _fill(table, rx, en, s)
        if out is not None:
            return out
    if not free:
        return None
    for rx, en in table.free_patterns:
        out = _fill(table, rx, en, s)
        if out is not None:
            return out
    return None


def _translate(table, s):
    # 頭の字で引く型を先に、頭が {0} の型（「{0}・{1}」のように何にでも当たる）は後に。
    # 字下げの付いた行で「{0}・{1}」が先に当たり、「辞書に無い語がある（ht・Cli）」が
    # 訳されずに残っていた（2026-10-26 うにさん「再変換メニューの文字列」）
    m = re.match(r'([ 　]*)(.*?)([ 　]*)\Z', s, re.S)
    lead, body, tail = m.groups()
    for free in (False, True):
        out = _core(table, s, free)
        if out is not None:
            return out
        if (lead or tail) and body:
            out = _core(table, body, free)
            if out is not None:
                return lead.replace('　', '  ') + out + tail.replace('　', ' ')
    # 「保存できませんでした:\n<エラー>」のように、後ろに値が続く行
    for ja, en in table.prefixes:
        if s.startswith(ja) and len(s) > len(ja):
            rest = s[len(ja):]
            if _JA.search(rest):
                rest = _translate(table, rest)
            return en + (' ' if en[-1:] == ':' and rest[:1] not in (' ', '\n') else '') + rest
    # 何行かの文は1行ずつ
    if '\n' in s:
        lines = s.split('\n')
        done = [_translate(table, ln) if _JA.search(ln) else ln for ln in lines]
        if done != lines:
            return '\n'.join(done)
    return s


_PUNCT = (('（', ' ('), ('）', ')'), ('・', ', '), ('／', ' / '), ('。', '. '),
          ('：', ': '), ('、', ', '), ('──', ' - '), ('——', ' - '))
_KEEP = re.compile(r'(「[^」]*」|`[^`]*`)')
_terms_rx = {}


def _by_terms(table, s):
    """
    品詞判定・補正根拠の行を、語（品詞・活用形の名前）ごとに訳す。

    これらの行は `名詞（サ変）・連用形／原形 走る（辞書に無い語）` のように
    名前を記号でつないで組み立てるので、行まるごとでは表に載らない。
    名前（ui_lang_en.TERMS）だけを置き換え、「」と ` ` の中（本人の文字）は
    そのまま残す。名前に当たらない日本語は日本語のまま。
    """
    terms = getattr(table, 'terms', None)
    if not terms:
        return s
    rx = _terms_rx.get(id(table))
    if rx is None:
        rx = re.compile('|'.join(re.escape(t) for t in
                                 sorted(terms, key=len, reverse=True)))
        _terms_rx[id(table)] = rx
    out = []
    for i, part in enumerate(_KEEP.split(s)):
        if i % 2:
            out.append('“%s”' % part[1:-1] if part[:1] == '「' else part)
            continue
        part = rx.sub(lambda m: terms[m.group(0)], part)
        for a, b in _PUNCT:
            part = part.replace(a, b)
        out.append(part)
    # 行の頭の字下げ（一覧の「  」）だけは残す
    return '  ' + re.sub(r' {2,}', ' ', ''.join(out)).strip()


def tr(text):
    """画面に出す文字を、いまの言語に訳す。日本語のとき・表に無いときはそのまま。"""
    if (_lang == 'ja' or not isinstance(text, str) or isinstance(text, Raw)
            or not text or not _JA.search(text)):
        return text
    hit = _cache.get(text)
    if hit is not None:
        return hit
    table = _table(_lang)
    out = _translate(table, text)
    if text[:2] == '  ' and _JA.search(_KEEP.sub('', out)):
        # 品詞判定・補正根拠の一覧の行（app が「  」を付けて並べる）。
        # 行まるごと・型で訳し切れなかった名前を、語ごとに置き換える。
        out = _by_terms(table, out)
    if text in table.ime_only or text.strip('　 ') in table.ime_only:
        out = '%s%s  %s' % (IME_INDENT, out.strip(), IME_NOTE.get(_lang, ''))
    _cache[text] = out
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    _remember(out, text)
    return out


def original(text):
    """画面に出した訳から、元の日本語へ戻す（訳していなければそのまま）。"""
    if _lang == 'ja' or not isinstance(text, str):
        return text
    return _reverse.get(text, text)


# ------------------------------------------------------------
# tkinter の出入り口
# ------------------------------------------------------------

def _tr_cnf(widget, cnf):
    if not cnf:
        return cnf
    if isinstance(cnf, dict):
        if not any(k in cnf for k in _TEXT_KEYS):
            return cnf
        new = dict(cnf)
        for k in _TEXT_KEYS:
            v = new.get(k)
            if isinstance(v, Raw):
                if k == 'text':
                    try:
                        widget._ui_lang_raw = True
                    except Exception:
                        pass
            elif isinstance(v, str):
                if k == 'text' and getattr(widget, '_ui_lang_raw', False):
                    continue
                new[k] = tr(v)
        return new
    if isinstance(cnf, (tuple, list)):
        return type(cnf)(_tr_cnf(widget, c) for c in cnf)
    return cnf


def install():
    """tkinter の出入り口を差し替える（何度呼んでもよい）。"""
    global _installed
    if _installed:
        return
    _installed = True
    Misc = tkinter.Misc

    orig_options = Misc._options

    def _options(self, cnf, kw=None):
        if _lang != 'ja':
            cnf = _tr_cnf(self, cnf)
            if kw:
                kw = _tr_cnf(self, kw)
        return orig_options(self, cnf, kw)
    Misc._options = _options

    orig_cget = Misc.cget

    def cget(self, key):
        value = orig_cget(self, key)
        if _lang != 'ja' and key in _TEXT_KEYS and isinstance(value, str):
            return _reverse.get(value, value)
        return value
    Misc.cget = cget
    Misc.__getitem__ = cget

    orig_entrycget = tkinter.Menu.entrycget

    def entrycget(self, index, option):
        value = orig_entrycget(self, index, option)
        if _lang != 'ja' and option in _TEXT_KEYS and isinstance(value, str):
            return _reverse.get(value, value)
        return value
    tkinter.Menu.entrycget = entrycget

    orig_title = tkinter.Wm.wm_title

    def wm_title(self, string=None):
        if string is None:
            value = orig_title(self)
            return original(value) if isinstance(value, str) else value
        return orig_title(self, tr(string))
    tkinter.Wm.wm_title = wm_title
    tkinter.Wm.title = wm_title

    try:
        from tkinter import ttk
        orig_heading = ttk.Treeview.heading

        def heading(self, column, option=None, **kw):
            # 表の見出し（全タブの検索結果のタブ・行:桁…）は _options を通らない
            if _lang != 'ja' and isinstance(kw.get('text'), str) and not isinstance(kw['text'], Raw):
                kw['text'] = tr(kw['text'])
            return orig_heading(self, column, option, **kw)
        ttk.Treeview.heading = heading
    except Exception:
        pass

    try:
        from tkinter import messagebox
        orig_show = messagebox._show

        def _show(title=None, message=None, _icon=None, _type=None, **options):
            if _lang != 'ja':
                title, message = tr(title), tr(message)
                if 'detail' in options:
                    options['detail'] = tr(options['detail'])
            return orig_show(title, message, _icon, _type, **options)
        messagebox._show = _show
    except Exception:
        pass

    try:
        from tkinter import commondialog
        orig_dialog_show = commondialog.Dialog.show

        def show(self, **options):
            if _lang != 'ja':
                for opts in (self.options, options):
                    if opts.get('title'):
                        opts['title'] = tr(opts['title'])
                    if opts.get('filetypes'):
                        opts['filetypes'] = [
                            (tr(ft[0]),) + tuple(ft[1:])
                            if isinstance(ft, (tuple, list)) and ft else ft
                            for ft in opts['filetypes']]
            return orig_dialog_show(self, **options)
        commondialog.Dialog.show = show
    except Exception:
        pass


# ------------------------------------------------------------
# 切り替え
# ------------------------------------------------------------

def system_language():
    """
    Windows の表示言語から決める（設定に言語が無い最初の起動で使う）。

    日本語の Windows なら 'ja'、それ以外は 'en'。英語の人が最初から
    英語で使え、自分で Language を探さなくてよい（2026-10-26）。
    """
    try:
        import ctypes
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return 'ja' if (langid & 0x3ff) == 0x11 else 'en'
    except Exception:
        pass
    try:
        import locale
        code = (locale.getlocale()[0] or '').lower()
        if code:
            return 'ja' if code.startswith(('ja', 'japanese')) else 'en'
    except Exception:
        pass
    return DEFAULT_LANGUAGE


def set_language(lang, root=None):
    """
    言語を切り替え、開いている窓とメニューの文字を訳し直す。

    lang が空（設定で一度も選んでいない）なら、Windows の表示言語で決める。
    """
    global _lang
    if not lang:
        lang = system_language()
    if lang not in dict(LANGUAGES):
        lang = DEFAULT_LANGUAGE
    install()
    if lang == _lang:
        return
    _lang = lang
    _cache.clear()
    if root is not None:
        retranslate(root)


def _retext(widget):
    """1つのウィジェットの文字を、元の日本語から訳し直す。"""
    call = widget.tk.call
    if isinstance(widget, tkinter.Wm):
        try:
            cur = call('wm', 'title', widget._w)
            src = _reverse.get(cur, cur)
            call('wm', 'title', widget._w, tr(src))
        except tkinter.TclError:
            pass
    if isinstance(widget, tkinter.Menu):
        try:
            end = widget.index('end')
        except tkinter.TclError:
            end = None
        for i in range(0 if end is None else end + 1):
            for key in ('label', 'accelerator'):
                try:
                    cur = call(widget._w, 'entrycget', i, '-' + key)
                except tkinter.TclError:
                    continue
                if not isinstance(cur, str) or not cur:
                    continue
                src = _reverse.get(cur, cur)
                try:
                    call(widget._w, 'entryconfigure', i, '-' + key, tr(src))
                except tkinter.TclError:
                    pass
        return
    if getattr(widget, '_ui_lang_raw', False):
        return
    try:
        cur = call(widget._w, 'cget', '-text')
    except tkinter.TclError:
        return
    if not isinstance(cur, str) or not cur:
        return
    try:
        if call(widget._w, 'cget', '-textvariable'):
            return      # 変数に結んだ文字（入力欄など）は触らない
    except tkinter.TclError:
        pass
    src = _reverse.get(cur, cur)
    try:
        call(widget._w, 'configure', '-text', tr(src))
    except tkinter.TclError:
        pass


def retranslate(root):
    """root の下の窓・ウィジェット・メニューを全部訳し直す。"""
    stack = [root]
    seen = set()
    while stack:
        w = stack.pop()
        if id(w) in seen:
            continue
        seen.add(id(w))
        try:
            _retext(w)
            stack.extend(w.winfo_children())
        except Exception:
            continue
