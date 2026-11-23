"""verify_remap - 自动判定侧键映射到底是固件生效还是软件在干活。

判据 (关键区别在 injected 标记):
    硬件发出的 Ctrl+C/V  -> 固件映射生效
    软件注入的 Ctrl+C/V  -> 是 btnremap.py 在干活
    出现 XBUTTON          -> 固件没生效, 侧键仍然发的是鼠标按键

用法: 双击 verify_remap.cmd, 然后按一下两个侧键, 窗口会自动给结论。
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_XBUTTONDOWN = 0x020B
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01

user32 = ctypes.WinDLL('user32', use_last_error=True)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.c_void_p)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('pt', wintypes.POINT), ('mouseData', wintypes.DWORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.c_void_p)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]

events = []
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verify_remap.log')

MOD_VK = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C}
CTRL_VK = {0x11, 0xA2, 0xA3}
_pressed_mods = set()

KEY_NAMES = {0x43: 'Ctrl+C', 0x56: 'Ctrl+V', 0x58: 'Ctrl+X'}


def fmt_kb(vk, injected):
    nm = KEY_NAMES.get(vk, f'VK 0x{vk:02X}')
    return f"键盘 {nm} {'(软件注入)' if injected else '(硬件)'}"


def kb_proc(nCode, wParam, lParam):
    if nCode == 0:
        k = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        injected = bool(k.flags & LLKHF_INJECTED)
        # 自己维护修饰键状态, 不用 GetAsyncKeyState (低级钩子执行时按键状态还没更新)
        if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if k.vkCode in MOD_VK:
                _pressed_mods.add(k.vkCode)
            elif k.vkCode in KEY_NAMES and (_pressed_mods & CTRL_VK):
                events.append((fmt_kb(k.vkCode, injected), injected, 'kb'))
                print(f"  >> {events[-1][0]}")
        elif wParam in (0x0101, 0x0105):  # KEYUP / SYSKEYUP
            _pressed_mods.discard(k.vkCode)
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


def ms_proc(nCode, wParam, lParam):
    if nCode == 0 and wParam == WM_XBUTTONDOWN:
        m = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        btn = (m.mouseData >> 16) & 0xFFFF
        injected = bool(m.flags & LLMHF_INJECTED)
        events.append((f"鼠标 XBUTTON{btn} {'(软件注入)' if injected else '(硬件)'}", injected, 'ms'))
        print(f"  >> {events[-1][0]}")
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


kb_cb = HOOKPROC(kb_proc)
ms_cb = HOOKPROC(ms_proc)


def verdict():
    hw_keys = [e for e in events if e[0].startswith('键盘') and not e[1]]
    hw_mouse = [e for e in events if e[2] == 'ms' and not e[1]]
    sw_keys = [e for e in events if e[0].startswith('键盘') and e[1]]

    if hw_keys:
        return ('PASS', '固件映射生效 —— 鼠标自己发出了键盘组合键，不依赖任何软件。\n'
                        '       拔下来插到别的电脑也是这个行为。')
    if hw_mouse:
        return ('FAIL', '固件映射没有生效 —— 侧键仍然发送鼠标按键（Windows 只看到 XBUTTON）。\n'
                        '       说明这次写入没能被固件应用，需要换 layer 或改用软件方案。')
    if sw_keys:
        return ('SOFTWARE', '只有软件注入的按键 —— 是 btnremap.py 在干活，不是固件。\n'
                            '       先结束 pythonw.exe 再测一次。')
    return ('NONE', '没有捕捉到任何侧键事件。请确认按的是侧面那两个键。')


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 45
    if not user32.SetWindowsHookExW(WH_KEYBOARD_LL, kb_cb, None, 0):
        print('安装键盘钩子失败')
        return 1
    if not user32.SetWindowsHookExW(WH_MOUSE_LL, ms_cb, None, 0):
        print('安装鼠标钩子失败')
        return 1

    print('=' * 56)
    print('  侧键映射验证')
    print('=' * 56)
    print(f'  监听中，{secs} 秒内请按一下两个侧键。')
    print('  提示：先结束 pythonw.exe（软件方案），否则结论会被干扰。')
    print('-' * 56)

    end = time.time() + secs
    msg = wintypes.MSG()
    while time.time() < end and len(events) < 4:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.02)

    print('-' * 56)
    code, text = verdict()
    print(f'结论: [{code}] {text}')
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{code}] {text}\n")
            for e in events:
                f.write(f"    {e[0]}\n")
    except OSError:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
