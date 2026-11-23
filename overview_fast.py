# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""俯瞰（右ダブルクリックを押したまま）の速い形・試作（2026-11-20 うにさん「作りを変えて試す」）。

今の形は、本文の欄・補正欄そのものの字を小さくし、Tk が両方の欄の全部の行を組み直す（入る時と出る時の2回。3,000行で
入って出るまで約1秒の大半）。この形は、同じ本文を映す「分身」（Tk の peer・本文は同じものを共有する）を小さい字で
前もって作っておき、俯瞰の間だけ欄の上に重ねて見せる。欄そのものの字は変えないので、出る時は分身を隠すだけ。

・分身は最初に使う時（または起動の少し後）に作り、あとは隠して取っておく。本文の編集は Tk が分身にもそのまま映す
・押したまま上下に動かすと、分身を掴んで動かす（今の形と同じ向き）。分身の上端から、ふだんの字で1画面ぶんの範囲に
  枠（今の形と同じ ov_dest のタグ）を付け、離すと本文の欄をその上端の行へ置く（今の形と同じ）
・裏の絵: 欄の後ろの絵の Canvas を欄より前に出し、分身を透かして見せる（paper_window.show_through）
・見た目の違い（試作の今の形との違い）: タグに字の大きさを持つ所（タイトル・目次・品詞の字の大きさ）は俯瞰の間だけ
  俯瞰の字との比で小さくする（shrink_tag_fonts）。左右の行をそろえる隙間（text_layout の詰め物）は俯瞰の間だけ 0（squash_padding）。行番号は俯瞰の間は本文の欄のまま
