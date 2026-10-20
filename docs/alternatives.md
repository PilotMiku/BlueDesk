# C# / .NET 与 Qt / C++ 替代实现

Python + PySide6 是本项目的主实现，适合快速交付、跨平台 BLE 和 GATT 调试。但如果产品需要更深的 Windows 经典蓝牙/RFCOMM 集成、更成熟的安装包，或团队已有 C#/Qt 技术栈，可以考虑以下替代方案。

---

## 1. 方案对比

| 维度 | Python + PySide6（本项目） | C# / .NET + WPF | Qt / C++ |
| --- | --- | --- | --- |
| Windows BLE | Bleak/WinRT，成熟 | WinRT，最原生 | Qt Bluetooth，成熟 |
| Windows 经典 RFCOMM | PyBluez 不稳定 | 32feet.NET，成熟 | QBluetoothSocket，可用 |
| macOS BLE | Bleak/CoreBluetooth，成熟 | 需绑定或 Swift 桥接 | Qt Bluetooth/CoreBluetooth，通常可用 |
| macOS 经典 | 基本不可用 | 需 Swift 桥接 | 支持有限 |
| UI 开发速度 | 快 | 中 | 慢 |
| 安装包 | PyInstaller，体积较大 | 成熟 | 需部署 Qt 运行库 |
| 跨平台单代码库 | 好（BLE） | Windows 强，macOS 弱 | 好（BLE） |
| 硬件协议扩展 | Python 快速 | 强类型、稳定 | 性能最好 |
| 授权 | PySide6 LGPL | .NET MIT | Qt LGPL/商业 |

推荐：

- **快速原型 / 工具型产品 / BLE 为主**：Python + PySide6。
- **Windows 企业软件 / 经典蓝牙 + RFCOMM / 需要稳定安装包**：C#/.NET + WPF，macOS 用 Swift 辅助。
- **已有 Qt 团队 / 需要 C++ 性能 / 跨平台 BLE**：Qt 6 + Qt Bluetooth。

---

# 2. C# / .NET + WPF

## 2.1 目标框架

~~~xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net8.0-windows10.0.19041.0</TargetFramework>
    <UseWPF>true</UseWPF>
    <SupportedOSPlatformVersion>10.0.17763.0</SupportedOSPlatformVersion>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="InTheHand.Net.Bluetooth" Version="4.2.4" />
  </ItemGroup>
</Project>
~~~

说明：

- net8.0-windows10.0.19041.0 让 WinRT API 可直接使用。
- 32feet.NET 的 NuGet 包名是 InTheHand.Net.Bluetooth，版本需按实际发布更新。
- Windows 经典蓝牙需要目标机器有可用的蓝牙驱动/栈。

## 2.2 分层

~~~text
BlueDesk.Wpf
├── Views
│   ├── MainWindow.xaml
│   ├── DeviceListView.xaml
│   └── Panels
│       ├── AudioPanel.xaml
│       ├── MousePanel.xaml
│       ├── KeyboardPanel.xaml
│       └── WearablePanel.xaml
├── ViewModels
│   ├── MainViewModel.cs
│   ├── DeviceViewModel.cs
│   └── PanelFactory.cs
├── Services
│   ├── IBluetoothService.cs
│   ├── WindowsBleService.cs
│   ├── WindowsClassicService.cs
│   ├── MacBridgeService.cs
│   └── ProtocolRegistry.cs
├── Models
│   ├── DeviceInfo.cs
│   ├── DeviceType.cs
│   └── Telemetry.cs
└── Helpers
    ├── VolumeController.cs
    └── MediaKeySender.cs
~~~

## 2.3 数据模型

~~~csharp
public enum DeviceType
{
    Headphones,
    Speaker,
    CarAudio,
    Mouse,
    Keyboard,
    Gamepad,
    Wearable,
    Phone,
    Unknown
}

public sealed class DeviceInfo
{
    public string Id { get; init; } = "";
    public string Name { get; set; } = "";
    public string Address { get; init; } = "";
    public DeviceType Type { get; set; } = DeviceType.Unknown;
    public short? Rssi { get; set; }
    public bool Paired { get; set; }
    public bool Connected { get; set; }
    public string Transport { get; set; } = "unknown";
    public double Confidence { get; set; }
    public string ClassificationSource { get; set; } = "";
    public Dictionary<int, byte[]> ManufacturerData { get; } = new();
}
~~~

## 2.4 BLE 扫描（WinRT）

~~~csharp
using Windows.Devices.Bluetooth.Advertisement;

public sealed class WindowsBleService
{
    private BluetoothLEAdvertisementWatcher? _watcher;

