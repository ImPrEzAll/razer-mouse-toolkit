"""btnremap - 鼠标侧键重映射 (全局低级鼠标钩子, 不需要雷云/Synapse)

默认映射:
    前侧键 (Forward / XBUTTON2) -> Ctrl+C  复制
    后侧键 (Back    / XBUTTON1) -> Ctrl+V  粘贴

想改成别的动作, 只改下面的 ACTIONS 表即可。
常用动作: 'copy', 'paste', 'cut', 'undo', 'redo', 'enter', 'esc', 'browser_back'
也可以用 ('hotkey', [VK...]) 自定义, 例如 ('hotkey', [0x11, 0x54]) = Ctrl+T

用法:
    pyw btnremap.py           后台静默运行
    python btnremap.py -v     前台运行并打印每次触发 (调试用)
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

# ============ 映射表 (改这里) ============
XBUTTON1 = 0x0001   # 后侧键
XBUTTON2 = 0x0002   # 前侧键

ACTIONS = {
    XBUTTON2: 'copy',    # 前侧键 -> 复制
    XBUTTON1: 'paste',   # 后侧键 -> 粘贴
}

VK = {
    'ctrl': 0x11, 'shift': 0x10, 'alt': 0x12, 'win': 0x5B,
    'a': 0x41, 'c': 0x43, 'v': 0x56, 'x': 0x58, 'z': 0x5A, 'y': 0x59,
    't': 0x54, 'w': 0x57, 's': 0x53, 'f': 0x46, 'enter': 0x0D,
    'esc': 0x1B, 'tab': 0x09, 'space': 0x20,
    'back': 0xA6, 'forward': 0xA7, 'volume_up': 0xAF, 'volume_down': 0xAE,
    'media_play': 0xB3,
}

NAMED = {
    'copy':  [VK['ctrl'], VK['c']],
    'paste': [VK['ctrl'], VK['v']],
    'cut':   [VK['ctrl'], VK['x']],
    'undo':  [VK['ctrl'], VK['z']],
    'redo':  [VK['ctrl'], VK['y']],
    'back':  [VK['back']],
    'forward': [VK['forward']],
    'enter': [VK['enter']],
    'esc':   [VK['esc']],
    'tab':   [VK['tab']],
    'volume_up': [VK['volume_up']],
    'volume_down': [VK['volume_down']],
    'media_play': [VK['media_play']],
}
# ========================================

WH_MOUSE_LL = 14
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
LLMHF_INJECTED = 0x00000001
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('pt', wintypes.POINT),
        ('mouseData', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_void_p),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ('dx', wintypes.LONG), ('dy', wintypes.LONG),
        ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', wintypes.WORD), ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('union', _INPUT_UNION)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.SendInput.restype = wintypes.UINT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]

_verbose = '-v' in sys.argv or '--verbose' in sys.argv
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'btnremap.log')


def log(msg, always=False):
    """always=True 时无论是否 -v 都写日志文件, 用于判断开机自启是否成功"""
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    if _verbose:
        print(line, flush=True)
    if always or _verbose:
        try:
            with open(_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except OSError:
            pass



def send_keys(vk_list):
    """按下组合键再逆序松开"""
    events = []
    for vk in vk_list:
        ev = INPUT(type=INPUT_KEYBOARD)
        ev.union.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)
        events.append(ev)
    for vk in reversed(vk_list):
        ev = INPUT(type=INPUT_KEYBOARD)
        ev.union.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
        events.append(ev)
    arr = (INPUT * len(events))(*events)
    user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))


def resolve(action):
    if isinstance(action, str):
        return NAMED.get(action)
    if isinstance(action, (tuple, list)) and len(action) == 2 and action[0] == 'hotkey':
        return list(action[1])
    return None


_swallow_up = set()
_pressed = set()


def hook_proc(nCode, wParam, lParam):
    if nCode == 0:
        info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        if wParam == WM_XBUTTONDOWN:
            button = (info.mouseData >> 16) & 0xFFFF
            action = ACTIONS.get(button)
            if action is not None and button not in _pressed:
                vks = resolve(action)
                if vks:
                    _pressed.add(button)
                    _swallow_up.add(button)
                    log(f"XBUTTON{1 if button == XBUTTON1 else 2} -> {action} {vks}")
                    send_keys(vks)
                return 1  # 吞掉原始侧键事件
        elif wParam == WM_XBUTTONUP:
            button = (info.mouseData >> 16) & 0xFFFF
            if button in _swallow_up:
                _swallow_up.discard(button)
                _pressed.discard(button)
                return 1
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


_callback = HOOKPROC(hook_proc)


def main():
    # 单实例: 两个自启项同时触发时, 只保留一个, 避免动作发两次
    if os.environ.get('BTNREMAP_TEST') != '1':
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        _mutex = kernel32.CreateMutexW(None, True, 'Local\\BtnRemapSingleInstance')
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            log('已有实例在运行, 本实例退出', always=True)
            return 0

    hook = user32.SetWindowsHookExW(WH_MOUSE_LL, _callback, None, 0)
    if not hook:
        err = ctypes.get_last_error()
        log(f'安装钩子失败, GetLastError={err}', always=True)
        return 1

    pid_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'btnremap.pid')
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
    except OSError:
        pass

    log(f'钩子已安装 pid={os.getpid()} python={sys.version.split()[0]} '
        f'map={{XBUTTON2:{ACTIONS.get(XBUTTON2)}, XBUTTON1:{ACTIONS.get(XBUTTON1)}}}', always=True)
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    user32.UnhookWindowsHookEx(hook)
    log('退出', always=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
