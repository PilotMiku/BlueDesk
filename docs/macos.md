# macOS 实现说明

本文补充 [README](../README.md) 中 macOS 端的架构、权限、CoreBluetooth 主线程问题、经典蓝牙限制与关键代码。项目实际实现位于：

- [platform/macos.py](../src/bluedesk/platform/macos.py)
- [platform/parsers.py](../src/bluedesk/platform/parsers.py)
- [scan_service.py](../src/bluedesk/scan_service.py)
- [connection_manager.py](../src/bluedesk/connection_manager.py)

## 1. 支持范围

Qt 兼容性提示：Bleak/CoreBluetooth 路径支持 macOS 10.15+，但 PySide6 6.5+ 官方最低系统版本高于 10.15。如果必须支持 10.15，请使用 PySide6 6.4.x，并在 10.15 真机验证 UI 与打包产物；新系统可继续使用 6.8.x。

| 能力 | macOS 10.15+ | 实现方式 |
| --- | --- | --- |
| BLE 扫描 | 支持 | Bleak / CoreBluetooth |
| BLE GATT | 支持 | Bleak / CoreBluetooth |
| 已配对设备枚举 | 支持 | system_profiler，原生 IOBluetooth 后备，可选 blueutil |
| 已配对设备连接 / 断开 | 支持 | 原生 IOBluetooth；可选 blueutil |
| 系统音量 | 支持 | osascript |
| 媒体控制 | 支持（受自动化权限影响） | AppleScript |
| 经典 inquiry / SDP / RFCOMM | 不支持 | 需 Swift/ObjC 辅助进程或 Qt |
| 系统配对 | 打开设置；blueutil 可选 | open / blueutil |
| 蓝牙权限 | 需要 | TCC / Info.plist |

## 2. 权限与 Info.plist

### 2.1 必需键

打包为 .app 时：

~~~xml
<key>NSBluetoothAlwaysUsageDescription</key>
<string>BlueDesk 需要访问蓝牙以扫描、连接和管理附近的蓝牙设备。</string>
<key>NSBluetoothPeripheralUsageDescription</key>
<string>BlueDesk 需要访问蓝牙以连接蓝牙外设。</string>
~~~

- macOS 10.15–11 使用 NSBluetoothPeripheralUsageDescription。
- macOS 11+ 推荐同时提供 NSBluetoothAlwaysUsageDescription。
- 缺少描述字符串时，系统可能直接拒绝访问或崩溃。
- 如果启用 App Sandbox，需要：

~~~xml
<key>com.apple.security.device.bluetooth</key>
<true/>
~~~

### 2.2 未打包直接运行

- python -m bluedesk 运行在 Terminal / iTerm / Python 进程下。
- TCC 权限归属于启动它的应用（Terminal、iTerm、PyCharm、VS Code 等）。
- 首次扫描时系统弹出“允许此应用使用蓝牙？”。
- 如果误点拒绝：
  - 系统设置 > 隐私与安全性 > 蓝牙，重新开启对应终端/应用。
  - 或 reset：

~~~bash
tccutil reset Bluetooth com.apple.Terminal
tccutil reset Bluetooth com.googlecode.iterm2
~~~

- 重新签名或移动 .app 后，TCC 可能再次询问。

### 2.3 自动化与辅助功能

- AppleScript 控制 Spotify/Music 会触发“自动化”权限。
- 如果使用原生 NX_KEYTYPE 媒体键注入，还需要“辅助功能”权限。
- 无权限时应显示可读错误，而不是静默失败。

## 3. CoreBluetooth 与 Bleak

### 3.1 地址不是 MAC

CoreBluetooth 使用 CBPeripheral.identifier（UUID）标识设备，不使用 MAC：

~~~text
B04F546F-216B-BEF5-7461-F4E6BB46020A
~~~

- 该 UUID 在同一 Mac 上通常稳定，但不等同于 MAC。
- 不能用它和 system_profiler 的 MAC 直接匹配。
- 私有随机地址设备的 UUID 也可能变化。
- 这是 BlueDesk 在 macOS 上按名称二次合并的原因。

### 3.2 必须预加载 PyObjC

Bleak 在实例化 Scanner 时才导入 CoreBluetooth 后端：

~~~text
bleak/__init__.py
  → get_platform_scanner_backend_type()
  → import bleak.backends.corebluetooth.scanner
  → import objc, CoreBluetooth, Foundation
~~~

