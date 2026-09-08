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
編集中の内容の自動保存と、次回起動時の復元。

Windows 11 のメモ帳と同じ使い勝手を目指す:

  - 書いた内容は自動的に控えられる
  - 保存せずに閉じても、次に開くと続きがある
  - ファイルとして保存済みなら、そのファイルとの結び付きも覚える

「保存」（ファイルへの書き出し）とは別物であることに注意。
こちらはユーザーが意識しない裏方の控えで、
アプリのフォルダに session.json として置かれる。

保存形式は最初から **タブの配列** にしてある。
今は1つしか使っていないが、あとでタブ機能を入れるときに
形式を変えずに済ませるため（形式が変わると、
それまでの控えが読めなくなって書きかけが消えてしまう）。

    {
      "version": 1,
      "active": 0,                  # 選択中のタブの位置
      "tabs": [
        {
          "text": "書きかけの内容",
          "path": "C:/.../memo.txt",   # 保存先。未保存なら null
          "saved": false,              # 保存済みの内容と一致しているか
          "cursor": "3.5",             # カーソル位置
          "scroll": 0.0                # スクロール位置
        }
      ]
    }
"""

import json
import os
import time

SESSION_VERSION = 1


def new_tab(text='', path=None, saved=True, cursor='1.0', scroll=0.0,
            title=None, bookmarks=None, top=None):
    """タブ1つぶんの控えを作る。

    top: 画面のいちばん上に見えていた**行番号**（1始まり）。
        scroll（割合）は折り返しや解析後の描き直しで意味がずれる
        ので、復元はこちらを優先する（2026-08-16・実機の報告
        「タブ移動して戻ってくると、スクロール位置が変わって
        しまう」）。古い控えには無いので None を許す。
    """
    return {
        'text': text,
        'path': path,
        'saved': saved,
        'cursor': cursor,
        'scroll': scroll,
        'top': top,
        'title': title,
        'bookmarks': sorted(bookmarks) if bookmarks else [],
    }


FRESH_TAB_BOOKMARKS = (1,)


def fresh_tab(**kw):
    """
    **新しく作る**タブの控え（項目48-RA・2026-09-05・うにさんの指定
    「新規タブができた際、1行目を自動でブックマークオンにする」）。

    ★★ **`new_tab` の既定値にしてはいけない。** `new_tab` は
    **控えからの復元**（`load`）と**1.5秒ごとの自動保存**
    （`update_active`）も通る工場なので、そこに既定を置くと
    **本人が外した1行目の印が、打つたびに戻ってくる**。

    「1行目に印を付ける」と書くのは**この1か所だけ**（48-GN——
    決めているのは最初の行）。ほかの道は `fresh_tab()` を呼ぶ。
    呼び手が `bookmarks=` を渡したときは**そちらが勝つ**
    （`setdefault`）ので、控えから戻す道を塞がない。
    """
    kw.setdefault('bookmarks', FRESH_TAB_BOOKMARKS)
    return new_tab(**kw)


def tab_title(tab):
    """タブに表示する名前。未保存なら「無題」。"""
    if tab.get('title'):
        return tab['title']
    path = tab.get('path')
    if path:
        return os.path.basename(path)
    return '無題'


def is_blank(tab):
    """中身が実質から（空行だけ）かどうか。"""
    return not (tab.get('text') or '').strip()


class SessionStore:
    """
    編集中の内容の控え。

    書くたびに保存すると重いので、呼び出し側が一定間隔で
    save() を呼ぶ想定（app.py が入力の落ち着きを見て呼ぶ）。
    """

    def __init__(self, path=None):
        self.path = path
        self.tabs = []
        self.active = 0

    # ------------------------------------------------------------
    def set_single(self, text, path=None, saved=True, cursor='1.0',
                   scroll=0.0, bookmarks=None):
        """タブ1つだけの状態にする（タブ機能が入るまでの使い方）。"""
        self.tabs = [new_tab(text, path, saved, cursor, scroll,
                            bookmarks=bookmarks)]
        self.active = 0

    def reset_fresh(self, text='', path=None, saved=True):
        """
        **新しく作り直して1枚にする**（項目48-RA）。起動して控えが
        読めなかったときの道。`fresh_tab` を通すので、
        「1行目に印を付ける」は**あちらの1か所のまま**（48-GN）。
        """
        self.tabs = [fresh_tab(text=text, path=path, saved=saved)]
        self.active = 0

    def current(self):
        if not self.tabs:
            return None
        i = max(0, min(self.active, len(self.tabs) - 1))
        return self.tabs[i]

    # --- タブ操作（タブ管理UI・2026-08-09） ---
    def update_active(self, tab):
        """選択中のタブの控えを差し替える。タブが無ければ作る。"""
        if not self.tabs:
            self.tabs = [tab]
            self.active = 0
            return
        i = max(0, min(self.active, len(self.tabs) - 1))
        self.tabs[i] = tab

    def add_tab(self, tab=None, activate=True):
        """タブを1つ足す。戻り値はその位置。"""
        # **新しく作る**ので `fresh_tab`（項目48-RA）。控えから戻す
        # ときは呼び手が `tab` を渡すので、そちらはそのまま
        self.tabs.append(tab if tab is not None else fresh_tab())
        i = len(self.tabs) - 1
        if activate:
            self.active = i
        return i

    def remove_tab(self, index):
        """
        タブを1つ閉じる。最後の1つを閉じたら空のタブを作る。

        戻り値: 閉じたあとに表示すべきタブが**変わった**か
        （選択中のタブを閉じた・最後の1つを閉じた場合に True）。
        """
        if not (0 <= index < len(self.tabs)):
            return False
        old_active = max(0, min(self.active, len(self.tabs) - 1))
        del self.tabs[index]
        if not self.tabs:
            # 最後の1つを閉じた補充も「新しく作る」（項目48-RA）
            self.tabs = [fresh_tab()]
            self.active = 0
            return True
        if index == old_active:
            self.active = min(index, len(self.tabs) - 1)
            return True
        self.active = old_active - 1 if index < old_active else old_active
        return False

    def has_content(self):
        """復元する意味のある内容があるか。"""
        return any(not is_blank(t) or t.get('path') for t in self.tabs)

    # ------------------------------------------------------------
    def save(self, path=None):
        """
        控えを書き出す。

        書き込みは一時ファイル経由にする。書いている途中で
        アプリが落ちると、中途半端な内容で上書きされて
        書きかけが丸ごと消えるため。
        """
        path = path or self.path
        if not path:
            return False
        data = {
            'version': SESSION_VERSION,
            'saved_at': time.time(),
            'active': self.active,
            'tabs': self.tabs,
        }
        try:
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, path)
            return True
        except Exception:
            return False

    def load(self, path=None):
        """
        控えを読み込む。

        読めなければ何もしない（起動は止めない）。
        壊れた控えのせいでアプリが開かなくなるのが一番困るため。
        """
        path = path or self.path
        if not path or not os.path.exists(path):
            return False
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return False
        if data.get('version') != SESSION_VERSION:
            return False
        tabs = data.get('tabs')
        if not isinstance(tabs, list) or not tabs:
            return False
        clean = []
        for t in tabs:
            if not isinstance(t, dict):
                continue
            clean.append(new_tab(
                text=t.get('text', ''),
                path=t.get('path'),
                saved=bool(t.get('saved', True)),
                cursor=t.get('cursor', '1.0'),
                scroll=t.get('scroll', 0.0) or 0.0,
                title=t.get('title'),
                bookmarks=t.get('bookmarks'),
                top=t.get('top'),  # 48-VI: 保存した表示行番号も復元する
            ))
        if not clean:
            return False
        self.tabs = clean
        self.active = max(0, min(int(data.get('active', 0) or 0),
                                 len(clean) - 1))
        return True
