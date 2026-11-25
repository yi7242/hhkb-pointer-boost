// HHKB Pointer Boost for macOS
// Menu bar app that changes mouse tracking speed while a chosen key is held.

import AppKit
import SwiftUI
import Darwin

let appName = "HHKB Pointer Boost"
let appID = Bundle.main.bundleIdentifier ?? "local.hhkbpointerboost"
let showRequest = Notification.Name("local.hhkbpointerboost.show")
let speedRange: ClosedRange<Double> = 0...5
let pollChoices = [16, 30, 50, 100]

func clampSpeed(_ value: Double) -> Double { min(max(value, speedRange.lowerBound), speedRange.upperBound) }

// MARK: - Pointer speed

/// Sets the tracking speed of connected mice through IOHIDEventSystemClient,
/// which takes effect immediately like the System Settings slider.
/// Services whose acceleration type is not the mouse one (trackpads) are left alone.
final class PointerSpeed {
    private typealias CreateClient = @convention(c) (CFAllocator?) -> UnsafeMutableRawPointer?
    private typealias CopyServices = @convention(c) (UnsafeMutableRawPointer) -> UnsafeMutableRawPointer?
    private typealias CopyProperty = @convention(c) (UnsafeRawPointer, UnsafeRawPointer) -> UnsafeMutableRawPointer?
    private typealias SetProperty = @convention(c) (UnsafeRawPointer, UnsafeRawPointer, UnsafeRawPointer) -> UInt8
    private typealias ConformsTo = @convention(c) (UnsafeRawPointer, UInt32, UInt32) -> UInt8

    private static let accelerationTypeKey = "HIDPointerAccelerationType"
    private static let mouseAccelerationKey = "HIDMouseAcceleration"

    private let client: UnsafeMutableRawPointer?
    private let copyServices: CopyServices?
    private let copyProperty: CopyProperty?
    private let setProperty: SetProperty?
    private let conformsTo: ConformsTo?

    init() {
        let handle = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_NOW)
        func load<T>(_ name: String, _ type: T.Type) -> T? {
            guard let handle, let symbol = dlsym(handle, name) else { return nil }
            return unsafeBitCast(symbol, to: type)
        }
        let create = load("IOHIDEventSystemClientCreateSimpleClient", CreateClient.self)
        copyServices = load("IOHIDEventSystemClientCopyServices", CopyServices.self)
        copyProperty = load("IOHIDServiceClientCopyProperty", CopyProperty.self)
        setProperty = load("IOHIDServiceClientSetProperty", SetProperty.self)
        conformsTo = load("IOHIDServiceClientConformsTo", ConformsTo.self)
        client = create?(kCFAllocatorDefault)
    }

    var isAvailable: Bool { client != nil && copyServices != nil && setProperty != nil }

    /// Current tracking speed of the first connected mouse (System Settings scale, 0...3 by default).
    func speed() -> Double? {
        var result: Double?
        forEachMouse { service in
            if result == nil, let number = copy(service, Self.mouseAccelerationKey) as? NSNumber {
                result = number.doubleValue / 65536
            }
        }
        return result
    }

    /// Returns the number of mice that accepted the new speed.
    @discardableResult
    func setSpeed(_ value: Double) -> Int {
        guard let setProperty else { return 0 }
        let key = Self.mouseAccelerationKey as CFString
        // The HID system stores acceleration as IOFixed (16.16 fixed point).
        let number = NSNumber(value: Int((clampSpeed(value) * 65536).rounded())) as CFNumber
        var count = 0
        forEachMouse { service in
            let ok = setProperty(
                service,
                Unmanaged.passUnretained(key).toOpaque(),
                Unmanaged.passUnretained(number).toOpaque()
            )
            if ok != 0 { count += 1 }
        }
        return count
    }

    func mouseCount() -> Int {
        var count = 0
        forEachMouse { _ in count += 1 }
        return count
    }

    private func forEachMouse(_ body: (UnsafeRawPointer) -> Void) {
        guard let client, let copyServices, let raw = copyServices(client) else { return }
        let services = Unmanaged<CFArray>.fromOpaque(raw).takeRetainedValue()
        for index in 0..<CFArrayGetCount(services) {
            if let service = CFArrayGetValueAtIndex(services, index), isMouse(service) {
                body(service)
            }
        }
    }

    private func isMouse(_ service: UnsafeRawPointer) -> Bool {
        if let type = copy(service, Self.accelerationTypeKey) as? String {
            return type == Self.mouseAccelerationKey
        }
        // Generic Desktop page (0x01), Mouse usage (0x02)
        return conformsTo?(service, 0x01, 0x02) == 1
    }

    private func copy(_ service: UnsafeRawPointer, _ key: String) -> AnyObject? {
        let cfKey = key as CFString
        guard let copyProperty,
              let raw = copyProperty(service, Unmanaged.passUnretained(cfKey).toOpaque())
        else { return nil }
        return Unmanaged<AnyObject>.fromOpaque(raw).takeRetainedValue()
    }
}