如果第一次导入发生在 asyncio 工作线程，同时 Qt 的 AppKit 事件循环正在运行，可能出现死锁。现象：

- 扫描状态显示开始，但永远没有设备回调。
- 停止扫描也卡住。
- CPU 不高，日志停在“正在扫描”。

修复：在 Qt 主线程预加载。

~~~python
if sys.platform == "darwin" and BLEAK_AVAILABLE:
    try:
        import objc  # noqa: F401
        from bleak.backends.corebluetooth import client as _cb_client  # noqa: F401
        from bleak.backends.corebluetooth import scanner as _cb_scanner  # noqa: F401
    except Exception:
        pass
~~~

这段代码在 scan_service.py 模块导入时执行；AppController 由主线程创建，因此等价于主线程预加载。

### 3.3 扫描实现

~~~python
from bleak import BleakScanner

class ScanService(QObject):
    async def _scan(self):
        scanner = BleakScanner(detection_callback=self._on_detection)
        await scanner.start()
        while not self._stop_event.is_set():
            await asyncio.sleep(0.25)
        try:
            await asyncio.wait_for(scanner.stop(), timeout=3.0)
        except asyncio.TimeoutError:
            scanner._manager.central_manager.stopScan()
~~~

- macOS 不支持 passive scanning；Bleak 会抛错。
- 扫描回调中的 advertisement_data：
  - local_name
  - rssi
  - service_uuids
  - manufacturer_data（key 为 Company ID）
  - service_data
  - tx_power
- CoreBluetooth 可能不提供 Appearance；此时由 service UUID 与名称识别。
- 设备名称可能被截断（如 LE-Bose Revolve+ II SoundL），分类器需要容忍。

### 3.4 连接与 GATT

~~~python
from bleak import BleakClient

client = BleakClient(
    uuid,
    disconnected_callback=lambda c: on_disconnected(uuid),
    timeout=15.0,
)
await client.connect()
services = client.services

battery = await client.read_gatt_char("00002a19-0000-1000-8000-00805f9b34fb")
await client.start_notify(
    "00002a37-0000-1000-8000-00805f9b34fb",
    lambda char, data: on_heart_rate(bytes(data)),
)
~~~

- 连接后 services 才会填充。
- 部分设备连接后需要短暂等待服务发现完成。
- CoreBluetooth 连接是系统级共享资源；同一设备被其他应用占用时可能失败。
- 断开连接后系统可能保持物理链路一会儿，这是正常现象。

## 4. 已配对设备枚举

### 4.1 system_profiler

~~~bash
system_profiler SPBluetoothDataType -json
~~~

解析器兼容：

- 旧版 devices_list。
- 新版 device_connected / device_not_connected。
- device_name / device_address / device_minorType / device_connected / device_paired。
- 中英文 minorType（耳机、键盘、鼠标等）。

Python：

~~~python
code, out, _ = run_command(
    ["system_profiler", "SPBluetoothDataType", "-json"],
    timeout=15.0,
)
for item in parse_system_profiler_bluetooth(out):
    device = build_paired_device(
        name=item["name"],
        address=item["address"],
        minor_type=item.get("minor_type", ""),
        connected=item.get("connected", False),
        paired=item.get("paired", True),
        platform="macos",
        source="system_profiler",
    )
~~~

限制：

- 只列已配对/已知设备，不能发现附近未配对经典设备。
- 某些 BLE 设备没有地址字段，解析器生成 macos: 前缀合成 ID。
- 输出结构随 macOS 版本变化，必须做容错解析。
- system_profiler 可能耗时数秒；必须放到线程池。

### 4.2 blueutil（可选）

当前应用会自动安装 `pyobjc-framework-IOBluetooth`，优先通过 `IOBluetoothDevice` 的 `openConnection()` / `closeConnection()` 操作已配对设备，并核对系统连接状态。blueutil 是旧安装环境的可选兼容路径，不再是连接/断开的必需依赖。

解析器同时兼容 `device_name` 字段和新系统的 `{"设备名称": {"device_address": ...}}` 结构。系统报告的电量和固件信息会显示在真实设备详情中，连接状态每 10 秒刷新。

~~~bash
brew install blueutil
blueutil --paired --format json
blueutil --connect AA:BB:CC:DD:EE:FF
blueutil --disconnect AA:BB:CC:DD:EE:FF
blueutil --power 1
~~~

应用查找路径：

- /opt/homebrew/bin/blueutil
- /usr/local/bin/blueutil
- PATH

