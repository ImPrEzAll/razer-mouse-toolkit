"""Razer DeathAdder Essential (1532:0098) 直连控制库 —— 绕开 Synapse。

协议: HID feature report, report id 0, 90 字节 Razer report
      buffer = [0x00] + 90 bytes  (共 91)
      report: status, tid, remain(2), proto, data_size, class, id, args[80], crc, reserved
"""
import hid
import time

VID, PID = 0x1532, 0x0098


def _crc(buf):
    c = 0
    for i in range(2, 88):
        c ^= buf[i]
    return c


def build(tid, cls, cid, data_size=0x00, args=None):
    r = bytearray(90)
    r[0] = 0x00
    r[1] = tid
    r[4] = 0x00
    r[5] = data_size
    r[6] = cls
    r[7] = cid
    if args:
        for i, b in enumerate(args[:80]):
            r[8 + i] = b
    r[88] = _crc(r)
    return bytes(r)


class Device:
    def __init__(self):
        self.h = None
        for d in hid.enumerate(VID, PID):
            if d['interface_number'] == 0 and d['usage_page'] == 0x0001 and d['usage'] == 0x0002:
                h = hid.device()
                h.open_path(d['path'])
                self.h = h
                return
        raise RuntimeError('Razer DeathAdder Essential (1532:0098) 未找到')

    def close(self):
        if self.h:
            self.h.close()

    def xfer(self, cls, cid, data_size=0x00, args=None, tid=0x1F, retries=3):
        """发一条命令并读回响应, 返回 (status, args_list, raw)"""
        if args is None:
            args = [0] * 80
        else:
            args = list(args) + [0] * (80 - len(args))
        for attempt in range(retries):
            buf = [0x00] + list(build(tid, cls, cid, data_size, args))
            self.h.send_feature_report(buf)
            time.sleep(0.03)
            resp = self.h.get_feature_report(0x00, 91)
            if resp and len(resp) >= 91:
                status = resp[1]
                # 0x02 = busy, 重试
                if status == 0x02 and attempt < retries - 1:
                    time.sleep(0.05)
                    continue
                return status, list(resp[9:91]), bytes(resp)
        return status, list(resp[9:91]), bytes(resp)

    # ---- 具体功能 ----
    def firmware(self):
        st, a, _ = self.xfer(0x00, 0x81, 0x02, [0x00])
        major = a[0] if a else 0
        minor = a[1] if len(a) > 1 else 0
        return f"{major}.{minor}"

    def serial(self):
        st, a, _ = self.xfer(0x00, 0x82, 0x16)
        s = ''.join(chr(c) for c in a[:22] if 32 <= c < 127)
        return s

    def get_polling(self):
        st, a, _ = self.xfer(0x00, 0x85, 0x01)
        return a[0] if a else None

    def set_polling(self, hz):
        table = {125: 0x08, 500: 0x01, 1000: 0x02}
        if hz not in table:
            raise ValueError('支持 125 / 500 / 1000 Hz')
        st, a, _ = self.xfer(0x00, 0x05, 0x01, [table[hz]])
        return st

    def get_dpi(self):
        """返回 (x, y), 16 位大端直接就是 DPI 数值"""
        st, a, _ = self.xfer(0x04, 0x85, 0x07)
        x = (a[1] << 8) | a[2]
        y = (a[3] << 8) | a[4]
        return x, y

    def set_dpi(self, x, y=None, store=True, sync_stage=True):
        """设置当前 DPI。sync_stage=True 时同步更新活动档位的值，
        避免"当前 DPI 与档位表脱节"——否则按鼠标 DPI 键切档会跳回旧值。"""
        if y is None:
            y = x
        args = [(0x01 if store else 0x00), (x >> 8) & 0xFF, x & 0xFF, (y >> 8) & 0xFF, y & 0xFF, 0x00, 0x00]
        st, _, _ = self.xfer(0x04, 0x05, 0x07, args)
        if sync_stage:
            try:
                active, stages = self.get_dpi_stages()
                if stages and 1 <= active <= len(stages):
                    stages = list(stages)
                    stages[active - 1] = (x, y)
                    self.set_dpi_stages(stages, active, store)
            except Exception:
                pass
        return st

    # ---- DPI 分段 ----
    def get_dpi_stages(self):
        """返回 (active_index, [(x, y), ...])，档位从 1 开始编号"""
        st, a, _ = self.xfer(0x04, 0x86, 0x07, [0] * 7)
        if st != 0x02:
            return 0, []
        active, count = a[1], a[2]
        stages = []
        for i in range(count):
            off = 3 + i * 7
            if off + 4 >= len(a):
                break
            stages.append(((a[off + 1] << 8) | a[off + 2], (a[off + 3] << 8) | a[off + 4]))
        return active, stages

    def set_dpi_stages(self, stages, active=None, store=True):
        """整表写入（必须整表，单档写会错位）。stages = [(x, y), ...]，active 从 1 开始"""
        if not stages:
            raise ValueError('stages 不能为空')
        if active is None:
            active = 1
        active = max(1, min(len(stages), int(active)))
        args = [(0x01 if store else 0x00), active, len(stages)]
        for i, (x, y) in enumerate(stages, 1):
            args += [i, (x >> 8) & 0xFF, x & 0xFF, (y >> 8) & 0xFF, y & 0xFF, 0x00, 0x00]
        st, _, _ = self.xfer(0x04, 0x06, len(args), args)
        return st

    def set_dpi_stage(self, index, x, y=None, store=True):
        """改单个档位：内部走整表读-改-写"""
        active, stages = self.get_dpi_stages()
        if not stages:
            raise RuntimeError('读取档位失败')
        stages = list(stages)
        if not (1 <= index <= len(stages)):
            raise ValueError(f'档位号需在 1-{len(stages)}')
        stages[index - 1] = (x, y if y is not None else x)
        return self.set_dpi_stages(stages, active, store)

    def set_active_stage(self, index, store=True):
        active, stages = self.get_dpi_stages()
        if not stages:
            raise RuntimeError('读取档位失败')
        return self.set_dpi_stages(stages, index, store)

    # ---- 灯效 (class 0x0F, 新 Chroma 协议) ----
    # 该型号单色 logo 灯。两条独立通道:
    #   0x0F/0x02  效果寄存器（可读回：0x0F/0x82）
    #   0x0F/0x04  全局亮度 0-255（不可读回，只影响实际亮度）
    # 出厂常亮状态 = 效果寄存器 [0,4,1,0, 0,1,0,255]
    EFFECT_STATIC = 1
    EFFECT_BREATH = 2
    _FACTORY_TAIL = [0x00, 0x00, 0x01, 0x00, 0xFF]

    def get_lighting(self):
        """返回 {effect}；亮度不可读，故不返回"""
        st, a, _ = self.xfer(0x0F, 0x82, 0x0C, [0] * 8)
        if st != 0x02:
            return None
        return {'effect': a[2]}

    def set_effect(self, effect=EFFECT_STATIC, store=True):
        args = [(0x01 if store else 0x00), 0x00, effect & 0xFF] + list(self._FACTORY_TAIL)
        st, _, _ = self.xfer(0x0F, 0x02, 0x0C, args)
        return st

    def set_brightness(self, level=255, store=True):
        """全局亮度 0-255，0 = 熄灭"""
        level = max(0, min(255, int(level)))
        st, _, _ = self.xfer(0x0F, 0x04, 0x03, [(0x01 if store else 0x00), 0x00, level])
        return st

    def set_off(self, store=0x01):
        st, a, _ = self.xfer(0x03, 0x02, 0x04, [store, 0x00, 0x00, 0x00])
        return st