/// Tracking speed saved in System Settings, used when no mouse is connected at first launch.
func systemPreferenceSpeed() -> Double? {
    let value = CFPreferencesCopyAppValue("com.apple.mouse.scaling" as CFString, kCFPreferencesAnyApplication)
    if let number = value as? NSNumber { return number.doubleValue }
    if let text = value as? String { return Double(text) }
    return nil
}

// MARK: - Trigger keys

enum Trigger: String, CaseIterable, Identifiable {
    case leftOption = "左Option"
    case rightOption = "右Option"
    case leftShift = "左Shift"
    case rightShift = "右Shift"
    case leftControl = "左Control"
    case rightControl = "右Control"
    case leftCommand = "左Command"
    case rightCommand = "右Command"
    case f13 = "F13（専用キー向け）"
    case f14 = "F14（専用キー向け）"
    case f15 = "F15（専用キー向け）"
    case mouseBack = "マウス戻るボタン"
    case mouseForward = "マウス進むボタン"

    var id: String { rawValue }

    private enum Source {
        /// Device-dependent mask (left/right), generic modifier mask, virtual key code.
        case modifier(side: UInt64, generic: CGEventFlags, key: CGKeyCode)
        case key(CGKeyCode)
        case button(UInt32)
    }

    private var source: Source {
        switch self {
        case .leftControl: return .modifier(side: 0x0000_0001, generic: .maskControl, key: 59)
        case .leftShift: return .modifier(side: 0x0000_0002, generic: .maskShift, key: 56)
        case .rightShift: return .modifier(side: 0x0000_0004, generic: .maskShift, key: 60)
        case .leftCommand: return .modifier(side: 0x0000_0008, generic: .maskCommand, key: 55)
        case .rightCommand: return .modifier(side: 0x0000_0010, generic: .maskCommand, key: 54)
        case .leftOption: return .modifier(side: 0x0000_0020, generic: .maskAlternate, key: 58)
        case .rightOption: return .modifier(side: 0x0000_0040, generic: .maskAlternate, key: 61)
        case .rightControl: return .modifier(side: 0x0000_2000, generic: .maskControl, key: 62)
        case .f13: return .key(0x69)
        case .f14: return .key(0x6B)
        case .f15: return .key(0x71)
        case .mouseBack: return .button(3)
        case .mouseForward: return .button(4)
        }
    }

    /// Non-modifier keys can only be read with the Input Monitoring permission.
    var needsInputMonitoring: Bool {
        if case .key = source { return true }
        return false
    }

    func isDown() -> Bool {
        switch source {
        case let .modifier(side, generic, key):
            if CGEventSource.keyState(.hidSystemState, key: key) { return true }
            let flags = CGEventSource.flagsState(.hidSystemState)
            let deviceBits: UInt64 = 0x207F
            if flags.rawValue & deviceBits != 0 { return flags.rawValue & side != 0 }
            // Left/right bits are missing: fall back to the generic modifier.
            return flags.contains(generic)
        case let .key(code):
            return CGEventSource.keyState(.hidSystemState, key: code)
        case let .button(number):
            guard let button = CGMouseButton(rawValue: number) else { return false }
            return CGEventSource.buttonState(.hidSystemState, button: button)
        }
    }
}

// MARK: - Login item (LaunchAgent)

enum LoginItem {
    static let label = "local.hhkbpointerboost"

