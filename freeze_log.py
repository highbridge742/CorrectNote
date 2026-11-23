# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""本体が固まった時の記録（開発版・2026-11-23 うにさん「まだ入力後に4秒ほど固まるのがあります」）。

・番犬（CN_FREEZE_LOG_STACK=1 の時だけ）: 本体の after で 100ms ごとに faulthandler.dump_traceback_later(1.0) を掛け直す。
  本体が1秒以上止まった時だけ、その時の全スレッドの Python の呼び出しの並び（ファイル名・行番号・関数名だけ）が出る。
  既定では掛けない（2026-11-24: 他のスレッドが動いている最中に全スレッドの並びを書き出すと、ときどき 0xC0000005 で
  落ちた。行の状態の試験が4回に2回落ち、これを外すと5回とも通った）。
・入れるのは開発の PC だけ（アプリのフォルダに freeze_log.enable がある時）。公開版・EXE・試験の写しには無いので入らない。
・止まりが終わったら、その時刻と長さを1行書く（0.3秒を超えた止まり）。
・メモ欄・補正欄の Tk の呼び出しを時計で包み、0.3秒を超えた止まりの間に呼ばれた命令を「命令の名前ごとの回数と合計時間」
  だけ書く。引数（本文の字・タグの中身）は書かない。ほかに書くのは、行数・カーソルの行番号・その行の字数だけ。
