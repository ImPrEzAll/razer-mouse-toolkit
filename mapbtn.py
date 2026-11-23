"""mapbtn - 把按键动作直接写进雷蛇鼠标的板载内存 (走硬件, 换电脑也生效)

协议 (来自 OpenMouse / OpenSynapse 社区逆向结果):
    读: class 0x02, id 0x8C, args = [store, button, layer], data_size 0x03
    写: class 0x02, id 0x0C, args = [store, button, layer, a0..a6], data_size 0x0A
    store 字节: 0x01 = 写入闪存(断电保留), 0x00 = 仅本次通电有效（实测确认）
    动作编码:
        鼠标按键  [0x01, 0x01, <button id>, 0, 0, 0, 0]
        键盘按键  [0x02, 0x02, <modifiers>, <hid usage>, 0, 0, 0]
        默认/禁用 全 0

用法:
    mapbtn.py dump                     打印板载映射表
    mapbtn.py backup [文件]            备份整张表到 JSON (默认 mapbtn_backup.json)
    mapbtn.py restore [文件]           从备份还原整张表
    mapbtn.py set back ctrl+v          后侧键 = 粘贴
    mapbtn.py set forward ctrl+c       前侧键 = 复制
    mapbtn.py set back default         恢复默认
    mapbtn.py set back key:f13         只发一个键
    mapbtn.py set back mouse:4         映射成鼠标按键 4

安全约定:
    只写 profile 0, 且只写 layer 0-2。实测写入 profile >=2 会别名污染 profile 0/1,
    务必先 backup 再改。
"""
import json
import os
import sys
import time

import razer_da as R

BACKUP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mapbtn_backup.json')
MAX_PROFILE = 1
MAX_LAYER = 2

BUTTONS = {1: 'left', 2: 'right', 3: 'middle', 4: 'back', 5: 'forward', 9: 'b9', 10: 'b10'}
ALIASES = {
    'left': 0x01, 'l': 0x01,
    'right': 0x02, 'r': 0x02,
    'middle': 0x03, 'm': 0x03,
    'back': 0x04,
    'forward': 0x05, 'fwd': 0x05,
    'b9': 0x09, 'b10': 0x0A,
}

HID = {
    'a': 0x04, 'b': 0x05, 'c': 0x06, 'd': 0x07, 'e': 0x08, 'f': 0x09, 'g': 0x0A,
    'h': 0x0B, 'i': 0x0C, 'j': 0x0D, 'k': 0x0E, 'l': 0x0F, 'm': 0x10, 'n': 0x11,
    'o': 0x12, 'p': 0x13, 'q': 0x14, 'r': 0x15, 's': 0x16, 't': 0x17, 'u': 0x18,
    'v': 0x19, 'w': 0x1A, 'x': 0x1B, 'y': 0x1C, 'z': 0x1D,
    '1': 0x1E, '2': 0x1F, '3': 0x20, '4': 0x21, '5': 0x22, '6': 0x23,
    '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27,
    'enter': 0x28, 'esc': 0x29, 'backspace': 0x2A, 'tab': 0x2B, 'space': 0x2C,
    'minus': 0x2D, 'equal': 0x2E, 'leftbracket': 0x2F, 'rightbracket': 0x30,
    'backslash': 0x31, 'semicolon': 0x33, 'quote': 0x34, 'grave': 0x35,
    'comma': 0x36, 'period': 0x37, 'slash': 0x38, 'capslock': 0x39,
    'f1': 0x3A, 'f2': 0x3B, 'f3': 0x3C, 'f4': 0x3D, 'f5': 0x3E, 'f6': 0x3F,
    'f7': 0x40, 'f8': 0x41, 'f9': 0x42, 'f10': 0x43, 'f11': 0x44, 'f12': 0x45,
    'f13': 0x68, 'f24': 0x73,
    'insert': 0x49, 'home': 0x4A, 'pageup': 0x4B, 'delete': 0x4C,
    'end': 0x4D, 'pagedown': 0x4E, 'right_arrow': 0x4F, 'left_arrow': 0x50,
    'down_arrow': 0x51, 'up_arrow': 0x52,
    'volume_up': 0x80, 'volume_down': 0x81, 'mute': 0x7F,
    'play': 0xCD, 'next': 0xB5, 'prev': 0xB6,
}

MODS = {
    'ctrl': 0x01, 'lctrl': 0x01, 'rctrl': 0x10,
    'shift': 0x02, 'lshift': 0x02, 'rshift': 0x20,
    'alt': 0x04, 'lalt': 0x04, 'ralt': 0x40,
    'win': 0x08, 'gui': 0x08, 'rwin': 0x80,
}

PROFILE = 0x01        # 实测: 0x01 = 写入闪存(断电保留), 0x00 = 仅本次通电有效
LAYER = 0x00