    static var plistURL: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/LaunchAgents/\(label).plist")
    }

    static var executable: String { Bundle.main.executablePath ?? CommandLine.arguments[0] }

    static func isEnabled() -> Bool { FileManager.default.fileExists(atPath: plistURL.path) }

    static func set(_ enabled: Bool) throws {
        if !enabled {
            if isEnabled() { try FileManager.default.removeItem(at: plistURL) }
            return
        }
        let plist: [String: Any] = [
            "Label": label,
            "ProgramArguments": [executable, "--startup"],
            "RunAtLoad": true,
            "ProcessType": "Interactive",
            "LimitLoadToSessionType": "Aqua",
        ]
        try FileManager.default.createDirectory(
            at: plistURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        let data = try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
        try data.write(to: plistURL, options: .atomic)
    }

    /// Re-points the login item after the app has been moved.
    static func refreshPathIfNeeded() {
        guard isEnabled(),
              let data = try? Data(contentsOf: plistURL),
              let plist = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any],
              let args = plist["ProgramArguments"] as? [String]
        else { return }
        if args.first != executable { try? set(true) }
    }
}

// MARK: - Settings

final class BoostSettings: ObservableObject {
    @Published var enabled: Bool { didSet { UserDefaults.standard.set(enabled, forKey: "enabled") } }
    @Published var trigger: Trigger {
        didSet {
            UserDefaults.standard.set(trigger.rawValue, forKey: "trigger")
            onTriggerChange?()
        }
    }
    @Published var normalSpeed: Double { didSet { UserDefaults.standard.set(normalSpeed, forKey: "normalSpeed") } }
    @Published var boostSpeed: Double { didSet { UserDefaults.standard.set(boostSpeed, forKey: "boostSpeed") } }
    @Published var pollMs: Int { didSet { UserDefaults.standard.set(pollMs, forKey: "pollMs") } }
    @Published var launchAtLogin: Bool { didSet { onLaunchAtLoginChange?(launchAtLogin) } }

    @Published var speedText = ""
    @Published var stateText = ""
    @Published var needsInputMonitoring = false

    var onTriggerChange: (() -> Void)?
    var onLaunchAtLoginChange: ((Bool) -> Void)?

    init(currentSpeed: Double?) {
        let defaults = UserDefaults.standard
        enabled = defaults.object(forKey: "enabled") as? Bool ?? true
        trigger = defaults.string(forKey: "trigger").flatMap(Trigger.init(rawValue:)) ?? .leftOption
        normalSpeed = clampSpeed(defaults.object(forKey: "normalSpeed") as? Double ?? currentSpeed ?? 0.6875)
        boostSpeed = clampSpeed(defaults.object(forKey: "boostSpeed") as? Double ?? 3.0)
        let poll = defaults.object(forKey: "pollMs") as? Int ?? 16
        pollMs = pollChoices.contains(poll) ? poll : 16
        launchAtLogin = LoginItem.isEnabled()
    }
}

// MARK: - Settings window

struct SettingsView: View {
    @ObservedObject var settings: BoostSettings
    let openInputMonitoring: () -> Void
    let close: () -> Void
    let quit: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(appName).font(.title2.bold())
            Text("指定キーを押している間だけ、マウスのトラッキング速度を切り替えます。")

            GroupBox("現在の状態") {
                VStack(alignment: .leading, spacing: 4) {
                    Text(settings.speedText)
                    Text(settings.stateText)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(6)
            }

            GroupBox("設定") {
                VStack(alignment: .leading, spacing: 10) {
                    Toggle("ポインター加速を有効にする", isOn: $settings.enabled)
                    row("押している間のキー") {
                        Picker("", selection: $settings.trigger) {
                            ForEach(Trigger.allCases) { Text($0.rawValue).tag($0) }
                        }
                        .labelsHidden()
                    }
                    if settings.needsInputMonitoring {
                        HStack {
                            Text("このキーを読むには「入力監視」の許可が必要です。")
                                .foregroundStyle(.red)
                            Spacer()
                            Button("許可を開く", action: openInputMonitoring)
                        }
                    }
                    speedRow("通常時の速度", value: $settings.normalSpeed)
                    speedRow("キー押下中の速度", value: $settings.boostSpeed)
                    row("反応間隔") {
                        Picker("", selection: $settings.pollMs) {
                            ForEach(pollChoices, id: \.self) { Text("\($0) ms").tag($0) }
                        }
                        .labelsHidden()
                        .frame(width: 110)
                        Spacer()
                    }
                    Toggle("ログイン時に自動起動する", isOn: $settings.launchAtLogin)
                }
                .padding(6)
            }

            HStack {
                Button("終了", action: quit)
                Spacer()
                Button("閉じる", action: close).keyboardShortcut(.defaultAction)
            }
        }
        .padding(18)
        .frame(width: 460)
    }

    private func row<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        HStack {
            Text(title).frame(width: 130, alignment: .leading)
            content()
        }
    }

    private func speedRow(_ title: String, value: Binding<Double>) -> some View {
        row(title) {
            Slider(value: value, in: speedRange)
            Text(String(format: "%.2f", value.wrappedValue))
                .monospacedDigit()
                .frame(width: 40, alignment: .trailing)
        }
    }
}