    public event EventHandler<DeviceInfo>? DeviceDiscovered;

    public void Start()
    {
        _watcher = new BluetoothLEAdvertisementWatcher
        {
            ScanningMode = BluetoothLEScanningMode.Active
        };
        _watcher.Received += OnAdvertisement;
        _watcher.Start();
    }

    public void Stop()
    {
        _watcher?.Stop();
        _watcher = null;
    }

    private void OnAdvertisement(
        BluetoothLEAdvertisementWatcher sender,
        BluetoothLEAdvertisementReceivedEventArgs args)
    {
        var name = args.Advertisement.LocalName;
        if (string.IsNullOrWhiteSpace(name))
            name = "(未命名设备)";

        var device = new DeviceInfo
        {
            Id = args.BluetoothAddress.ToString("X12"),
            Address = FormatMac(args.BluetoothAddress),
            Name = name,
            Rssi = args.RawSignalStrengthInDBm,
            Transport = "ble"
        };

        foreach (var section in args.Advertisement.ManufacturerData)
        {
            device.ManufacturerData[(int)section.CompanyId] =
                section.Data.ToArray();
        }

        DeviceDiscovered?.Invoke(this, device);
    }

    private static string FormatMac(ulong address)
    {
        var hex = address.ToString("X12");
        return string.Join(":", Enumerable.Range(0, 6)
            .Select(i => hex.Substring(i * 2, 2)));
    }
}
~~~

## 2.5 已配对/经典设备发现（32feet.NET）

~~~csharp
using InTheHand.Net.Sockets;

public IReadOnlyList<DeviceInfo> DiscoverClassic()
{
    using var client = new BluetoothClient();
    var devices = client.DiscoverDevices(
        maxDevices: 30,
        authenticated: true,
        remembered: true,
        unknown: true);

    return devices.Select(d => new DeviceInfo
    {
        Id = d.DeviceAddress.ToString(),
        Address = d.DeviceAddress.ToString("C"),
        Name = d.DeviceName,
        Rssi = d.Rssi,
        Paired = d.Authenticated,
        Connected = d.Connected,
        Transport = "classic"
    }).ToList();
}
~~~

注意：

- 32feet.NET 在 Windows 上依赖蓝牙栈，部分 BLE-only 适配器对经典发现支持差。
- 发现可能耗时 10-20 秒，应放在后台任务。
- 已配对设备可通过 client.PairedDevices 快速获取。

## 2.6 BLE GATT

~~~csharp
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.GenericAttributeProfile;

public async Task InspectAsync(ulong address)
{
    using var device = await BluetoothLEDevice.FromBluetoothAddressAsync(address);
    if (device is null)
        throw new InvalidOperationException("设备不可用");

    var serviceResult = await device.GetGattServicesAsync();
    foreach (var service in serviceResult.Services)
    {
        Console.WriteLine($"Service {service.Uuid}");

        var charResult = await service.GetCharacteristicsAsync();
        foreach (var characteristic in charResult.Characteristics)
        {
            Console.WriteLine(
                $"  Char {characteristic.Uuid} " +
                $"{characteristic.CharacteristicProperties}");

            if (characteristic.CharacteristicProperties.HasFlag(
                GattCharacteristicProperties.Read))
            {
                var read = await characteristic.ReadValueAsync();
                var bytes = new byte[read.Value.Length];
                using var reader = Windows.Storage.Streams.DataReader.FromBuffer(read.Value);
                reader.ReadBytes(bytes);
                Console.WriteLine(BitConverter.ToString(bytes));
            }
        }
    }
}
~~~

写入与通知：

~~~csharp
var writer = new Windows.Storage.Streams.DataWriter();
writer.WriteBytes(new byte[] { 0xA5, 0x01, 0x02 });
var buffer = writer.DetachBuffer();
await characteristic.WriteValueAsync(buffer, GattWriteOption.WriteWithResponse);

characteristic.ValueChanged += (_, args) =>
{
    var bytes = new byte[args.CharacteristicValue.Length];
    using var reader = Windows.Storage.Streams.DataReader.FromBuffer(args.CharacteristicValue);
    reader.ReadBytes(bytes);
    Console.WriteLine(BitConverter.ToString(bytes));
};
await characteristic.WriteClientCharacteristicConfigurationDescriptorAsync(
    GattClientCharacteristicConfigurationDescriptorValue.Notify);
~~~

## 2.7 经典 RFCOMM

~~~csharp
using InTheHand.Net.Bluetooth;
using InTheHand.Net.Sockets;

