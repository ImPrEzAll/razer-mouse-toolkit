"""Install / remove autostart for the portable build (no admin rights needed).

Usage:
    python\python.exe install_autostart.py            install
    python\python.exe install_autostart.py --remove   remove
    python\python.exe install_autostart.py --check    show current value
"""
import os
import sys
import winreg

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
NAME = 'BtnRemap'
HERE = os.path.dirname(os.path.abspath(__file__))

# 便携版优先用自带的 pythonw, 否则用系统 pyw
_LOCAL_PYW = os.path.join(HERE, 'python', 'pythonw.exe')
if os.path.exists(_LOCAL_PYW):
    CMD = f'"{_LOCAL_PYW}" "{os.path.join(HERE, "btnremap.py")}"'
else:
    CMD = f'"C:\\Windows\\pyw.exe" -3.10 "{os.path.join(HERE, "btnremap.py")}"'


def check():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, NAME)
            print(f'current: {NAME} = {val}')
            return True
    except FileNotFoundError:
        print('autostart not installed')
        return False


def install():
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, CMD)
    print(f'installed: {NAME} = {CMD}')


def remove():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NAME)
        print('removed')
    except FileNotFoundError:
        print('nothing to remove')


if __name__ == '__main__':
    if '--remove' in sys.argv:
        remove()
    elif '--check' in sys.argv:
        check()
    else:
        install()
        check()
