# Windows 实现说明

本文补充 [README](../README.md) 中 Windows 端的架构、权限、经典蓝牙/BLE 差异与关键代码。项目实际实现位于：

- [platform/windows.py](../src/bluedeck/platform/windows.py)
- [platform/parsers.py](../src/bluedeck/platform/parsers.py)
- [scan_service.py](../src/bluedeck/scan_service.py)
- [connection_manager.py](../src/bluedeck/connection_manager.py)
- [codecs.py](../src/bluedeck/codecs.py)

## 1. 支持范围

| 能力 | Windows 10 1809+ | Windows 11 | 实现方式 |
| --- | --- | --- | --- |
| BLE 扫描 | 支持 | 支持 | Bleak / WinRT |
| BLE GATT | 支持 | 支持 | Bleak / WinRT |
| 已配对设备枚举 | 支持 | 支持 | PowerShell PnP |
| 经典蓝牙发现 | 有限 | 有限 | WinRT / 32feet.NET 辅助进程 |
| RFCOMM / SPP | 依赖蓝牙栈 | 依赖蓝牙栈 | 32feet.NET 或 Qt Bluetooth |
| 系统音量 | 支持 | 支持 | pycaw |
| 媒体键 | 支持 | 支持 | keybd_event |
| 系统配对 UI | 支持 | 支持 | 打开 ms-settings:bluetooth |
| 蓝牙权限弹窗 | 通常无 | 通常无 | Win32 桌面应用 |

## 2. 权限与能力声明

### 2.1 普通 Python 桌面应用

- 不需要管理员权限。
- 第一次访问 BLE 时通常不会像 macOS 那样弹授权框。
- 需要确保：
  - 设置 > 蓝牙和其他设备 > 蓝牙已开启。
  - 设置 > 隐私和安全性 > 蓝牙允许应用控制蓝牙设备。
  - 企业策略/组策略没有禁用无线电。
- 某些设备在 GATT 访问前必须先完成系统配对；未配对时连接可能返回 Access Denied。
- 蓝牙关闭时 Bleak 会抛出 BleakError，UI 会显示错误并停止扫描。

### 2.2 MSIX / UWP 打包

如果使用 MSIX 打包，需要在 Package.appxmanifest 中声明：

~~~xml
<Capabilities>
  <DeviceCapability Name="bluetooth" />
</Capabilities>
~~~

桌面桥（Desktop Bridge）通常沿用 Win32 蓝牙能力，但企业环境仍可能限制。

### 2.3 配对状态

Windows 没有向普通 Win32 进程暴露“弹出配对对话框并返回结果”的稳定 Python API。BlueDesk 的策略：

1. 已配对设备：直接尝试 BLE 连接。
2. 未配对 BLE 设备：打开系统蓝牙设置，让用户确认配对，再重试。
3. 经典音频设备：由系统设置/驱动完成配对和连接。
4. 不伪造 pair 成功状态。

## 3. 蓝牙适配器初始化

BlueDesk 在 Windows 上不做显式 WinRT 初始化，Bleak 会调用 WinRT。应用初始化顺序：

~~~text
QApplication
  → AppController
    → AsyncRunner.start()
    → ScanService（导入 Bleak）
    → ConnectionManager
    → PlatformAdapter（WindowsPlatform）
~~~

Bleak 的 WinRT 后端会在扫描/连接时惰性加载。Windows 上没有 macOS 的 PyObjC 主线程导入限制，因此不需要额外预加载。

如果需要直接检查适配器状态，可使用 WinRT：

~~~csharp
using Windows.Devices.Radios;

var radios = await Radio.GetRadiosAsync();
var bluetooth = radios.FirstOrDefault(r => r.Kind == RadioKind.Bluetooth);
if (bluetooth == null || bluetooth.State != RadioState.On)
{
    // 提示用户开启蓝牙
}
~~~

Python 侧可以通过 Bleak 的异常处理间接判断：

