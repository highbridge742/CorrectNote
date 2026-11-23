# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""候補を自動で出す2つのオプション（2026-11-21 うにさん）。

・行の末尾で候補を自動で出す（設定 f5_auto_line_end・既定オン）
  「カーソルを移動して、行頭を含む右に文字がない時に、F5再変換を自動で開く。この時文字を打ったら、そのまま入力を
  はじめられるようにする」。カーソルを動かした後（打っている間は出さない）、右に字が無ければ F5 の予測の候補を開く。
・オンマウスで候補を出す（設定 hover_candidates・既定オン）
  「オンマウスした単語の再変換メニューを出す。分割モードでも出す。上下キーやクリックで再変換できる。ただしこの時の
  キー入力は、オンマウスを非表示にしてカーソル位置に入力を開始する」。メモ欄・補正欄の語の上で少し止まると、右クリック
  と同じ再変換の一覧を出す。

どちらも候補の窓は焦点を取らない（本文の欄に焦点のまま・app._make_dropdown の passive）。打った字は本文のカーソルの
位置へそのまま入る（IME の入力も本文の欄のまま）。候補は上下キー（オンマウスの時）・クリックで選ぶ。Esc で閉じる。
行末の候補をキーで選ぶ時は今までどおり F5（焦点を移した一覧で開き直す）。
出さない場面: スクロール・ドラッグ・選択中・俯瞰・引用モード・タイトルの行・ほかの候補の窓が開いている間・アプリが
前に出ていない間。重くしない: 少し待ってから出し、同じ所・同じ語では出し直さない。
CN_AUTO_LINE_END=0／CN_HOVER_CANDIDATES=0 でそれぞれ出さない（前の形）。

2026-11-21 01:37Z うにさんの追加:
・字を消して（BackSpace・Delete）カーソルが動いた後も出す（打った後は今までどおり出さない）。CN_AUTO_AFTER_DELETE=0 で前の形
・タブを移した直後・起動した直後は出さない（カーソルが一度動くまで）。CN_AUTO_SETTLE=0 で前の形
・行の末尾の候補の窓は、下の行の字を隠さないよう、窓が重なる行の字の右の余白へ出す。余白が足りなければ字の上でよいが、
  行頭の1字目は見えるように右へずらす（side_position）。CN_AUTO_SIDE=0 で前の形（カーソルの下）
