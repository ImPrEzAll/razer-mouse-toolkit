# Razer DeathAdder Essential 免驱控制工具

不依赖 Razer Synapse / 雷云，直接通过 HID Feature Report 与鼠标通信。
按键映射、DPI、灯效写入鼠标板载存储，**拔下来插到任何 Windows 电脑都保持**。

起因是雷云在一次开机后彻底无法识别设备（蓝牙 BLE 模块死锁），
而这只鼠标的侧键映射必须靠软件设置。于是把协议拆开，做了这套独立工具。

## 支持设备

| 型号 | VID:PID | 验证程度 |
|---|---|---|
| Razer DeathAdder Essential (2021) | `1532:0098` | 全部功能实测通过 |

协议结构与 OpenRazer 一致，其它雷蛇鼠标**大概率可用**，
但按键 ID 表和灯效命令可能不同，需要自行调整 `razer_da.py` 里的常量。

## 快速开始

```
1. 安装 hidapi:      py -3.10 -m pip install hidapi
2. 双击 razerui.cmd  → 浏览器自动打开控制台
```

详细操作见 [USAGE.txt](USAGE.txt)，完整协议说明见下文。

## 免责声明

本工具直接读写鼠标固件存储。虽然经过完整测试（包括写坏后恢复），
但**任何固件写入都有风险**。建议先运行 `mapbtn.cmd backup` 备份整张映射表。
作者不对设备损坏负责。

---

## 零、图形控制台（推荐）

**双击 `razerui.cmd`** → 浏览器自动打开 `http://127.0.0.1:18765`

界面包含：

- **DPI**：滑块调当前灵敏度、X/Y 分开设、5 个档位分别编辑并切换活动档
- **回报率**：125 / 500 / 1000 Hz 一键切换
- **按键映射**：7 个按键逐个下拉选择（复制/粘贴/撤销/保存/音量/多媒体/鼠标键/禁用），
  也支持自定义组合键（如 `ctrl+shift+t`、`f13`）

- **灯光**：亮度滑块（0-255）+ 常亮 / 呼吸 + 一键关闭（该型号只有单色 logo 灯，无颜色）

关闭命令行窗口即停止服务；程序不常驻、不写注册表。

先把 `ui.html` 直接打开也能看界面（预览模式，不连设备）。

## 一、侧键重映射（主要功能）

| 物理按键 | Windows 标识 | 动作 |
|---|---|---|
| 前侧键 | XBUTTON2 / Forward | Ctrl + C 复制 |
| 后侧键 | XBUTTON1 / Back | Ctrl + V 粘贴 |

拦下侧键事件并阻断原始的前进/后退，再用 `SendInput` 发出目标按键，
所以浏览器里不会误翻页。

已验证（注入真实侧键事件的端到端测试）：

```
XBUTTON2 -> copy  [17, 67]
XBUTTON1 -> paste [17, 86]
```

### 本机使用

双击 `start_btnremap.vbs`（静默无窗口）。

### 换电脑 / 放 U 盘

`portable\` 是**免安装便携版**，自带 Python 运行时（21 MB），
拷到 U 盘或任何 Windows 电脑，双击 `portable\START.cmd` 即用。
不需要管理员权限，目标机器不需要装 Python。

### 改映射

用记事本打开 `btnremap.py`，改开头：

```python
ACTIONS = {
    XBUTTON2: 'copy',    # 前侧键
    XBUTTON1: 'paste',   # 后侧键
}
```

可用动作：`copy` `paste` `cut` `undo` `redo` `enter` `esc` `tab`
`back` `forward` `volume_up` `volume_down` `media_play`

自定义组合键：`('hotkey', [0x11, 0x54])` 即 Ctrl+T。改完重启进程生效。

### 开机自启

已配置两条冗余路径（单实例锁保证只跑一个）：

1. 注册表 `HKCU\...\Run` 的 `BtnRemap`
2. 启动文件夹 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RazerSideButtons.vbs`

检查：运行 `status.cmd`（显示进程状态、自启项、最近日志）。
移除自启：`py -3.10 install_autostart.py --remove`，并删掉启动文件夹里那个 vbs。

## 二、板载按键映射（写进鼠标，换电脑也生效）

