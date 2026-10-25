# -*- coding: utf-8 -*-
"""The analysis child ends when its parent (the main window's process) is gone (2026-10-23 うにさん).

Before, a parent killed from Task Manager or crashed left its child waiting for work, still holding
600-850 MB. Now the child waits on its parent's handle and ends itself. A parent that closes its worker
as usual is unchanged: the child ends at once and the parent sees it end."""
import ctypes
import os
import subprocess
import sys
import textwrap
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = textwrap.dedent('''
    import sys, time
    sys.path.insert(0, %r)
    import analysis_worker
    if __name__ == '__main__':
        worker = analysis_worker.Worker()
        print(worker.process.pid, flush=True)
        if sys.argv[1] == 'close':
            sys.stdin.readline()
            worker.close()
            print('closed', worker.process.exitcode, flush=True)
        time.sleep(600)
''') % HERE

SYNCHRONIZE = 0x00100000
k32 = ctypes.WinDLL('kernel32', use_last_error=True) if sys.platform == 'win32' else None


def ended_within(pid, seconds):
    """True if the process `pid` ends within `seconds` (already gone counts)."""
    handle = k32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return True
    try:
        return k32.WaitForSingleObject(handle, int(seconds * 1000)) == 0
    finally:
        k32.CloseHandle(handle)


@unittest.skipUnless(sys.platform == 'win32', 'Windows processes')
class ExitWithParentTests(unittest.TestCase):
    def start(self, mode):
        script = os.path.join(HERE, '_worker_parent_probe.py')
        with open(script, 'w', encoding='utf-8') as f:
            f.write(PARENT)
        self.addCleanup(lambda: os.path.exists(script) and os.remove(script))
        parent = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', script, mode], cwd=HERE,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: parent.poll() is None and parent.kill())
        child = int(parent.stdout.readline())
        self.addCleanup(lambda: os.system('taskkill /F /PID %d >NUL 2>&1' % child) if not ended_within(child, 0) else None)
        self.assertFalse(ended_within(child, 1.0))           # the child is up and waiting for work
        return parent, child

    def test_the_child_ends_when_its_parent_is_killed(self):
        parent, child = self.start('kill')
        parent.kill()                                        # TerminateProcess: no atexit, no daemon clean-up
        parent.wait(10)
        self.assertTrue(ended_within(child, 5.0), 'the analysis child outlived its killed parent')

    def test_closing_as_usual_is_unchanged(self):
        parent, child = self.start('close')
        parent.stdin.write('\n'); parent.stdin.flush()
        self.assertTrue(parent.stdout.readline().startswith('closed'))
        self.assertTrue(ended_within(child, 2.0))
        self.assertIsNone(parent.poll())                     # the parent itself goes on


if __name__ == '__main__':
    unittest.main()