// MARK: - Icon

/// Same artwork as the Windows icon (make_hhkb_icon.py): charcoal tile, white H, orange +.
func makeIcon(size: CGFloat) -> NSImage {
    NSImage(size: NSSize(width: size, height: size), flipped: true) { rect in
        let s = rect.width
        let tile = NSBezierPath(
            roundedRect: rect.insetBy(dx: s * 0.03, dy: s * 0.03), xRadius: s * 0.22, yRadius: s * 0.22)
        NSColor(srgbRed: 0x33 / 255.0, green: 0x36 / 255.0, blue: 0x3B / 255.0, alpha: 1).setFill()
        tile.fill()
        func fill(_ rects: [(CGFloat, CGFloat, CGFloat, CGFloat)], _ color: NSColor) {
            color.setFill()
            for (x0, y0, x1, y1) in rects {
                NSRect(x: x0 * s, y: y0 * s, width: (x1 - x0) * s, height: (y1 - y0) * s).fill()
            }
        }
        fill([(0.15, 0.22, 0.30, 0.78), (0.46, 0.22, 0.61, 0.78), (0.15, 0.43, 0.61, 0.57)], .white)
        fill([(0.73, 0.36, 0.85, 0.64), (0.65, 0.44, 0.93, 0.56)],
             NSColor(srgbRed: 1, green: 0xB3 / 255.0, blue: 0, alpha: 1))
        return true
    }
}

