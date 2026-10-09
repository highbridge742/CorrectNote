# -*- coding: utf-8 -*-
"""IME handoff preserves fullwidth conversion bits and never writes source focus."""
import ctypes as C
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
import quick_ime as Q

class FullwidthSourceTests(unittest.TestCase):
 def source(self,mode,changed=False):
  user=Mock();user.GetForegroundWindow.return_value=123
  user.GetWindowThreadProcessId.return_value=456
  seen=[]
  def info(thread,ptr):
   self.assertEqual(thread,456);seen.append(True)
   ptr._obj.hwndFocus=790 if changed and len(seen)>1 else 789
   return True
  user.GetGUIThreadInfo.side_effect=info
  with patch.object(Q,'_api',return_value=user),patch.object(Q,'window_mode',return_value=mode) as read:
   result=Q.foreground_fullwidth_mode()
   read.assert_called_once_with(789)
  return result
 def test_fullwidth_hiragana_and_alphanumeric_keep_roman_and_script_bits(self):
  for conversion in (0x19,0x09,0x1b,0x18,0x08):
   with self.subTest(conversion=conversion):self.assertEqual(self.source((True,conversion)),conversion)
 def test_closed_halfwidth_and_unknown_do_not_change_new_window(self):
  for mode in (None,(False,0x19),(True,0x10),(True,0x13)):
   with self.subTest(mode=mode):self.assertIsNone(self.source(mode))
 def test_focus_change_during_query_discards_the_snapshot(self):
  self.assertIsNone(self.source((True,0x19),changed=True))
 def test_no_foreground_or_no_focused_control_is_unknown(self):
  user=Mock();user.GetForegroundWindow.return_value=0
  with patch.object(Q,'_api',return_value=user),patch.object(Q,'window_mode') as read:
   self.assertIsNone(Q.foreground_fullwidth_mode());read.assert_not_called()
 def test_control_distinguishes_successful_zero_from_timeout(self):
  user=Mock();user.SendMessageTimeoutW.return_value=1
  with patch.object(Q,'_api',return_value=user):self.assertEqual(Q._control(123,5),0)
  user.SendMessageTimeoutW.return_value=0
  with patch.object(Q,'_api',return_value=user):self.assertIsNone(Q._control(123,5))
  self.assertEqual(user.SendMessageTimeoutW.call_args.args[4:6],(0x23,40))

class DestinationModeTests(unittest.TestCase):
 def setUp(self):
  self.imm=Mock();self.hwnd=0x123456789;self.himc=0x987654321
  self.imm.ImmGetContext.return_value=self.himc
  self.opened=False;self.conversion=0x10;self.sentence=3
  def read(h,conv,sent):
   self.assertEqual(h,self.himc);conv._obj.value=self.conversion;sent._obj.value=self.sentence;return True
  self.imm.ImmGetConversionStatus.side_effect=read
  self.imm.ImmGetOpenStatus.side_effect=lambda h:self.opened
  def convert(h,conv,sent):self.assertEqual((h,sent),(self.himc,3));self.conversion=conv;return True
  self.imm.ImmSetConversionStatus.side_effect=convert
  def opened(h,state):self.assertEqual(h,self.himc);self.opened=bool(state);return True
  self.imm.ImmSetOpenStatus.side_effect=opened
 def test_only_destination_context_is_changed_and_released(self):
  import ime_watch
  with patch.object(ime_watch,'_imm32',return_value=self.imm),patch.object(Q,'window_mode',side_effect=lambda h:(self.opened,self.conversion)):
   self.assertTrue(Q.apply_fullwidth_mode(self.hwnd,0x19))
  self.imm.ImmGetContext.assert_called_once_with(self.hwnd)
  self.imm.ImmReleaseContext.assert_called_once_with(self.hwnd,self.himc)
  self.assertEqual((self.opened,self.conversion,self.sentence),(True,0x19,3))
 def test_failed_context_read_releases_and_reports_failure(self):
  import ime_watch
  self.imm.ImmGetConversionStatus.side_effect=None;self.imm.ImmGetConversionStatus.return_value=False
  with patch.object(ime_watch,'_imm32',return_value=self.imm):self.assertFalse(Q.apply_fullwidth_mode(self.hwnd,0x19))
  self.imm.ImmReleaseContext.assert_called_once_with(self.hwnd,self.himc)
  self.imm.ImmSetOpenStatus.assert_not_called()
 def test_unknown_or_halfwidth_does_not_touch_any_context(self):
  import ime_watch
  with patch.object(ime_watch,'_imm32') as factory:
   for mode in (None,0x10,0):self.assertFalse(Q.apply_fullwidth_mode(self.hwnd,mode))
   factory.assert_not_called()
 def test_focus_reset_fallback_addresses_only_destination_ime(self):
  import ime_watch
  self.imm.ImmGetDefaultIMEWnd.return_value=567
  with patch.object(ime_watch,'_imm32',return_value=self.imm),patch.object(Q,'window_mode',side_effect=[(False,0),(True,0x19)]),patch.object(Q,'_control',return_value=0) as command:
   self.assertTrue(Q.apply_fullwidth_mode(self.hwnd,0x19))
   self.assertEqual([c.args for c in command.call_args_list],[(567,2,0x19),(567,6,1)])
 def test_ime_refusal_remains_failure(self):
  import ime_watch
  self.imm.ImmGetDefaultIMEWnd.return_value=567
  with patch.object(ime_watch,'_imm32',return_value=self.imm),patch.object(Q,'window_mode',return_value=(False,0)),patch.object(Q,'_control',return_value=None):
   self.assertFalse(Q.apply_fullwidth_mode(self.hwnd,0x19))

if __name__=='__main__':unittest.main()