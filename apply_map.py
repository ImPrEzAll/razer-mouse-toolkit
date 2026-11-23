"""apply_map - 开机把映射下发到鼠标固件 (静默, 无窗口)

为什么需要它: 实测该型号的按键映射在断电后不保留 (写入只落在易失副本),
所以每次登录时重新下发一次。下发后由固件自己执行, 不依赖任何钩子。

映射来源: 同目录 mapbtn_backup.json (可用 mapbtn.py set 改完再 backup)
"""
import json
import os
import sys
import time

import razer_da as R

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP = os.path.join(HERE, 'mapbtn_backup.json')
LOG = os.path.join(HERE, 'apply_map.log')

# 没有备份文件时的默认映射: 侧键 = 复制 / 粘贴
DEFAULT_MAP = {
    '0/0/1': [1, 1, 1, 0, 0, 0, 0],
    '0/0/2': [1, 1, 2, 0, 0, 0, 0],
    '0/0/3': [1, 1, 3, 0, 0, 0, 0],
    '0/0/4': [2, 2, 1, 25, 0, 0, 0],   # back    -> Ctrl+V
    '0/0/5': [2, 2, 1, 6, 0, 0, 0],    # forward -> Ctrl+C
    '0/0/9': [1, 1, 9, 0, 0, 0, 0],
    '0/0/10': [1, 1, 10, 0, 0, 0, 0],
}


def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def close_all_virtual_mouse():
    """把映射写进固件后, 若软件钩子也在跑就会重复触发, 这里不做处理,
    由用户在需要时自行关闭 btnremap。"""


def main():
    for attempt in range(8):
        try:
            d = R.Device()
            break
        except Exception:
            time.sleep(1.5)
    else:
        log('设备未找到, 放弃')
        return 1

    try:
        data = DEFAULT_MAP
        if os.path.exists(BACKUP):
            with open(BACKUP, encoding='utf-8') as f:
                loaded = json.load(f)
            subset = {k: v for k, v in loaded.items() if k.startswith('0/') and v}
            if subset:
                data = subset

        ok = 0
        fail = 0
        for key, act in data.items():
            try:
                p, l, b = (int(x) for x in key.split('/'))
            except ValueError:
                continue
            st = None
            for _ in range(3):
                try:
                    st, _, _ = d.xfer(0x02, 0x0C, 0x0A, [p, b, l] + list(act) + [0] * 3, retries=2)
                    break
                except Exception:
                    time.sleep(0.3)
                    try:
                        d.close()
                    except Exception:
                        pass
                    d = R.Device()
            if st == 0x02:
                ok += 1
            else:
                fail += 1
        log(f'下发完成: 成功 {ok}, 失败 {fail}')
        return 0 if fail == 0 else 1
    finally:
        try:
            d.close()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
