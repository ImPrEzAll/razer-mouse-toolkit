"""检查 btnremap 是否在运行、自启项是否就位

用法: py -3.10 status.py
"""
import ctypes
import os
import sys
import winreg

HERE = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(HERE, 'btnremap.pid')
LOG_FILE = os.path.join(HERE, 'btnremap.log')
STARTUP_DIR = os.path.join(os.environ.get('APPDATA', ''),
                           r'Microsoft\Windows\Start Menu\Programs\Startup')
STARTUP_VBS = os.path.join(STARTUP_DIR, 'RazerSideButtons.vbs')

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def pid_alive(pid):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(h)


def main():
    print('=' * 52)
    print('侧键重映射 状态检查')
    print('=' * 52)

    # 1. 进程
    alive = False
    if os.path.exists(PID_FILE):
        try:
            pid = int(open(PID_FILE).read().strip())
            alive = pid_alive(pid)
            print(f'进程      : {"运行中" if alive else "未运行"} (pid {pid})')
        except (ValueError, OSError):
            print('进程      : pid 文件不可用')
    else:
        print('进程      : 未运行 (没有 pid 文件)')

    # 2. 自启项
    ok = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, 'BtnRemap')
        print(f'自启-注册表: 已配置')
        ok += 1
    except FileNotFoundError:
        print(f'自启-注册表: 未配置')

    if os.path.exists(STARTUP_VBS):
        print(f'自启-启动夹: 已配置')
        ok += 1
    else:
        print(f'自启-启动夹: 未配置')

    # 3. 日志
    print('-' * 52)
    if os.path.exists(LOG_FILE):
        lines = open(LOG_FILE, encoding='utf-8', errors='replace').read().splitlines()
        print(f'最近日志 (共 {len(lines)} 行):')
        for line in lines[-8:]:
            print('  ' + line)
    else:
        print('还没有日志文件 —— 说明新版脚本还没运行过')

    print('-' * 52)
    if alive:
        print('结论: 正在生效中, 侧键应该可用。')
    else:
        print('结论: 当前没有常驻进程。双击 START.cmd / start_btnremap.vbs 启动。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