・記録は保存の場所（savedata_dir）の freeze_log.txt 1つ。2MB を超えたら freeze_log.old.txt に回して書き直す。
CN_FREEZE_LOG=0 で入れない。
"""
import collections
import os
import sys
import time

NAME = 'freeze_log.txt'
OLD_NAME = 'freeze_log.old.txt'
MAX_BYTES = 2 * 1024 * 1024
TICK_MS = 100
DUMP_AFTER_S = 1.0
REPORT_S = 0.3
_CALLS_KEEP = 20000
CB_KEEP_S = 0.002       # 手続きの長さを控える下限（暇が来ない時の内訳に、細かい手続きの積み重ねも数える）


MARKER = 'freeze_log.enable'


def enabled(environ=None, frozen=None, folder=None):
    """入れるか。開発の PC だけ既定で入れる（アプリのフォルダに MARKER の印のファイルがある時）。EXE（Store 版を含む）・
    公開のリポジトリ（.py で動かす GitHub の検査も）・試験の写しには印が無いので入れない（2026-11-23 うにさん「リリースでは
    解析のログを取らないようにする。オンオフ管理でオフになっていればよい」・2026-11-24 公開用の一式の試験で落ちた）。
    CN_FREEZE_LOG=0 ならどこでも入れない、=1 ならどこでも入れる"""
    environ = os.environ if environ is None else environ
    frozen = bool(getattr(sys, 'frozen', False)) if frozen is None else frozen
    value = environ.get('CN_FREEZE_LOG')
    if value in ('0', '1'):
        return value == '1'
    if frozen:
        return False
    folder = os.path.dirname(os.path.abspath(__file__)) if folder is None else folder
    return os.path.exists(os.path.join(folder, MARKER))


def stack_on(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get('CN_FREEZE_LOG_STACK') == '1'


class _TkTimer:
    """widget.tk の代わり。call の時間を（命令の名前・時刻・長さ）だけ控える。それ以外はそのまま渡す。"""

    def __init__(self, real, sink):
        self._real = real
        self._sink = sink

    def call(self, *args):
        t = time.perf_counter()
        try:
            return self._real.call(*args)
        finally:
            try:
                a = args[0] if len(args) == 1 and isinstance(args[0], (tuple, list)) else args
                a = [x if isinstance(x, str) else str(x) for x in a[:3]]
                name = a[1] if len(a) > 1 and a[0].startswith('.') else (a[0] if a else '')
                if not name.isidentifier():
                    name = '?'                                   # 命令の名前でない物（字など）は書かない
                if name in ('get', 'index', 'dlineinfo') :
                    # 何千回も呼ばれる命令は、呼んだ手続きの名前も（ファイル・関数の名前だけ）
                    try:
                        f = sys._getframe(2)
                        if f.f_code.co_name in ('get', 'index', 'dlineinfo', 'count'):
                            f = f.f_back
                        up = f.f_back
                        # 呼んだ手続きの、もう1つ上も（何千回も呼ぶ手続きを、誰が呼んでいるか・2026-11-23）
                        name = '%s<%s.%s<%s' % (name, os.path.basename(f.f_code.co_filename)[:-3], f.f_code.co_name,
                                                up.f_code.co_name if up is not None else '-')
                    except Exception:
                        pass
                if name in ('tag', 'mark', 'count', 'edit', 'window', 'image', 'peer') and len(a) > 2:
                    sub = a[2].lstrip('-')
                    if sub.isidentifier():
                        name = name + ' ' + sub              # 下位の命令の名前まで（引数は書かない）
                self._sink.append((t, name[:60], time.perf_counter() - t))
            except Exception:
                pass

    def __getattr__(self, name):
        return getattr(self._real, name)


class FreezeLog:
    def __init__(self, app, folder):
        self.app = app
        self.path = os.path.join(folder, NAME)
        self.old = os.path.join(folder, OLD_NAME)
        self.calls = collections.deque(maxlen=_CALLS_KEEP)
        self.fh = None
        self.last = None
        self.job = None
        self.closed = False
        self.arm_ms = []

    def start(self):
        import faulthandler
        self._open()
        self._write('start %s pid=%d' % (time.strftime('%Y-%m-%d %H:%M:%S'), os.getpid()))
        for name in ('editor', 'result_view'):
            w = getattr(self.app, name, None)
            if w is not None and not isinstance(getattr(w, 'tk', None), _TkTimer):
                try:
                    w.tk = _TkTimer(w.tk, self.calls)
                except Exception:
                    pass
        self._faulthandler = faulthandler
        self.last = time.perf_counter()
        self.callbacks = collections.deque(maxlen=20000)
        self._wrap_callbacks()
        try:
            self.app.root.bind_all('<KeyPress>', self._key_latency, add='+')
        except Exception:
            pass
        self._tick()

    def _wrap_callbacks(self):
        """Tk から呼ばれる手続き（打鍵・after など）の長さを、名前だけ控える（50ms を超えたもの）。"""
        import tkinter
        if getattr(tkinter.CallWrapper, '_cn_freeze_wrapped', False):
            return
        real = tkinter.CallWrapper.__call__
        sink = self.callbacks

        def timed(wrapper, *args):
            t = time.perf_counter()
            try:
                return real(wrapper, *args)
            finally:
                ms = time.perf_counter() - t
                if ms > CB_KEEP_S:
                    try:
                        f = wrapper.func
                        if getattr(f, '__qualname__', '').endswith('callit') and f.__closure__ and 'func' in f.__code__.co_freevars:
                            f = f.__closure__[f.__code__.co_freevars.index('func')].cell_contents
                        name = getattr(f, '__qualname__', None) or getattr(getattr(f, '__func__', None), '__qualname__', '?')
                        sink.append((t, str(name)[:60], ms))
                    except Exception:
                        pass
        tkinter.CallWrapper.__call__ = timed
        tkinter.CallWrapper._cn_freeze_wrapped = True

    def _key_latency(self, event):
        """押したキーが本体に届くまでの遅れ（Windows の押した時刻と今の差）。0.3秒を超えたら1行（キーの字は書かない）。"""
        try:
            if sys.platform != 'win32' or not getattr(event, 'time', 0):
                return
            import ctypes
            now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
            lag = (now - (int(event.time) & 0xFFFFFFFF)) & 0xFFFFFFFF
            if 300 < lag < 60000:
                end = time.perf_counter()
                self._write('keylag %s lag_ms=%d %s %s' % (time.strftime('%H:%M:%S'), lag, self._where(),
                                                         self._summary(end - lag / 1000.0, end)))
        except Exception:
            pass

    def _summary(self, start, end):
        agg = {}
        for t, name, ms in list(self.calls):
            if start - 0.01 <= t <= end:
                c = agg.setdefault(name, [0, 0.0])
                c[0] += 1
                c[1] += ms
        top = sorted(agg.items(), key=lambda kv: -kv[1][1])[:12]
        cb = {}
        for t, name, ms in list(getattr(self, 'callbacks', ())):
            if start - 0.01 <= t <= end:
                c = cb.setdefault(name, [0, 0.0])
                c[0] += 1
                c[1] += ms
        cbtop = sorted(cb.items(), key=lambda kv: -kv[1][1])[:10]
        busy = sum(v[1] for v in cb.values())
        return 'cbsum=%dms/%d tk=[%s] cb=[%s]' % (
            int(busy * 1000), sum(v[0] for v in cb.values()),
            ', '.join('%s:%dx%dms' % (k, v[0], int(v[1] * 1000)) for k, v in top),
            ', '.join('%s:%dx%dms' % (k, v[0], int(v[1] * 1000)) for k, v in cbtop))

    def _open(self):
        try:
            if os.path.exists(self.path) and os.path.getsize(self.path) > MAX_BYTES:
                try:
                    os.replace(self.path, self.old)
                except OSError:
                    pass
            if self.fh is not None:
                try:
                    self.fh.close()
                except Exception:
                    pass
            self.fh = open(self.path, 'a', encoding='utf-8', buffering=1)
        except Exception:
            self.fh = None

    def _write(self, line):
        if self.fh is None:
            return
        try:
            self.fh.write(line + '\n')
            self.fh.flush()
        except Exception:
            pass

    def _watch_ime_commit(self):
        """IME が確定を知らせた時刻（ime_burst の見張りが覚える）から、メモ欄の字が変わるまでの遅れ。0.3秒を超えたら
        1行（確定の字は書かない・字数だけ）。100ms ごとの見回りなので、細かさは 0.1 秒。"""
        try:
            watch = getattr(self.app, '_ime_burst_watch', None)
            at = getattr(watch, '_at', 0.0) if watch is not None else 0.0
            ed = self.app.editor
            mark = (str(ed.index('insert')), str(ed.index('end-1c')))
        except Exception:
            return
        # 変換中（IME の入力の途中）の長さ: 100ms ごとに見て、始まりと終わりの時刻を控える
        try:
            import ime_watch
            live = bool(ime_watch.composition_active(int(self.app.root.winfo_id())))
        except Exception:
            live = None
        now_m = time.monotonic()
        if live and getattr(self, '_comp_from', None) is None:
            self._comp_from = now_m
        elif live is False and getattr(self, '_comp_from', None) is not None:
            self._comp_len = now_m - self._comp_from
            self._comp_from = None
        if at and at != getattr(self, '_ime_seen', None):
            self._ime_seen = at
            self._ime_wait = (at, mark)
            # 確定から、次に Tk が暇になる（画面が描かれる）までの遅れ（2026-11-23・字が入るのは確定のすぐ後でも、
            # 暇が来ないと描かれない。前の lag_ms は、見回りの時に字がもう入っていると次の打鍵までを数えていた）
            try:
                self.app.root.after_idle(lambda at=at: self._ime_drawn(at))
            except Exception:
                pass
            return
        wait = getattr(self, '_ime_wait', None)
        if wait is None:
            return
        if mark != wait[1]:
            lag = time.monotonic() - wait[0]
            self._ime_wait = None
            comp = getattr(self, '_comp_len', None)
            self._comp_len = None
            if lag > 0.3 and os.environ.get('CN_FREEZE_LOG_OLD_IMELAG') == '1':
                end = time.perf_counter()
                self._write('imelag %s lag_ms=%d comp_ms=%s %s %s' % (
                    time.strftime('%H:%M:%S'), int(lag * 1000), int(comp * 1000) if comp else '-', self._where(),
                    self._summary(end - lag, end)))
        elif time.monotonic() - wait[0] > 10:
            self._ime_wait = None

    def _ime_drawn(self, at):
        lag = time.monotonic() - at
        if lag > REPORT_S:
            end = time.perf_counter()
            comp = getattr(self, '_comp_len', None)
            self._write('imedraw %s lag_ms=%d comp_ms=%s %s %s' % (
                time.strftime('%H:%M:%S'), int(lag * 1000), int(comp * 1000) if comp else '-', self._where(),
                self._summary(end - lag, end)))

    def _idle_probe(self):
        """Tk が暇になる（画面を描く）までの遅れ。見回りごとに after_idle を1つ置き、呼ばれるまでの時間を見る。
        本体は止まっていなくても（見回りは動く）、after の手続きが続くと暇が来ず、打った字も入力カーソルも描かれない。"""
        if getattr(self, '_idle_from', None) is not None:
            return
        self._idle_from = time.perf_counter()
        try:
            self.app.root.after_idle(self._idle_came)
        except Exception:
            self._idle_from = None

    def _idle_came(self):
        start = getattr(self, '_idle_from', None)
        self._idle_from = None
        if start is None or self.closed:
            return
        now = time.perf_counter()
        if now - start > REPORT_S:
            self._write('idlelag %s wait_ms=%d %s %s' % (
                time.strftime('%H:%M:%S'), int((now - start) * 1000), self._where(), self._summary(start, now)))

    def _watch_caret(self):
        """入力カーソルの見え方（insertwidth・insertofftime・insertontime・insertbackground・焦点の窓の種類）が変わったら
        時刻と値を1行（本文なし）。"""
        try:
            ed = self.app.editor
            focus = ed.focus_get()
            where = ('editor' if focus is ed else 'result' if focus is getattr(self.app, 'result_view', None)
                     else 'quick' if focus is getattr(self.app, '_quick_text', None)
                     else (focus.winfo_class() if focus is not None else 'none'))
            state = (str(ed.cget('insertwidth')), str(ed.cget('insertofftime')), str(ed.cget('insertontime')),
                     str(ed.cget('insertbackground')), str(ed.cget('state')), where)
        except Exception:
            return
        if state != getattr(self, '_caret_state', None):
            if getattr(self, '_caret_state', None) is not None:
                self._write('caret %s width=%s off=%s on=%s color=%s state=%s focus=%s' % ((time.strftime('%H:%M:%S'),) + state))
            self._caret_state = state

    def _where(self):
        """本文の字は書かず、数だけ。"""
        try:
            ed = self.app.editor
            rows = int(str(ed.index('end-1c')).split('.')[0])
            row = int(str(ed.index('insert')).split('.')[0])
            chars = len(ed.get('%d.0' % row, '%d.end' % row))
            tabs = len(getattr(getattr(self.app, 'session', None), 'tabs', None) or ())
            return 'rows=%d insert_row=%d row_chars=%d tabs=%d' % (rows, row, chars, tabs)
        except Exception:
            return ''

    def _tick(self):
        if self.closed:
            return
        now = time.perf_counter()
        gap = now - self.last if self.last is not None else 0.0
        if gap > REPORT_S + TICK_MS / 1000.0:
            self._write('freeze %s gap_ms=%d %s %s' % (
                time.strftime('%H:%M:%S'), int(gap * 1000), self._where(), self._summary(self.last, now)))
        self.last = now
        self._watch_caret()
        self._watch_ime_commit()
        self._idle_probe()
        t = time.perf_counter()
        try:
            if self.fh is not None and stack_on():
                self._faulthandler.dump_traceback_later(DUMP_AFTER_S, repeat=False, file=self.fh, exit=False)
        except Exception:
            pass
        self.arm_ms.append((time.perf_counter() - t) * 1000)
        if len(self.arm_ms) > 200:
            del self.arm_ms[:100]
        if len(self.arm_ms) % 100 == 0:
            try:
                if os.path.getsize(self.path) > MAX_BYTES:
                    self._open()
            except OSError:
                pass
        try:
            self.job = self.app.root.after(TICK_MS, self._tick)
        except Exception:
            self.job = None

    def close(self):
        self.closed = True
        try:
            self._faulthandler.cancel_dump_traceback_later()
        except Exception:
            pass
        if self.job is not None:
            try:
                self.app.root.after_cancel(self.job)
            except Exception:
                pass
        self._write('stop %s' % time.strftime('%Y-%m-%d %H:%M:%S'))
        try:
            if self.fh is not None:
                self.fh.close()
        except Exception:
            pass
        self.fh = None


def install(app, folder):
    """入れる（CN_FREEZE_LOG=0 で入れない）。入れた物を返す。"""
    if not enabled() or getattr(app, '_freeze_log', None) is not None:
        return getattr(app, '_freeze_log', None)
    try:
        log = FreezeLog(app, folder)
        log.start()
        app._freeze_log = log
        return log
    except Exception:
        return None