**结论修正**：早期判断「该型号不能存按键映射」是错的。用协议直接探测后确认，
固件里确有按键映射表，可读可写，且能存键盘动作（含修饰键组合）。

**协议**（来自 OpenMouse / OpenSynapse 社区逆向结果，已在本机实测）

| 项 | 值 |
|---|---|
| 读 | class `0x02`, id `0x8C`, args = `[profile, button, layer]`, data_size `0x03` |
| 写 | class `0x02`, id `0x0C`, args = `[profile, button, layer, a0..a6]`, data_size `0x0A` |
| 按键表 | `0x02/0x84` 返回 `[7, 1, 2, 3, 4, 5, 9, 0A]` |
| 鼠标动作 | `[0x01, 0x01, <button id>, 0, 0, 0, 0]` |
| 键盘动作 | `[0x02, 0x02, <modifiers>, <HID usage>, 0, 0, 0]` |
| 默认/禁用 | 全 0 |

修饰符位：Ctrl `0x01`、Shift `0x02`、Alt `0x04`、Win `0x08`（右修饰符 `0x10/0x20/0x40/0x80`）。

**用法**

```
mapbtn.cmd dump                      打印板载映射表
mapbtn.cmd set forward ctrl+c        前侧键 = 复制
mapbtn.cmd set back ctrl+v           后侧键 = 粘贴
mapbtn.cmd set back key:f13          只发一个键
mapbtn.cmd set back mouse:4          映射成鼠标按键 4
mapbtn.cmd set back default          恢复默认
mapbtn.cmd reset                     全部恢复默认
```

可选按键：`left right middle back forward b9 b10`；键码支持 a-z、0-9、
`enter esc tab space backspace`、`f1`-`f24`、方向键、`volume_up` 等。

写入后**立即生效于固件**，鼠标拔下来插到任何电脑都是这个行为，不需要任何软件。

### 验证结果（已全部通过）

**1. 固件自己执行映射 —— 实测 PASS**

软件钩子进程已全部结束、自启已删除，按下侧键时 `verify_remap.py` 仍捕获到：

```
键盘 Ctrl+V (硬件)
键盘 Ctrl+C (硬件)
键盘 Ctrl+V (硬件)
```

括号内为无注入标记事件，即鼠标固件自己发出的键盘报文，不经过任何软件。

**2. 映射已写入闪存，断电保留 —— 实测通过**

关键在写命令的第一个参数字节 `args[0]`：

| args[0] | 效果 |
|---|---|
| `0x01` | **写入闪存**，拔插/断电后保留 |
| `0x00` | 仅本次通电有效，断电丢失 |

早期一直发 `0x00`，所以前三次拔插测试全部丢失；改成 `0x01` 后拔插测试保留成功。
同一标志位也适用于 DPI（`set_dpi(store=True)` 默认已改为写闪存）。

**结论：「写进鼠标、插到任何电脑永久生效」在这个型号上是成立的。**

### 协议细节（实测）

- 读：`0x02/0x8C`，args = `[store, button, layer]`，data_size `0x03`
- 写：`0x02/0x0C`，args = `[store, button, layer, category, length, action...]`，data_size `0x0A`
- 动作编码：键盘 = `02 02 <modifiers> <hid usage>`，鼠标 = `01 01 <button>`，
  **`00 00` = Disabled（不是"默认"）** —— 早期把左键写成全 0 就是因此失效。
- 固件会校验按键 ID：不存在的 ID 返回 `0x03`，合法键（1-5/9/10）返回 `0x02`。
- 读回复中的 layer 字节不可信（反映最后一次写入的层）；`store` 字节不影响读结果。

### 灯光协议（实测，两条独立通道）

| 通道 | 命令 | 说明 |
|---|---|---|
| 效果 | 写 `0x0F/0x02`，读 `0x0F/0x82` | 寄存器 `[0,4,effect,0,0,1,0,255]`；`effect` 1=常亮 2=呼吸 |
| 全局亮度 | 写 `0x0F/0x04`，args `[store,0,0-255]` | **读不回来**，只影响实际亮度；0=熄灭 |

该型号只有**单色 logo 灯**，RGB 字节无效，可调的只有亮度。

