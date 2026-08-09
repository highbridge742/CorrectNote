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
「打った文字が入らない／勝手に消える」原因を切り分けるための診断。

    py keylog.py

**このアプリ（app.py）とは一切関係ない、素の tkinter の入力欄**を出す。
アプリ側の束縛（bind）を一切張っていないので、

  - ここでも同じ症状が出る  → 原因は tkinter と IME のやりとり。
                              アプリ側の束縛は無関係。
  - ここでは出ない          → 原因はアプリ側の束縛。
                              どのキーが届いているかが下の記録で分かる。

という切り分けができる。

--------------------------------------------------------------------
 やってほしいこと
--------------------------------------------------------------------
 1. このスクリプトを実行する
 2. 上の白い入力欄に、報告と同じ操作をする
      a. 適当に2行ぶん文字を打ち、1行目の行末にカーソルを置く
      b. 「る」のキー → F9 → F10 → Enter
      c. 「ー」のキー → F9 → F10 → Enter
      d. テンキーの「.」、テンキーの「-」
 3. 下の記録欄の内容を全部コピーして渡してください
    （「記録をコピー」ボタンでクリップボードに入ります）

--------------------------------------------------------------------
 記録の見かた（渡してもらえれば私が読みます）
--------------------------------------------------------------------
 keysym   Tk がそのキーをどう解釈したか（period / minus / Delete 等）
 keycode  Windows の仮想キーコード
 char     実際に入力されようとしている文字（空なら「文字が無い」）
 state    修飾キーの状態。**Ctrl や Alt が入っていないか**が要点。
          Ctrl が付いていると、Tk はその打鍵を「文字の入力ではない」
          とみなして無視する（＝文字が入らない）。さらに d や h に
          当たると Tk の既定動作で文字が削除される。
 文字数   その打鍵の直後に、入力欄の中身が何文字になったか。
          減っていれば、そこで削除が起きている。
"""

import tkinter as tk

# 修飾キーのビット（X11 由来。Windows の Tk でも同じ値が使われる）
_MODS = [
    (0x0001, 'Shift'),
    (0x0002, 'CapsLock'),
    (0x0004, 'Control'),
    (0x0008, 'Alt/Mod1'),
    (0x0010, 'NumLock'),
    (0x0020, 'Mod3'),
    (0x0040, 'Mod4'),
    (0x0080, 'AltGr/Mod5'),
]


def describe_state(state):
    try:
        state = int(state)
    except Exception:
        return str(state)
    names = [name for bit, name in _MODS if state & bit]
    return f'{state}({"+".join(names) if names else "なし"})'


def show(ch):
    """char をそのまま出すと見分けが付かないので、目に見える形にする。"""
    if ch == '':
        return '(空)'
    if len(ch) == 1 and ord(ch) < 0x20:
        return f'制御文字 0x{ord(ch):02x}'
    return repr(ch)


class KeyLog:
    def __init__(self, root):
        self.root = root
        root.title('キー入力の記録（切り分け用）')
        root.geometry('820x600')

        tk.Label(
            root, anchor='w', justify='left',
            text=('↓ ここに打ってください（素の入力欄。アプリの束縛は一切ありません）\n'
                  '  2行ぶん打って1行目の行末にカーソルを置き、'
                  '「る」→F9→F10→Enter などを試してください'),
        ).pack(fill='x', padx=8, pady=(8, 0))

        self.entry = tk.Text(root, height=6, font=('Yu Gothic UI', 12),
                             undo=True)
        self.entry.pack(fill='x', padx=8, pady=4)
        self.entry.insert('1.0', 'あいうえお\nかきくけこ\n')
        self.entry.mark_set('insert', '1.end')
        self.entry.focus_set()

        # 記録のためだけに束縛する。'break' は返さないので、
        # 入力欄の本来の動きには一切干渉しない。
        self.entry.bind('<KeyPress>', self.on_press, add=True)
        self.entry.bind('<KeyRelease>', self.on_release, add=True)

        bar = tk.Frame(root)
        bar.pack(fill='x', padx=8)
        tk.Button(bar, text='記録をコピー', command=self.copy).pack(side='left')
        tk.Button(bar, text='記録を消す', command=self.clear).pack(side='left',
                                                              padx=6)
        tk.Label(bar, text='  ← 押してから、貼り付けて渡してください').pack(
            side='left')

        self.log = tk.Text(root, font=('Consolas', 9), wrap='none')
        self.log.pack(fill='both', expand=True, padx=8, pady=8)

        self.write(f'tkinter: {tk.TkVersion}  patchlevel: '
                   f'{root.tk.call("info", "patchlevel")}')
        self.write('---- ここから記録 ----')

    def write(self, line):
        self.log.insert('end', line + '\n')
        self.log.see('end')

    def content_len(self):
        try:
            return len(self.entry.get('1.0', 'end-1c'))
        except Exception:
            return -1

    def log_event(self, kind, event):
        # 打鍵の「あと」の文字数を見たいので、少し遅らせて記録する。
        # 押した瞬間はまだ入力欄が書き換わっていない。
        before = self.content_len()
        cursor = self.entry.index('insert')

        def later():
            after = self.content_len()
            diff = after - before
            mark = ''
            if diff < 0:
                mark = f'  ★{-diff}文字 消えた'
            elif diff == 0:
                mark = '  ★文字が入らなかった'
            self.write(
                f'{kind:9s} keysym={getattr(event, "keysym", "?"):12s} '
                f'keycode={getattr(event, "keycode", "?"):<4} '
                f'char={show(getattr(event, "char", "")):16s} '
                f'state={describe_state(getattr(event, "state", 0)):22s} '
                f'位置={cursor:6s} 文字数 {before}->{after}{mark}')

        self.root.after(1, later)

    def on_press(self, event):
        self.log_event('KeyPress', event)

    def on_release(self, event):
        # 離したほうは keysym だけ控える（押した側と対にして見る）
        self.write(f'{"KeyRelease":9s} keysym={event.keysym}')

    def copy(self):
        text = self.log.get('1.0', 'end-1c')
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.write('（記録をクリップボードにコピーしました）')

    def clear(self):
        self.log.delete('1.0', 'end')


if __name__ == '__main__':
    root = tk.Tk()
    KeyLog(root)
    root.mainloop()
