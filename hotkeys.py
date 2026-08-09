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
アプリが非アクティブでも効くグローバルホットキー。

Ctrl+Insert / Ctrl+Shift+- を押すと、他のアプリを使っている最中でも
簡易入力ウィンドウを呼び出せるようにする。

Windows の RegisterHotKey API を ctypes 経由で直接呼ぶ。
外部ライブラリ（keyboard, pynput 等）は使わない。それらは
全キー入力を監視するグローバルフックを使うため、動作としては
キーロガーと見分けが付かず、ウイルス対策ソフトに誤検知されやすい。
RegisterHotKey は「特定のキーの組み合わせだけ」をOSに予約する方式で、
他のキー入力を監視しないため、誤検知されにくい。

RegisterHotKey は呼び出したスレッドのメッセージループでしか
WM_HOTKEY を受け取れない。tkinter のメインループとは別に、
専用のメッセージポンプを持つ小さなスレッドを1つ立てる。
tkinter は別スレッドから直接操作してはいけないため、
ホットキーが押されたら呼び出し側で root.after(0, ...) を使って
メインスレッドに処理を戻すこと（このクラス自体はそこまで面倒を見ない）。

Windows 以外（開発中のこの環境を含む）では HAS_SUPPORT が False になり、
呼び出しても無害（何も起こらない）。
"""

import sys
import threading

HAS_SUPPORT = (sys.platform == 'win32')

if HAS_SUPPORT:
    import ctypes
    from ctypes import wintypes

    # use_last_error=True にしておくと、RegisterHotKey が失敗したときの
    # 理由を ctypes.get_last_error() で読める。
    # 「押しても反応しない」ときに、登録自体ができていないのか
    # どうかを切り分けるのに要る。
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    WM_HOTKEY = 0x0312
    # WM_APP 以降はアプリが自由に使ってよい範囲（Win32の取り決め）。
    # 「設定が変わったので登録を見直せ」という合図に使う。
    _WM_APP_SYNC = 0x8000 + 1
else:
    WM_HOTKEY = None
    _WM_APP_SYNC = None

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004

# ホットキーの名前 -> [(修飾キー, 仮想キーコード), ...]。
# settings.active_hotkeys() が返す名前と対応させる。
#
# 'minus' は JIS配列の数字段いちばん右寄りにある「- =」キー
# （VK_OEM_MINUS）を Ctrl+Shift と一緒に押す組み合わせ。
# 以前は「Ctrl+=」として VK_OEM_PLUS(0xBB) を登録していたが、
# VK_OEM_PLUS が「=」なのは US配列の話で、
# **JIS配列では VK_OEM_PLUS は「;」のキー**である。
# そのため実機では Ctrl+= を押しても無反応になっていた。
# 刻印どおりに押せる組み合わせとして Ctrl+Shift+- に改めた。
HOTKEY_DEFS = {
    'insert': [(MOD_CONTROL, 0x2D)],                  # Ctrl + Insert
    'minus': [(MOD_CONTROL | MOD_SHIFT, 0xBD)],       # Ctrl + Shift + -
}

# 画面に出す名前。app.py のメニューや簡易入力ウィンドウの
# 説明文がここを参照する（表記をばらけさせないため）。
HOTKEY_LABELS = {
    'insert': 'Ctrl+Insert',
    'minus': 'Ctrl+Shift+-',
}

# id はホットキーごとに固有の小さい整数が必要（RegisterHotKey の仕様）。
# 組み合わせが複数ある名前には、その数だけ id を割り当てる。
_HOTKEY_IDS = {}
_ID_TO_NAME = {}
_next_id = 1
for _name, _combos in HOTKEY_DEFS.items():
    _ids = []
    for _combo in _combos:
        _HOTKEY_IDS.setdefault(_name, _ids).append(_next_id)
        _ID_TO_NAME[_next_id] = _name
        _next_id += 1


class GlobalHotkeys:
    """
    グローバルホットキーの登録・解除・待ち受けを行う。

    使い方:
        gh = GlobalHotkeys(on_triggered=callback)
        gh.start()
        gh.set_enabled('insert', True)
        gh.set_enabled('minus', False)
        ...
        gh.stop()
    """

    def __init__(self, on_triggered=None):
        self.on_triggered = on_triggered
        self._thread = None
        self._thread_id = None
        self._enabled = {name: False for name in HOTKEY_DEFS}
        self._registered = set()
        self._running = False
        # 登録に失敗したときの理由（診断用）。name -> [Win32エラー番号]
        # 値が None なら成功、[] なら「まだ登録を試みていない」。
        self._last_error = {}
        # 設定の変更をスレッドに伝え損ねないための取りこぼし防止。
        #
        # 以前は set_enabled が「_thread_id がまだ None なら、
        # スレッドの起動時にまとめて反映されるはず」と考えて
        # 何もせずに戻っていた。しかしスレッドは
        # 「_thread_id を入れる → すぐ _sync_registration する」
        # という順で動くため、
        #   スレッド: _thread_id を設定、まだ全部オフの状態で同期
        #   メイン  : _enabled を True にしたが _thread_id は None に見えた
        # という並びになると、**どちらも登録を行わないまま終わる**。
        # 実機で「押しても簡易入力が出ない／状態はエラー番号すら
        # 出ない（＝登録を試みていない）」となった原因がこれ。
        #
        # スレッド側が同期を終えるたびに世代番号を上げ、
        # 設定を変えた側はその世代を見て「自分の変更が反映済みか」を
        # 判断する。未反映ならスレッドを起こし直す。
        self._lock = threading.Lock()
        self._want_generation = 0     # 設定が変わるたびに増える
        self._done_generation = -1    # スレッドが最後に同期した世代

    @property
    def supported(self):
        return HAS_SUPPORT

    def start(self):
        """待ち受けスレッドを起動する。Windows以外では何もしない。"""
        if not HAS_SUPPORT or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """待ち受けを終える。登録したホットキーも解除する。"""
        if not HAS_SUPPORT or not self._running:
            return
        self._running = False
        if self._thread_id is not None:
            try:
                user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._thread = None
        self._thread_id = None

    def set_enabled(self, name, enabled):
        """
        個別のホットキーをオン/オフする。

        待ち受けスレッドが動いている間、いつ呼んでもよい。
        起動の前後どちらで呼ばれても取りこぼさない。
        実際の登録/解除はスレッド側のメッセージループが行う。
        """
        if name not in HOTKEY_DEFS:
            return
        with self._lock:
            self._enabled[name] = enabled
            self._want_generation += 1
        if not HAS_SUPPORT:
            return
        self._wake_thread()

    def _wake_thread(self):
        """スレッドに「設定が変わったので見直せ」と伝える。"""
        thread_id = self._thread_id
        if thread_id is None:
            return    # まだ起動前。起動時の同期で拾われる
        try:
            user32.PostThreadMessageW(thread_id, _WM_APP_SYNC, 0, 0)
        except Exception:
            pass

    # ------------------------------------------------------------
    def _run(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._sync_registration()
        # _thread_id を入れてから最初の同期を終えるまでの間に
        # set_enabled が呼ばれていた場合、その変更はまだ反映されて
        # いない。世代番号を見て、取りこぼしていればもう一度行う。
        if self._want_generation != self._done_generation:
            self._sync_registration()

        msg = wintypes.MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break   # WM_QUIT、またはエラー
            if msg.message == WM_HOTKEY:
                name = self._name_for_id(msg.wParam)
                if name and self.on_triggered:
                    try:
                        self.on_triggered(name)
                    except Exception:
                        pass
            elif msg.message == _WM_APP_SYNC:
                self._sync_registration()

        self._unregister_all()

    def _sync_registration(self):
        """今の設定に合わせて、登録するホットキーを増減させる。"""
        with self._lock:
            wanted = dict(self._enabled)
            generation = self._want_generation
        for name, want in wanted.items():
            already = name in self._registered
            if want and not already:
                ok = False
                errors = []
                for hk_id, (mods, vk) in zip(_HOTKEY_IDS[name],
                                             HOTKEY_DEFS[name]):
                    # 1つでも登録できれば、その名前は有効とみなす。
                    # 配列違いで存在しないキーや、他のアプリに
                    # 先取りされている組み合わせは登録に失敗するが、
                    # 残りが生きていれば機能としては使える。
                    if user32.RegisterHotKey(None, hk_id, mods, vk):
                        ok = True
                    else:
                        # 失敗の理由を控える。1409 は
                        # ERROR_HOTKEY_ALREADY_REGISTERED（他のアプリが
                        # 既に使っている）。原因の切り分けに要る。
                        try:
                            errors.append(ctypes.get_last_error())
                        except Exception:
                            errors.append(0)
                if ok:
                    self._registered.add(name)
                self._last_error[name] = (None if ok else errors)
            elif not want and already:
                for hk_id in _HOTKEY_IDS[name]:
                    user32.UnregisterHotKey(None, hk_id)
                self._registered.discard(name)
                self._last_error.pop(name, None)
        self._done_generation = generation

    def status(self):
        """
        いま実際に登録できているかを返す（診断用）。

        「押しても簡易入力が出ない」とき、原因が
        「登録に失敗している」のか「登録はできているが
        キーが届いていない」のかを切り分けるために要る。
        """
        return {
            'supported': HAS_SUPPORT,
            'running': self._running,
            'enabled': dict(self._enabled),
            'registered': set(self._registered),
            'errors': dict(self._last_error),
        }

    def _unregister_all(self):
        for name in list(self._registered):
            for hk_id in _HOTKEY_IDS[name]:
                try:
                    user32.UnregisterHotKey(None, hk_id)
                except Exception:
                    pass
        self._registered.clear()

    @staticmethod
    def _name_for_id(hk_id):
        return _ID_TO_NAME.get(hk_id)
