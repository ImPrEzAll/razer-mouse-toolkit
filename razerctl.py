"""razerctl - 雷蛇 DeathAdder Essential 直连控制工具 (绕开 Razer Synapse)

用法:
    razerctl.py info                查看当前状态
    razerctl.py dpi 1600            设置 DPI (单值)
    razerctl.py dpi 1600 1200       分别设置 X / Y
    razerctl.py poll 1000           设置轮询率 (125 / 500 / 1000)
    razerctl.py bright 100          设置亮度 0-100 (实验)
    razerctl.py led 255 0 0         设置 logo 静态颜色 (实验)
    razerctl.py led off             关闭 logo 灯 (实验)
"""
import sys
import time

import razer_da as R

POLL_NAME = {8: 125, 1: 500, 2: 1000}


def cmd_info(d):
    print("型号      : Razer DeathAdder Essential (1532:0098)")
    print(f"固件      : {d.firmware()}")
    print(f"序列号    : {d.serial()}")
    x, y = d.get_dpi()
    print(f"当前 DPI  : {x} x {y}")
    p = d.get_polling()
    print(f"轮询率    : {POLL_NAME.get(p, '?')} Hz")


def cmd_dpi(d, args):
    if not args:
        x, y = d.get_dpi()
        print(f"当前 DPI: {x} x {y}")
        return 0
    x = int(args[0])
    y = int(args[1]) if len(args) > 1 else None
    if not (100 <= x <= 6400):
        print("DPI 需要在 100 - 6400 之间")
        return 2
    st = d.set_dpi(x, y)
    time.sleep(0.2)
    rx, ry = d.get_dpi()
    print(f"已写入 DPI {x} x {y or x}  (状态 0x{st:02X})")
    print(f"回读确认 : {rx} x {ry}")
    return 0 if (rx, ry) == (x, y or x) else 1


def cmd_poll(d, args):
    if not args:
        print(f"当前轮询率: {POLL_NAME.get(d.get_polling(), '?')} Hz")
        return 0
    hz = int(args[0])
    if hz not in (125, 500, 1000):
        print("轮询率只支持 125 / 500 / 1000")
        return 2
    st = d.set_polling(hz)
    time.sleep(0.2)
    got = POLL_NAME.get(d.get_polling(), '?')
    print(f"已写入 {hz} Hz (状态 0x{st:02X})  回读确认: {got} Hz")
    return 0 if got == hz else 1


def cmd_bright(d, args):
    pct = int(args[0]) if args else 100
    st = d.set_brightness(max(0, min(100, pct)))
    print(f"亮度写入 {pct}% (状态 0x{st:02X}) —— 看下鼠标 logo 亮度是否变化")
    return 0


def cmd_led(d, args):
    if args and args[0].lower() == 'off':
        st = d.set_off()
        print(f"已关闭 logo 灯 (状态 0x{st:02X})")
        return 0
    if len(args) < 3:
        print("用法: led <r> <g> <b>  或  led off")
        return 2
    r, g, b = (max(0, min(255, int(v))) for v in args[:3])
    st = d.set_static(r, g, b)
    print(f"已写入静态色 #{r:02X}{g:02X}{b:02X} (状态 0x{st:02X}) —— 看下 logo 是否变色")
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] in ('-h', '--help', 'help'):
        print(__doc__)
        return 0
    d = R.Device()
    try:
        cmd = argv[1].lower()
        rest = argv[2:]
        if cmd == 'info':
            cmd_info(d)
            return 0
        if cmd == 'dpi':
            return cmd_dpi(d, rest)
        if cmd in ('poll', 'polling'):
            return cmd_poll(d, rest)
        if cmd in ('bright', 'brightness'):
            return cmd_bright(d, rest)
        if cmd == 'led':
            return cmd_led(d, rest)
        print(f"未知命令: {cmd}")
        print(__doc__)
        return 2
    finally:
        d.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv))
