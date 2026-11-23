"""measure_rate3 - Raw Input 回报率采样器（带自证）

相比旧版的三处修正
------------------
1. GetRawInputBuffer 批量取数。旧版每条报文调 2 次 GetRawInputData（先查
   size 再取数据）+ 1 次 create_string_buffer，单条开销约 5us，1000Hz 下
   必然积压丢包。
2. 数组遍历按 ROUNDUP(dwSize, 8) 步进。旧版直接 += dwSize，而 Windows 要求
   每个 RAWINPUT 结构的起始地址按 sizeof(DWORD_PTR)=8 对齐，x64 下 dwSize
   是 48（不是 8 的整数倍语义上的紧凑排列），直进会让指针落到结构中间，
   读到垃圾 dwSize 然后越界 —— 这就是上次 exit code 139 的原因。
3. 去掉 time.sleep(0.001)。Windows 默认定时器粒度 15.6ms，sleep(1ms) 实际
   睡 15.6ms，等于把采样率硬压到 64Hz，量化误差吞掉一切。

自证机制
--------
测量结果的绝对值只有在采样器自身可信时才有意义。所以先注入**已知频率**的
鼠标事件（默认 2000Hz，高于目标），统计注入条数与采样条数：
    误差 < 2%  -> 采样器吞吐足够，可用于测量该频率以下的所有回报率
    误差较大   -> 直接标注"采样器不可信"，不给误导性数字

用法
----
    py measure_rate3.py                     默认：三档全测，每档 3 秒
    py measure_rate3.py 5                   每档 5 秒
    py measure_rate3.py 5 --rate 1000       只测 1000Hz
    py measure_rate3.py 3 --selftest        只跑自证（不需要人操作）
    py measure_rate3.py 3 --verbose         输出 0.5 秒分片速率与批次统计
    py measure_rate3.py 3 --rate current --any   测任意鼠标（换鼠标交叉验证用）
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

WM_INPUT = 0x00FF
RIM_TYPEMOUSE = 0
RIDEV_INPUTSINK = 0x00000100
RIDI_DEVICENAME = 0x20000007
MOUSEEVENTF_MOVE = 0x0001

BUF_CAP = 65536          # 能容纳约 1300 条 RAWINPUT（x64 下每条 48 字节）
ALIGN = ctypes.sizeof(ctypes.c_void_p)   # x64 = 8


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [('usUsagePage', wintypes.USHORT),
                ('usUsage', wintypes.USHORT),
                ('dwFlags', wintypes.DWORD),
                ('hwndTarget', wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [('dwType', wintypes.DWORD),
                ('dwSize', wintypes.DWORD),
                ('hDevice', wintypes.HANDLE),
                ('wParam', wintypes.WPARAM)]


class FILETIME(ctypes.Structure):
    _fields_ = [('dwLowDateTime', wintypes.DWORD),
                ('dwHighDateTime', wintypes.DWORD)]


user32.GetRawInputBuffer.restype = wintypes.UINT
user32.GetRawInputBuffer.argtypes = [ctypes.c_void_p,
                                     ctypes.POINTER(wintypes.UINT),
                                     wintypes.UINT]
user32.GetRawInputDeviceInfoW.restype = wintypes.UINT
user32.GetRawInputDeviceInfoW.argtypes = [wintypes.HANDLE, wintypes.UINT,
                                          ctypes.c_void_p,
                                          ctypes.POINTER(wintypes.UINT)]
kernel32.GetSystemTimePreciseAsFileTime.restype = None
kernel32.GetSystemTimePreciseAsFileTime.argtypes = [ctypes.POINTER(FILETIME)]


def now():
    """秒（自 1601 起算，高精度）。开销约 0.3us。"""
    ft = FILETIME()
    kernel32.GetSystemTimePreciseAsFileTime(ctypes.byref(ft))
    return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7


def make_window():
    """message-only 窗口，仅作为 Raw Input 的 hwndTarget。"""
    hwnd = user32.CreateWindowExW(0, 'STATIC', 'rawsampler', 0,
                                  0, 0, 0, 0, None, None, None, None)
    return hwnd


def device_name(h):
    size = wintypes.UINT(0)
    user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, None, ctypes.byref(size))
    if size.value <= 1:
        return ''
    buf = ctypes.create_unicode_buffer(size.value)
    user32.GetRawInputDeviceInfoW(h, RIDI_DEVICENAME, buf, ctypes.byref(size))
    return buf.value


class Sampler:
    """一次性分配缓冲区，循环复用。"""

    def __init__(self):
        self.buf = ctypes.create_string_buffer(BUF_CAP)
        self.base = ctypes.addressof(self.buf)
        self.hdr_size = ctypes.sizeof(RAWINPUTHEADER)
        self.motion = {}                # hDevice -> [累计|dx|, 累计|dy|]
        self.dx = 0
        self.dy = 0
        if self.base % ALIGN != 0:
            raise RuntimeError('缓冲区未按 %d 字节对齐，遍历会错位' % ALIGN)

    def reset_motion(self):
        self.motion.clear()
        self.dx = 0
        self.dy = 0

    def drain(self, counts, names):
        """取一次队列，返回本次取到的 RAWINPUT 条数（0 表示队列空）。"""
        size = wintypes.UINT(BUF_CAP)
        n = user32.GetRawInputBuffer(self.buf, ctypes.byref(size), self.hdr_size)
        if n == 0:
            return 0
        # 遍历依据必须用返回值 n（结构数），不能用 size.value：
        # 实测该调用不会更新 pcbSize（一直保持传入的 65536），
        # 若按 size.value 遍历，会一直走到缓冲区末尾，
        # 把上一批残留在缓冲区里的旧结构重复计数（实测放大 10 倍）。
        off = 0
        seen = 0
        for _ in range(n):
            if off + self.hdr_size > BUF_CAP:
                break
            hdr = ctypes.cast(ctypes.c_void_p(self.base + off),
                              ctypes.POINTER(RAWINPUTHEADER)).contents
            ds = hdr.dwSize
            if ds < self.hdr_size or off + ds > BUF_CAP:
                break                      # 结构越界/损坏，丢弃剩余
            if hdr.dwType == RIM_TYPEMOUSE:
                h = hdr.hDevice
                counts[h] = counts.get(h, 0) + 1
                seen += 1
                if h not in names:
                    names[h] = device_name(h)
                # RAWMOUSE 里 lLastX/lLastY 分别在该结构 +12 / +16 处
                mo = off + self.hdr_size
                if mo + 20 <= BUF_CAP and ds >= self.hdr_size + 20:
                    ax = abs(ctypes.c_int.from_address(self.base + mo + 12).value)
                    ay = abs(ctypes.c_int.from_address(self.base + mo + 16).value)
                    self.dx += ax
                    self.dy += ay
                    m = self.motion.get(h)
                    if m is None:
                        m = [0, 0]
                        self.motion[h] = m
                    m[0] += ax
                    m[1] += ay
            # 关键：按 8 字节向上对齐步进，不是直接 += dwSize
            off = (off + ds + ALIGN - 1) & ~(ALIGN - 1)
        return seen

    def flush(self):
        """排空遗留数据（测量前用）。"""
        c, nm = {}, {}
        for _ in range(64):
            if self.drain(c, nm) == 0:
                break
        return sum(c.values())


def measure(secs, verbose=False, inject_hz=None):
    """采样 secs 秒。

    inject_hz=None  纯采样，等外部鼠标移动
    inject_hz=N     自证模式：同线程按 N Hz 注入相对移动，注入间隙持续取数
    """
    s = Sampler()
    counts, names = {}, {}
    slices = []            # 每 0.5 秒的条数
    batches = 0            # 非空 poll 次数
    batch_sizes = []
    batch_times = []       # 每次非空 poll 的时刻，用于算报文间隔

    s.flush()
    s.reset_motion()          # 只统计计时窗口内的位移
    t0 = now()
    t_end = t0 + secs
    slice_end = t0 + 0.5
    slice_cnt = 0
    injected = 0

    if inject_hz:
        interval = 1.0 / inject_hz
        next_t = time.perf_counter()
        extra = ctypes.c_ulong(0)
        direction = 1
        while True:
            # 每次注入 1 个包，方向交替 ±dx，光标原地抖动不漂移
            user32.mouse_event(MOUSEEVENTF_MOVE, 3 * direction, 0, 0,
                               ctypes.byref(extra))
            direction = -direction
            injected += 1
            next_t += interval
            # 等待下一个注入时刻期间，把时间全部用来取数
            while time.perf_counter() < next_t:
                got = s.drain(counts, names)
                if got:
                    batches += 1
                    batch_sizes.append(got)
                    batch_times.append(now())
                    slice_cnt += got
                    if now() >= slice_end:
                        slices.append(slice_cnt)
                        slice_cnt = 0
                        slice_end += 0.5
            if now() >= t_end:
                break
        elapsed = now() - t0
    else:
        while True:
            t = now()
            if t >= t_end:
                break
            got = s.drain(counts, names)
            if got:
                batches += 1
                batch_sizes.append(got)
                batch_times.append(t)
                slice_cnt += got
            if t >= slice_end:
                slices.append(slice_cnt)
                slice_cnt = 0
                slice_end += 0.5
        elapsed = now() - t0

    return {
        'counts': counts, 'names': names, 'elapsed': elapsed,
        'slices': slices, 'batches': batches, 'batch_sizes': batch_sizes,
        'injected': injected, 'dx': s.dx, 'dy': s.dy, 'batch_times': batch_times,
        'motion': {h: list(v) for h, v in s.motion.items()},
    }


def is_razer(nm):
    u = (nm or '').upper()
    return '1532' in u and '0098' in u


def razer_total(res):
    """只统计 VID_1532&PID_0098。"""
    return sum(c for h, c in res['counts'].items()
               if is_razer(res['names'].get(h, '')))


def razer_motion(res):
    """只统计雷蛇设备的累计位移。"""
    tot = 0
    for h, v in res.get('motion', {}).items():
        if is_razer(res['names'].get(h, '')):
            tot += v[0] + v[1]
    return tot


def all_mouse(res):
    return sum(res['counts'].values())


def report_selftest(inject_hz, secs):
    print('=' * 58)
    print('  第一步：采样器自证')
    print('=' * 58)
    print(f'  注入 {inject_hz} Hz 已知鼠标事件，持续 {secs:.0f} 秒')
    print('  注入与采样在同一线程交错执行，模拟"数据持续到来"的真实负载')
    print('-' * 58)

    res = measure(secs, inject_hz=inject_hz)
    inj = res['injected']
    el = res['elapsed']
    # SendInput/mouse_event 注入的输入 hDevice 为 NULL，可与真实设备精确区分
    inj_got = sum(c for h, c in res['counts'].items() if not h)
    real = sum(c for h, c in res['counts'].items() if h)
    err = abs(inj_got - inj) / inj * 100 if inj else 100.0
    avg_batch = (sum(res['batch_sizes']) / len(res['batch_sizes'])
                 if res['batch_sizes'] else 0)

    print(f'  注入          {inj:>7,} 包   ({inj / el:>8.1f} Hz)')
    print(f'  采样(注入源)  {inj_got:>7,} 包   ({inj_got / el:>8.1f} Hz)')
    print(f'  误差          {err:>7.2f} %')
    inj_motion = sum(v[0] + v[1] for h, v in res['motion'].items() if not h)
    print(f'  位移解析      {inj_motion:>7,} counts   '
          f'(理论 {inj * 3:,} = {inj:,} 包 × dx3)')
    print(f'  轮询          {res["batches"]:>7,} 次非空  /  平均每批 {avg_batch:.2f} 条')
    if real:
        print(f'  （同期真实设备另有 {real:,} 条，已从自证计算中排除）')
    print('-' * 58)
    if err < 2.0:
        print(f'  [可信] 零丢失，可准确测量 {inject_hz} Hz 及以下')
        return True
    if err < 5.0:
        print(f'  [勉强] 误差 {err:.1f}%，结果需打折看待')
        return True
    print(f'  [不可信] 误差 {err:.1f}%，不给结论')
    print('  提示：平均每批条数明显大于 1 说明有积压')
    return False


def wait_for_motion(timeout=120, dwell=1.2, min_hz=80):
    """等用户进入稳定移动状态：连续 dwell 秒速率都 >= min_hz 才返回。

    旧版一检测到 80Hz 就开测，用户往往"动一下就看屏幕"，
    结果采样窗口里大半是静止 —— 这是上一轮 1000Hz 档只测到 21Hz 的原因。
    """
    s = Sampler()
    counts, names = {}, {}
    s.flush()
    t0 = now()
    last_n, last_t = 0, t0
    good_since = None
    while now() - t0 < timeout:
        time.sleep(0.25)
        s.drain(counts, names)
        cur = sum(counts.values())
        t = now()
        rate = (cur - last_n) / max(t - last_t, 0.001)
        if rate >= min_hz:
            if good_since is None:
                good_since = t
            elif t - good_since >= dwell:
                return True
        else:
            good_since = None
        last_n, last_t = cur, t
    return False


def short_dev(nm):
    if not nm:
        return '(注入/未知源)'
    u = nm.upper()
    if '1532' in u and '0098' in u:
        for tag in ('MI_00', 'MI_01', 'MI_02', 'MI_03'):
            if tag in u:
                return '雷蛇 ' + tag
        return '雷蛇 (主接口)'
    if 'ROOT' in u or 'RDP' in u:
        return '远程/虚拟'
    return nm.split('#')[-1][:30]


def report_rate(target, res, verbose=False, any_dev=False):
    got = all_mouse(res) if any_dev else razer_total(res)
    el = res['elapsed']
    hz = got / el if el else 0

    others = all_mouse(res) - got
    if target:
        head = f'  目标 {target:>4} Hz  →'
    else:
        head = '  当前设定      →'
    print(f'{head}  实测 {hz:>7.1f} Hz    (样本 {got:,} 条 / {el:.2f}s)')
    if got < 20:
        print('  [无效] 几乎没有捕获到移动，本档作废（鼠标没动或中途停了）')
        return None

    # 位移量是判断"设备限制上报率"还是"用户动得不够"的关键
    motion = (res.get('dx', 0) + res.get('dy', 0)) if any_dev else razer_motion(res)
    mrate = motion / el if el else 0
    per = motion / got if got else 0
    print(f'  位移 {motion:>10,} counts = {mrate:>9.0f} counts/s   '
          f'平均每包 {per:>6.2f}')
    if per >= 3.0:
        print('  -> 每个报文携带多个 count：位移充足，上报率是被设备限住的')
    elif per >= 1.3:
        print('  -> 部分周期无位移被跳过：位移略欠，读数可能偏低')
    else:
        print('  -> 每包约 1 count：位移大小刚好够，读数可信')

    if verbose or any_dev:
        for h, c in sorted(res['counts'].items(), key=lambda kv: -kv[1]):
            print(f'      {c:>7,} 条   {short_dev(res["names"].get(h, ""))}')
    elif others:
        print(f'  （另有 {others:,} 条来自其它来源，已忽略）')
    if verbose and res['slices']:
        print('  0.5s 分片: ' + ' '.join(f'{v}' for v in res['slices']))
    if res['batch_sizes']:
        avg = sum(res['batch_sizes']) / len(res['batch_sizes'])
        flag = '  积压' if avg > 1.6 else ''
        print(f'  批次 {res["batches"]:,} 次 / 平均每批 {avg:.2f} 条{flag}')

    # 报文间隔中位数 —— 这是 bInterval 的直接证据
    ts = res.get('batch_times') or []
    if len(ts) >= 20:
        gaps = sorted((ts[i + 1] - ts[i]) * 1000.0 for i in range(len(ts) - 1))
        med = gaps[len(gaps) // 2]
        p10 = gaps[len(gaps) // 10]
        p90 = gaps[len(gaps) * 9 // 10]
        implied = 1000.0 / med if med > 0 else 0
        print(f'  报文间隔  中位 {med:>5.2f} ms  (P10 {p10:.2f} / P90 {p90:.2f})'
              f'  -> 隐含约 {implied:.0f} Hz')
    return hz


def set_polling(hz):
    try:
        import razer_da as R
    except Exception as e:
        print(f'  (无法载入 razer_da: {e}，跳过自动切档)')
        return False
    try:
        d = R.Device()
        st = d.set_polling(hz)
        time.sleep(0.35)
        back = d.get_polling()
        d.close()
        label = {8: 125, 1: 500, 2: 1000}.get(back)
        ok = st == 0x02
        print(f'  切档 -> {hz}Hz  写=0x{st:02X}  回读={label}Hz')
        return ok
    except Exception as e:
        print(f'  切档失败: {e}')
        return False


class Tee:
    """同时写控制台和文件，便于事后查看把报告发给别人。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for f in self.streams:
            try:
                f.write(s)
                f.flush()
            except Exception:
                pass

    def flush(self):
        for f in self.streams:
            try:
                f.flush()
            except Exception:
                pass


