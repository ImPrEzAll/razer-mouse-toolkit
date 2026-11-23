"""disable_synapse_autostart - 禁用 / 恢复雷云自启

用法:
    py disable_synapse_autostart.py            删除雷云自启（并备份原值）
    py disable_synapse_autostart.py --restore  从备份恢复自启

为什么只禁自启而不卸载：
    RzDev_0098.sys 是鼠标 MI_02 接口（Razer Control Device）的驱动，
    按键映射 / DPI / 灯效全部通过该接口通信。
    卸载雷云很可能连带删除这个驱动 —— 设备会变成"未知设备"，
    本工具直接失效且不易恢复。而雷云真正的问题只是"运行时会覆盖设置"，
    禁掉自启就够了。
"""
import json
import os
import sys
import winreg

KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
NAME = 'RazerAppEngine'
HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'razer_autostart_backup.json')


def read_value():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(k, NAME)
            return val
        finally:
            winreg.CloseKey(k)
    except FileNotFoundError:
        return None


def disable():
    val = read_value()
    if not val:
        print('自启项本就不存在，无需处理')
        return 0

    with open(BACKUP, 'w', encoding='utf-8') as f:
        json.dump({NAME: val}, f, ensure_ascii=False, indent=1)
    print('已备份原值 ->', os.path.basename(BACKUP))
    print('  ', val[:110])

    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE)
    try:
        winreg.DeleteValue(k, NAME)
        print('已删除自启项:', NAME)
    finally:
        winreg.CloseKey(k)

    if read_value() is None:
        print('验证通过：自启项已不存在')
        return 0
    print('!! 验证失败')
    return 1


def restore():
    if not os.path.exists(BACKUP):
        print('找不到备份文件:', BACKUP)
        return 2
    with open(BACKUP, encoding='utf-8') as f:
        data = json.load(f)
    val = data.get(NAME)
    if not val:
        print('备份内容为空')
        return 2

    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE)
    try:
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, val)
        print('已恢复自启项:', NAME)
        print('  ', val[:110])
    finally:
        winreg.CloseKey(k)
    return 0


def main():
    if '--restore' in sys.argv:
        return restore()
    return disable()


if __name__ == '__main__':
    sys.exit(main())