public async Task SendAsync(string mac, byte[] payload)
{
    var address = BluetoothAddress.Parse(mac);
    var endpoint = new BluetoothEndPoint(
        address,
        BluetoothService.SerialPort);

    using var client = new BluetoothClient();
    client.Connect(endpoint);

    using var stream = client.GetStream();
    await stream.WriteAsync(payload);
}
~~~

生产级实现还需要：

- SDP 查询真实 channel。
- 连接超时与取消。
- 数据分帧、校验和、重连。
- 后台线程与 UI 解耦。

## 2.8 系统音量与媒体键

C# 可使用：

- NAudio / CoreAudio API。
- AudioSwitcher.AudioApi.CoreAudio。
- 或 Win32 keybd_event 媒体键。

~~~csharp
using System.Runtime.InteropServices;

public static class MediaKeys
{
    private const byte VK_MEDIA_PLAY_PAUSE = 0xB3;
    private const uint KEYEVENTF_KEYUP = 0x0002;

    [DllImport("user32.dll")]
    private static extern void keybd_event(
        byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);

    public static void PlayPause()
    {
        keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, UIntPtr.Zero);
        keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
    }
}
~~~

## 2.9 macOS：C# 的限制与桥接

.NET 在 macOS 上：

- 没有官方跨平台 Bluetooth API。
- Xamarin.Mac / .NET for macOS 可以绑定 CoreBluetooth/IOBluetooth，但维护成本高、版本绑定复杂。
- 纯 C# 访问 IOBluetooth 的公开 API 非常有限。
- 推荐“Windows 原生 + macOS Swift 辅助进程”。

架构：

~~~text
Avalonia / .NET UI (macOS)
        │ JSON lines over stdin/stdout
        ▼
Swift Helper (signed)
  ├── CoreBluetooth (BLE)
  ├── IOBluetooth (classic paired)
  └── AppleScript / Media keys
~~~

C# 启动辅助进程：

~~~csharp
using System.Diagnostics;
using System.Text.Json;

var process = new Process
{
    StartInfo = new ProcessStartInfo
    {
        FileName = "/Applications/BlueDesk.app/Contents/Helpers/BlueDeskBLE",
        RedirectStandardInput = true,
        RedirectStandardOutput = true,
        UseShellExecute = false
    }
};
process.Start();

var request = JsonSerializer.Serialize(new { cmd = "scan.start" });
await process.StandardInput.WriteLineAsync(request);
await process.StandardInput.FlushAsync();

var response = await process.StandardOutput.ReadLineAsync();
Console.WriteLine(response);
~~~

Swift 辅助程序（CoreBluetooth）：

~~~swift
import Foundation
import CoreBluetooth

final class Scanner: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    private var manager: CBCentralManager!

    override init() {
        super.init()
        manager = CBCentralManager(delegate: self, queue: nil)
    }

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        guard central.state == .poweredOn else {
            emit(["event": "error", "message": "Bluetooth unavailable"])
            return
        }
        central.scanForPeripherals(withServices: nil, options: nil)
    }

    func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        emit([
            "event": "device",
            "id": peripheral.identifier.uuidString,
            "name": peripheral.name ?? advertisementData[CBAdvertisementDataLocalNameKey] as? String ?? "",
            "rssi": RSSI.intValue,
            "services": (advertisementData[CBAdvertisementDataServiceUUIDsKey] as? [CBUUID] ?? []).map { $0.uuidString }
        ])
    }

    private func emit(_ object: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: object),
              let line = String(data: data, encoding: .utf8) else { return }
        print(line)
        fflush(stdout)
    }
}

let scanner = Scanner()
RunLoop.main.run()
~~~

Swift 辅助程序需要：

- Info.plist 蓝牙权限描述。
- 签名与公证。
- 与主应用一致的 bundle/team 配置。
- JSON lines 协议版本化。
- 进程崩溃重启与超时。

## 2.10 共享协议

主应用与辅助进程建议使用版本化 JSON Lines：

~~~json
{"v":1,"cmd":"scan.start","mode":"ble"}
{"v":1,"event":"device","id":"UUID","name":"WH-1000XM5","rssi":-48,"type":"headphones"}
{"v":1,"cmd":"gatt.read","id":"UUID","char":"00002a19-0000-1000-8000-00805f9b34fb"}
{"v":1,"event":"data","id":"UUID","char":"...","hex":"4B"}
~~~

---

# 3. Qt 6 / C++

## 3.1 CMake

~~~cmake
cmake_minimum_required(VERSION 3.21)
project(BlueDeskQt LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 REQUIRED COMPONENTS Core Widgets Bluetooth)