原生 IOBluetooth 绑定与 blueutil 均未安装时：
- 连接操作会打开系统设置。
- 面板中系统配对能力显示为不可用。
- 不把“打开设置”当作连接成功。

blueutil 的权限继承：
- 从应用内调用时，blueutil 继承应用的蓝牙 TCC 权限。
- 从 Terminal 调用时，继承 Terminal 的权限。

### 4.3 ioreg

~~~bash
ioreg -l -w 0 | grep -i -A 5 -B 2 bluetooth
~~~

- 可用于调试，但输出不是稳定 API。
- 不适合作为产品级设备枚举。
- BlueDesk 未将 ioreg 作为主路径。

## 5. 经典蓝牙限制

macOS 没有向第三方应用提供与 Windows 等价的经典蓝牙 Python API：

- 无 HCI inquiry。
- 无 SDP 浏览。
- 无 RFCOMM socket。
- IOBluetooth 的公开 Objective-C API 存在，但 Python 绑定有限，且随系统版本变化。
- CoreBluetooth 只覆盖 BLE。

因此：

1. system_profiler / blueutil 只能处理已配对设备。
2. 无法实现“发现附近未配对经典耳机并主动配对”的纯 Python 流程。
3. 无法读取经典 A2DP/AVRCP 的厂商私有 EQ 数据。
4. 需要完整经典蓝牙能力时，应使用 Swift/ObjC 辅助进程或 Qt。

### 5.1 Swift 辅助进程思路

~~~swift
import IOBluetooth
import Foundation

let devices = IOBluetoothDevice.pairedDevices() ?? []
for case let device as IOBluetoothDevice in devices {
    print(device.name ?? "", device.addressString ?? "", device.isConnected())
}
~~~

- 可枚举已配对设备。
- 可调用 openConnection()/closeConnection()。
- SDP/RFCOMM 需要 IOBluetoothRFCOMMChannel，API 较老且需要处理回调。
- 通过 XPC、stdin/stdout JSON 或 localhost HTTP 与 Python 通信。
- 需要签名、权限与 notarization。

### 5.2 Qt Bluetooth

- macOS 后端基于 CoreBluetooth，BLE 可用。
- 经典 discovery / RFCOMM 支持有限或不可用，具体取决于 Qt 版本。
- 不建议把 Qt 作为 macOS 经典蓝牙的可靠解决方案。

## 6. 系统音量

~~~applescript
set volume output volume 60
set volume output muted true
output volume of (get volume settings)
~~~

Python：

~~~python
def set_output_volume(percent: int) -> None:
    value = max(0, min(100, percent))
    code, out, err = run_command(
        ["osascript", "-e", "set volume output volume %d" % value],
        timeout=5.0,
    )
    if code != 0:
        raise PlatformError(err.strip() or "osascript failed")
~~~

特点：

- 不需要自动化权限。
- 控制默认输出设备。
- 如果要控制蓝牙耳机独立音量，需要 CoreAudio：
  - 枚举 AudioDevice。
  - 设置 kAudioDevicePropertyVolumeScalar。
  - 或切换 default output device。
- 这不在标准 GATT 范围内。

## 7. 媒体控制

~~~applescript
set runningApps to {}
tell application "System Events" to set runningApps to name of every process
if runningApps contains "Spotify" then
    tell application "Spotify" to playpause
else if runningApps contains "Music" then
    tell application "Music" to playpause
else
    error "Spotify/Music 均未运行"
end if
~~~

支持：
- play_pause
- next
- previous
- stop

为什么不直接用媒体键：
- NSEvent/CGEvent 注入 NX_KEYTYPE_PLAY 需要辅助功能权限。
- 需要辅助程序或 PyObjC Quartz 调用。
- AppleScript 更容易部署，但只覆盖 Spotify/Music。
- 对系统全局媒体（浏览器、播客）支持有限。

未来可加 Swift 辅助进程：

~~~swift
import Cocoa

func sendMediaKey(_ key: Int32) {
    let flags = NSEvent.ModifierFlags(rawValue: 0xA00)
    let data1 = (key << 16) | (0xA << 8)
    let event = NSEvent.otherEvent(
        with: .systemDefined,
        location: .zero,
        modifierFlags: flags,
        timestamp: 0,
        windowNumber: 0,
        context: nil,
        subtype: 8,
        data1: Int(data1),
        data2: -1
    )
    event?.post(tap: .cghidEventTap)
}
~~~

需要 Accessibility 授权与签名。