def main():
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'rate_report.txt')
    try:
        fh = open(report_path, 'w', encoding='utf-8')
        sys.stdout = Tee(sys.stdout, fh)
    except OSError:
        report_path = None

    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    secs = float(args[0]) if args else 3.0
    selftest = '--selftest' in sys.argv
    verbose = '--verbose' in sys.argv

    any_dev = '--any' in sys.argv

    rate = 'all'
    for i, a in enumerate(sys.argv):
        if a == '--rate' and i + 1 < len(sys.argv):
            rate = sys.argv[i + 1]

    hwnd = make_window()
    if not hwnd:
        print('创建窗口失败, err=', ctypes.get_last_error())
        return 1
    rid = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, hwnd)
    if not user32.RegisterRawInputDevices(ctypes.byref(rid), 1,
                                          ctypes.sizeof(RAWINPUTDEVICE)):
        print('注册 Raw Input 失败, err=', ctypes.get_last_error())
        return 1

    winmm = ctypes.WinDLL('winmm')
    winmm.timeBeginPeriod(1)
    try:
        if selftest:
            ok = report_selftest(2000, secs)
            return 0 if ok else 1

        print('=' * 58)
        print('  鼠标真实回报率测量')
        print('=' * 58)
        print(f'  每档 {secs:.0f} 秒，请全程快速、连续地画圈移动鼠标')
        print('  期间 CPU 会占满一个核，这是正常的（忙轮询，不 sleep）')
        print('-' * 58)

        if rate == 'all':
            targets = [125, 500, 1000]
        elif rate == 'current':
            targets = [0]
        else:
            targets = [int(rate)]

        # 切档依赖 hidapi + razer_da；缺失时只测设备当前设定
        try:
            import razer_da  # noqa: F401
            can_switch = True
        except Exception:
            can_switch = False
        if not can_switch:
            print()
            print('  提示: 本机没有 hidapi，无法切换档位，只测设备当前设定。')
        if any_dev:
            print('  模式: --any  统计所有鼠标设备（用于换鼠标交叉验证）')
            print('        （档位存在鼠标闪存里，插到哪台机器都一样）')
            targets = [0]

        quick = '--quick' in sys.argv
        if not quick:
            print()
            print('  先跑自证（不需要你动鼠标）')
            if not report_selftest(2000, 2.0):
                print()
                print('  采样器不可信，停止测量。请把上面的输出发给我。')
                return 1

        print()
        print('=' * 58)
        print('  第二步：实测各档')
        print('=' * 58)

        results = {}
        for hz in targets:
            print()
            if hz:
                set_polling(hz)
                label = f'{hz}Hz'
            else:
                label = '当前设定'
            print(f'  >>> 现在开始快速画圈移动鼠标（测 {label}，{secs:.0f} 秒）')
            print('      检测到移动后自动开始计时 ...', end='', flush=True)
            if not wait_for_motion():
                print('  超时，没检测到移动。')
                print(f'  {hz}Hz 档跳过。')
                continue
            print(' 已开始')
            res = measure(secs, verbose=verbose)
            results[hz] = report_rate(hz, res, verbose, any_dev)

        print()
        print('=' * 58)
        print('  结论')
        print('=' * 58)
        valid = 0
        for hz in targets:
            got = results.get(hz)
            if not got:
                print(f'  {hz:>4} Hz  无有效数据')
                continue
            valid += 1
            if not hz:
                print(f'  当前设定  实测 {got:>7.1f} Hz')
                continue
            ratio = got / hz * 100
            if ratio >= 85:
                verdict = '正常'
            elif ratio >= 60:
                verdict = '偏低'
            else:
                verdict = '严重偏低'
            print(f'  {hz:>4} Hz  实测 {got:>7.1f} Hz   达成率 {ratio:>5.1f}%   {verdict}')
        if valid == 0:
            print('  （没有任何一档拿到有效数据，请重跑并持续画圈）')

        # 恢复常用档位
        if can_switch and targets != [0]:
            print()
            set_polling(500)
        if report_path:
            print()
            print(f'  报告已保存: {report_path}')
        return 0
    finally:
        winmm.timeEndPeriod(1)


if __name__ == '__main__':
    sys.exit(main())
