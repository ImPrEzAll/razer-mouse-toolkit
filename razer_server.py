"""razer_server - 雷蛇鼠标本地控制台的后端

启动后浏览器访问 http://127.0.0.1:18765
所有参数直接写入鼠标固件（断电保留）。

API:
  GET  /api/state
  POST /api/dpi       {x, y}
  POST /api/stages    {stages: [[x,y],...], active}
  POST /api/polling   {hz}
  POST /api/button    {button, spec}
  POST /api/lighting  {effect, on, r, g, b}
"""
import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import razer_da as R
from mapbtn import HID, MODS

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 18765

BTN_ORDER = [5, 4, 3, 9, 10, 1, 2]  # 前侧 / 后侧 / 中 / b9 / b10 / 左 / 右
BTN_NAMES = {1: '左键', 2: '右键', 3: '中键', 4: '后侧键', 5: '前侧键', 9: 'DPI 键', 10: '配置键'}

POLL_NAME = {8: 125, 1: 500, 2: 1000}
POLL_CODE = {125: 0x08, 500: 0x01, 1000: 0x02}

HID_KEEP = {"left", "right", "middle", "back", "forward", "b9", "b10"}
IDENTITY = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 9: 9, 10: 10}


def parse_spec(spec, button):
    """把前端传来的动作描述转成 7 字节 action"""
    s = (spec or '').strip().lower()
    if s in ('', 'identity', 'default'):
        return [0x01, 0x01, IDENTITY.get(button, button), 0, 0, 0, 0]
    if s in ('disabled', 'none', 'off'):
        return [0] * 7
    if s.startswith('mouse:'):
        b = int(s.split(':', 1)[1])
        return [0x01, 0x01, b, 0, 0, 0, 0]
    key = s[4:] if s.startswith('key:') else s
    mods = 0
    usage = None
    for part in key.split('+'):
        part = part.strip()
        if part in MODS:
            mods |= MODS[part]
        elif part in HID:
            usage = HID[part]
        else:
            raise ValueError(f'不认识的按键: {part}')
    if usage is None:
        raise ValueError('缺少主键')
    return [0x02, 0x02, mods, usage, 0, 0, 0]


FRIENDLY = {
    'ctrl+c': '复制', 'ctrl+v': '粘贴', 'ctrl+x': '剪切', 'ctrl+z': '撤销', 'ctrl+y': '重做',
    'ctrl+s': '保存', 'ctrl+a': '全选', 'ctrl+f': '查找', 'ctrl+t': '新标签', 'ctrl+w': '关标签',
    'ctrl+shift+t': '恢复标签', 'ctrl+shift+esc': '任务管理器',
    'enter': '回车', 'esc': 'Esc', 'tab': 'Tab', 'space': '空格', 'backspace': '退格',
    'volume_up': '音量+', 'volume_down': '音量-', 'mute': '静音', 'play': '播放/暂停',
    'next': '下一曲', 'prev': '上一曲',
}


def describe_action(act, button):
    if not any(act):
        return '禁用'
    if act[0] == 0x01 and act[1] == 0x01:
        b = act[2]
        if b == IDENTITY.get(button):
            return '默认'
        return f'鼠标键 {b}'
    if act[0] == 0x02:
        mods, usage = act[2], act[3]
        names = [k for k, v in MODS.items() if mods & v and k in ('ctrl', 'shift', 'alt', 'win')]
        keyname = next((k for k, v in HID.items() if v == usage), f'0x{usage:02X}')
        combo = '+'.join(names + [keyname])
        return FRIENDLY.get(combo, combo)
    return ' '.join(f'{b:02X}' for b in act)


def read_state(d):
    fw = d.firmware()
    serial = d.serial()
    dx, dy = d.get_dpi()
    active, stages = d.get_dpi_stages()
    poll = POLL_NAME.get(d.get_polling(), None)
    light = d.get_lighting() or {}
    buttons = {}
    for b in BTN_ORDER:
        st, act = read_action_safe(d, b)
        buttons[str(b)] = {
            'name': BTN_NAMES.get(b, str(b)),
            'raw': act,
            'spec': spec_of(act, b),
            'label': describe_action(act, b),
        }
    return {
        'ok': True,
        'device': {'model': 'Razer DeathAdder Essential', 'vid': '1532', 'pid': '0098',
                   'firmware': fw, 'serial': serial},
        'dpi': {'x': dx, 'y': dy},
        'stages': {'active': active, 'list': stages},
        'polling': poll,
        'lighting': light,
        'buttons': buttons,
        'friendly': FRIENDLY,
    }