・デバッグメニュー「俯瞰を速い形で出す（試作）」（設定 overview_fast・既定オン）。CN_OVERVIEW_FAST=0 で今の形
"""
import os
import tkinter as tk

SUFFIX = '_cn_ov'
WARP_TOLERANCE = 60      # 戻した先から、この画素より離れた報せは戻す前のもの
WARP_SKIP_MAX = 8        # 戻す前の報せをいくつまで捨てて待つか
# 俯瞰でブックマークのある行の字の大きさ（pt）。2026-11-20 うにさん「縮小時に、ブックマークがある行は、一回り大きく
# してください」。俯瞰の字（app.OVERVIEW_FONT_SIZE＝5）より一回り大きい 8。デバッグのパラメータ（overview_bookmark）。
# 今の形・速い形の両方で使う（bookmark_rows_on / bookmark_rows_off）。CN_OVERVIEW_BOOKMARK=0 で前の形（大きくしない）
# 2026-11-21 05:01Z うにさん「ブックマーク行のフォントサイズをより大きくする」: 8 → 11（本文の字の大きさくらい）。
# デバッグの窓で値を保存してあれば、そちらが使われる
BOOKMARK_SIZE = 11
BOOKMARK_SIZE_MAX = 20
BOOKMARK_TAG = 'cn_ov_bookmark'


def bookmark_rows_on(app, panes):
    """俯瞰の間、ブックマークのある行を一回り大きい字にする（本文の欄・補正欄。分身はタグを共有するので同じに見える）。"""
    if os.environ.get('CN_OVERVIEW_BOOKMARK') == '0':
        return
    rows = sorted(r for r in (getattr(app, 'bookmarks', None) or ()) if isinstance(r, int) and r >= 1)
    try:
        family = app._editor_font()[0]
    except Exception:
        family = 'TkDefaultFont'
    for pane in panes:
        try:
            pane.tag_configure(BOOKMARK_TAG, font=(family, int(BOOKMARK_SIZE)))
            pane.tag_remove(BOOKMARK_TAG, '1.0', 'end')
            for r in rows:
                pane.tag_add(BOOKMARK_TAG, '%d.0' % r, '%d.0' % (r + 1))
            pane.tag_raise(BOOKMARK_TAG)
        except tk.TclError:
            pass


def bookmark_rows_off(panes):
    for pane in panes:
        try:
            pane.tag_remove(BOOKMARK_TAG, '1.0', 'end')
        except tk.TclError:
            pass


STUCK_LOG_AFTER = 20


def end_slide_on(environ=None):
    """分身が下端に着いた後は、範囲の枠だけを下へ滑らせる（06:23Z）。CN_OVERVIEW_END_SLIDE=0 で前の形"""
    environ = os.environ if environ is None else environ
    return environ.get('CN_OVERVIEW_END_SLIDE') != '0'


def log(app, what, info):
    """tools_local/scroll_trace/overview_fast.log へ1行（開発の時だけ・app.redo_trace_on と同じ決まり）。"""
    try:
        import time as _time
        mod = app_module_of(app)
        if not mod.redo_trace_on():
            return
        folder = getattr(app, '_scroll_trace_dir', None) or os.path.join(mod.data_dir(), 'tools_local', 'scroll_trace')
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, 'overview_fast.log')
        try:
            if os.path.getsize(path) > 128 * 1024:
                os.remove(path)
        except OSError:
            pass
        with open(path, 'a', encoding='utf-8') as f:
            f.write('%s  %s  %s\n' % (_time.strftime('%Y-%m-%d %H:%M:%S'), what,
                                      '  '.join('%s=%s' % kv for kv in info.items())))
    except Exception:
        pass


def drag_line_height(tkapp, peer, environ=None):
    """掴んで送る1段の高さ（px）: 分身の字の行の高さ（2026-11-21）。前は上端の表示の行の高さで、タイトルの字を元の
    大きさに保つようにしてから、上端がタイトルの行だと1段が 52px になり、送りがとても遅かった（写しで実測）。
    CN_OVERVIEW_LINE_H_FONT=0 で前の形"""
    environ = os.environ if environ is None else environ
    if environ.get('CN_OVERVIEW_LINE_H_FONT') != '0':
        try:
            got = int(tkapp.call('font', 'metrics', tkapp.call(peer, 'cget', '-font'), '-linespace'))
            if got > 0:
                return got
        except (tk.TclError, ValueError):
            pass
    try:
        info = tkapp.call(peer, 'dlineinfo', '@0,0')
        return max(1, int(tkapp.splitlist(info)[3])) if info else 8
    except (tk.TclError, ValueError):
        return 8


# --- 縮小の間は行番号を隠す（2026-11-21 05:12Z うにさん「行番号が縮小時に追従しないので、それが意図的なら番号を非表示に
# する」）。速い形は欄の字を変えないので、行番号はふだんの行のまま残っていた。行番号の欄の上に地の色の覆いを置く。
# CN_OVERVIEW_HIDE_GUTTER=0 で前の形
def hide_gutters_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_OVERVIEW_HIDE_GUTTER') != '0'


def hide_gutters(app):
    covers = []
    if not hide_gutters_on():
        return covers
    for name in ('editor_gutter', 'result_gutter'):
        g = getattr(app, name, None)
        if g is None:
            continue
        try:
            if not g.winfo_ismapped():
                continue
            cover = tk.Frame(g.master, bg=str(g.cget('background')), bd=0, highlightthickness=0)
            cover.place(in_=g, x=0, y=0, relwidth=1, relheight=1, bordermode='outside')
            cover.lift(g)
            covers.append(cover)
        except tk.TclError:
            pass
    return covers


def hide_gutters_off(covers):
    for cover in covers or ():
        try:
            cover.destroy()
        except tk.TclError:
            pass


def idle_state(environ=None):
    """俯瞰に出ていない間の分身の -state。Tk 8.6.9 では、同じ本文の分身が1つでも disabled だと、本文の Undo が
    効かなくなる（取り消しの手続きがその分身で走り、字を戻せない）。起動の4秒後に前もって作る分身を disabled で
    作っていたので、それからは本文の Ctrl+Z が効かなかった（2026-11-20・tests_gui_shortcuts_menu の「括弧の巡回の
    後の Undo」で見つかった）。出ていない間は normal（窓に置かないので打てない）、俯瞰に出ている間だけ disabled。
    CN_OVERVIEW_PEER_NORMAL=0 で前の形（いつも disabled）"""
    environ = os.environ if environ is None else environ
    return 'disabled' if environ.get('CN_OVERVIEW_PEER_NORMAL') == '0' else 'normal'


def enabled(app, environ=None):
    """俯瞰を速い形で出すか。2026-11-23 うにさん「デバッグメニューから俯瞰の項目を削除し、チェックオンとして以降処理します」:
    設定 overview_fast は見ない（前に切って保存した人も速い形）。CN_OVERVIEW_FAST=0 の時だけ今の形"""
    environ = os.environ if environ is None else environ
    return environ.get('CN_OVERVIEW_FAST') != '0'


def app_module_of(app, environ=None):
    """色・字の大きさを読む、動いているアプリのモジュール。`py app.py` では app は __main__ なので、`import app` は
    最初の配色（ライト）のままの2つ目の写しを読み込む（doc_window._app_module と同じ）。ダークでも俯瞰の範囲の枠が
    ライトの HOVER_BG（#e9eff1）で塗られ、白い帯の下の字が読めなかった（2026-11-20 16:28Z うにさん「縮小モードの
    範囲が白いです」）。CN_OVERVIEW_FAST_THEME=0 で前の形（いつも import app）"""
    import sys
    environ = os.environ if environ is None else environ
    module = None
    if environ.get('CN_OVERVIEW_FAST_THEME') != '0':
        module = sys.modules.get(type(app).__module__)
        if module is not None and not hasattr(module, 'OVERVIEW_DEST_TAG'):
            module = None
    if module is None:
        import app as module
    return module


# 左右の行をそろえる隙間（text_layout の詰め物・paired_row_pad_<px>）。タグは分身と共有なので、ふだんの字で測った
# 隙間が小さい字の分身にもそのまま付き、分割表示の俯瞰は行と行の間が大きく空いて、範囲の枠も見えている範囲にしては
# 縦に長かった（同じ 16:28Z の報告「範囲にしては縦に長いな」）。俯瞰の間だけ隙間を 0 にし、出る時に名前の px から
# 戻す（今の形は字を替える時に clear_padding で外している）。CN_OVERVIEW_FAST_PAD=0 で前の形（隙間のまま）
PAD_PREFIX = 'paired_row_pad_'


def pad_squash_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_OVERVIEW_FAST_PAD') != '0'


HEAD_SPACE_TAG = 'cn_ov_head_space'


def keep_head_space(pane):
    """タイトル・目次の行（見出しの行）の行の間を、ふだんの欄と同じに保つ（2026-11-21 05:12Z うにさん「タイトルと目次は
    縦に短くなるので、できれば見た目をキープする」）。分身は行の間が 0 で、左右をそろえる隙間も 0 にするので、見出しの
    行だけ縦に詰まっていた。見出しの行に、欄の行の間＋その行の隙間を持つタグを一番上に重ねる（出る時に外す）。
    CN_OVERVIEW_KEEP_HEAD=0 で前の形"""
    if not keep_head_fonts_on():
        return
    try:
        raw = _raw(pane)
        head = _head_rows(pane)
        if head <= 0:
            return
        s1, s3 = int(pane.cget('spacing1')), int(pane.cget('spacing3'))
        for row in range(1, head + 1):
            pad = 0
            for tag in pane.tk.splitlist(pane.tk.call(raw, 'tag', 'names', '%d.0' % row)):
                if str(tag).startswith(PAD_PREFIX):
                    try:
                        pad = max(pad, int(str(tag)[len(PAD_PREFIX):]))
                    except ValueError:
                        pass
            name = '%s_%d' % (HEAD_SPACE_TAG, pad)
            pane.tk.call(raw, 'tag', 'configure', name, '-spacing1', s1, '-spacing3', s3 + pad)
            pane.tk.call(raw, 'tag', 'add', name, '%d.0' % row, '%d.0' % (row + 1))
            pane.tk.call(raw, 'tag', 'raise', name)
    except (tk.TclError, ValueError):
        pass


def drop_head_space(pane):
    try:
        raw = _raw(pane)
        for tag in pane.tk.splitlist(pane.tk.call(raw, 'tag', 'names')):
            if str(tag).startswith(HEAD_SPACE_TAG):
                pane.tk.call(raw, 'tag', 'remove', tag, '1.0', 'end')
    except tk.TclError:
        pass


def squash_padding(panes):
    done = []
    if not pad_squash_on():
        for pane in panes:
            keep_head_space(pane)
        return done
    for pane in panes:
        try:
            raw = _raw(pane)
            for tag in pane.tk.splitlist(pane.tk.call(raw, 'tag', 'names')):
                if tag.startswith(PAD_PREFIX):
                    pane.tk.call(raw, 'tag', 'configure', tag, '-spacing3', 0)
            done.append(pane)
        except tk.TclError:
            pass
        keep_head_space(pane)
    return done


def restore_padding(panes):
    for pane in panes:
        drop_head_space(pane)
        try:
            raw = _raw(pane)
            base = int(pane.cget('spacing3'))
            for tag in pane.tk.splitlist(pane.tk.call(raw, 'tag', 'names')):
                if tag.startswith(PAD_PREFIX):
                    try:
                        px = int(tag[len(PAD_PREFIX):])
                    except ValueError:
                        continue
                    pane.tk.call(raw, 'tag', 'configure', tag, '-spacing3', base + px)
        except (tk.TclError, ValueError):
            pass


# タグに字の大きさを持つ所（品詞の字の大きさ pos_font_*・書式・題）は分身と共有で、分身でもふだんの大きさのまま
# だった。品詞の字の大きさは、ほとんどの行に1字はある（数字・名詞などの 10〜14pt）ので、行の高さがふだんの字の
# まま（実測 26px・小さい字なら 9px）で、範囲の枠が見えている範囲とほとんど同じ高さに見えた（同じ 16:28Z の報告
# 「範囲にしては縦に長いな」）。俯瞰の間だけ、そのタグの字を俯瞰の字との比で小さくし、出る時に戻す（今の形は字を
# 替える時に _refresh_pos_font_tags で同じことをしている）。ブックマークの行（BOOKMARK_TAG）は除く。
# CN_OVERVIEW_FAST_TAGFONT=0 で前の形（タグの字はふだんのまま）
def tag_font_shrink_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_OVERVIEW_FAST_TAGFONT') != '0'


_FONT_ACTUAL = {}


def _font_size_of(pane, spec):
    """字の指定 spec の実際の形と大きさ。同じ指定は控えから（2026-11-21 軽量化: 縮小に入るたびにタグごとに Font を
    作って問い合わせていた。3,000行のタブで 176 回・22ms＝入る時間の約2割）。CN_OVERVIEW_FONT_MEMO=0 で前の形"""
    key = str(spec)
    if os.environ.get('CN_OVERVIEW_FONT_MEMO') != '0':
        got = _FONT_ACTUAL.get(key)
        if got is not None:
            return dict(got[0]), got[1]
    from tkinter import font as tkfont
    actual = tkfont.Font(root=pane, font=spec).actual()
    size = int(actual.get('size') or 0)
    if len(_FONT_ACTUAL) > 512:
        _FONT_ACTUAL.clear()
    _FONT_ACTUAL[key] = (dict(actual), size)
    return actual, size


# タイトルと目次（title_inline の見出しの行・cn_head_*）の字は小さくしない（2026-11-21 05:01Z うにさん「タイトルと目次の
# フォントサイズは元のままにする」）。CN_OVERVIEW_KEEP_HEAD=0 で前の形（見出しも小さく）
KEEP_TAG_PREFIXES = ('cn_head',)


def keep_head_fonts_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_OVERVIEW_KEEP_HEAD') != '0'


def shrink_tag_fonts(panes, small):
    """俯瞰の間、タグの字を俯瞰の字との比で小さくする。戻すための控え [(pane, tag, 元の字, 付けた字)] を返す。"""
    saved = []
    if not tag_font_shrink_on():
        return saved
    for pane in panes:
        try:
            raw = _raw(pane)
            _actual, base = _font_size_of(pane, str(pane.cget('font')))
            base = abs(base) or 11
            for tag in pane.tk.splitlist(pane.tk.call(raw, 'tag', 'names')):
                if tag == BOOKMARK_TAG or tag == 'sel':
                    continue
                if str(tag).startswith(KEEP_TAG_PREFIXES) and keep_head_fonts_on():
                    continue                  # タイトル・目次の字はそのまま（05:01Z）
                spec = str(pane.tk.call(raw, 'tag', 'cget', tag, '-font'))
                if not spec:
                    continue
                actual, size = _font_size_of(pane, spec)
                if not size:
                    continue
                new = max(1, int(round(abs(size) * small / float(base))))
                applied = (actual.get('family') or 'TkDefaultFont', new if size > 0 else -new)
                for key, word in (('weight', 'bold'), ('slant', 'italic')):
                    if str(actual.get(key, '')).lower() == word:
                        applied += (word,)
                for key in ('underline', 'overstrike'):
                    if actual.get(key):
                        applied += (key,)
                pane.tk.call(raw, 'tag', 'configure', tag, '-font', applied)
                saved.append((pane, tag, spec, str(pane.tk.call(raw, 'tag', 'cget', tag, '-font'))))
        except (tk.TclError, ValueError, TypeError):
            pass
    return saved


def restore_tag_fonts(saved):
    for pane, tag, spec, applied in saved or ():
        try:
            raw = _raw(pane)
            if str(pane.tk.call(raw, 'tag', 'cget', tag, '-font')) == applied:     # 俯瞰の間に付け直された字は触らない
                pane.tk.call(raw, 'tag', 'configure', tag, '-font', spec)
        except tk.TclError:
            pass


def _peer_pady(pane):
    """分身の上下の余白: 見出しの見た目を保つ時は欄と同じ（タイトルが上へ寄らない・05:12Z）。前の形は 2px"""
    if keep_head_fonts_on():
        try:
            return int(pane.cget('pady'))
        except (tk.TclError, ValueError):
            pass
    return 2


def _raw(pane):
    return getattr(pane, '_cn_body_raw', None) or pane._w


_UNDO_CALLS = ('insert', 'delete', 'replace', 'see')


def _route_undo(pane, name):
    """Tk 8.6.9 は Undo の一手を、いちばん新しい分身の名前で控える（「分身の名前 insert/delete/mark set insert/see」で
    呼び返す）。起動の4秒後に作るこの分身がいちばん新しくなり、Ctrl+Z の字の戻しが本文の欄の命令（undo_feedback の色・
    タブごとの取り消し・解析の観察者）を素通りした（disabled の間は字も戻らなかった）。2026-11-20 tests_gui_undo_feedback・
    tests_gui_shortcuts_menu で見つかった。title_inline._writer と同じく、分身の名前に来た字の出し入れ（と insert の印・see）
    だけを、生の位置を本文の位置に直して欄の命令へ回す。ほかの命令（yview・index・configure など）は本物の分身へ。
    CN_OVERVIEW_PEER_ROUTE=0 で前の形"""
    if os.environ.get('CN_OVERVIEW_PEER_ROUTE') == '0':
        return
    tkapp = pane.tk
    real = name + '_real'
    try:
        tkapp.call('rename', name, real)
    except tk.TclError:
        return

    def route(*args):
        sub = str(args[0]) if args else ''
        if sub in _UNDO_CALLS or (sub == 'mark' and len(args) > 2 and str(args[1]) == 'set' and str(args[2]) == 'insert'):
            import body_index
            return tkapp.call(pane._w, *body_index.untranslate(args, _head_rows(pane)))
        return tkapp.call(real, *args)
    tkapp.createcommand(name, route)

    def gone(widget):
        if str(widget) == name:
            try:
                tkapp.deletecommand(name)
            except tk.TclError:
                pass
    try:
        tkapp.call('bind', name, '<Destroy>', '+' + pane.register(gone) + ' %W')      # 窓の名前は name のまま
    except tk.TclError:
        pass


def _head_rows(pane):
    try:
        import title_inline
        return int(title_inline.head_rows(pane))
    except Exception:
        return 0


def _back_canvas(pane):
    """欄の後ろで絵を描く Canvas（appearance.Paper._make_back）。無ければ None。"""
    try:
        for child in pane.master.winfo_children():
            if getattr(child, '_correctnote_paper_pane', None) is pane:
                return child
    except Exception:
        pass
    return None


class FastOverview:
    def __init__(self, app):
        self.app = app
        self.peers = {}          # 欄の名前 → 分身の名前
        self.active = None

    # 分身 --------------------------------------------------------------------
    def panes(self):
        app = self.app
        out = [app.editor]
        try:
            unified = app._layout_is_unified()
        except Exception:
            unified = True
        rv = getattr(app, 'result_view', None)
        if not unified and rv is not None:
            try:
                if rv.winfo_ismapped():
                    out.append(rv)
            except tk.TclError:
                pass
        return out

    def _font(self):
        app_module = app_module_of(self.app)
        family = self.app._editor_font()[0]
        return (family, getattr(app_module, 'OVERVIEW_FONT_SIZE', 5))

    def peer(self, pane):
        name = self.peers.get(pane._w)
        tkapp = pane.tk
        if name and int(tkapp.call('winfo', 'exists', name)):
            tkapp.call(name, 'configure', '-font', self._font(), '-pady', _peer_pady(pane),
                       '-background', str(pane.cget('background')),
                       '-foreground', str(pane.cget('foreground')))
            return name
        name = pane._w + SUFFIX
        tkapp.call(_raw(pane), 'peer', 'create', name,
                   '-font', self._font(), '-wrap', str(pane.cget('wrap')),
                   '-spacing1', 0, '-spacing2', 0, '-spacing3', 0, '-pady', _peer_pady(pane), '-padx', str(pane.cget('padx')),
                   '-background', str(pane.cget('background')), '-foreground', str(pane.cget('foreground')),
                   '-borderwidth', 0, '-highlightthickness', 0, '-insertwidth', 0, '-takefocus', 0,
                   '-cursor', str(pane.cget('cursor')), '-state', idle_state(), '-relief', 'flat')
        self.peers[pane._w] = name
        _route_undo(pane, name)
        return name

    def prepare(self):
        """前もって分身を作る（Tk は分身の行の組み立てを裏で少しずつ進める）。"""
        if not enabled(self.app) or self.active is not None:
            return
        for pane in self.panes():
            try:
                self.peer(pane)
            except tk.TclError:
                pass

    # 入る・動かす・出る ----------------------------------------------------------
    def enter(self, event, widget):
        app = self.app
        try:
            top = int(str(app.editor.tk.call(_raw(app.editor), 'index', '@0,0')).split('.')[0])
            h = max(1, app.editor.winfo_height() - 1)
            bottom = int(str(app.editor.tk.call(_raw(app.editor), 'index', '@0,%d' % h)).split('.')[0])
            n = max(1, bottom - top + 1)
        except Exception:
            top, n = 1, 23
        shown = []
        for pane in self.panes():
            name = self.peer(pane)
            tkapp = pane.tk
            back = _back_canvas(pane)
            # 欄の縁（borderwidth・highlightthickness）の内側に重ねる。分身は縁なしなので、そのぶんずらさないと本文の
            # 行頭が左右にずれる（2026-11-20 うにさん「本文の行頭位置が左右に揺れるので、揺れないように」・1px ずれていた）
            try:
                off = int(pane.cget('borderwidth')) + int(pane.cget('highlightthickness'))
            except (tk.TclError, ValueError):
                off = 0
            tkapp.call('place', name, '-in', pane._w, '-x', off, '-y', off, '-relwidth', 1, '-relheight', 1,
                       '-width', -2 * off, '-height', -2 * off, '-bordermode', 'outside')
            if back is not None:
                # 絵の Canvas を欄より前へ（欄の大きい字が透けて見えないように）、分身をそのさらに前へ
                tkapp.call('raise', back._w, pane._w)
            tkapp.call('raise', name)
            tkapp.call(name, 'configure', '-state', 'disabled')        # 俯瞰の間は打てない（出る時に idle_state へ）
            if back is not None:
                try:
                    import paper_window
                    key = paper_window.colorref(pane.winfo_rgb(str(pane.cget('background'))))
                    paper_window.show_through(int(tkapp.call('winfo', 'id', name)), key)
                except Exception:
                    pass
            tkapp.call(name, 'yview', '%d.0' % top)
            shown.append((pane, name, back))
        bookmark_rows_on(app, [pane for pane, _name, _back in shown])
        squashed = squash_padding([pane for pane, _name, _back in shown])
        try:
            small = int(self._font()[1])
        except Exception:
            small = 5
        fonts = shrink_tag_fonts([pane for pane, _name, _back in shown], small)
        gutter_covers = hide_gutters(app)
        self.active = dict(widget=widget, shown=shown, n=n, last_y=event.y_root, accum=0.0, squashed=squashed,
                           press=(getattr(event, 'x_root', 0), event.y_root),
                           fonts=fonts, gutter_covers=gutter_covers)
        app._overview = {'fast': True, 'widget': widget, 'moved': getattr(app, '_view_moved_count', 0),
                         'shown_at': 0.0}
        self._mark()
        try:
            app._scroll_cursor_hide(widget)
        except Exception:
            pass
        watch_right_button(app)
        try:      # 縮小の中の絵文字も色付きで（overview_emoji・2026-11-21 うにさん）
            import overview_emoji
            overview_emoji.for_overview(self, shown)
        except Exception:
            pass
        return 'break'

    def _left(self):
        return self.active['shown'][0][1] if self.active and self.active['shown'] else None

    def _top_raw(self):
        name = self._left()
        tkapp = self.app.editor.tk
        return int(str(tkapp.call(name, 'index', '@0,0')).split('.')[0])

    def _mark(self):
        """分身の上端から、ふだんの字で1画面ぶんに枠（今の形と同じ ov_dest のタグ）。"""
        app = self.app
        try:
            app_module = app_module_of(app)
            tag = app_module.OVERVIEW_DEST_TAG
            hover = getattr(app_module, 'HOVER_BG', '#ddeeff')
            raw = _raw(app.editor)
            tkapp = app.editor.tk
            tkapp.call(raw, 'tag', 'configure', tag, '-background', hover,
                       '-borderwidth', getattr(app_module, 'OVERVIEW_DEST_BORDER', 1), '-relief', 'solid')
            top = max(self._top_raw() + self.active.get('aim', 0), _head_rows(app.editor) + 1)
            tkapp.call(raw, 'tag', 'remove', tag, '1.0', 'end')
            tkapp.call(raw, 'tag', 'add', tag, '%d.0' % top, '%d.0' % (top + self.active['n']))
        except Exception:
            pass

    def motion(self, event):
        a = self.active
        if a is None:
            return 'break'
        want = a.get('warp_to')
        if want is not None:
            # カーソルを戻した後: 戻す前に並んでいた報せ（戻り先から遠い）は数えない（今の形の _edge_warp と同じ）
            if abs(event.y_root - want) > WARP_TOLERANCE and a.get('warp_skip', 0) < WARP_SKIP_MAX:
                a['warp_skip'] = a.get('warp_skip', 0) + 1
                return 'break'
            a.pop('warp_to', None)
            a['warp_skip'] = 0
            a['last_y'] = event.y_root
            return 'break'
        dy = event.y_root - a['last_y']
        a['last_y'] = event.y_root
        if not dy:
            self._edge_warp(event)
            return 'break'
        tkapp = self.app.editor.tk
        left = self._left()
        try:
            # 掴んで動かす（今の形と同じ向き・同じ量: 小さい字の1行の高さ動くごとに1段＝yview scroll 1 units）
            if 'line_h' not in a:
                a['line_h'] = drag_line_height(tkapp, left)
            a['accum'] += dy
            lines = int(a['accum'] / a['line_h'])
            if not lines:
                self._edge_warp(event)
                return 'break'
            a['accum'] -= lines * a['line_h']
            before = self._top_raw()
            aim_before = a.get('aim', 0)
            fwd = -lines
            if fwd < 0 and a.get('aim', 0) > 0:
                back = min(a['aim'], -fwd)              # 上へ: 先に下へ滑らせた枠から戻す
                a['aim'] -= back
                fwd += back
            if fwd:
                self._scroll(left, fwd)
            top = self._top_raw()
            if fwd > 0 and top == before and end_slide_on():
                # 分身が下端に着いて送れない（Tk の Text は最後のページより下へ送れない）: 分身は送らず、範囲の枠だけを
                # 下へ滑らせ、最後の行まで選べるようにする（2026-11-21 06:23Z うにさん「一番下の少し前から、そこより下に
                # 行けなくなります」・今の形の 48-LH' と同じ）。離した時の本文の位置もこの枠の上端
                a['aim'] = min(a.get('aim', 0) + fwd, max(0, self._last_body_row() - top))
            self._watch_stuck(a, lines, before + aim_before, top + a.get('aim', 0), event)
            for pane, name, back in a['shown'][1:]:
                tkapp.call(name, 'yview', '%d.0' % top)                  # 補正欄の分身は同じ行へ
        except tk.TclError:
            pass
        self._mark()
        try:      # 動かした後の絵文字の色付け（空き時間に1回・overview_emoji）
            import overview_emoji
            overview_emoji.moved(self)
        except Exception:
            pass
        self._edge_warp(event)
        return 'break'

    def _watch_stuck(self, a, lines, before, top, event):
        """送ったのに上端が動かないことが続いたら、その時の様子を1回だけ記録する（2026-11-21 05:12Z うにさん「縮小で、
        やはり途中でスクロールが止まる」。写しでは再現できないので、次に起きた時の手がかり）。字は書かない。"""
        if top != before or (lines > 0 and top <= 1) or (lines < 0 and top >= self._last_body_row()):
            a['stuck'] = 0
            return
        a['stuck'] = a.get('stuck', 0) + 1
        if a['stuck'] != STUCK_LOG_AFTER:
            return
        try:
            last = int(str(self.app.editor.tk.call(_raw(self.app.editor), 'index', 'end-1c')).split('.')[0])
        except (tk.TclError, ValueError):
            last = None
        log(self.app, 'stuck', dict(top=top, last=last, lines=lines, line_h=a.get('line_h'),
                                    accum=round(a.get('accum', 0.0), 1), y_root=getattr(event, 'y_root', None),
                                    warp_to=a.get('warp_to'), warp_skip=a.get('warp_skip'), no_warp=a.get('no_warp'),
                                    warped=a.get('warped')))

    def _edge_warp(self, event):
        """カーソルが画面の上下の端に近づいたら、欄の中ほどへ戻す（今の形の app._edge_warp と同じ・カーソルは俯瞰の
        間は隠してある）。端でマウスの動きの報せが来なくなり、下へ進まなくなっていた（2026-11-21 05:01Z）。
        戻せない道具（SetCursorPos が効かない）では戻さない。CN_OVERVIEW_EDGE_WARP=0 で前の形"""
        a = self.active
        if a is None or a.get('no_warp') or os.environ.get('CN_OVERVIEW_EDGE_WARP') == '0':
            return
        app = self.app
        widget = a.get('widget') or app.editor
        try:
            py = int(event.y_root)
            top, h = widget.winfo_rooty(), widget.winfo_height()
            try:
                area = app_module_of(app).monitor_work_area(int(event.x_root), py)
            except Exception:
                area = None
            screen_top, screen_bottom = (area[1], area[3]) if area else (0, widget.winfo_screenheight())
            edge = min(int(getattr(app, 'DRAG_WARP_EDGE', 64)), max(1, (screen_bottom - screen_top) // 4))
            if screen_top + edge < py < screen_bottom - 1 - edge:
                return
            lo = max(top + 1, screen_top + edge + 1)
            hi = min(top + h - 2, screen_bottom - edge - 2)
            if hi <= lo:
                return
            want = (lo + hi) // 2
            x = int(event.x_root) - widget.winfo_rootx()
            got = app._warp_pointer(widget, x, want - top)
        except Exception:
            return
        if got == 'sync':
            a['last_y'] = want
            a['warp_to'] = want
            a['warp_skip'] = 0
            a['warped'] = True
        elif not got:
            a['no_warp'] = True

    def exit(self):
        a, self.active = self.active, None
        app = self.app
        try:      # 縮小の中の絵文字の色付けを外す（overview_emoji）
            import overview_emoji
            overview_emoji.off(self)
        except Exception:
            pass
        if a is None:
            return
        try:
            top = self._top_raw_of(a)
        except Exception:
            top = None
        try:
            app_module = app_module_of(app)
            app.editor.tk.call(_raw(app.editor), 'tag', 'remove', app_module.OVERVIEW_DEST_TAG, '1.0', 'end')
        except Exception:
            pass
        bookmark_rows_off([pane for pane, _name, _back in a['shown']])
        restore_padding(a.get('squashed') or ())
        for pane, _name, _back in a['shown']:
            drop_head_space(pane)
        hide_gutters_off(a.get('gutter_covers'))
        if a.get('warped') and a.get('press'):
            # 端で戻したカーソルは、離したら押した所へ戻す（今の形と同じ）
            try:
                w = a.get('widget') or app.editor
                app._warp_pointer(w, a['press'][0] - w.winfo_rootx(), a['press'][1] - w.winfo_rooty())
            except Exception:
                pass
        restore_tag_fonts(a.get('fonts'))
        for pane, name, back in a['shown']:
            tkapp = pane.tk
            try:
                tkapp.call('place', 'forget', name)
                tkapp.call(name, 'configure', '-state', idle_state())     # 本文の Undo を止めない（idle_state）
                if back is not None:
                    tkapp.call('lower', back._w, pane._w)                 # 絵の Canvas を欄の後ろへ戻す
            except tk.TclError:
                pass
        app._overview = None
        if getattr(app, '_align_skipped_in_overview', False):
            app._align_skipped_in_overview = False
            try:      # 俯瞰の間に止めた行そろえ（app._align_pane_rows）を、出た後に1回
                app.root.after_idle(app._align_pane_rows)
            except Exception:
                pass
        try:
            app._scroll_cursor_restore()
        except Exception:
            pass
        if top is not None:
            body = top - _head_rows(app.editor)
            try:
                if body <= 1:
                    app.editor.yview_moveto(0)
                else:
                    app.editor.yview('%d.0' % body)
            except tk.TclError:
                pass

    def _top_raw_of(self, a):
        name = a['shown'][0][1]
        return int(str(self.app.editor.tk.call(name, 'index', '@0,0')).split('.')[0]) + a.get('aim', 0)

    def _scroll(self, peer, units):
        self.app.editor.tk.call(peer, 'yview', 'scroll', units, 'units')

    def _last_body_row(self):
        try:
            return int(str(self.app.editor.tk.call(_raw(self.app.editor), 'index', 'end-1c')).split('.')[0])
        except (tk.TclError, ValueError):
            return 1


WATCH_MS = 60


def right_button_down(app=None):
    """右ボタンがいま押されているか（Windows の GetAsyncKeyState・左右を入れ替えた設定も見る）。分からなければ None。"""
    import sys
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        vk = 0x01 if user32.GetSystemMetrics(23) else 0x02       # SM_SWAPBUTTON なら物の右は VK_LBUTTON
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return None


def watch_right_button(app, down=None):
    """俯瞰の間、右ボタンが離れていたら必ず出る（2026-11-20 うにさん「左と右を同時にダブルクリックしたら、右クリックを
    離しているのに縮小のままになった」: 右の離しの知らせが、左の押しの掴み（分身・別の欄）へ行って届かなかった）。
    今の形・速い形の両方。今の形は見せる最短の時間（OVERVIEW_MIN_SHOW_S）は待つ。CN_OVERVIEW_BUTTON_WATCH=0 で見張らない"""
    if os.environ.get('CN_OVERVIEW_BUTTON_WATCH') == '0':
        return
    if getattr(app, '_ov_button_job', None) is not None:
        return

    def tick():
        app._ov_button_job = None
        overview = getattr(app, '_overview', None)
        if overview is None or getattr(app, '_closing', False):
            return
        probe = down if down is not None else right_button_down      # 呼ぶ時に引く（差し替えられるように）
        if getattr(app, '_overview_exit_job', None) is None and probe(app) is False:
            import time
            shown = overview.get('shown_at', 0.0) if isinstance(overview, dict) else 0.0
            least = getattr(app, 'OVERVIEW_MIN_SHOW_S', 0.0)
            if overview.get('fast') or time.monotonic() - shown >= least:
                try:
                    app._overview_exit()
                except Exception:
                    pass
                return
        try:
            app._ov_button_job = app.root.after(WATCH_MS, tick)
        except Exception:
            app._ov_button_job = None
    try:
        app._ov_button_job = app.root.after(WATCH_MS, tick)
    except Exception:
        app._ov_button_job = None


def active(app):
    """俯瞰の速い形の最中なら、その FastOverview（本物だけ。作り物の app の属性は数えない）。"""
    ovf = getattr(app, '_ovf', None)
    if isinstance(ovf, FastOverview) and ovf.active is not None:
        return ovf
    return None


def install(app):
    if getattr(app, '_ovf', None) is None:
        app._ovf = FastOverview(app)
    return app._ovf