## 8. 打包、签名与公证

### 8.1 PyInstaller

~~~bash
python -m pip install pyinstaller
pyinstaller --windowed --name BlueDesk \
  --icon assets/BlueDesk.icns \
  src/bluedesk/__main__.py
~~~

生成 .app 后：

1. 编辑 dist/BlueDesk.app/Contents/Info.plist，加入蓝牙描述键。
2. 使用正确的 bundle identifier。
3. codesign：

~~~bash
codesign --deep --force --options runtime \
  --sign "Developer ID Application: Your Name (TEAMID)" \
  dist/BlueDesk.app
~~~

4. 公证：

~~~bash
xcrun notarytool submit dist/BlueDesk.zip \
  --keychain-profile "notary-profile" --wait
xcrun stapler staple dist/BlueDesk.app
~~~

### 8.2 权限与签名关系

- TCC 记录与 bundle identifier / 签名相关。
- 修改签名、移动路径、重打包可能导致再次授权。
- 开发时可使用 ad-hoc 签名，但分发必须 Developer ID + notarization。
- 如果应用被 Gatekeeper 拦截，先右键打开或用 spctl 检查。

## 9. 调试蓝牙权限

查看系统日志：

~~~bash
log stream --predicate 'subsystem == "com.apple.bluetooth"' --level debug
~~~

检查 TCC：

~~~bash
sqlite3 ~/Library/Application\ Support/com.apple.TCC/TCC.db \
  "select service, client, auth_value from access where service like '%Bluetooth%';"
~~~

如果数据库受 SIP 保护无法读取，使用系统设置界面。

快速测试 CoreBluetooth：

~~~python
import asyncio
from bleak import BleakScanner

async def main():
    devices = await BleakScanner.discover(timeout=5)
    print(len(devices))

asyncio.run(main())
~~~

如果命令行能扫描、Qt 应用不能：
- 检查 PyObjC 是否在工作线程首次导入。
- 检查 Info.plist 权限字符串。
- 检查应用是否在系统设置的蓝牙列表中。
- 检查是否有其他应用占用设备。

## 10. 设备重命名

- BLE 已连接时可写 GAP Device Name 0x2A00。
- 系统配对名称由 macOS 管理，第三方应用不能通用修改。
- 使用 blueutil 也没有重命名命令。
- 最终方案：打开系统设置让用户修改，或实现厂商配置协议。

## 11. 测试清单

1. 首次启动：系统蓝牙授权弹窗。
2. 拒绝授权：UI 显示错误，不崩溃；重新开启后扫描可用。
3. BLE 扫描：30+ 广播，RSSI 更新。
4. 扫描停止/重启：不卡死。
5. system_profiler 解析：新旧结构。
6. blueutil 已安装/未安装。
7. 连接 BLE 设备：GATT 服务发现。
8. Battery / Heart Rate / Device Info 读取。
9. 通知订阅/取消。
10. 音量设置/读取。
11. 媒体控制：Spotify/Music 运行/未运行。
12. 日志目录不可写：应用继续运行。
13. .app 打包后权限、签名、公证。
14. 经典设备：明确显示“不支持纯 Python RFCOMM”。

## 12. 已知 macOS 坑

- **PyObjC 导入死锁**：最重要，已在项目中修复。
- **地址是 UUID**：不要显示成 MAC。
- **system_profiler 慢**：必须异步。
- **BLE 广播名称截断/为空**：分类需容错。
- **Appearance 不总是存在**：优先 CoD/服务/名称。
- **CoreBluetooth 缓存**：服务和名称可能缓存，重启应用/系统后刷新。
- **权限静默失败**：CoreBluetooth 状态可能是 unauthorized，必须给出明确提示。
- **音频设备不是 GATT**：不要尝试用 BLE 控制 A2DP 音量。
- **媒体键权限**：AppleScript 自动化与辅助功能是两个不同权限。
- **Intel/Apple Silicon**：PySide6/Bleak 需匹配架构；universal2 包更稳妥。
- **macOS 26+**：系统设置 URL 可能变化；保留 fallback 到打开设置根页面。

## 13. 相关文件

- [MacOSPlatform](../src/bluedesk/platform/macos.py)
- [system_profiler 解析器](../src/bluedesk/platform/parsers.py)
- [BLE 扫描与预加载](../src/bluedesk/scan_service.py)
- [连接与 GATT](../src/bluedesk/connection_manager.py)
- [C# / Qt 替代方案](alternatives.md)
