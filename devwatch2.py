"""devwatch2 - 正确的设备变化监听（在 WndProc 里接 WM_DEVICECHANGE）

上一版用 STATIC 窗口 + PeekMessage 监听，拔插鼠标都收不到事件。
原因是 WM_DEVICECHANGE 由 BroadcastSystemMessage 以**同步**方式发送，
直接调用窗口过程，不进入消息队列，因此 PeekMessage 永远看不到。

正确做法：自己注册窗口类，在 WndProc 里拦截。

用法：
    py devwatch2.py switch 20     切档测试（不需要人）
    py devwatch2.py wait 30       只监听，用于拔插自证
"""
import ctypes
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

WM_DEVICECHANGE = 0x0219
DBT_DEVNODES_CHANGED = 0x0007
DBT_DEVICEARRIVAL = 0x8000
DBT_DEVICEREMOVECOMPLETE = 0x8004

EVENT_NAMES = {
    DBT_DEVNODES_CHANGED: 'DEVNODES_CHANGED    设备节点变化',
    DBT_DEVICEARRIVAL: 'DEVICEARRIVAL       设备到达',
    DBT_DEVICEREMOVECOMPLETE: 'DEVICEREMOVECOMPLETE 设备移除',
}

user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [('style', wintypes.UINT),
                ('lpfnWndProc', WNDPROC),
                ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int),
                ('hInstance', wintypes.HINSTANCE),
                ('hIcon', wintypes.HICON),
                ('hCursor', wintypes.HANDLE),
                ('hbrBackground', wintypes.HBRUSH),
                ('lpszMenuName', wintypes.LPCWSTR),
                ('lpszClassName', wintypes.LPCWSTR)]


events = []
t_start = 0.0


@WNDPROC
def wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_DEVICECHANGE:
        events.append((time.time() - t_start, wparam))
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def create_window():
    hinst = kernel32.GetModuleHandleW(None)
    cls_name = 'DevWatchWnd2'
    wc = WNDCLASSW()
    wc.style = 0
    wc.lpfnWndProc = wndproc
    wc.cbClsExtra = 0
    wc.cbWndExtra = 0
    wc.hInstance = hinst
    wc.hIcon = None
    wc.hCursor = None
    wc.hbrBackground = None
    wc.lpszMenuName = None
    wc.lpszClassName = cls_name
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    if not user32.RegisterClassW(ctypes.byref(wc)):
        err = ctypes.get_last_error()
        if err != 1410:          # 1410 = 类已存在
            raise OSError(f'RegisterClassW 失败, err={err}')

    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR,
                                       wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int,
                                       wintypes.HWND, wintypes.HMENU,
                                       wintypes.HINSTANCE, wintypes.LPVOID]
    hwnd = user32.CreateWindowExW(0, cls_name, 'devwatch2', 0,
                                  0, 0, 0, 0, None, None, hinst, None)
    if not hwnd:
        raise OSError(f'CreateWindowExW 失败, err={ctypes.get_last_error()}')
    return hwnd


def pump(deadline, action=None, at=0.0):
    """处理消息直到 deadline。action 在 at 秒时执行一次。"""
    msg = wintypes.MSG()
    done = False
    while time.time() - t_start < deadline:
        if action and not done and time.time() - t_start >= at:
            action()
            done = True
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.005)


def main():
    global t_start
    mode = sys.argv[1] if len(sys.argv) > 1 else 'switch'
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0

    hwnd = create_window()
    t_start = time.time()

    if mode == 'wait':
        print('=' * 60)
        print(f'  监听 {secs:.0f} 秒，请现在拔插一次鼠标')
        print('=' * 60)
        pump(secs)
        print(f'\n捕获 {len(events)} 个事件：')
        for t, w in events:
            print(f'  +{t:6.2f}s  {EVENT_NAMES.get(w, hex(w))}')
        # DEVNODES_CHANGED 也计入：未注册 RegisterDeviceNotification 的窗口
        # 只能收到这个通用通知，收不到 ARRIVAL/REMOVECOMPLETE。
        ok = any(w in (DBT_DEVICEARRIVAL, DBT_DEVICEREMOVECOMPLETE,
                       DBT_DEVNODES_CHANGED) for _, w in events)
        print()
        if ok:
            print('  [有效] 能收到设备节点变化，监听通道可信。')
            return 0
        print('  [无效] 一个事件都没收到，监听通道有问题。')
        return 2

    # switch 模式：自动切档 + 切模式，看是否触发枚举
    import razer_da as R
    d = R.Device()
    print('=' * 60)
    print('  切档 / 切模式 是否触发 USB 重新枚举')
    print('=' * 60)

    timeline = [
        (1.0, '切档 -> 125Hz', lambda: d.set_polling(125)),
        (4.0, '切档 -> 1000Hz', lambda: d.set_polling(1000)),
        (7.0, '切模式 -> Driver(3)', lambda: d.xfer(0x00, 0x04, 0x02, [3, 0])),
        (10.0, '切模式 -> Hardware(0)', lambda: d.xfer(0x00, 0x04, 0x02, [0, 0])),
        (13.0, 'DPC 变更 (对照: 写 DPI 1200)', lambda: d.set_dpi(1200)),
    ]

    idx = 0
    marks = []
    msg = wintypes.MSG()
    while time.time() - t_start < secs:
        now = time.time() - t_start
        if idx < len(timeline) and now >= timeline[idx][0]:
            marks.append((now, timeline[idx][1], len(events)))
            timeline[idx][2]()
            idx += 1
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.005)

    print()
    for i, (t, label, n0) in enumerate(marks):
        n1 = marks[i + 1][2] if i + 1 < len(marks) else len(events)
        print(f'  +{t:5.1f}s  {label:28s} 事件 {n1 - n0} 个')
    print()
    print(f'  总事件数: {len(events)}')
    for t, w in events:
        print(f'    +{t:6.2f}s  {EVENT_NAMES.get(w, hex(w))}')

    try:
        d.set_dpi(1600)
        st, a, _ = d.xfer(0x00, 0x84, 0x02, [0, 0])
        print(f'  收尾: 模式={a[0]}  已恢复 DPI 1600')
    except Exception as e:
        print(f'  收尾异常: {e}')
    d.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