> 踩过的坑：早期误判 `0x0F/0x04` "无效"，因为只用 `0x82` 回读做判据，
> 而亮度不会反映在 `0x82` 里。结果把亮度写成 20 后一直调不亮，折腾了很久。

### 安全工具

- `mapbtn.py backup` / `restore` —— 整表存档与还原（改之前务必先 backup）
- `reset_to_normal.cmd` —— 一键恢复全部按键为鼠标原功能
- 只写 `profile 0` + `layer 0/1/2`；写 `profile >=2` 会别名污染 profile 0/1（实测）

**一键判定**：双击 `verify_remap.cmd`（先结束 pythonw.exe），按一下两个侧键，
窗口自动给出 `PASS` / `FAIL` / `SOFTWARE` 结论并写入 `verify_remap.log`。

> 原因：`SendInput` 注入的输入在 OS 层生成，**从定义上不经过设备固件**，
> 所以注入永远无法触发固件映射路径。唯一信号源是真实按键。

**一键判定**：双击 `verify_remap.cmd`（先结束 pythonw.exe），按一下两个侧键，
窗口自动给出 `PASS` / `FAIL` / `SOFTWARE` 结论并写入 `verify_remap.log`。

> 如果发现没生效，先拔插一次鼠标（让固件重新加载映射）。
> 另注：设备有 `Driver Mode` / 硬件模式之分，Synapse 运行时可能由上位机接管映射。

## 三、软件层兜底（不需要硬件写入时）

`btnremap.py` 是全局钩子方案，不依赖鼠标型号、不改固件，纯软件。
适合临时用、或者不想动固件的情况。

```
razerctl.cmd info            固件、序列号、当前 DPI、轮询率
razerctl.cmd dpi 1600        设置 DPI（100 - 6400）
razerctl.cmd dpi 1600 1200   分别设置 X / Y
razerctl.cmd poll 1000       轮询率 125 / 500 / 1000
```

实测：DPI 1600 → 3200 → 1600、轮询率 500 → 1000 → 500 均写入成功且回读一致。



## 四、回报率实测结论（2026-11-23）

### 结论先说

**这只鼠标的物理上报周期固定为 8 ms（约 125 Hz）。500 / 1000 Hz 档位只改了固件参数，
没有改变 USB 端点描述符，所以实际不可能超过 125 Hz。**

```
档位设置     实测上报率      报文间隔中位数
125 Hz       125.0 Hz       8.00 ms
500 Hz       132.3 Hz       7.99 ms
1000 Hz      132.3 Hz       8.00 ms
```

三档的间隔中位数完全相同（8 ms）。132 而非 125，是因为偶尔一次轮询取到 2 个报文
（平均每批 1.04 条），不是真的跑到了 132 Hz。

### 采样器可信度（自证）

测量绝对值只有在采样器可信时才有意义，所以每次运行先注入已知频率：

```
注入  4,000 包 (2000.0 Hz)
采样  4,000 包 (2000.0 Hz)    误差 0.00%
位移  12,000 counts           理论 12,000（4,000 包 × dx3）
```

注入事件的 `hDevice` 为 NULL，可与真实设备精确区分，互不污染。

### 排除过的假设

| 假设 | 实验 | 结果 |
|---|---|---|
| 采样器丢包 | 2000 Hz 注入自证 | 误差 0.00% |
| 移动太慢导致跳过空周期 | 统计平均每包位移 | 63–107 counts/包，位移充足 |
| USB 分线器限制（TT 调度） | 从 `Hub_#0004` 换到直连 `Hub_#0002` | 无变化 |
| Hardware Mode 限速 | 切 `Driver_Mode(3)` | 128.0 Hz，无变化 |
| 端点间隔随档位变化，需重新枚举 | 写入 1000 Hz 后拔插 | 129.5 Hz，无变化 |
| USB 选择性暂停 | 查电源计划 | 已启用，但只影响空闲挂起，与活跃上报无关 |

### 自己复测

```
measure_rate.cmd                    三档全测，每档 3 秒
measure_rate.cmd 5                  每档 5 秒
measure_rate.cmd 3 --rate 1000      只测 1000Hz 档
measure_rate.cmd 3 --rate current   不切档，测设备当前设定
measure_rate.cmd 2 --selftest       只跑自证，不需要人操作
```