def read_action(d, button, profile=PROFILE, layer=LAYER):
    st, a, _ = d.xfer(0x02, 0x8C, 0x03, [profile, button, layer], retries=2)
    return st, list(a[3:10])


def write_action(d, button, action, profile=PROFILE, layer=LAYER):
    args = [profile, button, layer] + list(action) + [0] * 3
    st, _, _ = d.xfer(0x02, 0x0C, 0x0A, args, retries=2)
    return st


def parse_action(text):
    t = text.strip().lower()
    if t in ('default', 'none', 'off', 'reset'):
        return [0] * 7
    if t.startswith('mouse:'):
        bid = int(t.split(':', 1)[1], 0)
        return [0x01, 0x01, bid, 0, 0, 0, 0]
    if t.startswith('key:'):
        t = t.split(':', 1)[1]
    parts = t.split('+')
    mod = 0
    key = None
    for p in parts:
        p = p.strip()
        if p in MODS:
            mod |= MODS[p]
        elif p in HID:
            key = HID[p]
        else:
            raise ValueError(f'无法识别的按键: {p}')
    if key is None:
        raise ValueError('缺少主键, 例如 ctrl+c')
    return [0x02, 0x02, mod, key, 0, 0, 0]


def describe(action):
    if not any(action):
        return '默认'
    if action[0] == 0x01 and action[1] == 0x01:
        return f'鼠标按键 {action[2]}'
    if action[0] == 0x02:
        mod = action[2]
        usage = action[3]
        names = [k for k, v in MODS.items() if v == mod and k in ('ctrl', 'shift', 'alt', 'win')]
        keyname = next((k for k, v in HID.items() if v == usage), f'0x{usage:02X}')
        return '+'.join(names + [keyname]) if names else keyname
    return '原始 ' + ' '.join(f'{b:02X}' for b in action)


def cmd_dump(d):
    print('button     当前映射')
    print('-' * 40)
    for b, name in BUTTONS.items():
        st, act = read_action(d, b)
        print(f'{name:8s}   {describe(act)}   [{st:02X}] {act}')


def cmd_set(d, args):
    if len(args) < 2:
        print('用法: mapbtn.py set <back|forward|...> <动作>')
        return 2
    name = args[0].lower()
    if name not in ALIASES:
        print(f'未知按键: {name}  可用: {", ".join(ALIASES)}')
        return 2
    button = ALIASES[name]
    action = parse_action(' '.join(args[1:]))
    st = write_action(d, button, action)
    st2, got = read_action(d, button)
    ok = got == action
    print(f'{name} <- {describe(action)}   写入状态=0x{st:02X}  回读={got}  {"OK" if ok else "不一致!"}')
    return 0 if ok else 1


def snapshot(d):
    """整表快照: {"<layer>/<button>": action}  (store=0x01 读的是闪存里的表)"""
    data = {}
    for l in range(0, MAX_LAYER + 1):
        for b in BUTTONS:
            st, act = read_action(d, b, PROFILE, l)
            data[f"{l}/{b}"] = act if st == 0x02 else None
    return data


def cmd_backup(d, args):
    path = args[0] if args else BACKUP_PATH
    data = snapshot(d)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1)
    print(f'已备份 {len(data)} 条记录 -> {path}')
    return 0


def cmd_restore(d, args):
    path = args[0] if args else BACKUP_PATH
    if not os.path.exists(path):
        print(f'找不到备份文件: {path}')
        return 2
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    bad = 0
    for key, act in data.items():
        if act is None:
            continue
        parts = [int(x) for x in key.split('/')]
        l, b = parts[0], parts[1]
        if l > MAX_LAYER:
            continue
        st = write_action(d, b, act, PROFILE, l)
        if st != 0x02:
            bad += 1
    print(f'已还原 {len([v for v in data.values() if v])} 条记录, 失败 {bad} 条')
    cmd_dump(d)
    return 0 if bad == 0 else 1


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 0
    cmd = argv[1].lower()
    d = R.Device()
    try:
        if cmd == 'dump':
            cmd_dump(d)
            return 0
        if cmd == 'backup':
            return cmd_backup(d, argv[2:])
        if cmd == 'restore':
            return cmd_restore(d, argv[2:])
        if cmd == 'set':
            return cmd_set(d, argv[2:])
        if cmd == 'reset':
            # 注意: 写全 0 会让按键变成"无动作"。这里一律写恒等映射, 保证可用。
            for l in range(0, MAX_LAYER + 1):
                for b, bid in BUTTONS.items():
                    write_action(d, b, [0x01, 0x01, bid, 0, 0, 0, 0], PROFILE, l)
            print('已恢复全部按键为鼠标原功能 (恒等映射)')
            cmd_dump(d)
            return 0
        print(__doc__)
        return 2
    finally:
        d.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv))