// MARK: - App

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private let pointer = PointerSpeed()
    private let showOnStart: Bool
    private var settings: BoostSettings!
    private var statusItem: NSStatusItem!
    private var toggleItem: NSMenuItem!
    private var window: NSWindow?
    private var timer: Timer?
    private var signalSource: DispatchSourceSignal?
    private var boosted = false
    private var appliedSpeed: Double?
    private var knownMouseCount = -1
    private var lastDeviceCheck: TimeInterval = 0
    private var lastStatusRefresh: TimeInterval = 0

    init(showOnStart: Bool) {
        self.showOnStart = showOnStart
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        settings = BoostSettings(currentSpeed: pointer.speed() ?? systemPreferenceSpeed())
        settings.onTriggerChange = { [weak self] in self?.checkInputMonitoring(request: true) }
        settings.onLaunchAtLoginChange = { [weak self] enabled in self?.setLaunchAtLogin(enabled) }
        LoginItem.refreshPathIfNeeded()
        buildStatusItem()
        checkInputMonitoring(request: true)

        DistributedNotificationCenter.default().addObserver(
            self, selector: #selector(handleShowRequest(_:)), name: showRequest, object: nil)

        // Restore the normal speed when stopped by launchctl or logout.
        Darwin.signal(SIGTERM, SIG_IGN)
        let source = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
        source.setEventHandler { NSApp.terminate(nil) }
        source.resume()
        signalSource = source

        if showOnStart || !pointer.isAvailable { showSettings() }
        tick()
    }

    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        if let settings { pointer.setSpeed(settings.normalSpeed) }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showSettings()
        return false
    }

    // Polling loop -----------------------------------------------------------

    private func tick() {
        let now = ProcessInfo.processInfo.systemUptime
        let pressed = settings.enabled && settings.trigger.isDown()
        boosted = pressed
        let target = pressed ? settings.boostSpeed : settings.normalSpeed

        // A newly connected mouse starts at the System Settings speed; re-apply ours.
        if now - lastDeviceCheck >= 2 {
            lastDeviceCheck = now
            let count = pointer.mouseCount()
            if count != knownMouseCount {
                knownMouseCount = count
                appliedSpeed = nil
            }
        }
        if target != appliedSpeed {
            pointer.setSpeed(target)
            appliedSpeed = target
        }

        let windowVisible = window?.isVisible == true
        if windowVisible, now - lastStatusRefresh >= 0.5 {
            lastStatusRefresh = now
            refreshStatus()
        }
        let iconDisabled = !settings.enabled
        if statusItem.button?.appearsDisabled != iconDisabled {
            statusItem.button?.appearsDisabled = iconDisabled
        }

        let interval = (settings.enabled || windowVisible) ? Double(settings.pollMs) / 1000 : 0.5
        let next = Timer(timeInterval: interval, repeats: false) { [weak self] _ in self?.tick() }
        // .common keeps polling while a menu or slider is being tracked.
        RunLoop.main.add(next, forMode: .common)
        timer = next
    }

    private func refreshStatus() {
        let speedText: String
        if !pointer.isAvailable {
            speedText = "このMacではマウスの速度を変更できません"
        } else if let speed = pointer.speed() {
            speedText = String(format: "現在のトラッキング速度:  %.2f", speed)
        } else {
            speedText = "マウスが接続されていません"
        }
        let name = settings.trigger.rawValue
        let stateText: String
        if !settings.enabled {
            stateText = "動作状態:  オフ"
        } else if boosted {
            stateText = "動作状態:  加速中（\(name)）"
        } else {
            stateText = "動作状態:  通常（\(name)待機中）"
        }
        if settings.speedText != speedText { settings.speedText = speedText }
        if settings.stateText != stateText { settings.stateText = stateText }
        checkInputMonitoring(request: false)
    }

    private func checkInputMonitoring(request: Bool) {
        var missing = false
        if settings.trigger.needsInputMonitoring {
            if request, !CGPreflightListenEventAccess() { _ = CGRequestListenEventAccess() }
            missing = !CGPreflightListenEventAccess()
        }
        if settings.needsInputMonitoring != missing { settings.needsInputMonitoring = missing }
    }

    private func setLaunchAtLogin(_ enabled: Bool) {
        do {
            try LoginItem.set(enabled)
        } catch {
            let alert = NSAlert()
            alert.messageText = "自動起動の設定を変更できませんでした。"
            alert.informativeText = error.localizedDescription
            alert.runModal()
        }
    }

    // Menu bar ---------------------------------------------------------------

    private func buildStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem.button?.image = makeIcon(size: 18)
        statusItem.button?.toolTip = appName

        let menu = NSMenu()
        menu.delegate = self
        toggleItem = NSMenuItem(title: "有効", action: #selector(toggleEnabled), keyEquivalent: "")
        toggleItem.target = self
        menu.addItem(toggleItem)
        let settingsItem = NSMenuItem(title: "設定を開く…", action: #selector(showSettings), keyEquivalent: ",")
        settingsItem.target = self
        menu.addItem(settingsItem)
        menu.addItem(.separator())
        let quitItem = NSMenuItem(title: "終了", action: #selector(quit), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)
        statusItem.menu = menu
    }

    func menuWillOpen(_ menu: NSMenu) {
        toggleItem.state = settings.enabled ? .on : .off
    }

    @objc private func toggleEnabled() { settings.enabled.toggle() }

    @objc private func quit() { NSApp.terminate(nil) }

    @objc private func handleShowRequest(_ notification: Notification) { showSettings() }

    @objc func showSettings() {
        if window == nil {
            let view = SettingsView(
                settings: settings,
                openInputMonitoring: {
                    if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent") {
                        NSWorkspace.shared.open(url)
                    }
                },
                close: { [weak self] in self?.window?.close() },
                quit: { NSApp.terminate(nil) }
            )
            let newWindow = NSWindow(contentViewController: NSHostingController(rootView: view))
            newWindow.title = appName
            newWindow.styleMask = [.titled, .closable]
            newWindow.isReleasedWhenClosed = false
            newWindow.center()
            window = newWindow
        }
        refreshStatus()
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }
}

// MARK: - Entry point

let otherInstances = NSRunningApplication.runningApplications(withBundleIdentifier: appID)
    .filter { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }
if !otherInstances.isEmpty {
    DistributedNotificationCenter.default().postNotificationName(
        showRequest, object: nil, userInfo: nil, deliverImmediately: true)
    exit(0)
}

let application = NSApplication.shared
let delegate = AppDelegate(showOnStart: !CommandLine.arguments.contains("--startup"))
application.delegate = delegate
application.run()