出现提示后需持续画圈移动鼠标，工具确认持续移动 1.2 秒才正式计时。
测量期间 CPU 会占满一个核（忙轮询，不 sleep），属正常。
报告同时写入 `rate_report.txt`。

### 采样器三个必踩的坑（留给以后）

1. `GetRawInputBuffer` 的 `pcbSize` **返回时不会更新**（保持传入值）。必须用返回值
   `n`（结构数）作为遍历依据，否则会把上一批残留的旧结构重复计数（实测放大 10 倍）。
2. 数组遍历必须按 `ROUNDUP(dwSize, 8)` 步进（x64 下 `sizeof(RAWINPUTHEADER)=24`，
   鼠标 `dwSize=48`）。直接 `+= dwSize` 会指针错位并越界崩溃。
3. 不能用 `sleep(1ms)` 做轮询间隔 —— Windows 默认定时器粒度 15.6 ms，
   实际会睡 15.6 ms，等于把采样率硬压到 64 Hz。



## 五、与雷云（Synapse 4）的冲突 —— 必须知道

### 雷云会覆盖本工具写入的所有设置

实测记录（雷云启动后）：

```
back     Ctrl+V  →  鼠标按键4        （映射被重置）
forward  Ctrl+C  →  鼠标按键5
b9       恒等    →  [0,1,0,255,0,0,255]（无效残留）
灯效     effect=1 →  effect=8        （该型号不支持的值）
```

雷云进 Driver Mode 后会把它的 profile 同步下去，覆盖板载内容。
**两者不能同时使用。**

### 处置：禁用自启，但不卸载

已删除 `HKCU\...\Run\RazerAppEngine`，原值备份在 `razer_autostart_backup.json`。

**不要卸载雷云**，原因：

```
RzCommon.sys    → C:\WINDOWS\system32\drivers\RzCommon.sys
RzDev_0098.sys  → C:\WINDOWS\system32\drivers\RzDev_0098.sys
```

`RzDev_0098.sys` 是鼠标 `MI_02` 接口（Razer Control Device）的驱动。
按键映射、DPI、灯效全部通过该接口通信，卸载雷云很可能连带删除驱动，
设备会变成"未知设备"，工具直接失效且不易恢复。

### 恢复自启（如需）

```
py disable_synapse_autostart.py --restore
```

或手动把 `razer_autostart_backup.json` 里的值写回 Run 键。

### 注意

- **别手动打开雷云**，否则设置会被覆盖，需重新运行 `mapbtn.py restore`
- Windows 更新或雷云自动更新可能恢复自启项，届时重跑本脚本
- Driver Mode 下写入的设置，退回 Hardware Mode 后**依然保持**（已实测）



## 六、文件说明

| 文件 | 作用 |
|---|---|
| `razerui.cmd` | **图形控制台启动器（推荐入口）** |
| `razer_server.py` | 控制台后端（本地 HTTP API） |
| `ui.html` | 控制台界面 |
| `measure_rate.cmd` | **回报率实测启动器（带自证）** |
| `measure_rate3.py` | 回报率采样器（Raw Input + GetRawInputBuffer） |
| `mapbtn.py` / `.cmd` | 板载按键映射命令行 |
| `dump_map.py` | 导出完整板载映射表（profile × layer × button） |
| `btnremap.py` | 全局钩子方案（软件兜底，不挑鼠标） |
| `start_btnremap.vbs` | 软件方案静默启动器 |
| `stop_btnremap.cmd` | 软件方案停止 |
| `status.py` / `status.cmd` | 状态自检（进程 + 自启项 + 日志） |
| `install_autostart.py` | 安装/卸载注册表自启 |
| `portable\` | 免安装便携版（含 Python 运行时） |
| `razer_da.py` | 雷蛇 HID 协议库 |
| `razerctl.py` / `.cmd` | DPI / 轮询率命令行 |
| `selftest.py` | 侧键功能自测 |
| `probe.py` ~ `probe8.py` | 协议逆向过程脚本（留存备查） |
| `or_mouse.py` | OpenRazer 源码参考 |

本机依赖：Python 3.10 + `hidapi`（`mapbtn` / `razerctl` 需要；`btnremap` 零依赖）。