~~~python
try:
    scanner = BleakScanner(detection_callback=on_advertisement)
    await scanner.start()
except Exception as exc:
    # Bluetooth device is turned off / access denied / adapter missing
    report_error(exc)
~~~

## 4. 已配对设备枚举

### 4.1 PowerShell PnP（项目实现）

~~~powershell
$ErrorActionPreference='SilentlyContinue'
Get-PnpDevice -Class Bluetooth |
  Where-Object { $_.InstanceId -match 'BTH' -and $_.FriendlyName } |
  Select-Object FriendlyName,InstanceId,Status,Present |
  ConvertTo-Json -Depth 3
~~~

Python 调用：

~~~python
PS_SCRIPT = (
    "$ErrorActionPreference='SilentlyContinue'; "
    "Get-PnpDevice -Class Bluetooth | "
    "Where-Object { $_.InstanceId -match 'BTH' -and $_.FriendlyName } | "
    "Select-Object FriendlyName,InstanceId,Status,Present | ConvertTo-Json -Depth 3"
)

code, out, err = run_command(
    ["powershell", "-NoProfile", "-NonInteractive", "-Command", PS_SCRIPT],
    timeout=20.0,
)
~~~

解析：

~~~python
_MAC_RE = re.compile(r"(?:DEV_|&)([0-9A-F]{12})(?=[\_&]|$)", re.IGNORECASE)

def extract_mac_from_instance_id(instance_id: str):
    match = _MAC_RE.search(instance_id or "")
    if not match:
        return None
    raw = match.group(1).upper()
    return ":".join(raw[i:i + 2] for i in range(0, 12, 2))
~~~

- BTHENUM 通常是经典蓝牙。
- BTHLE 通常是 BLE。
- Status=OK 只表示设备存在，不保证当前已连接。
- Present 不是连接状态。
- PowerShell 单条结果会输出对象而不是数组，解析器同时兼容。
- 同一设备可能有多个 PnP 节点（音频、HFP、AVRCP），解析器按 MAC 去重。

### 4.2 WinRT 枚举（可选增强）

C# / WinRT 可以更准确地获取配对状态与连接状态：

~~~csharp
using Windows.Devices.Bluetooth;
using Windows.Devices.Enumeration;

var selector = BluetoothDevice.GetDeviceSelectorFromPairingState(true);
var infos = await DeviceInformation.FindAllAsync(
    selector,
    new[] { "System.Devices.Aep.SignalStrength" });

foreach (var info in infos)
{
    var device = await BluetoothDevice.FromIdAsync(info.Id);
    if (device is null) continue;
    Console.WriteLine($"{device.Name} {device.BluetoothAddress:X} paired={device.DeviceInformation.Pairing.IsPaired}");
    Console.WriteLine($"connected={device.ConnectionStatus}");
}
~~~

注意：

- BluetoothAddress 是 ulong，需要格式化为 12 位十六进制 MAC。
- FromIdAsync 可能返回 null（权限/设备移除）。
- BLE 与经典设备使用不同的 selector。

### 4.3 经典蓝牙发现

PowerShell PnP 只能看到已存在/已配对设备，不能替代经典 inquiry。可选方案：

1. **32feet.NET 辅助进程（推荐）**

~~~csharp
using InTheHand.Net.Sockets;

var client = new BluetoothClient();
var discovered = client.DiscoverDevices(
    maxDevices: 20,
    authenticated: true,
    remembered: true,
    unknown: true);

foreach (var device in discovered)
{
    Console.WriteLine($"{device.DeviceName} {device.DeviceAddress} {device.Rssi}");
}
~~~

2. **Qt Bluetooth**
   - QBluetoothDeviceDiscoveryAgent 在 Windows 上支持经典 + BLE。
   - 需要 MSVC 构建的 Qt；部署 QtBluetooth DLL。
3. **InTheHand.Net.Bluetooth**
   - 适合 RFCOMM/SPP。
   - 维护状态与 Windows 版本兼容性需要在目标环境验证。

