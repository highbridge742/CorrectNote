# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""本文の上のタイトルと目次（2026-11-15 うにさん「タイトルと目次を実装します。1行目の上に、フォントサイズ26で文字を1行
打てる欄を用意。品詞のサイズ倍率と色は適用するが、補正はしない。別名保存すると、タイトルが空欄であれば保存ファイル名を
入れる。タイトルの文字もコピーできるが、部分的コピーだとしても拡大表示はしない。白い枠は付ける。タイトルの下に目次を
並べる。ブックマークした行の文字をミラーリングして並べ、青文字で下線を付けリンクの見た目をする。クリックするとその
ブックマーク行にジャンプする。ブックマークした行が空欄かスペースのみであれば、そのあとに文字が書かれた行をミラーリング
する。ブックマークが最終行だったり、空欄のまま次のブックマークが来た場合は、対象外として目次には載せない。目次が全く
なければ、そのスペースは省かれる。タイトルと目次は下にスクロールすると見切れて見えなくなる。行番号は付けず、分割モード
でも、左右繋がった欄として表示する」）。

作り:
- 本文の1行目の上に、欄の高さぶんの余白を作る（1行目の頭の字だけに掛けたタグ PAD_TAG の spacing1）。左右の欄
  （editor・result_view）に同じ高さで掛けるので、左右の行はそろったまま。余白はタグなので、本文の字・保存する本文・
  解析には入らない。本文が変わるたびに「1行目だけ」に掛け直す。
- 欄（Frame: タイトルの Text 1行・26pt と、その下の目次のリンク）は、左右の欄をまたぐ箱（app._body）に place で重ね、
  本文の1行目の表示行の頭の位置に合わせる。1行目が見えなくなったら隠す（上へ見切れる）。
- タイトルはタブの控えの 'doc_title' に持つ（タブの見出しの 'title' とは別・.txt の本文には書かない）。解析・補正は
  通さない。品詞の倍率と色は本文と同じ決まり（pos_font）で塗る。コピーは白い枠だけ（拡大はしない）。
- 目次が長い時（ブックマークが多い時）は、全部並べて余白を伸ばす。
- CN_TITLE_TOC=0 で欄も余白も出ない（前の形）。

2026-11-15 うにさんの指摘で直した所（12件）:
- 目次・タイトルの上のホイールも、右ドラッグのスクロールも、本文へ渡す（_forward_wheel・_forward_right）。
- タイトルにカーソルがある時の F2・括弧は、タイトルの字に（app._bracket_widget）。ルーラーは何もしない（app._toggle_ruler）。
- 元に戻す・やり直しは、タイトルと本文で1つの列（TitleUndo。本文の Undo の流れに「本文以外の一手」として入れる）。
- 1行目の行番号は、余白の下の字の高さに描く（app の LineNumberGutter が PAD_TAG を余白の行として扱う）。
- 目次の字は本文の字の 0.85 倍（8〜11pt）。目次の下に区切りの線（テーマの線の色・目次が無い時は無し）。
- タブを替えたら、目次をその場で作り直す（switched。打鍵の待ちに乗せない）。
- 重さ: 余白の spacing を替える時だけ掛け直し、位置が同じなら place し直さない（スクロール1回 120ms → 20ms ほど）。
  打鍵では目次が替わった時だけ高さを測り直す（update_idletasks を打鍵の流れで呼ばない）。
- タイトルは本文の欄の上端へ寄せる（本文の上の内側の余白 pady のうち 2px だけ残す）。

2026-11-15 うにさんの指摘（3件）:
- タイトル・目次の上から始めた右ドラッグでもカーソルを隠す（app._scroll_panes に欄の部品を入れる・widgets()）。
- 目次と本文が重なって見えた: 絵のあるテーマでは本文の欄が透過色の窓（WS_EX_LAYERED・paper_window）で、Windows は
  透過色の子の窓を、上に重ねたふつうの窓より後に描く。欄が本文の下になり、本文の地（透過色）の所だけ欄が見えて、
  目次の行の間に本文の字が出ていた。欄も透過の窓（不透明の LWA_ALPHA 255）にして、同じ描き方の中で上に置く
  （_match_layered。黒い帯が出たので、下の直しで本文の欄の子の窓に替えた）。タブを替えた時は、欄の高さを字の大きさから測ってその場で余白と欄を決める（_measure。描き直しを
  待って測ると、その間は前の高さの余白のまま欄が置かれた）。
- 目次の字は本文の字の 0.85 倍に +1pt（本文 12pt なら 11pt・9〜12pt）。

2026-11-15 うにさんの指摘（2件・上の透過の窓の後）:
- 速いスクロールで目次に黒い帯が出た: 透過の窓（LWA_ALPHA）は、出し直した・大きさが変わった直後、中身を描くまで
  黒い地のまま見える。欄を本文の欄（Text）の子の窓にした（本文の欄の外に重ねない）。子の窓は本文の欄の描き方の中で
  上に描かれるので、絵のあるテーマでも透過の窓にしなくてよく、黒い地も、本文の字が透けることも無い。欄は本文の欄の
  内側だけに置く（はみ出すと窓を閉じる時に落ちやすい・tk-place-outside-interior）。分割の右の欄は、行をそろえる
  余白だけ（字は左の欄に）。
- タイトル・目次からの右ドラッグが、しばらく動かず、動くと目次がまとめて見切れた: 右ドラッグは行の単位で送るので、
  余白の付いた1行目（欄の高さぶん）が1回で消えていた。1行目・2行目が見えている間は画素で送る（app._drag_motion・
  _title_pad_scroll。本文から始めた右ドラッグも同じ）。
- 分割の右の欄（2026-11-15 最初の仕様「分割モードでも、左右繋がった欄として表示する」）: 右の欄（補正欄の Text）の子の
  窓に、左と同じ中身の写し（Mirror）を置き、左の欄の幅＋仕切りの幅だけ左へずらして描く。仕切りをまたいで続いた1枚に
  見える。タイトルの Text は1つ（左。幅は左右を合わせた幅）で、右の写しのクリックは本物のタイトルの同じ字の所へ
  カーソルを移す。カーソル・選択は写しにも描く。目次のクリック・ホイール・右ドラッグは右からも同じ。
- まだ黒い帯・空の瞬間・ずれた目次の行が見えた（2026-11-15 うにさん）: Tk の Text はスクロールを画面の画素のずらし
  （ScrollWindowEx）で行い、子の窓（欄）の所の画素も一緒にずらす。子の窓の描き直しは WM_PAINT 待ちで、Windows は
  ほかの知らせ（続くホイール）が無くなるまで WM_PAINT を出さないので、速いスクロールの間ずっと、ずれた画素・空の地が
  残った。欄を置き直したら、その場で欄の部品の描き直しを Tk の idle に積む（_repaint: 地の色を掛け直すと Tk は
  WM_PAINT を待たずに描く）。行番号の列の、余白の高さの所は地の色の板で覆う（絵の点が透けた・_cover_gutters）。