def spec_of(act, button):
    if not any(act):
        return 'disabled'
    if act[0] == 0x01 and act[1] == 0x01:
        if act[2] == IDENTITY.get(button):
            return 'default'
        return f'mouse:{act[2]}'
    if act[0] == 0x02:
        mods, usage = act[2], act[3]
        names = [k for k, v in MODS.items() if mods & v and k in ('ctrl', 'shift', 'alt', 'win')]
        keyname = next((k for k, v in HID.items() if v == usage), f'0x{usage:02X}')
        return '+'.join(names + [keyname])
    return 'default'


def read_action_safe(d, b):
    for _ in range(3):
        try:
            st, a, _ = d.xfer(0x02, 0x8C, 0x03, [0x01, b, 0x00], retries=2)
            return st, list(a[3:10])
        except Exception:
            time.sleep(0.2)
    return 0xFF, [0] * 7


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            path = os.path.join(HERE, 'ui.html')
            if not os.path.exists(path):
                return self._send(404, 'ui.html 缺失', 'text/plain; charset=utf-8')
            with open(path, 'rb') as f:
                return self._send(200, f.read(), 'text/html; charset=utf-8')
        if self.path.startswith('/api/state'):
            try:
                d = R.Device()
                try:
                    return self._send(200, json.dumps(read_state(d), ensure_ascii=False))
                finally:
                    d.close()
            except Exception as e:
                return self._send(200, json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False))
        return self._send(404, '{}')

    def do_POST(self):
        try:
            n = int(self.headers.get('Content-Length') or 0)
            payload = json.loads(self.rfile.read(n) or b'{}')
        except Exception:
            payload = {}
        try:
            result = self.dispatch(payload)
            self._send(200, json.dumps(result, ensure_ascii=False))
        except Exception as e:
            traceback.print_exc()
            self._send(200, json.dumps({'ok': False, 'error': str(e)}, ensure_ascii=False))

    def dispatch(self, p):
        d = R.Device()
        try:
            path = self.path.split('?')[0]
            if path == '/api/dpi':
                x = int(p.get('x', 1600))
                y = int(p.get('y', x))
                x = max(100, min(6400, x))
                y = max(100, min(6400, y))
                st = d.set_dpi(x, y)
                time.sleep(0.15)
                gx, gy = d.get_dpi()
                return {'ok': st == 0x02 and (gx, gy) == (x, y), 'dpi': {'x': gx, 'y': gy}}

            if path == '/api/stages':
                stages = [(int(a), int(b)) for a, b in p.get('stages', [])]
                if not stages:
                    raise ValueError('stages 为空')
                active = int(p.get('active', 1))
                st = d.set_dpi_stages(stages, active)
                time.sleep(0.2)
                a2, s2 = d.get_dpi_stages()
                return {'ok': st == 0x02, 'active': a2, 'list': s2}

            if path == '/api/polling':
                hz = int(p.get('hz', 500))
                if hz not in POLL_CODE:
                    raise ValueError('只支持 125/500/1000')
                st = d.set_polling(hz)
                time.sleep(0.15)
                got = POLL_NAME.get(d.get_polling())
                return {'ok': st == 0x02 and got == hz, 'polling': got}

            if path == '/api/button':
                b = int(p['button'])
                act = parse_spec(p.get('spec', 'default'), b)
                st = d.xfer(0x02, 0x0C, 0x0A, [0x01, b, 0x00] + act + [0] * 3, retries=2)[0]
                time.sleep(0.15)
                st2, got = read_action_safe(d, b)
                return {'ok': st == 0x02 and got == act, 'raw': got,
                        'label': describe_action(got, b), 'spec': spec_of(got, b)}

            if path == '/api/lighting':
                eff = int(p.get('effect', R.Device.EFFECT_STATIC))
                bri = max(0, min(255, int(p.get('brightness', 255))))
                st1 = d.set_effect(eff)
                time.sleep(0.1)
                st2 = d.set_brightness(bri)
                time.sleep(0.15)
                return {'ok': st1 == 0x02 and st2 == 0x02, 'lighting': d.get_lighting(),
                        'brightness': bri}

            raise ValueError('未知接口 ' + path)
        finally:
            d.close()


def main():
    for attempt in range(5):
        try:
            R.Device().close()
            break
        except Exception:
            time.sleep(1)
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print(f'雷蛇控制台已启动: http://127.0.0.1:{PORT}')
    print('关闭此窗口即停止服务')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