## 5. BLE 扫描

项目实现：

~~~python
from bleak import BleakScanner

async def scan():
    def on_advertisement(device, advertisement_data):
        name = advertisement_data.local_name or device.name or ""
        rssi = advertisement_data.rssi
        service_uuids = list(advertisement_data.service_uuids)
        manufacturer_data = dict(advertisement_data.manufacturer_data)
        # -> DeviceInfo -> classifier -> UI

    scanner = BleakScanner(detection_callback=on_advertisement)
    await scanner.start()
    await asyncio.sleep(30)
    await scanner.stop()
~~~

- Bleak 在 Windows 上使用 WinRT DeviceWatcher。
- 扫描回调可能重复；UI 层按地址合并并更新 RSSI。
- 广播中不一定有 Local Name，很多设备显示为空名称。
- Manufacturer Data 的 key 是整数 Company ID，value 是 bytes。

## 6. BLE 连接与 GATT

~~~python
from bleak import BleakClient

client = BleakClient(
    address,
    disconnected_callback=lambda c: on_disconnected(address),
    timeout=15.0,
)
await client.connect()

for service in client.services:
    for characteristic in service.characteristics:
        print(service.uuid, characteristic.uuid, characteristic.properties)

data = await client.read_gatt_char("00002a19-0000-1000-8000-00805f9b34fb")
await client.write_gatt_char(
    "00002a00-0000-1000-8000-00805f9b34fb",
    b"New Name",
    response=True,
)
await client.start_notify(uuid, lambda char, data: print(bytes(data).hex(" ")))
await client.stop_notify(uuid)
await client.disconnect()
~~~

项目中的处理：

- 连接成功后读取 Battery、Firmware、Model、Serial、Manufacturer。
- 若存在 Heart Rate Measurement 0x2A37，自动订阅。
- GATT 服务与特征值保存在 ConnectionManager，UI 通过 services_ready 信号获取。
- 断线回调清理服务并更新状态为 DISCONNECTED。

## 7. 经典 RFCOMM / SPP

### 7.1 Python 方案的风险

PyBluez / pybluez2：

- Windows 上依赖系统蓝牙栈和 MSVC 运行时。
- Python 3.10+ 的 wheel 不完整，常需要本地编译。
- 蓝牙 5 / LE 设备支持有限。
- 维护频率低，issue 响应慢。
- 不建议作为商业产品核心依赖。

如果只是实验，可尝试：

~~~python
import socket

MAC = "AA:BB:CC:DD:EE:FF"
PORT = 1
sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
sock.connect((MAC, PORT))
sock.sendall(b"\x01\x02\x03")
sock.close()
~~~

实际可用性取决于 Python 构建与 Windows 蓝牙栈。

### 7.2 推荐：C# 辅助进程

~~~csharp
using System.Net.Sockets;
using InTheHand.Net.Bluetooth;
using InTheHand.Net.Sockets;

var address = BluetoothAddress.Parse("AA:BB:CC:DD:EE:FF");
var endpoint = new BluetoothEndPoint(address, BluetoothService.SerialPort);

using var client = new BluetoothClient();
client.Connect(endpoint);

using var stream = client.GetStream();
var payload = new byte[] { 0xA5, 0x01, 0x02, 0x40, 0x06, 0xE2 };
await stream.WriteAsync(payload);
~~~

通过本地 HTTP/JSON-RPC 或 stdin/stdout 与 Python UI 通信：

~~~json
{"cmd":"rfcomm.connect","address":"AA:BB:CC:DD:EE:FF","channel":1}
{"cmd":"rfcomm.write","data":"A5 01 02 40 06 E2"}
{"event":"rfcomm.data","data":"01 02"}
~~~

优点：Windows 原生 API、稳定、可签名；缺点：多一个进程。

## 8. 系统音量（pycaw）

安装：

~~~powershell
python -m pip install pycaw comtypes
~~~

实现：

