"""一键复位: 把所有按键恢复成正常鼠标行为 (profile 0, layer 0/1/2)。

左/右/中 = 各自原功能，侧键 = 后退/前进，b9/b10 = 原功能。
不写 profile 1 以上, 避免别名污染。
"""
import time

import razer_da as R

IDENTITY = {1: 0x01, 2: 0x02, 3: 0x03, 4: 0x04, 5: 0x05, 9: 0x09, 10: 0x0A}
NAMES = {1: '左键', 2: '右键', 3: '中键', 4: '后侧键', 5: '前侧键', 9: 'b9', 10: 'b10'}


def reopen(d):
    try:
        d.close()
    except Exception:
        pass
    return R.Device()


def wr(d, b, l, act):
    for _ in range(3):
        try:
            st, _, _ = d.xfer(0x02, 0x0C, 0x0A, [0, b, l] + list(act) + [0] * 3, retries=2)
            return st
        except Exception:
            time.sleep(0.25)
            d = reopen(d)
    return None


def rd(d, b, l):
    for _ in range(3):
        try:
            st, a, _ = d.xfer(0x02, 0x8C, 0x03, [0, b, l], retries=2)
            return list(a[3:10])
        except Exception:
            time.sleep(0.25)
            d = reopen(d)
    return None


def main():
    d = R.Device()
    print('复位中...')
    for l in (0, 1, 2):
        for b, bid in IDENTITY.items():
            wr(d, b, l, [0x01, 0x01, bid, 0, 0, 0, 0])
    print('校验:')
    ok = True
    for b, bid in IDENTITY.items():
        act = [0x01, 0x01, bid, 0, 0, 0, 0]
        got = rd(d, b, 0)
        good = got == act
        ok = ok and good
        print(f'  {NAMES[b]:8s} {got} {"OK" if good else "!!"}')
    d.close()
    print('完成, 全部正常' if ok else '有异常, 建议拔插鼠标')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