qt_add_executable(BlueDeskQt
    src/main.cpp
    src/MainWindow.cpp
    src/BluetoothManager.cpp
    src/DeviceTypeClassifier.cpp
)

target_link_libraries(BlueDeskQt PRIVATE
    Qt6::Core
    Qt6::Widgets
    Qt6::Bluetooth
)
~~~

## 3.2 经典/BLE 发现

~~~cpp
#include <QBluetoothDeviceDiscoveryAgent>
#include <QBluetoothDeviceInfo>

auto *agent = new QBluetoothDeviceDiscoveryAgent(this);
agent->setLowEnergyDiscoveryTimeout(15000);

connect(agent, &QBluetoothDeviceDiscoveryAgent::deviceDiscovered,
        this, [this](const QBluetoothDeviceInfo &info) {
    DeviceInfo device;
    device.name = info.name();
    device.address = info.address().toString();
    device.rssi = info.rssi();
    device.paired = info.isValid() && info.address().isValid();

    const quint32 cod = info.classOfDevice();
    device.majorClass = (cod >> 8) & 0x1F;
    device.minorClass = (cod >> 2) & 0x3F;

    for (const QBluetoothUuid &uuid : info.serviceUuids()) {
        device.serviceUuids.append(uuid.toString());
    }

    device.type = classify(device);
    upsertDevice(device);
});

agent->start(QBluetoothDeviceDiscoveryAgent::LowEnergyMethod);
// 或 ClassicMethod / CombinedMethod
~~~

平台差异：

- Windows：ClassicMethod + LowEnergyMethod 通常可用。
- macOS：BLE 可用；经典发现支持有限，取决于 Qt 版本与系统。
- CombinedMethod 不一定在所有后端实现。
- Qt 6 的 QBluetoothDeviceInfo 可提供 manufacturerData、serviceData。

## 3.3 BLE 连接与 GATT

~~~cpp
#include <QLowEnergyController>
#include <QLowEnergyService>

auto *controller = QLowEnergyController::createCentral(info, this);

connect(controller, &QLowEnergyController::connected,
        controller, &QLowEnergyController::discoverServices);

connect(controller, &QLowEnergyController::serviceDiscovered,
        this, [this, controller](const QBluetoothUuid &uuid) {
    auto *service = controller->createServiceObject(uuid, this);
    if (service) {
        connect(service, &QLowEnergyService::stateChanged,
                service, [service](QLowEnergyService::ServiceState state) {
            if (state == QLowEnergyService::RemoteServiceDiscovered) {
                for (const auto &ch : service->characteristics()) {
                    qDebug() << ch.uuid() << ch.properties();
                }
            }
        });
        service->discoverDetails();
    }
});

connect(controller, &QLowEnergyController::disconnected,
        this, &MainWindow::onDisconnected);

controller->connectToDevice();
~~~

读取：

~~~cpp
auto service = controller->createServiceObject(serviceUuid, this);
auto ch = service->characteristic(charUuid);
service->readCharacteristic(ch);

connect(service, &QLowEnergyService::characteristicRead,
        this, [](const QLowEnergyCharacteristic &c, const QByteArray &value) {
    qDebug() << c.uuid() << value.toHex(' ');
});
~~~

写入：

~~~cpp
QByteArray payload = QByteArray::fromHex("A501024006E2");
service->writeCharacteristic(ch, payload, QLowEnergyService::WriteWithResponse);
~~~

通知：

~~~cpp
auto cccd = ch.clientCharacteristicConfiguration();
service->writeDescriptor(
    cccd,
    QLowEnergyCharacteristic::CCCDEnableNotification);

connect(service, &QLowEnergyService::characteristicChanged,
        this, [](const QLowEnergyCharacteristic &c, const QByteArray &value) {
    qDebug() << "notify" << c.uuid() << value.toHex(' ');
});
~~~

## 3.4 经典 RFCOMM / SPP

~~~cpp
#include <QBluetoothSocket>
#include <QBluetoothUuid>

auto *socket = new QBluetoothSocket(QBluetoothServiceInfo::RfcommProtocol, this);
socket->connectToService(
    QBluetoothAddress("AA:BB:CC:DD:EE:FF"),
    QBluetoothUuid(QBluetoothUuid::ServiceClassUuid::SerialPort));

connect(socket, &QBluetoothSocket::connected, this, [socket]() {
    socket->write(QByteArray::fromHex("A501024006E2"));
});

connect(socket, &QBluetoothSocket::readyRead, this, [socket]() {
    qDebug() << socket->readAll().toHex(' ');
});
~~~

注意：

- macOS 上 QBluetoothSocket 的 RFCOMM 支持有限。
- 需要 SDP 查询确认 channel。
- Windows 上依赖蓝牙栈。