~~~python
from comtypes import CLSCTX_ALL, CoInitialize
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

try:
    CoInitialize()
except Exception:
    pass

speakers = AudioUtilities.GetSpeakers()
interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = interface.QueryInterface(IAudioEndpointVolume)

volume.SetMasterVolumeLevelScalar(0.6, None)
current = int(round(volume.GetMasterVolumeLevelScalar() * 100))
volume.SetMute(1, None)
~~~

注意：

- COM 初始化是线程相关的；如果从工作线程调用，需要在该线程 CoInitialize。
- GetSpeakers 返回默认输出端点；pycaw 新版本 API 可能变化。
- 不能保证当前音频路由到蓝牙耳机。
- 未安装 pycaw 时，BlueDesk 会显示明确错误，并保留媒体键功能。

## 9. 媒体键

~~~python
import ctypes

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

def send_media_key(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
~~~

- 作用于当前系统媒体会话。
- 不会启动播放器。
- 在某些全屏游戏/远程桌面中可能被拦截。

## 10. 系统设置跳转

~~~python
subprocess.run(["cmd", "/c", "start", "", "ms-settings:bluetooth"], timeout=5)
subprocess.run(["cmd", "/c", "start", "", "ms-settings:sound"], timeout=5)
~~~

## 11. 设备重命名

- BLE：尝试写 GAP Device Name 0x2A00。设备可能只读、需要绑定、或只改变广播名。
- 经典：Windows 没有向 Python 暴露通用配对设备重命名 API，打开系统设置。
- Windows 设置中的名称来自注册表/配对信息，GATT 写入通常不会更新它。
- 不要宣称“重命名成功”直到设备返回确认；UI 当前会提示系统配对名称可能不变。

## 12. 测试清单

1. 蓝牙关闭时启动扫描：应显示错误，不崩溃。
2. 配对/未配对 BLE 设备：连接成功/失败状态正确。
3. 服务发现：Generic Access、Device Information、Battery 正常显示。
4. Battery Level 读取 0-100。
5. 设备信息字符串读取与 UTF-8 解码。
6. 通知订阅/取消。
7. 写入未知特征值：有提示，日志记录。
8. 音量：pycaw 安装/未安装两种路径。
9. 媒体键：播放器运行/未运行。
10. 设置/日志目录不可写：应用仍启动。
11. 20+ 个 PnP 设备与重复节点：去重正确。
12. 拔插适配器/关闭蓝牙：断线回调与重连。

## 13. 已知 Windows 坑

- **MAC 格式**：WinRT BluetoothAddress 是 ulong；Bleak 地址是字符串，需要统一大小写。
- **重复节点**：同一耳机可能出现 BTHENUM、BTHLE、音频端点多个记录。
- **配对与连接不是同一状态**：已配对不代表已连接。
- **GATT 缓存**：Windows 可能缓存服务；设备固件升级后建议重新配对或清除缓存。
- **PowerShell 启动慢**：首次冷启动可能 1-3 秒；应放到线程池。
- **编码**：PowerShell 输出中文名称时需 UTF-8；subprocess text=True 使用系统编码，必要时设置 encoding="utf-8"。
- **企业策略**：可能禁止蓝牙或 WinRT 设备枚举。
- **驱动**：部分 CSR/Realtek 适配器对 BLE 支持差，建议 Intel/Apple/Broadcom。
- **RFCOMM 端口**：SPP 的 channel 不一定是 1；需要 SDP 查询。
- **音频路由**：系统音量 != 设备音量。

## 14. 相关文件

- [WindowsPlatform](../src/bluedeck/platform/windows.py)
- [PnP 解析器](../src/bluedeck/platform/parsers.py)
- [BLE 扫描](../src/bluedeck/scan_service.py)
- [连接与 GATT](../src/bluedeck/connection_manager.py)
- [DPI 示例帧](../src/bluedeck/protocols/vendor_examples.py)
- [C# / Qt 替代方案](alternatives.md)