"""
import os
import time

LINE_END_KEY = 'f5_auto_line_end'
HOVER_KEY = 'hover_candidates'
LINE_END_DELAY_MS = 300      # カーソルが止まってから
HOVER_DELAY_MS = 500         # 語の上で止まってから
HOVER_HIDE_MS = 400          # 語から離れて（一覧の上でなければ）閉じるまで
USER_ACTION_S = 0.6          # 本人のキー・左クリックから、この間に動いたカーソルだけを「本人が動かした」と見る
TYPED_QUIET_S = 0.8          # 打ってからこの間は、行末の候補を出さない（打っている間に出たり消えたりしない）
DELETE_KEYS = ('BackSpace', 'Delete')
SIDE_GAP = 16                # 字の右端から窓までの空き（px）
TAG = 'CorrectNotePassiveCandidates'
BUTTONS = 0x100 | 0x200 | 0x400
MODIFIER_KEYS = ('Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'Caps_Lock', 'Num_Lock',
                 'Win_L', 'Win_R', 'Super_L', 'Super_R', 'Meta_L', 'Meta_R')


def _setting(app, key):
    try:
        value = app.settings.get(key)
    except Exception:
        value = None
    return value is None or bool(value)


def line_end_on(app, environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_AUTO_LINE_END') != '0' and _setting(app, LINE_END_KEY)


def hover_on(app, environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_HOVER_CANDIDATES') != '0' and _setting(app, HOVER_KEY)


def passive(app):
    """焦点を取らずに開いている候補の窓の部品（無ければ None）。"""
    parts = getattr(app, '_dropdown_parts', None)
    if parts and parts.get('passive') and getattr(app, '_dropdown', None) is not None:
        return parts
    return None


def close(app):
    if passive(app) is not None:
        try:
            app._close_dropdown()
        except Exception:
            pass


# 遅れて届いたオンマウスの答えを、出す前に「今も出してよいか」確かめる（2026-11-23 うにさん 14:37Z「縮小中に予測候補が
# 出ました。縮小になる直前にオンマウスしたものが遅れたのだと思います」）。止まった時（頼んだ時）に世代の番号を控え、
# 縮小（俯瞰）・タブ替え・スクロール・打鍵・クリック・焦点が外れた時に番号を進め、出す前に番号が違えば捨てる。
# 番号を進める時に、待っている頼み・見直しの予約も取り消す。出す前には、縮小の最中でないこと（速い形 overview_fast も）・
# 見えている先頭の行が頼んだ時と同じこと（スクロールバー・キーで動いた分）も見る。マウスが語の上かは前から見ている
# （hover_show の _hit）。CN_HOVER_STALE_DROP=0 で前の形
def stale_drop_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_HOVER_STALE_DROP') != '0'


def _in_fast_overview(app):
    try:
        import overview_fast
        return overview_fast.active(app) is not None
    except Exception:
        return False


def bump(app, why=''):
    """オンマウスの世代を進める: 前に頼んだ答え・待っている見直しは、届いても出さない。"""
    if not stale_drop_on():
        return
    app._hover_gen = getattr(app, '_hover_gen', 0) + 1
    _cancel(app, '_hover_job')
    _cancel(app, '_hover_ask_job')
    app._hover_asks = None
    app._hover_waiting = None
    app._hover_want = None


def _top_of(widget):
    try:
        return str(widget.index('@0,0'))
    except Exception:
        return None


def _stamp(app, widget, snap):
    snap['gen'] = getattr(app, '_hover_gen', 0)
    snap['top'] = _top_of(widget)
    return snap


def stale(app, widget, snap):
    """頼んだ時から、出してはいけない形に変わったか。"""
    if not stale_drop_on() or 'gen' not in snap:
        return False
    if snap['gen'] != getattr(app, '_hover_gen', 0):
        return True
    if getattr(app, '_overview', None) is not None or _in_fast_overview(app):
        return True
    if snap.get('top') is not None and _top_of(widget) != snap['top']:
        return True
    return False


def _cancel(app, name):
    job = getattr(app, name, None)
    setattr(app, name, None)
    if job is not None:
        try:
            app.root.after_cancel(job)
        except Exception:
            pass


# --- 本文の欄へ掛ける -------------------------------------------------------------------
def _panes(app):
    return [w for w in (getattr(app, 'editor', None), getattr(app, 'result_view', None)) if w is not None]


def ensure_tags(app):
    """本文の欄・補正欄の bindtags の先頭に TAG（キー・クリック・ホイールを本文より先に見る）。"""
    for w in _panes(app):
        try:
            tags = tuple(w.bindtags())
            if TAG not in tags:
                w.bindtags((TAG,) + tags)
        except Exception:
            pass


def install(app):
    if getattr(app, '_auto_candidates_installed', False):
        return
    app._auto_candidates_installed = True
    root = app.root
    root.bind_class(TAG, '<KeyPress>', lambda e: on_key(app, e))
    root.bind_class(TAG, '<Motion>', lambda e: on_motion(app, e))
    root.bind_class(TAG, '<Leave>', lambda e: on_leave(app, e))
    root.bind_class(TAG, '<ButtonPress>', lambda e: on_press(app, e))
    root.bind_class(TAG, '<MouseWheel>', lambda e: (close(app), _cancel(app, '_hover_job'), bump(app, 'wheel'))[0])
    root.bind_class(TAG, '<FocusOut>', lambda e: _check_focus_later(app))
    ensure_tags(app)


def _check_focus_later(app):
    def check():
        try:
            if app.root.focus_get() is None:      # ほかのアプリへ移った
                close(app)
                bump(app, 'focus')
        except Exception:
            close(app)
    try:
        app.root.after(150, check)
    except Exception:
        pass


# --- 出さない場面 -----------------------------------------------------------------------
def _in_head(widget, raw_index):
    try:
        import title_inline
        raw = getattr(widget, '_cn_body_raw', None)
        if raw is None:
            return False
        row = int(str(widget.tk.call(raw, 'index', raw_index)).split('.')[0])
        return row <= int(title_inline.head_rows(widget))
    except Exception:
        return False


def busy(app, widget):
    """出すと邪魔な場面か。"""
    if getattr(app, '_closing', False):
        return True
    if getattr(app, '_dropdown', None) is not None and passive(app) is None:
        return True                       # ほかの（焦点を取った）候補の窓が開いている
    if getattr(app, '_overview', None) is not None or getattr(app, '_pick_mode', None):
        return True
    if stale_drop_on() and _in_fast_overview(app):
        return True                       # 俯瞰の速い形（overview_fast）も俯瞰（CN_HOVER_STALE_DROP）
    drag = getattr(app, '_drag', None)
    if drag:
        return True
    inertia = getattr(app, '_scroll_inertia', None)
    if getattr(inertia, 'job', None) is not None:
        return True
    if getattr(app, '_quick_win', None) is not None:
        try:
            if app.root.focus_get() is not None and str(app.root.focus_get()).startswith(str(app._quick_win)):
                return True
        except Exception:
            pass
    try:
        if widget.tag_ranges('sel'):
            return True
    except Exception:
        return True
    try:
        if app.root.focus_get() is None:  # アプリが前に出ていない
            return True
    except Exception:
        return True
    return False


# --- 行の末尾 -----------------------------------------------------------------------------
def cursor_changed(app, widget):
    """カーソルが動いた（_sync_cursor_line から・軽い: 予約だけ）。"""
    if widget is not getattr(app, 'editor', None):
        return
    if passive(app) is not None and passive(app).get('passive') == 'line_end':
        where = _where(widget)
        if where != passive(app).get('where'):
            close(app)                    # 行末を離れた
    if noun_warm_anywhere():
        warm_nouns(app, widget)           # 行末の自動の候補が切ってあっても・プログラムの動きでも（F5 で使う）
    if not line_end_on(app):
        return
    if (os.environ.get('CN_AUTO_USER_ONLY') != '0'
            and time.monotonic() - (getattr(app, '_auto_user_at', None) or -1e9) > USER_ACTION_S):
        # 本人のキー・左クリックで動いた時だけ（2026-11-21 07:44Z うにさん「解析が進むと、クリックせずとも予測候補が
        # 出ることがあるようだ」: 解析の結果を当てる・自動反映で字を置き換える・タブを組み直す時に、プログラムが
        # カーソルを動かしたのを「動いた」と見ていた）。CN_AUTO_USER_ONLY=0 で前の形
        return
    _cancel(app, '_line_end_job')
    try:
        app._line_end_job = app.root.after(LINE_END_DELAY_MS, lambda: line_end_check(app))
    except Exception:
        app._line_end_job = None
    if not noun_warm_anywhere():
        warm_nouns(app, widget)


# 周りの名詞を前もって数える（2026-11-21 軽量化）。行頭の予測は上下40行の名詞を数える（初めての行の辺りで 130ms・
# 同じ所は 23ms）。待つ 0.3 秒の間に、空いた時に少しずつ（4行ずつ）数えて控えておき、開く時に待たせない。答えは同じ
# （同じ関数で同じ行を数えるだけ）。名詞を使う所（行が空・行頭の候補だけ）だけ。CN_AUTO_NOUN_WARM=0 で前の形
WARM_ROWS_PER_STEP = 4
# 名詞の下ごしらえは、カーソルが少し止まってから始める（2026-11-22）。前はカーソルが動いて 1ms 後に始め、エンターで
# 空の行へ移るたびに周りの行の名詞を本体で数えていた: 打鍵の直後に本体が塞がり、未解析の印の時計がそのエンターの
# 描き直しと重なって、行番号を1打で4回描いた（tests_gutter_once・期待は2回まで）。続けて打てば（カーソルが動けば）
# 取り消す（warm_nouns の頭の _cancel）。行の末尾の候補は打ってから TYPED_QUIET_S 待って出るので、その前に済む。
# CN_AUTO_NOUN_WARM_LATER=0 で前の形（1ms 後）
WARM_DELAY_MS = 150


# 周りの名詞の下ごしらえは、カーソルがどこで止まっても始める（2026-11-22・軽量化）。前は行頭（と行頭の候補の後）で
# 止まった時だけで、行末や行の途中から空の行へ移ってすぐ F5 を押すと、周りの約70行の名詞を本体でその場で数えて
# 一覧が開くまで約 240ms 待った（2,000行の写し）。行ごとの名詞は行の字をかぎに控えるので、2回目からは変わった行だけ。
# 行末の自動の候補を切っていても F5 の予測は周りの名詞を使うので、その時も始める。CN_AUTO_NOUN_WARM_ANYWHERE=0 で前の形
def noun_warm_anywhere():
    return os.environ.get('CN_AUTO_NOUN_WARM_ANYWHERE') != '0'


def warm_nouns(app, widget):
    _cancel(app, '_noun_warm_job')
    if os.environ.get('CN_AUTO_NOUN_WARM') == '0':
        return
    try:
        import f5_predict
        if not f5_predict.clip_nouns_on():
            return
        before = widget.get('insert linestart', 'insert')
        if before.strip() and not noun_warm_anywhere():
            whole = widget.get('1.0', '3.0')
            if not f5_predict.after_head(app, before, f5_predict.wide_for(widget, whole) or f5_predict.has_wide(before)):
                return
        row = int(str(widget.index('insert')).split('.')[0])
        last = int(str(widget.index('end-1c')).split('.')[0])
        rows = [r for r in range(max(1, row - f5_predict.AROUND_ROWS), min(last, row + f5_predict.AROUND_ROWS) + 1)]
    except Exception:
        return

    def step():
        app._noun_warm_job = None
        try:
            import f5_predict
            done = 0
            while rows and done < WARM_ROWS_PER_STEP:
                r = rows.pop(0)
                line = widget.get('%d.0' % r, '%d.end' % r)
                if line.strip() and line not in f5_predict._NOUN_MEMO:
                    f5_predict._row_nouns(line)
                    done += 1
            if rows:
                app._noun_warm_job = app.root.after(1, step)
        except Exception:
            app._noun_warm_job = None
    try:
        first = 1 if os.environ.get('CN_AUTO_NOUN_WARM_LATER') == '0' else WARM_DELAY_MS
        app._noun_warm_job = app.root.after(first, step)
    except Exception:
        app._noun_warm_job = None


def _where(widget):
    try:
        return str(widget.index('insert'))
    except Exception:
        return None


def line_end_check(app, now=None):
    """右に字が無ければ、F5 の予測の候補を焦点を取らずに開く。開いたら True。"""
    app._line_end_job = None
    w = getattr(app, 'editor', None)
    if w is None or not line_end_on(app):
        return False
    now = time.monotonic() if now is None else now
    edited = getattr(app, '_last_edit_at', 0.0) or 0.0
    if now - edited < TYPED_QUIET_S:
        deleted = getattr(app, '_auto_deleted_at', None)
        if not (deleted is not None and deleted >= edited - 0.5 and os.environ.get('CN_AUTO_AFTER_DELETE') != '0'):
            return False                  # 打っている（消した後は出す）
    try:
        if app.root.focus_get() is not w:
            return False
    except Exception:
        return False
    if busy(app, w) or _in_head(w, 'insert'):
        return False
    import f5_predict
    if not f5_predict.enabled() or not f5_predict.right_is_empty(w):
        return False
    if getattr(app, '_auto_scroll_hold', False) and os.environ.get('CN_AUTO_SCROLL_HOLD') != '0':
        return False                      # スクロールの後、クリックかキーでカーソルを動かすまで（05:16Z）
    if jump_held(app):
        return False                      # PageUp・1行目・ブックマーク・目次・検索などで飛んだ後（14:13Z）
    if now - (getattr(app, '_auto_scrolled_at', None) or -1e9) < SCROLL_QUIET_S:
        return False                      # スクロールした直後（スクロールで動いたカーソル）
    shown_now = passive(app)
    if (shown_now is not None and shown_now.get('passive') == 'hover'
            and os.environ.get('CN_AUTO_HOVER_FIRST') != '0'):
        return False                      # オンマウスの一覧が出ている間は、行の末尾の予測で置き換えない（06:33Z）
    if (getattr(app, '_hover_asks', None) and getattr(app, '_hover_ask_job', None) is not None
            and os.environ.get('CN_AUTO_HOVER_FIRST') != '0'):
        return False                      # オンマウスの一覧が子の答えを待っている間も（出てすぐ替わるちらつきを出さない）
    where = _where(w)
    if not _settled(app, where):
        return False                      # 起動・タブの切り替えの直後
    shown = passive(app)
    if shown is not None and shown.get('where') == where:
        return False                      # 同じ所には出し直さない
    if getattr(app, '_line_end_dismissed', None) == where:
        return False                      # Esc で閉じた所
    try:
        from app import _python_text_position as _pos
    except Exception:
        _pos = None
    try:
        import sys
        mod = sys.modules.get(type(app).__module__)
        _pos = getattr(mod, '_python_text_position', None) or _pos
        row, col = _pos(w, w.index('insert'))
    except Exception:
        return False
    app._dropdown_passive = 'line_end'
    try:
        opened = bool(app._f5_predict_open(w, row, col, 'main'))
    except Exception:
        opened = False
    finally:
        app._dropdown_passive = None
    if opened and passive(app) is not None:
        passive(app)['where'] = where
    return opened


# 飛んだ移動の後は出さない（2026-11-21 14:13Z うにさん「以下でカーソル移動した場合は予測候補を出さない／ページアップキー
# ／ページダウンキー／Ctrl+Home または1行目ボタンで移動／Ctrl+End または最終行ボタンで移動／Alt+上下またはブックマークボタン
# または目次ジャンプで移動した場合／検索でジャンプした場合／デリートキーで改行を消した場合」）。行の末尾の自動の候補・
# 続けて出す予測（predict_chain）のどちらも出さない。スクロールの後と同じく、その後の左クリックか、ほかのキー（カーソルキー・
# 打鍵）で元に戻る。F5 を押して開く予測はそのまま。CN_AUTO_SKIP_JUMPS=0 で前の形
JUMP_KEYS = ('Prior', 'Next', 'KP_Prior', 'KP_Next')


def skip_jumps_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_AUTO_SKIP_JUMPS') != '0'


def jumped(app):
    """飛んだ移動をした（ボタン・目次・検索・キー）: 止めを立て、待っている表示を取り消す。"""
    if not skip_jumps_on():
        return
    app._auto_jump_hold = True
    _cancel(app, '_line_end_job')
    parts = passive(app)
    if parts is not None and parts.get('passive') == 'line_end':
        close(app)


def jump_held(app):
    return bool(getattr(app, '_auto_jump_hold', False)) and skip_jumps_on()


def _is_jump_key(event):
    """PageUp・PageDown と、改行を消す Delete。Ctrl+Home・End と Alt+上下は、それぞれの移動の道（_goto_document_edge・
    _goto_bookmark）で立てる。"""
    keysym = getattr(event, 'keysym', '') or ''
    if keysym in JUMP_KEYS:
        return True
    if keysym in ('Delete', 'KP_Delete'):
        w = getattr(event, 'widget', None)
        try:
            if w is not None and not w.tag_ranges('sel') and w.get('insert') == chr(10):
                return True
        except Exception:
            pass
    return False


# スクロールした後は出さない（2026-11-21 03:01Z うにさん「スクロールした後も予測が出るので、ここでは出さない」）。
# スクロールで本文のカーソルが画面の中へ動くと、カーソルが動いたとして行の末尾の候補が出ていた。ホイール・右ドラッグと
# 惰性・スクロールバー（app._close_menu_on_scroll）から呼び、待っている表示を取り消し、SCROLL_QUIET_S の間は出さない。
# 止まった後にカーソルを自分で動かせば、また出る。CN_AUTO_SCROLL_QUIET=0 で前の形
SCROLL_QUIET_S = 1.0


# スクロールした後は、クリックやキーでカーソルを動かすまで出さない（2026-11-21 05:16Z うにさん「スクロール後に、予測候補が
# 開くことがあります。スクロールしたあとは、クリックやキーによる移動をするまで予測こうほを出さない」）。前は止まってから
# 1秒だけ待っていたので、スクロールでカーソルが後から動くと出た。CN_AUTO_SCROLL_HOLD=0 で前の形（1秒だけ）


def on_press(app, event):
    close(app)
    _cancel(app, '_hover_job')
    bump(app, 'press')                    # クリック・右ダブルクリック（縮小）: 頼んでいた答えは出さない
    if getattr(event, 'num', None) == 1:
        app._auto_scroll_hold = False     # 左クリックでカーソルを置いた
        app._auto_jump_hold = False       # 飛んだ移動の後の止めも下ろす（14:13Z）
        app._auto_user_at = time.monotonic()
    return None


def scrolled(app):
    if os.environ.get('CN_AUTO_SCROLL_QUIET') == '0':
        return
    app._auto_scrolled_at = time.monotonic()
    app._auto_scroll_hold = True          # クリック（左）かキーで下ろす（on_press・on_key）
    _cancel(app, '_line_end_job')
    _cancel(app, '_hover_job')
    app._hover_want = None
    bump(app, 'scroll')


def settle(app):
    """起動・タブの切り替え（app._load_active_tab）: カーソルが一度動くまで、行の末尾の候補を出さない。"""
    close(app)
    _cancel(app, '_line_end_job')
    bump(app, 'tab')                      # タブの切り替え・起動
    st = app._auto_settle = {'where': None, 'at': time.monotonic()}
    app._line_end_dismissed = None

    def remember():
        if getattr(app, '_auto_settle', None) is st and st['where'] is None:
            st['where'] = _where(getattr(app, 'editor', None))      # 読み込んだ後のカーソルの所
    try:
        app.root.after_idle(remember)
    except Exception:
        pass


SETTLE_S = 1.0     # 起動・タブの切り替えから、この間は出さない


def _settled(app, where):
    st = getattr(app, '_auto_settle', None)
    if st is None or os.environ.get('CN_AUTO_SETTLE') == '0':
        return True
    if time.monotonic() - st.get('at', 0.0) < SETTLE_S:
        st['where'] = where
        return False
    if st.get('where') is None:
        st['where'] = where               # 開いた時のカーソルの所（ここでは出さない）
        return False
    if st['where'] == where:
        return False
    app._auto_settle = None               # 動いた
    return True


def side_position(app, width, height, area):
    """予測の候補の窓の置き場 (x, y)（画面の座標）。分からなければ None（今までどおりカーソルの下）。
    ・マウスが本文の欄の上にあれば、その近く（2026-11-21 01:55Z うにさん「予測の候補は、マウスカーソルの近くに出す。
      なるべく余白に出す」）: 窓の上端はマウスの少し下、窓が重なる行の字の右の余白へ（マウスが余白にあればマウスの右）
    ・マウスが欄の外なら、カーソルの行の下の行の横の余白（01:37Z）
    どちらも余白が足りなければ字の上で、行頭の1字目が見えるように右へずらす。CN_AUTO_SIDE=0 で前の形・
    CN_AUTO_NEAR_POINTER=0 でマウスの近くにしない"""
    if os.environ.get('CN_AUTO_SIDE') == '0':
        return None
    w = getattr(app, 'editor', None)
    try:
        info = _dline(w, 'insert')
        if not info:
            return None
        top = int(info[1])
        line_h = max(1, int(info[3]))
        pane_w, pane_h = w.winfo_width(), w.winfo_height()
        rx, ry = w.winfo_rootx(), w.winfo_rooty()
        y0 = top + line_h                 # 窓の上端（欄の中の座標）
        px = None
        if os.environ.get('CN_AUTO_NEAR_POINTER') != '0':
            try:
                gx, gy = w.winfo_pointerxy()
                if 0 <= gx - rx < pane_w and 0 <= gy - ry < pane_h:
                    px, y0 = gx - rx, gy - ry + POINTER_GAP
            except Exception:
                px = None
        right, first = _text_edges(w, y0, height, pane_h)
        a_l, a_t, a_r, a_b = area
        limit = min(a_r, rx + pane_w)
        x = rx + right + SIDE_GAP
        if px is not None:
            x = max(x, rx + px + POINTER_GAP)   # マウスが余白にあれば、マウスの右
        if x + width > limit:
            x = max(rx + first + 4, limit - width)        # 余白が足りない: 字の上。行頭の1字目は見えるように
        if keep_in_pane_on():
            # 本文の欄（分割ではメモ欄）の外へははみ出さない: 補正欄を隠さない（2026-11-21 05:09Z うにさん「分割で余白が
            # ない時、メモ欄の右端に出して補正欄は隠さない」）。CN_AUTO_KEEP_IN_PANE=0 で前の形
            x = max(rx, min(x, limit - width))
        x = max(a_l, min(x, a_r - width))
        y = ry + y0
        if y + height > a_b:
            y = max(a_t, y - height - line_h - (POINTER_GAP if px is not None else 0))
        return int(x), int(y)
    except Exception:
        return None


POINTER_GAP = 14


def keep_in_pane_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_AUTO_KEEP_IN_PANE') != '0'


def _raw_call(w, *args):
    """本文の欄の生の Text へ（title_inline の行番号の変換を通さない）。'@x,y' の位置は生の欄で引かないと、
    変換を通した欄ではどの y でも同じ行が返り、字の右端が測れず、窓が余白ではなく補正欄の上へ出た
    （2026-11-21 05:09Z うにさん「分割モードで、予測が補正欄を隠している」）"""
    raw = getattr(w, '_cn_body_raw', None)
    return w.tk.call(raw or w._w, *args)


def _ints(w, got):
    try:
        parts = w.tk.splitlist(got)
    except Exception:
        return None
    return tuple(int(float(x)) for x in parts) if parts else None


def _dline(w, index):
    try:
        return _ints(w, _raw_call(w, 'dlineinfo', index))
    except Exception:
        return None


def _bbox(w, index):
    try:
        return _ints(w, _raw_call(w, 'bbox', index))
    except Exception:
        return None


def _text_edges(w, y0, height, pane_h):
    """欄の中の y0 から height の範囲に重なる表示の行の、字の右端と1字目の右端（欄の中の x）。"""
    right = first = 0
    d = _dline(w, '@0,%d' % max(0, y0 - 1))
    y = int(d[1]) if d else y0
    steps = 0
    while y < min(pane_h, y0 + height) and steps < 400:
        steps += 1
        d = _dline(w, '@0,%d' % y)
        if not d:
            break
        if int(d[1]) + max(1, int(d[3])) <= y:
            # 字の最後の行より下（'@0,y' は最後の行を返す）: もう行は無い。ここで止めないと y が戻って回り続け、
            # 本体が応答なしになった（2026-11-21 03:50Z うにさん「起動したら重すぎて応答なし」）
            break
        right = max(right, int(d[0]) + int(d[2]))
        try:      # その表示の行の1字目（空の行の改行の字は数えない: 改行の字の枠は行の右端まで伸びる）
            ch = str(_raw_call(w, 'get', '@0,%d' % y))
        except Exception:
            ch = ''
        b = _bbox(w, '@0,%d' % y) if ch and ch != chr(10) else None
        if b:
            first = max(first, int(b[0]) + int(b[2]))
        y = int(d[1]) + max(1, int(d[3]))
    return right, first


# --- オンマウス -----------------------------------------------------------------------------
# オンマウスでは、解析の子に語の単位を尋ねない（2026-11-21 軽量化）。分割のメモ欄の行の単位が控えに無いと、
# app._editor_line_units は子に尋ねる（analysis_async.ask_child）。ask_child は子が解いている途中の行の求めを取り消して
# から答えを待つ（最大 8 秒）ので、マウスを置いただけで、重い行の解析を捨てて解き直しにし、本体も待たせていた。
# 控えのある行（解析が済んだ行）だけオンマウスの一覧を出す（右クリック・F5 は今までどおり）。CN_HOVER_NO_CHILD_ASK=0 で前の形
def _units_ready(app, widget, event):
    if os.environ.get('CN_HOVER_NO_CHILD_ASK') == '0':
        return True
    try:
        if app._layout_is_unified():
            return True                       # 統合は line_units（子に尋ねない）
        row = int(str(widget.index('@%d,%d' % (event.x, event.y))).split('.')[0])
        import ui_projection
        results = ui_projection.results(app)
        if not 0 < row <= len(results):
            return False
        projected = results[row - 1] or {}
        key = (projected.get('original'), projected.get('corrected'), False)
        return key in (getattr(app, '_suspect_units_cache', None) or {})
    except Exception:
        return False


# オンマウスで候補を出すのは入力カーソルの近くに限定（2026-11-23 01:21 JST うにさん「オプションに、『オンマウスで候補を
# 出すのは入力カーソルの近くに限定』を追加。デフォルトはオフ。デバッグメニューに、この近くが上下何行かのパラメータを出す。
# デフォルトを10。上限は100」）。オンの時、マウスの下の行（論理行＝行番号の数え方）が入力カーソルの行から上下
# HOVER_NEAR_ROWS 行を超えていれば出さない。0 はカーソルの行だけ。設定 hover_near_cursor（既定オフ）・
# CN_HOVER_NEAR_CURSOR=0 で設定に関係なく前の形
HOVER_NEAR_ROWS = 10
HOVER_NEAR_ROWS_MAX = 100


def near_cursor_on(app, environ=None):
    environ = os.environ if environ is None else environ
    if environ.get('CN_HOVER_NEAR_CURSOR') == '0':
        return False
    try:
        return app.settings.get('hover_near_cursor') is True
    except Exception:
        return False


def near_cursor(app, widget, event):
    """マウスの下の行が入力カーソルの近くか（限定がオフなら いつも True）。"""
    if not near_cursor_on(app):
        return True
    try:
        row = int(str(widget.index('@%d,%d' % (event.x, event.y))).split('.')[0])
        cursor = int(str(app.editor.index('insert')).split('.')[0])
        limit = max(0, min(HOVER_NEAR_ROWS_MAX, int(HOVER_NEAR_ROWS)))
    except Exception:
        return True
    return abs(row - cursor) <= limit


def _hit(app, widget, event):
    """(欄の名, 行, 語) か None。"""
    if not near_cursor(app, widget, event):
        return None
    try:
        if widget is app.editor:
            if _in_head(widget, '@%d,%d' % (event.x, event.y)):
                return None
            if not _units_ready(app, widget, event):
                if not plan_units_on():
                    return None
                hit = _plan_hit(app, widget, event)      # 控えから戻した行: 品詞のフォントの控えの切れ目で語1つ
            else:
                hit = app._editor_unit_under_pointer(event)
            pane = 'editor'
        elif widget is getattr(app, 'result_view', None):
            if app._layout_is_unified() or _in_head(widget, '@%d,%d' % (event.x, event.y)):
                return None
            hit = app._unit_under_pointer(event)
            pane = 'result'
        else:
            return None
    except Exception:
        return None
    if not hit:
        return None
    row, unit = hit
    if not (unit.get('text') or '').strip():
        return None
    if not _word_like(app, widget, pane, row, unit):
        return None
    return pane, row, unit


# オンマウスは語1つの時だけ（2026-11-22 うにさん「未解析行にオンマウスすると行全体が選択されて、長い分析が出る。単語単体に
# できないのであれば出さない。／URLのオンマウスで、品詞の分析は要らない」）。
# ・語の切れ目の控えに無い所（メモ欄で解析の単位が無く、空白で区切った塊を仕立てた所・_fallback_unit）は出さない
# ・行まるごと（HOVER_WHOLE_LINE_MIN 字より長い）や、HOVER_WORD_MAX 字より長い単位は出さない
# ・URL（http:// https:// www. で始まる並び）に掛かる単位は出さない（品詞の判定・同音の語・かな表記は要らない）
# 右クリック・F5 は今まで通り。CN_HOVER_WORD_ONLY=0・CN_HOVER_URL_NO_POS=0 でそれぞれ前の形
HOVER_WORD_MAX = 24
HOVER_WHOLE_LINE_MIN = 12
_URL = None


def _url_spans(line):
    global _URL
    if _URL is None:
        import re
        _URL = re.compile(r'(?:https?://|www\.)[^\s\u3000]+', re.I)
    return [m.span() for m in _URL.finditer(line or '')]


def _word_like(app, widget, pane, row, unit):
    text = unit.get('text') or ''
    try:
        line = widget.get('%d.0' % row, '%d.end' % row)
    except Exception:
        line = ''
    if os.environ.get('CN_HOVER_URL_NO_POS') != '0':
        start, end = unit.get('start'), unit.get('end')
        for a, b in _url_spans(line):
            if isinstance(start, int) and isinstance(end, int):
                if start < b and end > a:
                    return False
            elif text and text in line[a:b]:
                return False
        if '://' in text or text.lower().startswith('www.'):
            return False
    if os.environ.get('CN_HOVER_WORD_ONLY') == '0':
        return True
    word = text.strip()
    if len(word) > HOVER_WORD_MAX:
        return False
    if word == line.strip() and len(word) > HOVER_WHOLE_LINE_MIN:
        return False
    if pane == 'editor' and unit.get('_from_plan'):
        return True                               # 品詞のフォントの控えの切れ目（語1つ）
    if pane == 'editor':
        # 解析の単位から取れた語か（取れなければ app が空白で区切った塊を仕立てている）
        try:
            units = app._units_for_row(row) or []
        except Exception:
            units = []
        key = (unit.get('start'), unit.get('end'), unit.get('text'))
        if not any((u.get('start'), u.get('end'), u.get('text')) == key for u in units):
            return False
    return True


# 控えから戻した行（答えはあるが、語の切れ目の控え _suspect_units_cache が空の行）では、品詞のフォントの控え
# （boundary_colors の plan: 品詞ごとの (品詞, 始め, 終わり)）の切れ目で語1つを作る（2026-11-22 うにさん「縦線がなくても
# 未解析の状態だったのだと思っている。品詞のフォントはついていたが」）。品詞のフォントが付いている行なら切れ目は分かる。
# 解析の子には尋ねない・解き直しも起こさない（一覧を開く時の _redo_row_now も止める）。控えが無ければ今どおり出さない。
# CN_HOVER_UNITS_FROM_PLAN=0 で前の形
def plan_units_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_HOVER_UNITS_FROM_PLAN') != '0'


def _plan_hit(app, widget, event):
    try:
        import sys
        import unicodedata
        mod = sys.modules.get(type(app).__module__)
        pos = getattr(mod, '_python_text_position')
        index = widget.index('@%d,%d' % (event.x, event.y))
        row, col = pos(widget, index)
        text = widget.get('%d.0' % row, '%d.end' % row)
        import boundary_colors
        plan = boundary_colors.plan_for(app, widget, row, text)
    except Exception:
        return None
    if not plan or len(plan) < 3 or not plan[2]:
        return None
    for major, start, end in plan[2]:
        if not (start <= col < end) or not (0 <= start < end <= len(text)):
            continue
        word = text[start:end]
        if not any(unicodedata.category(c)[0] in 'LN' for c in word):
            return None                           # 記号・空白だけ
        return row, {'start': start, 'end': end, 'text': word, 'base': word, 'reading': '', 'prev': '', 'next': '',
                     'kind': 'plain', 'detail': None, 'pos': major, '_from_plan': True}
    return None


def _key(hit):
    pane, row, unit = hit
    return (pane, row, unit.get('start'), unit.get('end'), unit.get('text'))


# 軽くする（2026-11-21 08:17Z うにさん「挙動は、軽量化できるところがないか探って」）。前はマウスの動きの知らせごとに
# 語を見分けていて（_hit・メモ欄は行の単位を組み直すので1回 15ms）、メモ欄の上でマウスを動かすだけで主スレッドが
# 塞がった。動きの知らせでは字の位置だけを見て（0.1ms 以下）、止まってから HOVER_DELAY_MS 後に1回だけ語を見分ける。
# 出ている一覧の語の上にいる間は何もしない。CN_HOVER_LIGHT=0 で前の形
def _light_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_HOVER_LIGHT') != '0'


def _pos_at(widget, event):
    try:
        row, col = str(widget.index('@%d,%d' % (event.x, event.y))).split('.')
        return int(row), int(col)
    except Exception:
        return None


def on_motion(app, event):
    if not hover_on(app):
        return None
    widget = event.widget
    if int(getattr(event, 'state', 0) or 0) & BUTTONS:
        _cancel(app, '_hover_job')
        return None
    if _light_on():
        return _on_motion_light(app, event, widget)
    return _on_motion_old(app, event, widget)


def _on_motion_light(app, event, widget):
    pos = _pos_at(widget, event)
    pane = 'editor' if widget is getattr(app, 'editor', None) else 'result'
    shown = passive(app)
    if shown is not None and shown.get('passive') == 'hover':
        k = shown.get('hover_key')
        if pos is not None and k and k[0] == pane and k[1] == pos[0] and k[2] <= pos[1] < k[3]:
            _cancel(app, '_hover_hide_job')     # 出ている一覧の語の上
            _cancel(app, '_hover_job')
            return None
        _hide_later(app)
    if pos is None:
        _cancel(app, '_hover_job')
        return None
    _cancel(app, '_hover_job')                  # 止まるまで待ち直す
    snap = _stamp(app, widget, dict(x=event.x, y=event.y, x_root=event.x_root, y_root=event.y_root))
    try:
        app._hover_job = app.root.after(HOVER_DELAY_MS, lambda: _hover_rest(app, widget, snap))
    except Exception:
        app._hover_job = None
    return None


def _hover_rest(app, widget, snap):
    """止まった: ここで初めて語を見分けて出す。"""
    from types import SimpleNamespace
    app._hover_job = None
    event = SimpleNamespace(x=snap['x'], y=snap['y'], x_root=snap['x_root'], y_root=snap['y_root'], widget=widget,
                            state=0)
    hit = _hit(app, widget, event)
    if not hit:
        return False
    return hover_show(app, widget, _key(hit), snap)


def _on_motion_old(app, event, widget):
    hit = _hit(app, widget, event)
    shown = passive(app)
    key = _key(hit) if hit else None
    if shown is not None and shown.get('passive') == 'hover':
        if key is not None and shown.get('hover_key') == key:
            _cancel(app, '_hover_hide_job')
            return None
        _hide_later(app)
    if key is None:
        _cancel(app, '_hover_job')
        app._hover_want = None
        return None
    if getattr(app, '_hover_want', None) == key and getattr(app, '_hover_job', None) is not None:
        return None
    _cancel(app, '_hover_job')
    app._hover_want = key
    snap = _stamp(app, widget, dict(x=event.x, y=event.y, x_root=event.x_root, y_root=event.y_root))
    try:
        app._hover_job = app.root.after(HOVER_DELAY_MS, lambda: hover_show(app, widget, key, snap))
    except Exception:
        app._hover_job = None
    return None


def on_leave(app, event):
    _cancel(app, '_hover_job')
    app._hover_want = None
    shown = passive(app)
    if shown is not None and shown.get('passive') == 'hover':
        _hide_later(app)
    return None


def _hide_later(app):
    if getattr(app, '_hover_hide_job', None) is not None:
        return

    def hide():
        app._hover_hide_job = None
        shown = passive(app)
        if shown is None or shown.get('passive') != 'hover' or shown.get('pointer_inside'):
            return
        close(app)
    try:
        app._hover_hide_job = app.root.after(HOVER_HIDE_MS, hide)
    except Exception:
        app._hover_hide_job = None


# 解析の子が働いている間は、オンマウスの一覧を出さない（2026-11-22 うにさん 11-21 16:55Z「文字を打ってると応答がなくなる。
# 右の補正欄が空欄になって動かないが待つと動く」）。オンマウスの一覧（同音の語・助詞・類語）は解析の子に作らせ
# （analysis_async.ask_child）、子が解いている行を取り消してから答えを最大8秒待ち、来なければ本体で表を読んで作っていた。
# 打っている間・控えから戻した行を解き直している間にマウスが本文の上で止まるたびに、本体が約10〜15秒止まっていた
# （うにさんのアプリで「応答なし」が 10秒×4回・写しでも解析中のオンマウス1回で 0.1〜0.7秒）。解析が待っている・子が
# 他を解いている・子がいない時は出さない（次に止まった時にまた見る）。右クリック・F5 は今まで通り。
# CN_HOVER_SKIP_WHEN_BUSY=0 で前の形
# 出さない場面を「子が実際に解いている間」に絞る（2026-11-22 01:59Z うにさん「オンマウスしても候補が出ません」）。前は解析が
# 待っているだけでも出さず（_foreground_analysis_pending）、裏の先読みの間はずっと出なかった。子が空いていれば一覧の中身の
# 問い合わせはすぐ答えが返る（解いている行を取り消すことも無い）。子が今の行・同じ子の裏の行を解いている時と、子がいない時は
# 出さず、マウスが同じ語の上にある間は HOVER_RETRY_MS ごとに見直して、空いたら出す（HOVER_RETRY_S まで）。
# CN_HOVER_ASYNC=0 で前の形（解析が待っている間はずっと出さない）
HOVER_RETRY_MS = 250
HOVER_RETRY_S = 10.0


def analysis_busy(app):
    if os.environ.get('CN_HOVER_SKIP_WHEN_BUSY') == '0':
        return False
    if os.environ.get('CN_HOVER_ASYNC') == '0':
        try:
            if app._foreground_analysis_pending():
                return True
        except Exception:
            pass
    if getattr(app, '_async_request', None) is not None:
        return True
    if getattr(app, '_async_background_request', None) is not None:
        try:
            import memory_usage
            if memory_usage.shares_worker(app):
                return True               # 同じ子が裏の行を解いている（問い合わせはその後ろに並んで待つ）
        except Exception:
            return True
    try:
        import analysis_async
        if not analysis_async.child_alive(app):
            return True                   # 子がいない（作り直すと本体が待つ）
    except Exception:
        return True
    return False


# 打っている最中は作らない（2026-11-22・一覧を作る1回が本体で最大約 300ms。打鍵が待たされる）。最後の打鍵から
# HOVER_TYPED_QUIET_S たってから（マウスが止まっている間は _retry_later で見直す）。CN_HOVER_TYPED_QUIET=0 で前の形
HOVER_TYPED_QUIET_S = 1.0


def hover_typed_recently(app, now=None):
    if os.environ.get('CN_HOVER_TYPED_QUIET') == '0':
        return False
    now = time.monotonic() if now is None else now
    last = max(getattr(app, '_last_edit_at', 0.0) or 0.0, getattr(app, '_auto_key_at', 0.0) or 0.0)
    return now - last < HOVER_TYPED_QUIET_S


def _retry_later(app, widget, key, snap):
    """子が空くのを待って出し直す（本体は待たない・時計で見直すだけ）。マウスが動けば _hit の見分けで止まる。
    解析が続いている間は、子が1行を解き終えて次の行を頼む前の一瞬（app._analyze_slice → run_waiting_hover）に出す。"""
    if os.environ.get('CN_HOVER_ASYNC') == '0':
        return
    since = snap.setdefault('busy_since', time.monotonic())
    if time.monotonic() - since > HOVER_RETRY_S:
        app._hover_waiting = None
        return
    app._hover_waiting = (widget, key, snap)
    _cancel(app, '_hover_job')
    try:
        app._hover_job = app.root.after(HOVER_RETRY_MS, lambda: hover_show(app, widget, key, snap))
    except Exception:
        app._hover_job = None


# --- 子への頼みを待たない（2026-11-22・一覧を作る1回の本体の約 300ms のうち、約 250ms は子の答えを本体で待つ所だった）---------
# オンマウスで一覧を作る時だけ、analysis_async.ask_child の代わりに、頼みを子の列へ出して待たずに抜ける（_Deferred）。子は今の
# 行を解き終えてから順に答える（取り消さない）。答えは時計（HOVER_ASK_POLL_MS）で見に行き、そろったら組み立てを続ける。続ける
# 前に、打鍵が HOVER_TYPED_QUIET_S 以内にあった・マウスが語から外れた時はやめる。本体の「古い答えの片付け」（Worker.poll）で
# 答えが消えないよう、受け取り口で先に取り分ける。CN_HOVER_ASYNC=0 で前の形（本体で待つ）
HOVER_ASK_POLL_MS = 15
HOVER_ASK_TIMEOUT_S = 6.0


class _Deferred(BaseException):
    """子に頼んだ答えを待っている（例外を飲み込む所を通り抜けるよう BaseException）。"""


class _GiveUp(BaseException):
    """待たない頼みができない（子がいない・状態が違う・答えが誤り）。"""


class _Busy(BaseException):
    """子が本体の行を解いている（今は頼まない。行と行の間に出し直す）。"""


# 子は「新しい頼みが来たら、解いている頼みと並んでいる頼みを捨てて新しい方を解く」（analysis_worker._serve_requests）。
# オンマウスの頼みを、本体の行を解いている子へ出すと、本体の行が捨てられて答えが来ず、解析がそこで止まっていた
# （2026-11-22 19:49 JST うにさん「いま解析が進んでいないように見える」・子は2つとも CPU 0%・残り約320行のまま）。
# 本体の行が子にある間は頼まず、行と行の間（run_waiting_hover・子が空いている）に、本体で待つ形（子はすぐ答える）で出す。
# 答えが来ないまま待ちの時間を過ぎた時も、行と行の間に出し直す。CN_HOVER_ASK_NO_SUPERSEDE=0 で前の形
def _no_supersede_on():
    return os.environ.get('CN_HOVER_ASK_NO_SUPERSEDE') != '0'


def worker_in_use(app):
    """本体の頼み（打った行・行・裏のタブの行）が子に出ていて、答えをまだ受け取っていないか。"""
    if getattr(app, '_async_request', None) is not None:
        return True
    if getattr(app, '_async_background_request', None) is not None:
        try:
            import memory_usage
            return bool(memory_usage.shares_worker(app))
        except Exception:
            return True
    return False


def _async_ask_on():
    return os.environ.get('CN_HOVER_ASYNC') != '0'


def _drain(worker):
    """子の答えの受け口を空けて、worker.ready に置く（Worker.poll と同じ置き方。片付けはしない）。"""
    import queue as _queue
    from analysis_worker import merge_usage
    while True:
        try:
            identifier, result, error = worker.outbox.get_nowait()
        except _queue.Empty:
            break
        if isinstance(identifier, tuple):
            worker.partials.setdefault(identifier[1], []).append(result)
            continue
        merge_usage(result)
        worker.ready[identifier] = (result, error)


def _keep_mine(app, worker):
    """本体が自分の答えを受け取る時（Worker.poll）、その前にオンマウスの答えを取り分ける（片付けで消えないように）。"""
    if getattr(worker, '_cn_hover_poll', False):
        return
    real = worker.poll

    def poll(request_id, _real=real, _worker=worker):
        # オンマウスと F5（f5_async）の、待たない頼みの答えを取り分ける
        for mine in (getattr(app, '_hover_asks', None), (getattr(app, '_f5_wait', None) or {}).get('asks')):
            if not mine or not mine.get('pending'):
                continue
            try:
                _drain(_worker)
                for key, rid in list(mine['pending'].items()):
                    got = _worker.ready.pop(rid, None)
                    if got is not None:
                        mine['got'][key] = got
                        mine['pending'].pop(key, None)
            except Exception:
                pass
        return _real(request_id)
    worker.poll = poll
    worker._cn_hover_poll = True


def _hover_ask(app, store=None):
    def ask(app_, task):
        import pickle
        import analysis_async
        mine = app_._hover_asks if store is None else store(app_)
        try:
            key = pickle.dumps(task, pickle.HIGHEST_PROTOCOL)
        except Exception:
            raise _GiveUp()
        if key in mine['done']:
            return mine['done'][key]
        if key in mine['got']:
            result, error = mine['got'].pop(key)
            if error:
                raise _GiveUp()
            mine['done'][key] = result
            return result
        if key not in mine['pending']:
            worker = getattr(app_, '_correction_worker', None)
            try:
                alive = worker is not None and not getattr(worker, 'closed', False) and worker.process.is_alive()
            except Exception:
                alive = False
            if not alive or analysis_async.state_key(app_) != getattr(app_, '_worker_state', None):
                raise _GiveUp()               # 子がいない・子の持つ状態が違う（本体で作らない・次に止まった時にまた見る）
            if _no_supersede_on() and worker_in_use(app_):
                raise _Busy()                 # 本体の行を捨てさせない（行と行の間に出し直す）
            _keep_mine(app_, worker)
            mine['pending'][key] = worker.submit(task, None)
            if gap_async_on():
                # 子が空いている時に出した頼み: 答えが来るまで解析の次の行を頼まない（頼むと、この頼みが捨てられる）。
                # 待ちを外す見分けに、頼んだ子・解析の段取りを控える（hold_analysis）
                mine['gap'] = True
                mine['worker'] = worker
                mine['work'] = getattr(app_, '_analyze_work', None)
        raise _Deferred()
    return ask


def _poll_asks(app, widget, key, snap):
    app._hover_ask_job = None
    mine = getattr(app, '_hover_asks', None)
    if not mine or mine.get('key') != key:
        return
    worker = getattr(app, '_correction_worker', None)
    try:
        if worker is not None and mine['pending']:
            _drain(worker)
            for k, rid in list(mine['pending'].items()):
                got = worker.ready.pop(rid, None)
                if got is not None:
                    mine['got'][k] = got
                    mine['pending'].pop(k, None)
    except Exception:
        app._hover_asks = None
        return
    if mine['pending']:
        if time.monotonic() - mine['since'] > HOVER_ASK_TIMEOUT_S:
            app._hover_asks = None            # 答えが来ない（片付けで消えた等）: やめる。次に止まった時にまた見る
            if _no_supersede_on():
                _retry_later(app, widget, key, snap)   # 本体の行が後から頼まれて捨てられた: 行と行の間に出し直す
            return
        try:
            app._hover_ask_job = app.root.after(HOVER_ASK_POLL_MS, lambda: _poll_asks(app, widget, key, snap))
        except Exception:
            app._hover_asks = None
        return
    hover_show(app, widget, key, snap, between_rows=True)     # そろった: 組み立てを続ける（打鍵・マウスの動きはそこで見る）


# 行と行の間のオンマウスを、本体で待たずに作る（2026-11-23・軽量化）。前は行と行の間に子へ尋ねて本体で答えを待ったので、
# 解析の最中のオンマウスで本体が 100〜260ms 止まった（写し・300行）。今は、子が空いている行と行の間に、待たない頼みを
# 出し、その答えがそろうまで（最長 HOVER_ASK_TIMEOUT_S）次の行を頼まずに待つ（解析の方が少し待つ。本体は止まらない・
# 子は本体の行を捨てない）。CN_HOVER_GAP_ASYNC=0 で前の形（行と行の間は本体で待つ）
class HoldAnalysis(BaseException):
    """行と行の間でオンマウスの頼みを出した: この回は次の行を頼まない（app._analyze_slice が受ける）。"""


def gap_async_on():
    return os.environ.get('CN_HOVER_GAP_ASYNC') != '0' and _no_supersede_on() and _async_ask_on()


def hold_analysis(app):
    """オンマウスの頼みの答えを待っている間は、解析の次の行を頼まない（app._analyze_slice の頭）。
    外す時（待ち続けない）: 答えがそろった・HOVER_ASK_TIMEOUT_S を過ぎた・頼んだ子がいない／作り直された・タブを替えた
    など解析の段取りが変わった・本体の頼みが出ている。続けてオンマウスしても解析が止まり続けないよう、前の待ちの後に
    解析が1行も進んでいなければ、新しい待ちには入らない（オンマウスの頼みは子に後回しにされ、後でまた見る）"""
    if not gap_async_on():
        return False
    mine = getattr(app, '_hover_asks', None)
    if not mine or not mine.get('gap') or not mine.get('pending'):
        return False
    if time.monotonic() - mine.get('since', 0.0) > HOVER_ASK_TIMEOUT_S:
        return False
    if getattr(app, '_async_request', None) is not None:
        return False
    worker = mine.get('worker')
    if worker is not None:
        try:
            alive = (worker is getattr(app, '_correction_worker', None) and not getattr(worker, 'closed', False)
                     and worker.process.is_alive())
        except Exception:
            alive = False
        if not alive:
            return False
    if 'work' in mine and mine.get('work') != getattr(app, '_analyze_work', None):
        return False
    if not mine.get('holding'):
        pos = getattr(app, '_analyze_pos', None)
        last = getattr(app, '_hover_hold_pos', None)
        if last is not None and pos is not None and pos <= last and _analysis_left(app):
            return False                   # 前の待ちの後、まだ1行も進んでいない: 解析を先に
        mine['holding'] = True
        app._hover_hold_pos = pos
    return True


def _analysis_left(app):
    try:
        return getattr(app, '_analyze_pos', 0) < len(getattr(app, '_analyze_todo', None) or ())
    except Exception:
        return False


def run_waiting_hover(app):
    """解析の行と行の間（子が1行を解き終え、次の行を頼む前・子が空いている）に、待っているオンマウスの一覧を出す。
    子に頼む一覧の中身はすぐ答えが返り、解いている行を取り消すことも無い（app._analyze_slice から）。"""
    waiting = getattr(app, '_hover_waiting', None)
    if not waiting or os.environ.get('CN_HOVER_ASYNC') == '0':
        return False
    if getattr(app, '_async_request', None) is not None:
        return False
    app._hover_waiting = None
    widget, key, snap = waiting
    if time.monotonic() - snap.get('busy_since', time.monotonic()) > HOVER_RETRY_S:
        return False
    if gap_async_on() and getattr(app, '_cn_in_analyze_slice', False):
        try:
            shown = bool(hover_show(app, widget, key, snap, between_rows=True, idle_child=False))
        except Exception:
            return False
        mine = getattr(app, '_hover_asks', None)
        if not shown and mine and mine.get('pending'):
            mine['gap'] = True
            raise HoldAnalysis()           # 頼みを出した: 次の行はまだ頼まない（子が先にこの答えを返す）
        return shown
    try:
        return bool(hover_show(app, widget, key, snap, between_rows=True, idle_child=_no_supersede_on()))
    except Exception:
        return False


def hover_show(app, widget, key, snap, between_rows=False, idle_child=False):
    """語の上で止まった: 右クリックと同じ再変換の一覧を、焦点を取らずに出す。出したら True。"""
    from types import SimpleNamespace
    app._hover_job = None
    if stale(app, widget, snap):
        if getattr(app, '_hover_asks', None) and app._hover_asks.get('key') == key:
            app._hover_asks = None
        return False                      # 頼んだ後に縮小・タブ替え・スクロール・打鍵・クリックがあった（遅れて届いた）
    if not hover_on(app) or busy(app, widget):
        return False
    if hover_typed_recently(app):
        _retry_later(app, widget, key, snap)
        return False                      # 打ってから HOVER_TYPED_QUIET_S たつまで作らない（打鍵を待たせない）
    if not between_rows and not _async_ask_on() and analysis_busy(app):
        _retry_later(app, widget, key, snap)
        return False                      # 解析の子が働いている間は出さない（応答なし・11-21 16:55Z）。空いたら出す
    shown = passive(app)
    if shown is not None and shown.get('hover_key') == key:
        return False
    # まだ同じ語の上か（止まっている間に動いた・欄を出た）
    try:
        px, py = widget.winfo_pointerxy()
        x, y = px - widget.winfo_rootx(), py - widget.winfo_rooty()
        if not (0 <= x < widget.winfo_width() and 0 <= y < widget.winfo_height()):
            return False
    except Exception:
        x, y = snap['x'], snap['y']
        px, py = snap['x_root'], snap['y_root']
    event = SimpleNamespace(x=x, y=y, x_root=px, y_root=py, widget=widget, state=0)
    hit = _hit(app, widget, event)
    if not hit or _key(hit) != key:
        return False
    pane, row, unit = hit
    close(app)
    if os.environ.get('CN_AUTO_HOVER_FIRST') != '0':
        # オンマウスで開いた直後に、待っていた行の末尾の予測が開いてオンマウスの一覧を消していた（2026-11-21 06:33Z
        # うにさん「オンマウスで単語を開いてすぐ、行頭の予測候補が表示されてオンマウス単語が消されてしまう」）。
        # 待っている行の末尾の表示を取り消す。CN_AUTO_HOVER_FIRST=0 で前の形
        _cancel(app, '_line_end_job')
    status = None
    try:
        status = app.status.cget('text')
    except Exception:
        pass
    app._dropdown_passive = 'hover'
    no_redo = bool(unit.get('_from_plan'))
    if no_redo:
        app._redo_row_now = lambda i: False       # 品詞の控えから作った語: 一覧を開いても解き直しを起こさない
    # 行と行の間（子が空いている・本体の次の行はこの後で頼む）は本体で待つ形で頼む。待たない頼みにすると、すぐ後の
    # 本体の行の頼みに捨てられて答えが来ない（_Busy の前の説明）
    asking = _async_ask_on() and not idle_child
    real_ask = None
    if asking:
        mine = getattr(app, '_hover_asks', None)
        if not mine or mine.get('key') != key:
            app._hover_asks = mine = dict(key=key, pending={}, got={}, done={}, since=time.monotonic())
        import analysis_async
        real_ask = analysis_async.ask_child
        analysis_async.ask_child = _hover_ask(app)
    deferred = False
    busy_now = False
    try:
        if pane == 'editor':
            app._open_editor_dropdown(event, row, unit)
        else:
            app._open_dropdown(event, row, unit)
    except _Deferred:
        deferred = True                            # 子の答えを待つ（本体は待たない）
    except _Busy:
        app._hover_asks = None
        busy_now = True
    except _GiveUp:
        app._hover_asks = None
    except Exception:
        pass
    finally:
        if real_ask is not None:
            import analysis_async
            analysis_async.ask_child = real_ask
        app._dropdown_passive = None
        if no_redo:
            try:
                del app._redo_row_now
            except Exception:
                pass
    if busy_now:
        _retry_later(app, widget, key, snap)       # 子が本体の行を解いている: 行と行の間に出し直す
        return False
    if deferred:
        _cancel(app, '_hover_ask_job')
        try:
            app._hover_ask_job = app.root.after(HOVER_ASK_POLL_MS, lambda: _poll_asks(app, widget, key, snap))
        except Exception:
            app._hover_asks = None
        return False
    if asking:
        app._hover_asks = None
    shown = passive(app)
    if shown is None:
        if status is not None:
            try:
                app.status.config(text=status)       # 候補が無い語: 知らせの文を書き換えたままにしない
            except Exception:
                pass
        return False
    shown['hover_key'] = key
    return True


def popup_made(app, dd, parts):
    """焦点を取らない窓ができた（app._make_dropdown から）。一覧の上にいる間はオンマウスの窓を閉じない。"""
    def enter(_e=None):
        parts['pointer_inside'] = True
        _cancel(app, '_hover_hide_job')

    def leave(_e=None):
        parts['pointer_inside'] = False
        if parts.get('passive') == 'hover':
            _hide_later(app)
    def refocus():
        # 一覧をクリックすると窓へ焦点が移る（一覧は閉じる）: 本文の欄へ戻す
        try:
            focus = app.root.focus_get()
            if focus is None or focus not in _panes(app):
                app.editor.focus_set()
        except Exception:
            pass
    try:
        dd.bind('<Enter>', enter, add='+')
        dd.bind('<Leave>', leave, add='+')
        lb = parts.get('lb')
        if lb is not None:
            lb.bind('<ButtonRelease-1>', lambda e: app.root.after_idle(refocus), add='+')
    except Exception:
        pass


# --- キー -----------------------------------------------------------------------------
def on_key(app, event):
    """焦点を取らない窓が開いている時、本文の欄より先にキーを見る。"""
    keysym = getattr(event, 'keysym', '') or ''
    char = getattr(event, 'char', '') or ''
    if keysym not in MODIFIER_KEYS:
        app._auto_scroll_hold = False     # キーで動かした・打った（スクロールの後の止めを下ろす）
        app._auto_user_at = time.monotonic()
        app._auto_key_at = app._auto_user_at      # 最後の打鍵（オンマウスの一覧は、ここから少したってから作る）
        bump(app, 'key')
        if _is_jump_key(event):
            jumped(app)                   # PageUp・PageDown・改行を消す Delete（14:13Z）
        else:
            app._auto_jump_hold = False   # ほかのキー（カーソルキー・打鍵）で飛んだ後の止めを下ろす
    if keysym in DELETE_KEYS and not char.strip():
        app._auto_deleted_at = time.monotonic()      # 消した（このあとの本文の変化は打ったのではない）
    elif len(char) == 1 and char.isprintable():
        app._auto_deleted_at = None
    parts = passive(app)
    if parts is None:
        return None
    if keysym in MODIFIER_KEYS:
        return None
    if keysym == 'Escape':
        if parts.get('passive') == 'line_end':
            app._line_end_dismissed = parts.get('where')
        close(app)
        return 'break'
    printable = len(char) == 1 and char.isprintable()
    if parts.get('passive') == 'hover' and not printable:
        if keysym in ('Up', 'Down') and os.environ.get('CN_HOVER_ARROWS_MOVE_CURSOR') == '0':
            # 前の形: 上下キーで一覧の中を選ぶ。2026-11-21 07:34Z うにさん「オンマウスの再変換では、上下キーはカーソル
            # 移動にする」から、上下キーは一覧を閉じて本文のカーソルを動かす（下の「そのほかのキー」と同じ）。
            # 選ぶのはクリック。CN_HOVER_ARROWS_MOVE_CURSOR=0 で前の形
            move = parts.get('move')
            if move is not None:
                move(-1 if keysym == 'Up' else 1)
            return 'break'
        if keysym in ('Return', 'KP_Enter'):
            lb = parts.get('lb')
            try:
                if lb is not None and lb.curselection():
                    pick = parts.get('pick')
                    if pick is not None:
                        pick()
                    return 'break'
            except Exception:
                pass
    if (parts.get('passive') == 'line_end' and keysym == getattr(app, 'CANDIDATE_KEY', 'F5')
            and os.environ.get('CN_F5_FOCUS_IN_PLACE') != '0'):
        return None                       # F5: 閉じずに、同じ所の一覧へ焦点を移す（app._f5_focus_in_place・17:48Z）
    # そのほかのキー: 窓を閉じて、本文の欄にそのまま渡す（カーソルの位置へ入力を始める）
    close(app)
    if parts.get('passive') == 'hover':
        try:
            focus = app.root.focus_get()
            if focus is not getattr(app, 'editor', None) and printable:
                app.editor.focus_set()
        except Exception:
            pass
    return None