## 3.5 已配对设备

~~~cpp
QBluetoothLocalDevice local;
for (const QBluetoothAddress &address : local.connectedDevices()) {
    qDebug() << "connected" << address.toString();
}
~~~

QBluetoothLocalDevice 的能力取决于平台；不能保证列出所有配对设备。

## 3.6 类型识别

可以把本项目的 classifier.py 规则直接移植为 C++/Qt：

~~~cpp
DeviceType classify(const DeviceInfo &d)
{
    const quint32 cod = d.classOfDevice;
    const quint32 major = (cod >> 8) & 0x1F;
    const quint32 minor = (cod >> 2) & 0x3F;

    if (major == 0x04) {
        if (minor == 0x05 || minor == 0x01 || minor == 0x02)
            return DeviceType::Headphones;
        if (minor == 0x07)
            return DeviceType::CarAudio;
        return DeviceType::Speaker;
    }
    if (major == 0x05) {
        if (minor == 0x10 || minor == 0x30)
            return DeviceType::Keyboard;
        if (minor == 0x20)
            return DeviceType::Mouse;
        if (minor == 0x04 || minor == 0x08)
            return DeviceType::Gamepad;
    }
    if (major == 0x07 || major == 0x09)
        return DeviceType::Wearable;

    return classifyByName(d.name);
}
~~~

## 3.7 Qt 平台差异

| 能力 | Windows | macOS |
| --- | --- | --- |
| BLE 扫描 | 支持 | 支持 |
| BLE GATT | 支持 | 支持 |
| 经典发现 | 支持（视蓝牙栈） | 有限 |
| RFCOMM | QBluetoothSocket 可用 | 支持有限 |
| 已配对列表 | QBluetoothLocalDevice 有限 | 有限 |
| 系统音量 | 需 Win32/第三方 | 需 CoreAudio/AppleScript |
| 权限 | 无统一弹窗 | Info.plist + TCC |
| 部署 | Qt DLL + MSVC 运行库 | .app + frameworks + 签名 |

## 3.8 Qt 项目结构建议

~~~text
BlueDeskQt/
├── CMakeLists.txt
├── src/
│   ├── main.cpp
│   ├── MainWindow.*
│   ├── DeviceListModel.*
│   ├── DeviceListDelegate.*
│   ├── BluetoothManager.*
│   ├── BleConnection.*
│   ├── ClassicConnection.*
│   ├── DeviceTypeClassifier.*
│   ├── ProtocolRegistry.*
│   ├── panels/
│   │   ├── AudioPanel.*
│   │   ├── MousePanel.*
│   │   ├── KeyboardPanel.*
│   │   └── WearablePanel.*
│   └── platform/
│       ├── MacVolume.*
│       └── WindowsVolume.*
└── resources/
    └── theme.qss
~~~

---

# 4. 推荐决策

## 4.1 选择 Python + PySide6 的情况

- 主要目标是 BLE 设备管理与 GATT 调试。
- 需要尽快交付跨平台 UI。
- 团队熟悉 Python，硬件协议迭代频繁。
- 可以接受经典蓝牙功能受限。

## 4.2 选择 C# / WPF 的情况

- 主要用户在 Windows。
- 需要稳定 RFCOMM/SPP、企业部署、MSI 安装包。
- 需要与 Windows 系统 API、注册表、组策略深度集成。
- 可以接受 macOS 采用 Swift 辅助进程。

## 4.3 选择 Qt / C++ 的情况

- 已有 Qt 技术栈与构建体系。
- 需要 C++ 性能或与现有 Qt 应用集成。
- 目标以 BLE 为主，经典蓝牙只在 Windows 使用。
- 能承担 Qt 部署、签名、跨平台测试成本。

## 4.4 混合架构

对于“Windows 经典蓝牙 + macOS 经典蓝牙 + 跨平台 UI”的强需求，最稳妥的是：

~~~text
跨平台 UI（Python/PySide6 或 Avalonia/Qt）
        │
        ├── Windows Helper（C# / 32feet.NET / WinRT）
        └── macOS Helper（Swift / IOBluetooth / CoreBluetooth）
        │
        └── 统一 JSON-RPC 协议
~~~

这样可以把平台相关风险隔离在小型、可独立测试的辅助进程中，而 UI 和设备模型保持跨平台。

---

## 5. 相关文档

- [项目 README](../README.md)
- [Windows 实现](windows.md)
- [macOS 实现](macos.md)
- [设备类型识别](../src/bluedesk/classifier.py)
- [协议适配器](../src/bluedesk/protocols)