"""
import time
import os
import tkinter as tk
import tkinter.font as tkfont

ENV = 'CN_TITLE_TOC'
PAD_TAG = 'cn_title_pad'
TITLE_SIZE = 26
TITLE_SIZE_MAX = 60         # デバッグのパラメータの上限（2026-11-16 うにさん「タイトルのフォントサイズをデバッグパラメータに」）
TOC_SIZE = 12               # 目次の字の上限（本文の字の 0.85 倍＋1・9〜12）
TOC_SCALE = 0.85
TOC_POINT = 0               # 目次の字の大きさ（デバッグのパラメータ）。0 は本文の字から決める（上の決め方）
TOC_POINT_MAX = 40
TOP_GAP = 2                 # タイトルの上に残す余白（窓の端の余白の決まり）
LINK_LIGHT = '#1f5fbf'      # 明るい欄で読める青
LINK_DARK = '#9cc8ff'       # 暗い欄で読める青（2026-11-15 うにさん「ダークモードで目次の青色が見えにくい」: 前は #7fb2ff）
# 暗い欄は、地の色とのコントラストが LINK_CONTRAST 以上になるまで、この順に明るい青を選ぶ（テーマごとに地が違う）
LINK_DARK_STEPS = ('#9cc8ff', '#a9d0ff', '#b6d7ff', '#c3dfff', '#d0e6ff')
LINK_CONTRAST = 7.0


def _luminance(rgb):
    """相対輝度（WCAG）。rgb は 0〜1 の3つ。"""
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(rgb_a, rgb_b):
    a, b = _luminance(rgb_a), _luminance(rgb_b)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _hex_rgb(color):
    color = color.lstrip('#')
    return tuple(int(color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def link_color(bg_rgb, dark):
    """目次の字の色。暗い地なら、地とのコントラストが LINK_CONTRAST 以上の、いちばん落ち着いた青（本文より目立ちすぎない）。"""
    if not dark:
        return LINK_LIGHT
    for color in LINK_DARK_STEPS:
        if contrast(_hex_rgb(color), bg_rgb) >= LINK_CONTRAST:
            return color
    return LINK_DARK_STEPS[-1]


def enabled(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get(ENV) != '0'


# --- 決まり（画面を使わない） ------------------------------------------------
def toc_entries(lines, bookmarks):
    """目次に載せる [(飛ぶ行, 見せる行, 見せる字)]。行は1始まり。
    ブックマークの行に字があれば、その行。空欄か空白だけなら、次のブックマークより前で、その後に初めて字が書かれた行を
    映す（飛ぶのはブックマークの行）。後ろに字の行が無い（最終行・空欄のまま次のブックマーク）なら載せない。"""
    rows = sorted(b for b in set(bookmarks or ()) if isinstance(b, int) and 1 <= b <= len(lines))
    out = []
    for k, row in enumerate(rows):
        text = lines[row - 1]
        if text.strip():
            out.append((row, row, text.strip()))
            continue
        stop = rows[k + 1] if k + 1 < len(rows) else len(lines) + 1
        for shown in range(row + 1, stop):
            if lines[shown - 1].strip():
                out.append((row, shown, lines[shown - 1].strip()))
                break
    return out


def title_for_save_as(title, path):
    """別名保存の時のタイトル: 空欄なら保存したファイルの名前（拡張子を除く）。字があればそのまま。"""
    if (title or '').strip():
        return title
    base = os.path.basename(path or '')
    return os.path.splitext(base)[0]


def one_line(text):
    """タイトルは1行だけ（貼り付けた改行の後ろは捨てる）。"""
    return (text or '').replace('\r', '').split('\n', 1)[0]


# --- 保存と読み込み（2026-11-15 うにさん「本文の1行目として保存します。また、その下は空白行として保存する」） ---
# 保存: タイトルに字があれば、ファイルの頭に「タイトルの1行＋空白行1行」、その後に本文。空なら本文だけ。
# 読み込み: 1行目に字があり2行目が空（空白だけも空）で、しかもこのアプリがそのファイルをそのタイトルで保存した記録が
# 在る時だけ、1行目をタイトル・2行目を区切りとして取り、3行目からを本文にする。どちらかが違えば全部を本文のまま
# （何も失わない）。記録は savedata の doc_titles.json（ファイルの絶対パス → 保存したタイトル）。中で持つ本文
# （解析・行番号・ブックマーク）はタイトルと区切りを除いたまま。CN_TITLE_TOC=0 なら足し引きしない
RECORD_NAME = 'doc_titles.json'
RECORD_MAX = 2000


def _key(path):
    return os.path.normcase(os.path.realpath(path or ''))


def load_records(folder):
    import json
    try:
        with open(os.path.join(folder, RECORD_NAME), encoding='utf-8') as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_record(folder, path, title):
    """path をこのタイトル付きで保存した記録（空のタイトルなら記録を消す）。"""
    import json
    records = load_records(folder)
    key = _key(path)
    if (title or '').strip():
        records.pop(key, None)
        records[key] = one_line(title)
        while len(records) > RECORD_MAX:
            records.pop(next(iter(records)))
    elif key in records:
        records.pop(key)
    else:
        return
    target = os.path.join(folder, RECORD_NAME)
    tmp = target + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False)
        os.replace(tmp, target)
    except Exception:
        pass


def compose_for_save(title, content, metadata, fmt):
    """ファイルに書く本文と書式: タイトルがあれば「タイトル＋空白行＋本文」（改行の形は本文の主な形）。"""
    title = one_line(title)
    if not enabled() or not title.strip():
        return content, metadata
    value = fmt.clean(metadata, content)
    whole = title + '\n\n' + content
    if value['endings']:
        value = dict(value, endings=value['newline'] * 2 + value['endings'])
    return whole, value


def split_loaded(content, metadata, path, folder, fmt):
    """読み込んだ中身から (本文, 書式, タイトル)。タイトルとして取れなければ (中身, 書式, '')。"""
    if not enabled() or not content:
        return content, metadata, ''
    lines = content.split('\n')
    if len(lines) < 2 or not lines[0].strip() or lines[1].strip():
        return content, metadata, ''
    if load_records(folder).get(_key(path)) != lines[0]:
        return content, metadata, ''
    body = '\n'.join(lines[2:])
    value = fmt.clean(metadata, content)
    if value['endings']:
        rest = value['endings'][2:]
        value = dict(value, endings=rest if any(c != value['newline'] for c in rest) else '')
    return body, fmt.clean(value, body), lines[0]


# --- 欄 ----------------------------------------------------------------------
class TitleToc:
    def __init__(self, app):
        self.app = app
        # 欄は本文の欄（Text）の子の窓（本文の上に別の窓として重ねない・2026-11-15 黒い帯・字が透けた件）
        self.parent = getattr(app, 'editor', None) or app._body
        # 欄を入れる箱（見えている所だけを切り取る）。1行目が少し上へ送られた時は、欄も上の分が見切れて残りが見える
        self.clip = tk.Frame(self.parent, bd=0, highlightthickness=0)
        self.frame = tk.Frame(self.clip, bd=0, highlightthickness=0)
        # 元に戻すは本文と1つの列（TitleUndo）なので、タイトルの Text 自身の履歴は使わない
        self.title = tk.Text(self.frame, height=1, wrap='none', relief='flat', bd=0, highlightthickness=0,
                             padx=14, pady=0, undo=False, width=1)
        self.title.pack(fill='x', pady=(0, 4))
        self.toc = tk.Frame(self.frame, bd=0, highlightthickness=0)
        self.toc.pack(fill='x', padx=14, pady=(0, 4))
        # 目次の下の区切りの線（目次が無い時は出さない）
        self.rule = tk.Frame(self.frame, height=1, bd=0, highlightthickness=0)
        self.rule.pack(fill='x', padx=14, pady=(0, 6))
        self.links = []
        self._placed = None
        self._title_text = ''
        self._title_last = False        # 最後にカーソルがあったのがタイトルか（ボタン・メニューは焦点を動かさない）
        self._entries = None
        self._height = None
        self._colors = None
        self._loading = False
        self.title.bind('<Return>', lambda e: 'break')
        self.title.bind('<KP_Enter>', lambda e: 'break')
        self.title.bind('<<Paste>>', self._paste)
        self.title.bind('<<Modified>>', self._modified)
        self.title.bind('<FocusIn>', lambda e: setattr(self, '_title_last', True), add=True)
        editor = getattr(app, 'editor', None)
        if editor is not None:
            try:
                editor.bind('<FocusIn>', lambda e: setattr(self, '_title_last', False), add=True)
            except Exception:
                pass
        self.undo = TitleUndo(self)
        for seq, kind in (('<<Undo>>', 'undo'), ('<<Redo>>', 'redo')):
            self.title.bind(seq, lambda e, k=kind: self.undo.from_title(k))
        for seq in ('<Control-c>', '<Control-C>', '<Control-Insert>'):
            self.title.bind(seq, self._copy)
        self.parent.bind('<Configure>', lambda e: self.position(), add=True)
        body = getattr(app, '_body', None)
        if body is not None and body is not self.parent:
            body.bind('<Configure>', lambda e: self.position(), add=True)
        self.frame.bind('<Destroy>', self._destroyed, add=True)
        self.mirror = None
        # タイトルの字より右・下の空いた所のクリックで、タイトルの末尾（頭の側なら頭）へカーソルを
        # （2026-11-15 うにさん「タイトルの末尾の右側余白をクリックしたら、タイトルの末尾にカーソルを置く」）
        for widget in (self.clip, self.frame):
            widget.bind('<Button-1>', self.click_title_band, add=True)
        # 写しにもカーソル・選択を描く（右の欄に掛かった所でも見える）
        for seq in ('<KeyRelease>', '<ButtonRelease-1>', '<B1-Motion>', '<FocusIn>', '<FocusOut>', '<<Selection>>'):
            self.title.bind(seq, lambda e: self._mirror_call('sync_caret'), add=True)
        # 欄の上でホイール・タッチのパン・右ドラッグをしても、本文が送られる（欄は本文と一緒に動く）
        for widget in (self.clip, self.frame, self.title, self.toc, self.rule):
            self._forward_wheel(widget)
            self._forward_right(widget)
        self.restyle()

    def click_title_band(self, event, source=None):
        """タイトルの行の高さの所のクリック（タイトルの Text の外の余白・右の欄の写し）: タイトルに焦点を移し、クリックした
        横の位置に近い字の所（字より右なら末尾・左の余白なら頭）へカーソルを置く。目次の行・その下はそのまま。"""
        title = self.title
        try:
            y = event.y_root - title.winfo_rooty()
            if not (-TOP_GAP - 2 <= y < title.winfo_height() + 4):
                return None
            box = (source or title)
            x = event.x_root - box.winfo_rootx()
            yy = max(0, min(y, title.winfo_height() - 1))
            at = box.index('@%d,%d' % (x, yy))
            title.focus_set()
            title.mark_set('insert', at)
            title.tag_remove('sel', '1.0', 'end')
            title.see('insert')
        except (tk.TclError, AttributeError):
            return None
        self._title_last = True
        try:
            title.after_idle(lambda: self._mirror_call('sync_caret'))
        except tk.TclError:
            pass
        return 'break'

    def _mirror_call(self, name):
        mirror = getattr(self, 'mirror', None)
        if mirror is not None:
            try:
                getattr(mirror, name)()
            except tk.TclError:
                pass

    def _split_pane(self):
        """分割で右の欄が出ているなら、その Text（補正欄）。統合・右が隠れている時は None。"""
        result = getattr(self.app, 'result_view', None)
        if result is None or result is getattr(self.app, 'editor', None):
            return None
        try:
            unified = getattr(self.app, '_layout_is_unified', lambda: True)()
            if unified or not result.winfo_ismapped():
                return None
        except tk.TclError:
            return None
        return result

    def _destroyed(self, event=None):
        """窓を閉じる時: 待っている描き直しを外す（閉じた後に走らない）。"""
        for name in ('_after', '_idle'):
            job = getattr(self, name, None)
            if job is not None:
                try:
                    self.frame.after_cancel(job)
                except Exception:
                    pass
                setattr(self, name, None)

    # タイトル --------------------------------------------------------------
    def get_title(self):
        return one_line(self.title.get('1.0', 'end-1c'))

    def has_cursor(self):
        """カーソルがタイトルにあるか（焦点がタイトル。ボタン・メニューで焦点が外れていても、最後がタイトルなら）。"""
        try:
            focused = self.title.focus_get()
        except (tk.TclError, KeyError):
            focused = None
        if focused is self.title:
            return True
        return bool(self._title_last) and focused is not getattr(self.app, 'editor', None)

    def set_title(self, text, layout=True):
        self._loading = True
        try:
            self.title.delete('1.0', 'end')
            self.title.insert('1.0', one_line(text))
            self.title.edit_modified(False)
            self._title_text = one_line(text)
        finally:
            self._loading = False
        self.paint_pos(layout=layout)
        if layout:
            self.layout()

    def _replace_title(self, text, at=None):
        """元に戻す・やり直しでタイトルの字を替える（一手として積まない）。"""
        self._loading = True
        try:
            self.title.delete('1.0', 'end')
            self.title.insert('1.0', text)
            self.title.edit_modified(False)
            self._title_text = text
            if at is not None:
                self.title.mark_set('insert', at)
        finally:
            self._loading = False
        self.paint_pos()
        self._save_soon()

    def _paste(self, event=None):
        try:
            got = self.title.clipboard_get()
        except tk.TclError:
            return 'break'
        try:
            self.title.delete('sel.first', 'sel.last')
        except tk.TclError:
            pass
        self.title.insert('insert', one_line(got))
        return 'break'

    def _modified(self, event=None):
        if not self.title.edit_modified():
            return
        self.title.edit_modified(False)
        text = self.title.get('1.0', 'end-1c')
        if '\n' in text:
            self.title.delete('1.0', 'end')
            self.title.insert('1.0', one_line(text))
            text = one_line(text)
        before, self._title_text = self._title_text, text
        self.paint_pos()
        if before != text:
            # タブの名前もタイトルに合わせる（まとめて少し後で・tab_label・2026-11-16）
            queue = getattr(self.app, '_queue_tab_names', None)
            if queue is not None:
                try:
                    queue()
                except Exception:
                    pass
        if self._loading:
            return
        if before != text:
            self.undo.record(before, text, self.title.index('insert'))
        self._save_soon()

    def _save_soon(self):
        save = getattr(self.app, '_schedule_session_save', None)
        if save is not None:
            try:
                save()
            except Exception:
                pass

    def _copy(self, event=None):
        """選んだ字をコピー。白い枠だけ付け、拡大の表示はしない。"""
        try:
            first, last = self.title.index('sel.first'), self.title.index('sel.last')
        except tk.TclError:
            return 'break'
        text = self.title.get(first, last)
        if not text:
            return 'break'
        self.title.clipboard_clear()
        self.title.clipboard_append(text)
        show = getattr(self.app, '_show_copy_frame', None)
        if show is not None:
            try:
                show(self.title, first, last)
            except Exception:
                pass
        return 'break'

    def paint_pos(self, layout=True):
        """品詞の倍率と色（本文と同じ決まり）。解析・補正は通さない（形態素の切り分けだけ）。"""
        import pos_font
        w = self.title
        for tag in w.tag_names():
            if tag.startswith('cn_title_pos_'):
                w.tag_remove(tag, '1.0', 'end')
        text = w.get('1.0', 'end-1c')
        if not text.strip():
            self._mirror_call('sync_title')
            return
        try:
            tokens = self.app.store._tokenize_fn(text)
            runs = pos_font.spans(text, tokens)
        except Exception:
            return
        settings = getattr(self.app, 'settings', None)
        try:
            multipliers = pos_font.normalize_multipliers(settings.get('pos_font_multipliers') if settings else None)
        except Exception:
            multipliers = {}
        try:
            colors = pos_font.current_colors(settings)
        except Exception:
            colors = {}
        family = self._family()
        for cat, start, end in runs:
            tag = 'cn_title_pos_' + str(pos_font.POS_CATEGORIES.index(cat)) if cat in pos_font.POS_CATEGORIES else None
            if tag is None:
                continue
            opts = {'font': (family, pos_font.font_size(TITLE_SIZE, multipliers.get(cat, 1.0)))}
            if colors.get(cat):
                opts['foreground'] = colors[cat]
            w.tag_configure(tag, **opts)
            w.tag_add(tag, f'1.0+{start}c', f'1.0+{end}c')
        self._mirror_call('sync_title')
        if layout:
            self.layout()

    # 目次 ------------------------------------------------------------------
    def refresh_toc(self, force=False, layout=True):
        try:
            lines = self.app.editor_source_text().split('\n')
        except Exception:
            lines = []
        entries = toc_entries(lines, getattr(self.app, 'bookmarks', ()))
        if entries == self._entries and not force:
            return False
        self._entries = entries
        for link in self.links:
            link.destroy()
        self.links = []
        for row, _shown, text in entries:
            link = tk.Label(self.toc, text=text, anchor='w', justify='left', cursor='hand2', bd=0)
            link.pack(fill='x', anchor='w')
            link.bind('<Button-1>', lambda e, r=row: self.jump(r))
            link._cn_row = row
            self._forward_wheel(link)
            self._forward_right(link)
            self.links.append(link)
        self._style_links()
        if entries:
            # 目次を外していた時は区切りの線も外れているので、目次 → 線 の順に詰め直す
            self.rule.pack_forget()
            self.toc.pack(fill='x', padx=14, pady=(0, 4))
            self.rule.pack(fill='x', padx=14, pady=(0, 6))
        else:
            self.toc.pack_forget()        # 目次が無ければ、その分は詰める（区切りの線も）
            self.rule.pack_forget()
        self._mirror_call('sync_toc')
        if layout:
            self.layout()
        return True

    def changed(self, delay=120):
        """本文・ブックマーク・表示が変わった: 少し待ってから目次を作り直し、余白と位置を合わせ直す（打つたびには作らない）。"""
        pending = getattr(self, '_after', None)
        if pending is not None:
            try:
                self.frame.after_cancel(pending)
            except tk.TclError:
                pass
        try:
            self._after = self.frame.after(delay, self._changed_now)
        except tk.TclError:
            self._after = None

    def _changed_now(self):
        self._after = None
        if not self.refresh_toc():
            # 目次が替わらなければ高さも同じ: 余白と位置だけ（打鍵の流れで update_idletasks を呼ばない）
            self.ensure_pad()
            self.position()

    def switched(self, title):
        """タブを替えた: タイトルと目次をその場で作り直す（打鍵の待ちに乗せると、替えた後の描き直しのたびに待ちが
        延びて、目次の切り替わりが遅れた・2026-11-15 うにさん）。高さの測り直しだけ、描き終わった後に。"""
        pending = getattr(self, '_after', None)
        if pending is not None:
            try:
                self.frame.after_cancel(pending)
            except tk.TclError:
                pass
            self._after = None
        self.set_title(title, layout=False)
        self.refresh_toc(force=True, layout=False)
        # 高さはその場で測る（余白と欄の位置を同じ回で決める。描き直しを待つと、その間は前の高さの余白のまま）
        self.layout()

    def _layout_later(self):
        self._idle = None
        try:
            if self.frame.winfo_exists():
                self.layout()
        except tk.TclError:
            pass

    def jump(self, row):
        go = getattr(self.app, '_goto_line', None)
        if go is not None:
            go(row)
            try:
                self.app.editor.focus_set()
            except Exception:
                pass

    # 色・字 ----------------------------------------------------------------
    def _family(self):
        try:
            return self.app._editor_font()[0]
        except Exception:
            return 'Yu Gothic UI'

    def _link_color(self):
        """目次の字の色（今の地の色に合わせる）。"""
        bg = self._colors[0] if self._colors else self._pane_colors()[0]
        try:
            rgb = tuple(v / 65535.0 for v in self.frame.winfo_rgb(bg))
        except tk.TclError:
            return LINK_DARK if self._dark() else LINK_LIGHT
        return link_color(rgb, self._dark())

    def _dark(self):
        """いまの本文の地が暗いか（テーマの色から見る）。"""
        bg = self._colors[0] if self._colors else self._pane_colors()[0]
        try:
            r, g, b = (v / 65535.0 for v in self.frame.winfo_rgb(bg))
        except tk.TclError:
            return False
        return 0.299 * r + 0.587 * g + 0.114 * b < 0.5

    def _forward_right(self, widget):
        """右ドラッグのスクロール（本文と同じ動き）を、欄の上でも。座標は本文の欄の中の位置に直して渡す。
        動かさずに離した時は何もしない（本文の右クリックの候補は出さない）。"""
        def as_editor(event):
            from types import SimpleNamespace
            editor = self.app.editor
            try:
                x = event.x_root - editor.winfo_rootx()
                y = event.y_root - editor.winfo_rooty()
            except tk.TclError:
                return None
            return SimpleNamespace(widget=editor, x=x, y=y, x_root=event.x_root, y_root=event.y_root,
                                   state=getattr(event, 'state', 0), time=getattr(event, 'time', 0),
                                   num=3, delta=0, keysym='', char='', type=getattr(event, 'type', ''))

        def call(name, *rest):
            def handler(event):
                ev = as_editor(event)
                go = getattr(self.app, name, None)
                if ev is not None and go is not None:
                    try:
                        go(ev, self.app.editor, *rest)
                    except Exception:
                        pass
                return 'break'
            return handler
        widget.bind('<ButtonPress-3>', call('_drag_press', True), add=True)
        widget.bind('<B3-Motion>', call('_drag_motion'), add=True)
        widget.bind('<ButtonRelease-3>', call('_drag_release'), add=True)

    def _forward_wheel(self, widget):
        def wheel(event):
            editor = getattr(self.app, 'editor', None)
            if editor is None:
                return 'break'
            try:
                editor.event_generate('<MouseWheel>', delta=event.delta, state=event.state,
                                      x=max(1, editor.winfo_width() // 2), y=1)
            except tk.TclError:
                try:
                    editor.yview_scroll(-1 if event.delta > 0 else 1, 'units')
                except tk.TclError:
                    pass
            return 'break'
        widget.bind('<MouseWheel>', wheel, add=True)

    def _pane_colors(self):
        """本文の Text の今の色（テーマ・明暗の切り替えのあとも、本文と同じ色を取る）。"""
        editor = getattr(self.app, 'editor', None)
        import sys
        mod = sys.modules.get(type(self.app).__module__)
        try:
            return (editor.cget('bg'), editor.cget('fg'), editor.cget('insertbackground'),
                    editor.cget('selectbackground'), editor.cget('selectforeground'))
        except Exception:
            ink = getattr(mod, 'INK', '#1c2b2d')
            return (getattr(mod, 'PANEL', '#f0f0ed'), ink, ink, getattr(mod, 'EDITOR_SEL_BG', '#cfe3ff'), ink)

    def _rule_color(self):
        """区切りの線の色（本文のルーラーと同じ RULE・テーマ・明暗で替わる）。"""
        import sys
        mod = sys.modules.get(type(self.app).__module__)
        return getattr(mod, 'RULE', '#d8d3c4')

    def _toc_size(self):
        if TOC_POINT > 0:
            return TOC_POINT            # デバッグのパラメータで決めた大きさ
        try:
            body = abs(int(self.app._editor_font()[1]))
        except Exception:
            body = 12
        return max(9, min(TOC_SIZE, int(round(body * TOC_SCALE)) + 1))

    def refresh_sizes(self):
        """タイトル・目次の字の大きさ（デバッグのパラメータ）が変わった: その場で付け直す（行の高さ・分割の右の高さ
        合わせもタグの字の大きさで追いつく）。"""
        self.restyle()
        self.paint_pos()

    def restyle(self):
        bg, ink, cursor, sel, selfg = self._pane_colors()
        self._colors = (bg, ink, cursor, sel, selfg, self._family())
        for widget in (self.clip, self.frame, self.toc):
            widget.configure(bg=bg)
        try:
            self.rule.configure(bg=self._rule_color())
        except tk.TclError:
            pass
        self.title.configure(bg=bg, fg=ink, insertbackground=cursor, font=(self._family(), TITLE_SIZE),
                             selectbackground=sel, selectforeground=selfg)
        self._style_links()

    def _style_links(self):
        if not self._colors:
            return
        bg = self._colors[0]
        color = self._link_color()
        font = tkfont.Font(family=self._family(), size=self._toc_size(), underline=True)
        for link in self.links:
            link.configure(bg=bg, fg=color, font=font)
        self._link_font = font
        self._mirror_call('restyle')

    # 余白と位置 ------------------------------------------------------------
    def panes(self):
        out = [getattr(self.app, 'editor', None)]
        result = getattr(self.app, 'result_view', None)
        if result is not None:
            out.append(result)
        return [p for p in out if p is not None]

    def _measure(self):
        """欄の高さ（pack が出す高さと同じ）を、字の大きさと詰め物から測る。update_idletasks を呼ばない（打鍵・タブの
        切り替えの流れで、ほかの描き直しまで先に走らせない）。"""
        def font_space(widget):
            try:
                return int(widget.tk.call('font', 'metrics', widget.cget('font'), '-linespace'))
            except (tk.TclError, ValueError):
                return 0

        def edge(widget, pad):
            total = 0
            for key in ('borderwidth', 'highlightthickness') + ((pad,) if pad else ()):
                try:
                    total += int(float(str(widget.cget(key))))
                except (tk.TclError, ValueError):
                    pass
            return 2 * total

        height = font_space(self.title) + edge(self.title, 'pady') + 4
        if self.links:
            height += sum(font_space(link) + edge(link, 'pady') for link in self.links) + 4
            height += int(float(str(self.rule.cget('height')))) + 6
        return height

    def layout(self):
        """欄の高さに合わせて、1行目の上の余白を掛け直し、位置を合わせる。"""
        try:
            height = self._measure()
        except tk.TclError:
            return
        self._height = height
        self.ensure_pad()
        self.position()

    def _shift(self):
        """タイトルを本文の欄の上端へ寄せる分: 本文の上の内側の余白（pady）のうち TOP_GAP だけ残す。"""
        editor = getattr(self.app, 'editor', None)
        try:
            edge = sum(int(float(str(editor.cget(k)))) for k in ('pady', 'borderwidth', 'highlightthickness'))
        except Exception:
            edge = 0
        return max(0, edge - TOP_GAP)

    @staticmethod
    def _border(widget):
        total = 0
        for key in ('borderwidth', 'highlightthickness'):
            try:
                total += int(float(str(widget.cget(key))))
            except (tk.TclError, ValueError):
                pass
        return total

    def _repaint(self):
        """欄の部品を、WM_PAINT を待たずに描き直す（Tk は設定が替わると idle で描く。地の色を同じ値で掛け直すだけ）。
        Text のスクロールのずらしで欄の所の画素が動いても、次の idle で描き直される（速いスクロールの間も）。"""
        _redraw(self.clip, self.frame, self.title, self.toc, self.rule, *self.links)

    def _gutters(self):
        out = []
        for name, pane in (('editor_gutter', getattr(self.app, 'editor', None)),
                           ('result_gutter', getattr(self.app, 'result_view', None))):
            gutter = getattr(self.app, name, None)
            if gutter is not None and pane is not None:
                out.append((gutter, pane))
        return out

    def _cover_gutters(self, y, height):
        """行番号の列の、余白（タイトルと目次）の高さの所を、列の地の色の板で覆う（絵の点を透かさない）。
        2026-11-15 から列が自分の描き直しで塗る（app の LineNumberGutter・title_cover）。ここは前に作った板を外すだけ。"""
        for cover in list((getattr(self, '_covers', None) or {}).values()):
            try:
                cover.place_forget()
            except tk.TclError:
                pass
        return
        covers = getattr(self, '_covers', None)
        if covers is None:
            covers = self._covers = {}
        for gutter, pane in self._gutters():
            try:
                cover = covers.get(gutter)
                if cover is None or not cover.winfo_exists():
                    cover = covers[gutter] = tk.Frame(gutter, bd=0, highlightthickness=0)
                    self._forward_wheel(cover)
                    self._forward_right(cover)
                if height <= 0 or not pane.winfo_ismapped():
                    cover.place_forget()
                    continue
                dy = pane.winfo_rooty() - gutter.winfo_rooty()
                if cover.cget('bg') != gutter.cget('bg'):
                    cover.configure(bg=gutter.cget('bg'))
                was = cover.winfo_ismapped()
                cover.place(x=0, y=y + dy, relwidth=1, height=height, bordermode='outside')
                if not was:
                    cover.lift()          # 前へ出すのは出す時だけ（動かすたびに前へ出すと、そのたびに描き直しになる）
            except tk.TclError:
                pass

    def _hide(self):
        if self._placed is not None or self.clip.winfo_ismapped():
            self.clip.place_forget()
        self._placed = None
        self._cover_gutters(0, 0)
        if getattr(self, 'mirror', None) is not None:
            self.mirror.hide()

    def ensure_pad(self):
        """余白のタグを、左右の欄の1行目の頭の字だけに（本文が変わるたびに掛け直す）。"""
        height = max(0, (self._height or 0) - self._shift())
        import sys
        mod = sys.modules.get(type(self.app).__module__)
        base = getattr(mod, 'ROW_SPACING', (0, 1))[0]
        for pane in self.panes():
            try:
                # 余白の高さを替える時だけ掛け直す（spacing を掛け直すと、Tk が本文の行の並びを測り直して描き直す。
                # スクロールのたびに掛けて、スクロール1回が 20ms → 120ms になっていた・2026-11-15 うにさん「全体の動作が重い」）
                if getattr(pane, '_cn_title_pad_space', None) != base + height:
                    pane.tag_configure(PAD_TAG, spacing1=base + height)
                    pane._cn_title_pad_space = base + height
                ranges = pane.tag_ranges(PAD_TAG)
                if len(ranges) != 2 or str(ranges[0]) != '1.0' or str(ranges[1]) != pane.index('1.0+1c'):
                    pane.tag_remove(PAD_TAG, '1.0', 'end')
                    pane.tag_add(PAD_TAG, '1.0', '1.0+1c')
            except tk.TclError:
                pass

    def position(self):
        """欄を本文の1行目の表示行の頭に重ねる。1行目が見えない（下へ送った）なら隠す。"""
        if self._colors and self._colors != self._pane_colors() + (self._family(),):
            self.restyle()       # テーマ・明暗・字が替わった
        editor = getattr(self.app, 'editor', None)
        if editor is None or self._height is None:
            return
        try:
            self.ensure_pad()
            info = editor.dlineinfo('1.0')
            if info is None:
                self._hide()       # 1行目がまるごと上へ送られた
                return
            # 本文の欄（Text）の中の位置。1行目の表示行の頭（余白の頭）から、本文の上の内側の余白（pady）の分だけ
            # 上へ寄せる（上端から TOP_GAP）。欄は本文の欄の内側（枠の内）だけに置く
            border = self._border(editor)
            top = info[1] - self._shift()
            cut = max(0, border - top)          # 上へ見切れた分
            room = editor.winfo_height() - border - (top + cut)
            shown = min(self._height - cut, room)
            if shown <= 0:
                self._hide()
                return
            x0 = border
            width = max(1, editor.winfo_width() - 2 * border)
            # 分割の右の欄も1つの欄として: 中身の幅は左右を合わせた幅。右の欄には写しを、左の欄の幅＋仕切りの分だけずらして
            right = self._split_pane()
            total = width
            if right is not None:
                rborder = self._border(right)
                origin = editor.winfo_rootx() + border
                total = max(width, right.winfo_rootx() + right.winfo_width() - rborder - origin)
            self._place_mirror(right, total)
            where = (x0, top + cut, width, shown, cut, self._height, total)
            if where == self._placed and self.clip.winfo_ismapped():
                return          # 同じ所: 置き直さない（置き直すと欄と本文が描き直される）
            # 座標は本文の欄の窓の外の縁から（Text は詰め物 padx/pady も「内側の縁」に数えるので inside だとずれる）
            was = self.clip.winfo_ismapped()
            self.clip.place(in_=editor, x=x0, y=top + cut, width=width, height=shown, bordermode='outside')
            self.frame.place(x=0, y=-cut, width=total, height=self._height)
            if not was:
                self.clip.lift()      # 前へ出すのは出す時だけ（スクロールで動かすたびに前へ出すと重い・2026-11-15）
            self._placed = where
            self._repaint()
        except tk.TclError:
            pass

    def _place_mirror(self, right, total):
        """右の欄の写しを置く（分割でない時は隠す）。"""
        if right is None:
            if self.mirror is not None:
                self.mirror.hide()
            return
        if self.mirror is None or self.mirror.pane is not right:
            if self.mirror is not None:
                self.mirror.destroy()
            self.mirror = Mirror(self, right)
            self.mirror.sync_title()
            self.mirror.sync_toc()
        editor = self.app.editor
        dx = (right.winfo_rootx() + self._border(right)) - (editor.winfo_rootx() + self._border(editor))
        self.mirror.place(dx, total)




def _redraw(*widgets):
    """部品を、WM_PAINT を待たずに次の idle で描き直させる。箱・ラベルは地の色を同じ値で掛け直す（軽い）。Text は設定を
    掛け直すと行を組み直すので、空のタグを付け外しして、その行の描き直しだけを積む（2026-11-15 右ドラッグが重くなった件）。"""
    # 「見えるようになった」の知らせ（Expose）を自分で出す: 形の計り直し・並べ直しをせず、その部品を描くだけ
    # （地の色の掛け直しは、ラベルの大きさを計り直して目次の並びを組み直し、重かった・2026-11-15）
    for widget in widgets:
        try:
            widget.event_generate('<Expose>', x=0, y=0, width=max(1, widget.winfo_width()),
                                  height=max(1, widget.winfo_height()))
        except tk.TclError:
            pass


class Mirror:
    """分割の右の欄に置く、欄の写し（左の欄の続き）。字の持ち主は左のタイトル（TitleToc.title）で、写しは描くだけ。
    右の欄（Text）の子の窓・その欄の内側だけに置く（透ける窓・はみ出す窓にしない）。"""
    def __init__(self, toc, pane):
        self.toc, self.pane = toc, pane
        self.clip = tk.Frame(pane, bd=0, highlightthickness=0)
        self.frame = tk.Frame(self.clip, bd=0, highlightthickness=0)
        self.title = tk.Text(self.frame, height=1, wrap='none', relief='flat', bd=0, highlightthickness=0,
                             padx=14, pady=0, width=1, cursor='xterm', takefocus=0, state='disabled')
        self.title.pack(fill='x', pady=(0, 4))
        self.toc_frame = tk.Frame(self.frame, bd=0, highlightthickness=0)
        self.toc_frame.pack(fill='x', padx=14, pady=(0, 4))
        self.rule = tk.Frame(self.frame, height=1, bd=0, highlightthickness=0)
        self.rule.pack(fill='x', padx=14, pady=(0, 6))
        self.caret = tk.Frame(self.title, width=2, bd=0, highlightthickness=0)
        self.links = []
        self._placed = None
        self.title.bind('<Button-1>', self._click)
        for widget in (self.clip, self.frame):
            widget.bind('<Button-1>', lambda e: self.toc.click_title_band(e, self.title), add=True)
        self.title.bind('<Key>', lambda e: 'break')
        for widget in (self.clip, self.frame, self.title, self.toc_frame, self.rule):
            toc._forward_wheel(widget)
            toc._forward_right(widget)
        self.restyle()

    def widgets(self):
        return [self.clip, self.frame, self.title, self.toc_frame, self.rule] + list(self.links)

    def _click(self, event):
        """写しのタイトルのクリック: 本物のタイトルの同じ字の所へカーソルを移す（タイトルの編集は1つ。字より右なら末尾）。"""
        got = self.toc.click_title_band(event, self.title)
        if got is None:
            real = self.toc.title
            try:
                at = self.title.index('@%d,%d' % (event.x, event.y))
                real.focus_set()
                real.mark_set('insert', at)
                real.tag_remove('sel', '1.0', 'end')
            except tk.TclError:
                pass
            self.sync_caret()
        return 'break'

    def sync_title(self):
        src, w = self.toc.title, self.title
        w.configure(state='normal')
        try:
            w.delete('1.0', 'end')
            w.insert('1.0', src.get('1.0', 'end-1c'))
            for tag in src.tag_names():
                if not tag.startswith('cn_title_pos_'):
                    continue
                opts = {k: src.tag_cget(tag, k) for k in ('font', 'foreground') if src.tag_cget(tag, k)}
                if opts:
                    w.tag_configure(tag, **opts)
                ranges = src.tag_ranges(tag)
                for a, b in zip(ranges[::2], ranges[1::2]):
                    w.tag_add(tag, a, b)
        finally:
            w.configure(state='disabled')
        self.sync_caret()

    def sync_caret(self):
        """本物のタイトルのカーソル・選択を写しにも描く（焦点がタイトルにある時だけ）。"""
        src, w = self.toc.title, self.title
        w.tag_remove('sel', '1.0', 'end')
        try:
            ranges = src.tag_ranges('sel')
            if len(ranges) == 2:
                w.tag_add('sel', ranges[0], ranges[1])
            focused = src.focus_get() is src
        except (tk.TclError, KeyError):
            focused = False
        box = w.bbox(src.index('insert')) if focused else None
        if box is None and focused:
            box = w.bbox('end-1c')
            if box is not None:
                box = (box[0] + box[2], box[1], 0, box[3])
        if box is None:
            self.caret.place_forget()
            return
        # bbox は Text の外の縁からの位置（Text は詰め物も内側の縁に数えるので outside で置く）
        self.caret.place(x=box[0], y=box[1], width=2, height=box[3], bordermode='outside')

    def sync_toc(self):
        for link in self.links:
            link.destroy()
        self.links = []
        for real in self.toc.links:
            # 補正欄の側の目次の行はクリックしても飛ばない（手のカーソルも出さない・2026-11-15 うにさん「目次の補正欄側を
            # クリックするとジャンプする。反応しないようにする」）。ホイール・右ドラッグのスクロールは効かせる
            link = tk.Label(self.toc_frame, text=real.cget('text'), anchor='w', justify='left', cursor='arrow', bd=0)
            link.pack(fill='x', anchor='w')
            self.toc._forward_wheel(link)
            self.toc._forward_right(link)
            self.links.append(link)
        if self.links:
            self.rule.pack_forget()
            self.toc_frame.pack(fill='x', padx=14, pady=(0, 4))
            self.rule.pack(fill='x', padx=14, pady=(0, 6))
        else:
            self.toc_frame.pack_forget()
            self.rule.pack_forget()
        self.restyle()

    def restyle(self):
        colors = self.toc._colors
        if not colors:
            return
        bg, ink, cursor, sel, selfg, family = colors
        for widget in (self.clip, self.frame, self.toc_frame):
            widget.configure(bg=bg)
        self.rule.configure(bg=self.toc._rule_color())
        self.title.configure(bg=bg, fg=ink, font=(family, TITLE_SIZE), selectbackground=sel, selectforeground=selfg,
                             inactiveselectbackground=sel)
        self.caret.configure(bg=cursor)
        font = getattr(self.toc, '_link_font', None)
        color = self.toc._link_color()
        for link in self.links:
            link.configure(bg=bg, fg=color, **({'font': font} if font is not None else {}))

    def place(self, dx, total):
        """右の欄の1行目の余白に、中身を dx だけ左へずらして置く（左の欄の続きに見える）。"""
        pane = self.pane
        height = self.toc._height or 0
        info = pane.dlineinfo('1.0')
        if info is None:
            self.hide()
            return
        border = self.toc._border(pane)
        try:
            edge = sum(int(float(str(pane.cget(k)))) for k in ('pady', 'borderwidth', 'highlightthickness'))
        except (tk.TclError, ValueError):
            edge = 0
        top = info[1] - max(0, edge - TOP_GAP)
        cut = max(0, border - top)
        room = pane.winfo_height() - border - (top + cut)
        shown = min(height - cut, room)
        width = max(1, pane.winfo_width() - 2 * border)
        if shown <= 0:
            self.hide()
            return
        # 右の欄に字・線が見えている高さだけを覆う（多くは下の線だけ）。地だけの所は右の欄の余白そのもので同じ色なので、
        # 窓で覆わない（大きい窓を補正欄の上で動かすと、そのたびに補正欄が描き直されて重かった・2026-11-15）
        lo, hi = self._visible_span(dx)
        lo, hi = max(lo, cut), min(hi, cut + shown)
        if hi <= lo:
            self.hide()
            return
        where = (border, top + lo, width, hi - lo, lo, height, dx, total)
        if where == self._placed and self.clip.winfo_ismapped():
            return
        was = self.clip.winfo_ismapped()
        self.clip.place(in_=pane, x=border, y=top + lo, width=width, height=hi - lo, bordermode='outside')
        self.frame.place(x=-dx, y=-lo, width=total, height=height)
        if not was:
            self.clip.lift()
        self._placed = where
        try:
            focused = self.toc.title.focus_get() is self.toc.title
        except (tk.TclError, KeyError):
            focused = False
        if focused or self.caret.winfo_ismapped():
            self.sync_caret()         # カーソルを描くのはタイトルに焦点がある時だけ（動かすたびには要らない）
        # その場で描き直すのは、右の欄に見えている字のある部品だけ（地だけの所はずらされても地のまま。写しの目次の行の
        # 多くは左の欄の中で終わっていて、右には字が出ない・2026-11-15 右ドラッグを軽く）
        _redraw(self.rule, *self._visible_parts(dx))

    def _visible_span(self, dx):
        """中身の中で、右の欄に字・線が見えている縦の範囲 (上, 下)。下の線は左右に続くのでいつも入れる。"""
        # 位置は字の大きさと詰め物から計る（TitleToc._measure と同じ。写しが一度も出ていない時も計れる）
        parts = set(self._visible_parts(dx))
        spans = []
        try:
            def space(w):
                return int(w.tk.call('font', 'metrics', w.cget('font'), '-linespace'))

            def edge(w):
                return 2 * sum(int(float(str(w.cget(k)))) for k in ('borderwidth', 'highlightthickness', 'pady'))

            y = space(self.title) + edge(self.title)
            if self.title in parts:
                spans.append((0, y))
            y += 4
            if self.links:
                for link in self.links:
                    h = space(link) + edge(link)
                    if link in parts:
                        spans.append((y, y + h))
                    y += h
                y += 4
                spans.append((y, y + max(1, int(float(str(self.rule.cget('height')))))))
        except (tk.TclError, ValueError):
            return 0, self.toc._height or 0
        if not spans:
            return 0, 0
        return min(s for s, _e in spans), max(e for _s, e in spans)

    def _text_width(self, widget, text):
        """字の幅（字と字の形ごとに控える。スクロールのたびに計ると1回 20ms ほど掛かった・2026-11-15）。"""
        try:
            font = str(widget.cget('font'))
        except tk.TclError:
            return 0
        cache = getattr(self, '_widths', None)
        if cache is None or len(cache) > 400:
            cache = self._widths = {}
        key = (font, text)
        width = cache.get(key)
        if width is None:
            try:
                width = cache[key] = int(widget.tk.call('font', 'measure', font, text))
            except (tk.TclError, ValueError):
                width = cache[key] = 0
        return width

    def _visible_parts(self, dx):
        """右の欄に字が見えている部品（タイトル・目次の行）。中身の頭から dx より右まで字が続くものだけ。
        頭の余白は、タイトルの padx・目次の箱の padx（どちらも 14）。"""
        out = []
        try:
            text = self.title.get('1.0', 'end-1c')
        except tk.TclError:
            text = ''
        if text and 14 + self._text_width(self.title, text) * 1.6 > dx:     # 品詞の倍率で広がる分も見込む
            out.append(self.title)
        for link in self.links:
            try:
                label = link.cget('text')
            except tk.TclError:
                out.append(link)
                continue
            if 14 + self._text_width(link, label) + 4 > dx:
                out.append(link)
        return out

    def hide(self):
        if self._placed is not None or self.clip.winfo_ismapped():
            self.clip.place_forget()
        self._placed = None

    def destroy(self):
        try:
            self.clip.destroy()
        except tk.TclError:
            pass


class TitleUndo:
    """タイトルの書き換えを、本文の元に戻す・やり直しと1つの列にする（2026-11-15 うにさん「Undoがタイトルと本文で
    別々になっている。まとめる」）。本文の Undo の流れ（analysis_work の undo_hooks・undo_feedback の番号）に
    「本文以外の一手」として入れる（choice_undo・editor_guides と同じ形）。タブごと（tab_undo が別のタブへ移って戻す）。
    続けて打った字（MERGE_S 秒の内・間にほかの一手が無い）は1手にまとめる。記憶だけ・ファイルには書かない。"""
    MERGE_S = 1.0
    LIMIT = 200

    def __init__(self, toc):
        self.toc, self.app = toc, toc.app
        self.history, self.redo = [], []
        self.took = False
        self.last_place = None
        editor = getattr(self.app, 'editor', None)
        if editor is not None:
            try:
                from analysis_work import observe_text
                observe_text(editor)
                editor._correctnote_observers.setdefault('undo_hooks', []).append(self.undo_step)
            except Exception:
                pass

    def _owner(self):
        tab_undo = getattr(self.app, '_tab_undo', None)
        return getattr(tab_undo, 'owner', None)

    def record(self, before, after, index):
        from undo_feedback import next_seq, _SEQ
        now = time.monotonic()
        tab = self._owner()
        top = self.history[-1] if self.history else None
        if (top is not None and top['tab'] is tab and now - top['t'] < self.MERGE_S and top['seq'] == _SEQ[0]
                and top['after'] == before):
            top.update(after=after, t=now, index=index)
        else:
            self.history.append(dict(seq=next_seq(), tab=tab, before=before, after=after, t=now, index=index))
            del self.history[:-self.LIMIT]
        self.redo.clear()

    def _body_seq(self, kind):
        tab_undo = getattr(self.app, '_tab_undo', None)
        feedback = getattr(tab_undo, 'feedback', None)
        try:
            return feedback.next_seq(kind) if feedback is not None else None
        except Exception:
            return None

    def _due(self, kind):
        stack = self.history if kind == 'undo' else self.redo
        if not stack:
            return None
        top = stack[-1]
        if top['tab'] is not self._owner():
            return None
        if self.toc.get_title() != (top['after'] if kind == 'undo' else top['before']):
            return None
        body = self._body_seq(kind)
        if body is not None and (top['seq'] < body if kind == 'undo' else top['seq'] > body):
            return None         # 本文の一手のほうが先
        return top

    def due_step_seq(self, kind):
        top = self._due(kind)
        return None if top is None else top['seq']

    def step_top(self, kind):
        """(番号, 本文の字 None, タブ)（tab_undo が別のタブの一手を探す）。"""
        stack = self.history if kind == 'undo' else self.redo
        return (stack[-1]['seq'], None, stack[-1]['tab']) if stack else None

    def step_drop(self, kind):
        (self.history if kind == 'undo' else self.redo).pop()

    def undo_step(self, kind):
        top = self._due(kind)
        if top is None:
            return False
        stack, other = (self.history, self.redo) if kind == 'undo' else (self.redo, self.history)
        stack.pop()
        other.append(top)
        text = top['before'] if kind == 'undo' else top['after']
        self.toc._replace_title(text, at=self._place(top, text))
        self.last_place = None          # 本文のカーソルは動かさない
        self.took = True
        try:
            self.toc.title.focus_set()  # 戻した所（タイトル）へカーソルを
        except tk.TclError:
            pass
        return True

    @staticmethod
    def _place(entry, text):
        """戻した後のカーソルの所: 替わった所の終わり。"""
        a, b = entry['before'], entry['after']
        i = 0
        while i < min(len(a), len(b)) and a[i] == b[i]:
            i += 1
        j = 0
        while j < min(len(a), len(b)) - i and a[-1 - j] == b[-1 - j]:
            j += 1
        return '1.0+%dc' % max(0, len(text) - j)

    def from_title(self, kind):
        """タイトルで Ctrl+Z / Ctrl+Y: 本文と同じ列で1手。本文の一手なら本文へカーソルを移す。"""
        editor = getattr(self.app, 'editor', None)
        if editor is None:
            return 'break'
        self.took = False
        try:
            (editor.edit_undo if kind == 'undo' else editor.edit_redo)()
        except tk.TclError:
            return 'break'
        if not self.took:
            try:
                editor.focus_set()
                editor.see('insert')
            except tk.TclError:
                pass
        return 'break'




def _widgets_of(toc):
    """欄の部品（右ドラッグの間カーソルを隠す所・app._scroll_panes）。分割の右の写しも。"""
    out = [w for w in (toc.clip, toc.frame, toc.title, toc.toc, toc.rule) + tuple(toc.links)]
    out.extend(c for c in (getattr(toc, '_covers', None) or {}).values())
    if getattr(toc, 'mirror', None) is not None:
        out.extend(toc.mirror.widgets())
    return out


TitleToc.widgets = _widgets_of


def install(app):
    """CN_TITLE_TOC=0 なら何もしない（None）。CN_TITLE_TOC_INLINE=1 なら本文の中の字として置く形（title_inline）。"""
    if not enabled():
        return None
    import title_inline
    if title_inline.enabled():
        return title_inline.install(app)
    try:
        toc = TitleToc(app)
        render = getattr(app, '_render_corrected', None)
        if render is not None:
            def rendered(*a, **k):
                # 補正欄を描き直すと、1行目の余白のタグが外れる。描いた後に掛け直す（左右の行がずれないように）
                got = render(*a, **k)
                toc.ensure_pad()
                return got
            app._render_corrected = rendered
        return toc
    except Exception:
        import traceback
        traceback.print_exc()
        return None
