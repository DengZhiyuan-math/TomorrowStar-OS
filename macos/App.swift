import AppKit
import WebKit
import ApplicationServices
import CoreGraphics

func createDiagnosticDirectory(parent: URL, marker: String) throws -> URL {
    let manager = FileManager.default
    let root = parent.appendingPathComponent(marker, isDirectory: true)
    guard !manager.fileExists(atPath: root.path)
    else { throw CocoaError(.fileWriteNoPermission) }
    var ancestor = parent
    while ancestor.path != "/" {
        guard (try? manager.destinationOfSymbolicLink(atPath: ancestor.path)) == nil
        else { throw CocoaError(.fileWriteNoPermission) }
        ancestor.deleteLastPathComponent()
    }
    try manager.createDirectory(at: parent, withIntermediateDirectories: true,
                                attributes: [.posixPermissions: 0o700])
    try manager.createDirectory(at: root, withIntermediateDirectories: false,
                                attributes: [.posixPermissions: 0o700])
    return root
}

final class NativeExitLog {
    private let file: URL
    private let lock = NSLock()

    init?(parent: URL) {
        do {
            let root = try createDiagnosticDirectory(parent: parent,
                marker: "native-exit-" + UUID().uuidString.lowercased())
            file = root.appendingPathComponent("events.jsonl")
            guard FileManager.default.createFile(atPath: file.path, contents: nil,
                attributes: [.posixPermissions: 0o600]) else { return nil }
        } catch { return nil }
    }

    func record(_ event: String, reason: String? = nil, childPID: Int32? = nil,
                exitCode: Int32? = nil, signal: Int32? = nil) {
        lock.lock()
        defer { lock.unlock() }
        var row: [String: Any] = ["utc": ISO8601DateFormatter().string(from: Date()),
            "pid": getpid(), "ppid": getppid(), "event": event]
        if let reason = reason { row["reason"] = reason }
        if let childPID = childPID { row["child_pid"] = childPID }
        if let exitCode = exitCode { row["exit_code"] = exitCode }
        if let signal = signal { row["signal"] = signal }
        do {
            guard (try? file.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == false else { return }
            var data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
            data.append(10)
            let handle = try FileHandle(forWritingTo: file)
            defer { try? handle.close() }
            try handle.seekToEnd()
            try handle.write(contentsOf: data)
        } catch { /* Diagnostic failure must not delay shutdown. */ }
    }
}

// A fixed diagnostic route, selected before any workspace/config or window exists.
// It never requests permissions and cannot execute a caller-selected script.
struct NativeHostReceipt {
    static func frame(snapshot: [String: Any], nonce: String, backendPID: Int32,
                      sequence: Int, kind: String) throws -> Data {
        guard backendPID > 0, sequence > 0, ["sample", "check"].contains(kind),
              nonce.range(of: "^[a-f0-9]{32}$", options: .regularExpression)
                == nonce.startIndex..<nonce.endIndex else { throw CocoaError(.fileWriteInvalidFileName) }
        var row: [String: Any] = ["protocol": "current-native-host/v1", "scope": "current_instance",
            "kind": kind, "launch_nonce": nonce, "backend_pid": backendPID,
            "sequence": sequence, "captured_at": Date().timeIntervalSince1970]
        for key in ["bundle_id", "executable", "accessibility", "screen_recording", "active", "windows"] {
            guard let value = snapshot[key] else { throw CocoaError(.fileReadCorruptFile) }
            row[key] = value
        }
        row["native_pid"] = snapshot["pid"]
        row["native_responsible_pid"] = snapshot["responsible_pid"]
        var data = try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys])
        data.append(10)
        guard data.count <= 4096 else { throw CocoaError(.fileWriteOutOfSpace) }
        return data
    }
}

struct NativeHostCheckRequest {
    static func allows(body: Any, mainFrame: Bool, sameWebView: Bool,
                       origin: URLComponents, currentURL: URL?, backendURL: URL?) -> Bool {
        guard mainFrame, sameWebView,
              let request = body as? [String: Any], request.count == 1,
              request["action"] as? String == "check-current-host",
              let backendURL = backendURL, let currentURL = currentURL,
              backendURL.scheme == "http", backendURL.host == "127.0.0.1",
              let port = backendURL.port, (1...65535).contains(port),
              backendURL.user == nil, backendURL.password == nil,
              currentURL.scheme == "http", currentURL.host == "127.0.0.1",
              currentURL.port == port, currentURL.user == nil, currentURL.password == nil,
              origin.scheme == "http", origin.host == "127.0.0.1", origin.port == port,
              origin.user == nil, origin.password == nil else { return false }
        return true
    }
}

struct BackgroundCheckLaunch {
    let marker: String
    let permissionOnly: Bool
    let pdfOnly: Bool

    static func requested(in arguments: [String]) -> Bool {
        arguments.dropFirst().contains { value in
            ["--background-check", "--permission-check", "--permission-only", "--pdf-export-check"].contains {
                value == $0 || value.hasPrefix($0 + "=")
            }
        }
    }

    init(arguments: [String]) throws {
        guard arguments.count == 3,
              ["--background-check", "--permission-check", "--pdf-export-check"].contains(arguments[1]),
              arguments[2].range(of: "^gui-host-[a-z0-9-]{8,80}$", options: .regularExpression)
                == arguments[2].startIndex..<arguments[2].endIndex
        else { throw CocoaError(.fileWriteInvalidFileName) }
        marker = arguments[2]
        permissionOnly = arguments[1] == "--permission-check"
        pdfOnly = arguments[1] == "--pdf-export-check"
    }

    func backendArguments(resources: URL, root: URL) -> [String] {
        let script = pdfOnly ? "pdf_export_check.py" : "background_check.py"
        return ["-I", "-B", "-u", resources.appendingPathComponent(script).path]
            + (permissionOnly ? ["--permission-only"] : []) + [root.path]
    }
}

final class BackgroundCheckDelegate: NSObject, NSApplicationDelegate {
    private var backend: Process?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.prohibited)
        do {
            let launch = try BackgroundCheckLaunch(arguments: CommandLine.arguments)
            let manager = FileManager.default
            let parent = manager.homeDirectoryForCurrentUser
                .appendingPathComponent("Library/Application Support/TomorrowStar/diagnostics")
            let root = try createDiagnosticDirectory(parent: parent, marker: launch.marker)
            let native = try nativeHostSnapshot()
            try JSONSerialization.data(withJSONObject: native, options: [.prettyPrinted, .sortedKeys])
                .write(to: root.appendingPathComponent("native-tcc.json"), options: .withoutOverwriting)
            let resources = Bundle.main.resourceURL!
            let process = Process()
            process.executableURL = resources.appendingPathComponent("python/bin/python3.13")
            process.arguments = launch.backendArguments(resources: resources, root: root)
            process.currentDirectoryURL = resources
            process.environment = ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
                                   "HOME": manager.homeDirectoryForCurrentUser.path, "TMPDIR": NSTemporaryDirectory()]
            if launch.pdfOnly {
                let temporary = root.appendingPathComponent("tmp", isDirectory: true)
                try manager.createDirectory(at: temporary, withIntermediateDirectories: false,
                                            attributes: [.posixPermissions: 0o700])
                process.environment?["TMPDIR"] = temporary.path
                process.environment?["DEBUG"] = "pw:browser"
            }
            let log = root.appendingPathComponent("background.log")
            guard manager.createFile(atPath: log.path, contents: nil, attributes: [.posixPermissions: 0o600])
            else { throw CocoaError(.fileWriteNoPermission) }
            let handle = try FileHandle(forWritingTo: log)
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = handle
            process.standardError = handle
            process.terminationHandler = { _ in
                try? handle.close()
                DispatchQueue.main.async { NSApp.terminate(nil) }
            }
            backend = process
            try process.run()
        } catch {
            fputs("Background diagnostic refused: \(error)\n", stderr)
            NSApp.terminate(nil)
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { false }
}

func nativeHostSnapshot() throws -> [String: Any] {
    typealias Responsibility = @convention(c) (pid_t) -> pid_t
    guard let symbol = dlsym(dlopen(nil, RTLD_NOW), "responsibility_get_pid_responsible_for_pid"),
          let executable = Bundle.main.executableURL else { throw CocoaError(.executableRuntimeMismatch) }
    let responsible = unsafeBitCast(symbol, to: Responsibility.self)
    return ["pid": getpid(), "ppid": getppid(), "responsible_pid": responsible(getpid()),
        "bundle_id": Bundle.main.bundleIdentifier ?? "", "executable": executable.path,
        "accessibility": AXIsProcessTrusted(), "screen_recording": CGPreflightScreenCaptureAccess(),
        "active": NSRunningApplication.current.isActive,
        "windows": NSApp.windows.count, "permission_prompts": 0]
}

struct PipelineStatus {
    static let byteLimit = 65536
    let running: Bool
    let notificationID: String?

    static func endpoint(_ base: URL) -> URL? {
        guard var parts = URLComponents(url: base, resolvingAgainstBaseURL: false),
              parts.scheme == "http", parts.host == "127.0.0.1",
              let port = parts.port, (1...65535).contains(port),
              parts.user == nil, parts.password == nil,
              parts.path.isEmpty || parts.path == "/",
              parts.query == nil, parts.fragment == nil || parts.fragment == "flow" else { return nil }
        parts.fragment = nil
        parts.path = "/api/pipeline/state"
        return parts.url
    }

    static func decode(_ data: Data) -> PipelineStatus? {
        guard data.count <= byteLimit,
              let value = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              value["protocol"] as? String == "application-pipeline/v1",
              let control = value["control"] as? String, ["running", "paused"].contains(control),
              let status = value["status"] as? String, !status.isEmpty,
              value.keys.contains("notification") else { return nil }
        var notificationID: String?
        if !(value["notification"] is NSNull) {
            guard ["ready_for_review", "needs_input", "needs_recheck", "blocked", "cancelled",
                   "expired", "paused", "interrupted", "no_matches"].contains(status),
                  let notice = value["notification"] as? [String: Any],
                  let id = notice["id"] as? String, !id.isEmpty, id.count <= 200,
                  let title = notice["title"] as? String, !title.isEmpty, title.count <= 200,
                  let message = notice["message"] as? String, !message.isEmpty, message.count <= 1000
            else { return nil }
            notificationID = id
        }
        return PipelineStatus(running: control == "running", notificationID: notificationID)
    }
}

final class PipelineStatusRequest: NSObject, URLSessionDataDelegate {
    private let endpoint: URL
    private let completion: (PipelineStatus?) -> Void
    private var session: URLSession?
    private var bytes = Data()
    private var acceptedResponse = false
    private var finished = false

    init(endpoint: URL, completion: @escaping (PipelineStatus?) -> Void) {
        self.endpoint = endpoint
        self.completion = completion
        super.init()
    }

    func start() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        configuration.httpCookieAcceptPolicy = .never
        configuration.httpCookieStorage = nil
        configuration.urlCredentialStorage = nil
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 5
        configuration.timeoutIntervalForResource = 5
        configuration.connectionProxyDictionary = [:]
        // Main-queue callbacks serialize completion, shutdown and native state.
        session = URLSession(configuration: configuration, delegate: self, delegateQueue: .main)
        var request = URLRequest(url: endpoint)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        session?.dataTask(with: request).resume()
    }

    func cancel() { finish(nil) }

    private func finish(_ result: PipelineStatus?) {
        guard !finished else { return }
        finished = true
        session?.invalidateAndCancel()
        session = nil
        completion(result)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask,
                    didReceive response: URLResponse,
                    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        guard !finished, let response = response as? HTTPURLResponse,
              response.url == endpoint, response.statusCode == 200,
              response.mimeType == "application/json",
              response.expectedContentLength <= Int64(PipelineStatus.byteLimit)
        else { completionHandler(.cancel); finish(nil); return }
        acceptedResponse = true
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard !finished, data.count <= PipelineStatus.byteLimit - bytes.count
        else { finish(nil); return }
        bytes.append(data)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        finish(error == nil && acceptedResponse ? PipelineStatus.decode(bytes) : nil)
    }
}

struct Workspace: Codable {
    static let preparationRootRequired = CodingUserInfoKey(rawValue: "preparationRootRequired")!
    let applications: String
    let career_workspace: String
    let career_library_manifest: String?
    let cover_letter_template: String?
    let preparation_root: String?
    let application_processed_label: String?
    // Absent means on; an unreadable value turns automatic takeover off.
    let automatic_takeover: Bool?
    let takeover_executor: String?
    // Claude configuration for Opus scoring beside sol; absent means sol alone (2026-10-31).
    let match_second_opinion_claude_config: String?

    init(applications: String, career_workspace: String, preparation_root: String? = nil,
         application_processed_label: String? = nil, career_library_manifest: String? = nil,
         cover_letter_template: String? = nil, automatic_takeover: Bool? = nil,
         takeover_executor: String? = nil, match_second_opinion_claude_config: String? = nil) {
        self.applications = applications
        self.career_workspace = career_workspace
        self.career_library_manifest = career_library_manifest
        self.cover_letter_template = cover_letter_template
        self.preparation_root = preparation_root
        self.application_processed_label = application_processed_label
        self.automatic_takeover = automatic_takeover
        self.takeover_executor = takeover_executor
        self.match_second_opinion_claude_config = match_second_opinion_claude_config
    }

    enum CodingKeys: String, CodingKey { case applications, career_workspace, career_library_manifest, cover_letter_template, preparation_root, application_processed_label, automatic_takeover, takeover_executor, match_second_opinion_claude_config }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        applications = try values.decode(String.self, forKey: .applications)
        career_workspace = try values.decode(String.self, forKey: .career_workspace)
        career_library_manifest = try values.decodeIfPresent(String.self, forKey: .career_library_manifest)
        cover_letter_template = try values.decodeIfPresent(String.self, forKey: .cover_letter_template)
        // Invalid mail settings block only labeling/archiving, never workspace access.
        if !values.contains(.application_processed_label) || (try? values.decodeNil(forKey: .application_processed_label)) == true {
            application_processed_label = nil
        } else {
            application_processed_label = (try? values.decode(String.self, forKey: .application_processed_label)) ?? ""
        }
        automatic_takeover = values.contains(.automatic_takeover)
            ? (try? values.decode(Bool.self, forKey: .automatic_takeover)) ?? false : nil
        takeover_executor = try? values.decodeIfPresent(String.self, forKey: .takeover_executor)
        match_second_opinion_claude_config = try? values.decodeIfPresent(String.self, forKey: .match_second_opinion_claude_config)
        if decoder.userInfo[Self.preparationRootRequired] as? Bool == false {
            preparation_root = try? values.decode(String.self, forKey: .preparation_root)
        } else {
            preparation_root = values.contains(.preparation_root)
                ? try values.decode(String.self, forKey: .preparation_root) : nil
        }
    }

    func selectingFolders(applications: String, careerWorkspace: String) -> Workspace {
        Workspace(applications: applications, career_workspace: careerWorkspace, preparation_root: preparation_root,
                  application_processed_label: application_processed_label, career_library_manifest: career_library_manifest,
                  cover_letter_template: cover_letter_template, automatic_takeover: automatic_takeover,
                  takeover_executor: takeover_executor, match_second_opinion_claude_config: match_second_opinion_claude_config)
    }

    func selectingMailProcessingLabel(_ label: String) -> Workspace {
        Workspace(applications: applications, career_workspace: career_workspace, preparation_root: preparation_root,
                  application_processed_label: label.isEmpty ? nil : label, career_library_manifest: career_library_manifest,
                  cover_letter_template: cover_letter_template, automatic_takeover: automatic_takeover,
                  takeover_executor: takeover_executor, match_second_opinion_claude_config: match_second_opinion_claude_config)
    }

    func selectingAutomaticTakeover(_ enabled: Bool) -> Workspace {
        Workspace(applications: applications, career_workspace: career_workspace, preparation_root: preparation_root,
                  application_processed_label: application_processed_label, career_library_manifest: career_library_manifest,
                  cover_letter_template: cover_letter_template, automatic_takeover: enabled, takeover_executor: "codex", match_second_opinion_claude_config: match_second_opinion_claude_config)
    }
}

struct NativeLaunch {
    let syntheticRoot: URL?
    let configURL: URL
    private let mode: [String]
    private let workerRoot: URL?
    var canChangeWorkspace: Bool { syntheticRoot == nil }
    var canChangeMailProcessing: Bool { syntheticRoot == nil || mode == ["--synthetic-mail"] }
    var canChangeAutomaticTakeover: Bool { syntheticRoot == nil && mode == ["--single-job-flow"] }
    var nativeHostReceiptsEnabled: Bool { mode != ["--synthetic-mail"] }
    var backgroundPipelineEnabled: Bool {
        (syntheticRoot == nil && mode == ["--single-job-flow"]) || mode == ["--synthetic-mail"]
    }
    var flowTitle: String {
        (syntheticRoot == nil && mode.isEmpty) || mode == ["--synthetic-preparation"]
            ? "材料准备" : backgroundPipelineEnabled ? "自动申请" : "单岗位申请"
    }
    var windowTitle: String {
        if mode == ["--synthetic-preparation"] { return "TomorrowStar · 合成材料准备" }
        if mode == ["--synthetic-mail"] { return "TomorrowStar · 合成邮件验收" }
        return mode == ["--synthetic-browser"] ? "TomorrowStar · 合成浏览器验收" : "TomorrowStar · 职业工作台"
    }

    init(arguments: [String], home: URL) throws {
        let values = Array(arguments.dropFirst())
        let syntheticModes = ["--synthetic-flow", "--synthetic-preparation", "--synthetic-browser", "--synthetic-mail"]
        if values.contains(where: { value in
            syntheticModes.contains(where: { value == $0 || value.hasPrefix($0 + "=") })
        }) {
            guard values.count == 2, syntheticModes.contains(values[0]),
                  (values[1] as NSString).isAbsolutePath else {
                throw CocoaError(.fileReadInvalidFileName)
            }
            let root = URL(fileURLWithPath: values[1], isDirectory: true)
            guard root.path == values[1], !(values[1] as NSString).pathComponents.contains(".."),
                  !(values[1] as NSString).pathComponents.contains(".") else {
                throw CocoaError(.fileReadNoPermission)
            }
            try Self.requireUnlinked(root)
            syntheticRoot = root
            configURL = root.appendingPathComponent("portal.json")
            mode = [values[0]]
            workerRoot = nil
            return
        }
        syntheticRoot = nil
        let modes = values.filter { ["--single-job-flow", "--prepare-materials", "--automation-lab", "--codex-handoff"].contains($0) }
        guard modes.count <= 1, values.filter({ $0 == "--config" }).count <= 1,
              values.filter({ $0 == "--worker-root" }).count <= 1,
              !values.contains(where: { $0.hasPrefix("--worker-root=") }) else {
            throw CocoaError(.fileReadInvalidFileName)
        }
        mode = modes == ["--prepare-materials"] ? [] : modes.isEmpty ? ["--single-job-flow"] : modes
        if let index = values.firstIndex(of: "--worker-root") {
            guard modes == ["--single-job-flow"], values.count > index + 1 else {
                throw CocoaError(.fileReadInvalidFileName)
            }
            let path = values[index + 1]
            let root = URL(fileURLWithPath: path, isDirectory: true)
            guard (path as NSString).isAbsolutePath, path != "/", !path.contains("\0"),
                  root.path == path, !path.contains("//"),
                  !(path as NSString).pathComponents.contains(".."),
                  !(path as NSString).pathComponents.contains(".") else {
                throw CocoaError(.fileReadInvalidFileName)
            }
            try Self.requireUnlinked(root)
            var isDirectory: ObjCBool = false
            if FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory), !isDirectory.boolValue {
                throw CocoaError(.fileReadInvalidFileName)
            }
            workerRoot = root
        } else {
            workerRoot = nil
        }
        if let index = values.firstIndex(of: "--config") {
            guard values.count > index + 1, (values[index + 1] as NSString).isAbsolutePath else {
                throw CocoaError(.fileReadInvalidFileName)
            }
            configURL = URL(fileURLWithPath: values[index + 1])
        } else {
            configURL = home.appendingPathComponent("Library/Application Support/TomorrowStar/portal.json")
        }
    }

    func loadWorkspaceIfPresent() throws -> Workspace? {
        do { _ = try FileManager.default.attributesOfItem(atPath: configURL.path) }
        catch let error as CocoaError where error.code == .fileReadNoSuchFile { return nil }
        return try loadWorkspace()
    }

    func loadWorkspace() throws -> Workspace {
        if syntheticRoot != nil { try Self.requireUnlinked(configURL) }
        let decoder = JSONDecoder()
        decoder.userInfo[Workspace.preparationRootRequired] = mode.isEmpty
        let workspace = try decoder.decode(Workspace.self, from: Data(contentsOf: configURL))
        if mode.isEmpty, let path = workspace.preparation_root {
            let root = URL(fileURLWithPath: path, isDirectory: true)
            guard (path as NSString).isAbsolutePath, path != "/", !path.contains("\0"),
                  root.path == path, !(path as NSString).pathComponents.contains(".."),
                  !(path as NSString).pathComponents.contains(".") else {
                throw CocoaError(.fileReadInvalidFileName)
            }
            try Self.requireUnlinked(root)
            var isDirectory: ObjCBool = false
            if FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory), !isDirectory.boolValue {
                throw CocoaError(.fileReadInvalidFileName)
            }
        }
        if let root = syntheticRoot {
            guard workspace.applications == root.appendingPathComponent("applications").path,
                  workspace.career_workspace == root.appendingPathComponent("career").path else {
                throw CocoaError(.fileReadNoPermission)
            }
            if mode == ["--synthetic-mail"],
               workspace.preparation_root != root.appendingPathComponent("latex-base").path {
                throw CocoaError(.fileReadNoPermission)
            }
        }
        return workspace
    }

    func saveWorkspace(_ workspace: Workspace) throws {
        guard canChangeWorkspace else { throw CocoaError(.fileWriteNoPermission) }
        try writeWorkspace(workspace)
    }

    func saveMailProcessingLabel(_ label: String) throws {
        guard canChangeMailProcessing else { throw CocoaError(.fileWriteNoPermission) }
        let current = try loadWorkspace()
        try writeWorkspace(current.selectingMailProcessingLabel(label))
    }

    func saveAutomaticTakeover(_ enabled: Bool) throws {
        guard canChangeAutomaticTakeover else { throw CocoaError(.fileWriteNoPermission) }
        let current = try loadWorkspace()
        try writeWorkspace(current.selectingAutomaticTakeover(enabled))
    }

    private func writeWorkspace(_ workspace: Workspace) throws {
        let manager = FileManager.default
        if (try? configURL.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true {
            throw CocoaError(.fileWriteNoPermission)
        }
        try manager.createDirectory(at: configURL.deletingLastPathComponent(), withIntermediateDirectories: true,
                                    attributes: [.posixPermissions: 0o700])
        try JSONEncoder().encode(workspace).write(to: configURL, options: .atomic)
        try manager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: configURL.path)
    }

    private static func requireUnlinked(_ url: URL) throws {
        var ancestor = url
        while ancestor.path != "/" {
            guard (try? FileManager.default.destinationOfSymbolicLink(atPath: ancestor.path)) == nil else {
                throw CocoaError(.fileReadNoPermission)
            }
            ancestor.deleteLastPathComponent()
        }
    }

    func backendArguments(_ workspace: Workspace) -> [String] {
        if let root = syntheticRoot { return mode + [root.path] }
        var arguments = ["--applications", (workspace.applications as NSString).expandingTildeInPath,
                         "--career-workspace", (workspace.career_workspace as NSString).expandingTildeInPath]
        if let manifest = workspace.career_library_manifest {
            arguments += ["--career-library-manifest", (manifest as NSString).expandingTildeInPath]
        }
        if let template = workspace.cover_letter_template {
            arguments += ["--cover-letter-template", (template as NSString).expandingTildeInPath]
        }
        arguments += (mode.isEmpty ? workspace.preparation_root.map { ["--flow-root", $0] } ?? [] : []) + mode
        arguments += workerRoot.map { ["--worker-root", $0.path] } ?? []
        if let label = workspace.application_processed_label {
            // Invalid OS arguments must remain a local mail capability error.
            // Retain the original config value; send the existing invalid sentinel.
            let value = label.contains("\0") || label.utf8.count > 65_536 ? "" : label
            arguments.append("--application-processed-label=" + value)
        }
        // On by default; only Codex is an executor so far (MC-22, MC-23).
        if canChangeAutomaticTakeover && workspace.automatic_takeover != false {
            arguments += ["--automatic-takeover", "--takeover-executor=" + (workspace.takeover_executor ?? "codex")]
        }
        if let claude = workspace.match_second_opinion_claude_config {
            arguments += ["--second-opinion-claude-config", (claude as NSString).expandingTildeInPath]
        }
        return arguments
    }

    func canOpenExternal(_ url: URL) -> Bool {
        if syntheticRoot != nil {
            return ["http", "https"].contains(url.scheme ?? "") && ["127.0.0.1", "::1", "localhost"].contains(url.host ?? "")
        }
        return ["http", "https", "mailto"].contains(url.scheme ?? "")
    }
}

struct BackendStartupFailure {
    static func reason(from result: [String: Any]?) -> String {
        let allowed = ["codex-unavailable", "workspace-unavailable", "worker-mode-required"]
        if result?["status"] as? String == "error", let code = result?["code"] as? String,
           allowed.contains(code) { return code }
        return "invalid_ready_response"
    }

    static func canChooseFolders(for reason: String) -> Bool {
        reason == "workspace-unavailable"
    }

    static func message(for reason: String) -> String {
        switch reason {
        case "workspace-unavailable":
            return "请检查所选数据目录是否存在、可以访问。职业证据目录必须是独立的 Git 仓库。"
        case "codex-unavailable":
            return "模型服务尚不可用。请检查所选 Codex 工具路径；已有资料已保留。"
        case "worker-mode-required":
            return "当前启动模式与执行器配置不一致。请修正启动参数；已有任务已保留。"
        default:
            return "工作台服务未能启动或已中断。请重新启动工作台；已有资料和任务已保留。"
        }
    }
}

struct ResumeReviewResponse {
    static func editorURL(from data: Data) -> URL? {
        guard data.count <= 8192,
              let response = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              response["status"] as? String == "ready",
              let raw = response["url"] as? String,
              let parts = URLComponents(string: raw),
              parts.scheme == "http",
              ["127.0.0.1", "localhost", "::1", "[::1]"].contains(parts.host ?? ""),
              let port = parts.port, (1...65535).contains(port),
              parts.user == nil, parts.password == nil,
              parts.path == "/" || parts.path.isEmpty,
              parts.query == nil, parts.fragment == nil
        else { return nil }
        return parts.url
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate,
    WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, WKScriptMessageHandler {
    private var window: NSWindow!
    private var web: WKWebView!
    private var message: NSTextField!
    private var backend: Process?
    private var control: Pipe?
    private var address: URL?
    private var quitting = false
    private var checkingChanges = false
    private var nativeLaunchNonce: String?
    private var nativeReceiptSequence = 0
    private var pipelineTimer: Timer?
    private var pipelineRequest: PipelineStatusRequest?
    private var pipelineNotices = Set<String>()
    private var workspaceViews: [(String, String)] {
        [(launch?.flowTitle ?? "材料准备", "flow"), ("今日工作", "overview"), ("岗位与进度", "applications"),
         ("申请交接", "handoff"), ("职业证据", "evidence"),
         ("项目访谈", "interview"), ("公开展示", "website")]
    }
    private var downloads: [ObjectIdentifier: (temporary: URL, destination: URL)] = [:]
    private let launch = try? NativeLaunch(arguments: CommandLine.arguments,
                                         home: FileManager.default.homeDirectoryForCurrentUser)
    private lazy var exitLog = NativeExitLog(parent:
        launch?.syntheticRoot?.appendingPathComponent("runtime/diagnostics") ??
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/TomorrowStar/diagnostics"))

    func applicationDidFinishLaunching(_ notification: Notification) {
        exitLog?.record("native_started")
        NSApp.setActivationPolicy(.regular)
        installMenus()
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 850),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = launch?.windowTitle ?? "TomorrowStar · 职业工作台"
        window.minSize = NSSize(width: 850, height: 600)
        window.center()
        window.setFrameAutosaveName("TomorrowStarWorkspace")
        window.delegate = self
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.userContentController.add(self, name: "tomorrowstarNative")
        web = WKWebView(frame: .zero, configuration: configuration)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = true
        web.translatesAutoresizingMaskIntoConstraints = false
        message = NSTextField(wrappingLabelWithString: "正在启动你的职业工作台…")
        message.font = .systemFont(ofSize: 18)
        message.alignment = .center
        message.translatesAutoresizingMaskIntoConstraints = false
        let content = window.contentView!
        content.addSubview(web)
        content.addSubview(message)
        NSLayoutConstraint.activate([
            web.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            web.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            web.topAnchor.constraint(equalTo: content.topAnchor),
            web.bottomAnchor.constraint(equalTo: content.bottomAnchor),
            message.centerXAnchor.constraint(equalTo: content.centerXAnchor),
            message.centerYAnchor.constraint(equalTo: content.centerYAnchor),
            message.widthAnchor.constraint(lessThanOrEqualToConstant: 700)
        ])
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        guard let launch = launch else { failedStart(); return }
        do {
            if let workspace = try launch.loadWorkspaceIfPresent() { start(workspace) }
            else if launch.canChangeWorkspace { chooseFolders() }
            else { failedStart() }
        } catch {
            if launch.canChangeWorkspace { invalidConfiguration() }
            else { failedStart() }
        }
    }

    private func installMenus() {
        let bar = NSMenu()
        let appMenu = NSMenu(title: "TomorrowStar")
        appMenu.autoenablesItems = false
        appMenu.addItem(withTitle: "关于 TomorrowStar", action: #selector(about), keyEquivalent: "")
        appMenu.addItem(.separator())
        let folders = appMenu.addItem(withTitle: "数据文件夹…", action: #selector(changeFolders), keyEquivalent: ",")
        folders.isEnabled = launch?.canChangeWorkspace == true
        let mail = appMenu.addItem(withTitle: "邮件处理…", action: #selector(changeMailProcessing), keyEquivalent: "")
        mail.isEnabled = launch?.canChangeMailProcessing == true
        let takeover = appMenu.addItem(withTitle: "自动接管…", action: #selector(changeAutomaticTakeover), keyEquivalent: "")
        takeover.isEnabled = launch?.canChangeAutomaticTakeover == true
        appMenu.addItem(.separator())
        let permissionCheck = appMenu.addItem(withTitle: "检查当前宿主权限",
            action: #selector(checkCurrentHostPermissions), keyEquivalent: "")
        permissionCheck.target = self
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "隐藏 TomorrowStar", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "退出 TomorrowStar", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let edit = NSMenu(title: "编辑")
        edit.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
        let redo = edit.addItem(withTitle: "重做", action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        edit.addItem(.separator())
        edit.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "复制", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        let view = NSMenu(title: "显示")
        view.addItem(withTitle: "刷新工作台", action: #selector(refresh), keyEquivalent: "r")
        for (index, entry) in workspaceViews.enumerated() {
            let item = view.addItem(withTitle: entry.0, action: #selector(showView(_:)), keyEquivalent: String(index + 1))
            item.tag = index
        }
        view.addItem(.separator())
        let resumeReview = view.addItem(withTitle: "简历审阅（Prism）", action: #selector(openResumeReview), keyEquivalent: "8")
        resumeReview.isEnabled = launch?.canChangeWorkspace == true
        let windowMenu = NSMenu(title: "窗口")
        windowMenu.addItem(withTitle: "最小化", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "关闭", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        for menu in [appMenu, edit, view, windowMenu] {
            let item = NSMenuItem()
            item.submenu = menu
            bar.addItem(item)
        }
        NSApp.mainMenu = bar
        NSApp.windowsMenu = windowMenu
    }

    @objc private func about() {
        NSApp.orderFrontStandardAboutPanel(options: [
            .applicationName: "TomorrowStar",
            .applicationVersion: "0.1.0",
            .credits: NSAttributedString(string: "职业工作台\n岗位与进度 · 申请交接 · 职业证据 · 项目访谈\n本机运行，连接你选择的数据文件夹。")
        ])
    }

    @objc private func changeFolders() {
        guard window.attachedSheet == nil else { return }
        withSavedChanges { self.chooseFolders() }
    }
    @objc private func changeMailProcessing() {
        guard let launch = launch, launch.canChangeMailProcessing, let address = address,
              !checkingChanges, window.attachedSheet == nil else { return }
        let workspace: Workspace
        do {
            guard let saved = try launch.loadWorkspaceIfPresent() else { return }
            workspace = saved
        } catch { invalidConfiguration(); return }
        let alert = NSAlert()
        alert.messageText = "邮件处理"
        alert.informativeText = "可选：填写处理标签的完整原值。留空时只收录邮件，不标记或归档。保存后重新打开工作台生效。"
        let field = NSTextField(string: workspace.application_processed_label ?? "")
        field.frame = NSRect(x: 0, y: 0, width: 340, height: 24)
        field.placeholderString = "可选处理标签"
        alert.accessoryView = field
        alert.addButton(withTitle: "保存")
        alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: window) { response in
            guard response == .alertFirstButtonReturn, self.address == address,
                  !self.checkingChanges else { return }
            do {
                try launch.saveMailProcessingLabel(field.stringValue)
            } catch {
                self.settingsSaveFailed()
            }
        }
    }
    @objc private func changeAutomaticTakeover() {
        guard let launch = launch, launch.canChangeAutomaticTakeover, let address = address,
              !checkingChanges, window.attachedSheet == nil else { return }
        let workspace: Workspace
        do {
            guard let saved = try launch.loadWorkspaceIfPresent() else { return }
            workspace = saved
        } catch { invalidConfiguration(); return }
        let alert = NSAlert()
        alert.messageText = "自动接管"
        alert.informativeText = "脚本处理不了当前岗位时，交给执行者在原申请页接续（执行者：Codex）。最终 Submit 仍由你手动。关闭后这类岗位会停下等你。保存后重新打开工作台生效。"
        let toggle = NSButton(checkboxWithTitle: "开启自动接管", target: nil, action: nil)
        toggle.state = workspace.automatic_takeover == false ? .off : .on
        alert.accessoryView = toggle
        alert.addButton(withTitle: "保存")
        alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: window) { response in
            guard response == .alertFirstButtonReturn, self.address == address,
                  !self.checkingChanges else { return }
            do {
                try launch.saveAutomaticTakeover(toggle.state == .on)
            } catch {
                self.settingsSaveFailed()
            }
        }
    }
    @objc private func openResumeReview() {
        guard launch?.canChangeWorkspace == true, address != nil else { return }
        web.evaluateJavaScript("window.location.hash = '#resume-review'")
    }

    @objc private func refresh() { withSavedChanges { self.web.reload() } }
    @objc private func checkCurrentHostPermissions() { sendNativeHostReceipt(kind: "check") }

    func userContentController(_ userContentController: WKUserContentController,
                               didReceive scriptMessage: WKScriptMessage) {
        let securityOrigin = scriptMessage.frameInfo.securityOrigin
        var origin = URLComponents()
        origin.scheme = securityOrigin.protocol
        origin.host = securityOrigin.host
        origin.port = securityOrigin.port
        guard scriptMessage.name == "tomorrowstarNative",
              NativeHostCheckRequest.allows(body: scriptMessage.body,
                mainFrame: scriptMessage.frameInfo.isMainFrame,
                sameWebView: scriptMessage.webView === web,
                origin: origin, currentURL: web.url, backendURL: address) else { return }
        checkCurrentHostPermissions()
    }

    private func sendNativeHostReceipt(kind: String) {
        guard launch?.nativeHostReceiptsEnabled == true else { return }
        guard !quitting, let process = backend, process.isRunning else {
            exitLog?.record("native_receipt_unavailable", reason: "backend_unavailable")
            return
        }
        guard let nonce = nativeLaunchNonce, let input = control else {
            exitLog?.record("native_receipt_unavailable", reason: "control_unavailable")
            return
        }
        guard kind == "sample" || address != nil else {
            exitLog?.record("native_receipt_unavailable", reason: "portal_unavailable")
            return
        }
        do {
            let snapshot = try nativeHostSnapshot()
            nativeReceiptSequence += 1
            let frame = try NativeHostReceipt.frame(snapshot: snapshot, nonce: nonce,
                backendPID: process.processIdentifier, sequence: nativeReceiptSequence, kind: kind)
            try input.fileHandleForWriting.write(contentsOf: frame)
            exitLog?.record("native_receipt_sent", reason: kind, childPID: process.processIdentifier)
        } catch { exitLog?.record("native_permission_sample_failed") }
    }

    private func startPipelineSignals(process: Process, address: URL) {
        guard launch?.backgroundPipelineEnabled == true,
              let endpoint = PipelineStatus.endpoint(address) else { return }
        pipelineTimer?.invalidate()
        pipelineTimer = Timer.scheduledTimer(withTimeInterval: 10, repeats: true) { [weak self, weak process] _ in
            guard let self = self, let process = process else { return }
            self.pollPipeline(process: process, address: address, endpoint: endpoint)
        }
        pollPipeline(process: process, address: address, endpoint: endpoint)
    }

    private func pollPipeline(process: Process, address: URL, endpoint: URL) {
        guard !quitting, backend === process, process.isRunning,
              self.address == address, pipelineRequest == nil else { return }
        let request = PipelineStatusRequest(endpoint: endpoint) { [weak self, weak process] status in
            guard let self = self, let process = process,
                  !self.quitting, self.backend === process, process.isRunning,
                  self.address == address else { return }
            self.pipelineRequest = nil
            guard let status = status else { return }
            if status.running { self.sendNativeHostReceipt(kind: "check") }
            if let id = status.notificationID {
                NSApp.dockTile.badgeLabel = "1"
                if self.pipelineNotices.insert(id).inserted {
                    NSApp.requestUserAttention(.informationalRequest)
                }
            } else {
                NSApp.dockTile.badgeLabel = nil
            }
        }
        pipelineRequest = request
        request.start()
    }
    @objc private func showView(_ item: NSMenuItem) {
        guard let address = address else { return }
        var parts = URLComponents(url: address, resolvingAgainstBaseURL: false)!
        guard workspaceViews.indices.contains(item.tag) else { return }
        parts.fragment = workspaceViews[item.tag].1
        web.evaluateJavaScript("window.location.hash = '#\(parts.fragment!)'")
    }

    private func withSavedChanges(cancelled: @escaping () -> Void = {}, _ action: @escaping () -> Void) {
        guard !checkingChanges else { cancelled(); return }
        checkingChanges = true
        web.evaluateJavaScript("document.querySelector('#application-dialog')?.open === true && typeof isDirty === 'function' && !!isDirty()") { result, _ in
            self.checkingChanges = false
            if (result as? Bool) == true {
                let alert = NSAlert()
                alert.messageText = "还有未保存的投递修改"
                alert.informativeText = "继续后将放弃这些输入。你可以返回工作台保存。"
                alert.addButton(withTitle: "返回保存")
                alert.addButton(withTitle: "放弃并继续")
                alert.beginSheetModal(for: self.window) { response in
                    if response == .alertSecondButtonReturn { action() } else { cancelled() }
                }
            } else { action() }
        }
    }

    private func chooseFolders() {
        guard let launch = launch, launch.canChangeWorkspace else { return }
        let previous: Workspace?
        do {
            previous = try launch.loadWorkspaceIfPresent()
        } catch { invalidConfiguration(); return }
        let first = NSOpenPanel()
        first.title = "选择投递记录文件夹"
        first.message = "选择已有的求职投递笔记目录。记录继续保存在这个目录中。"
        first.prompt = "下一步"
        first.canChooseDirectories = true
        first.canChooseFiles = false
        first.canCreateDirectories = true
        first.beginSheetModal(for: window) { response in
            guard response == .OK, let applications = first.url else {
                self.message.stringValue = self.address == nil ? "请选择数据文件夹以打开工作台。菜单：TomorrowStar → 数据文件夹…" : ""
                return
            }
            let second = NSOpenPanel()
            second.title = "选择职业证据文件夹"
            second.message = "选择独立的私人 career-data Git 仓库。不要选择系统源码或 App 内部目录。"
            second.prompt = "打开工作台"
            second.canChooseDirectories = true
            second.canChooseFiles = false
            second.beginSheetModal(for: self.window) { response in
                guard response == .OK, let career = second.url else { return }
                self.start(previous?.selectingFolders(applications: applications.path, careerWorkspace: career.path)
                    ?? Workspace(applications: applications.path, career_workspace: career.path))
            }
        }
    }

    private func start(_ workspace: Workspace) {
        guard let launch = launch else { failedStart(); return }
        stopBackend(reason: "workspace_start")
        address = nil
        web.isHidden = true
        message.isHidden = false
        message.stringValue = "正在连接投递记录与职业证据…"
        let resources = Bundle.main.resourceURL!
        let process = Process()
        let output = Pipe()
        let input = Pipe()
        let nonce = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        nativeLaunchNonce = nonce
        nativeReceiptSequence = 0
        process.executableURL = resources.appendingPathComponent("python/bin/python3.13")
        process.arguments = ["-I", "-B", "-u", resources.appendingPathComponent("server.py").path] + launch.backendArguments(workspace)
        process.currentDirectoryURL = resources
        process.environment = ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8",
                               "HOME": FileManager.default.homeDirectoryForCurrentUser.path,
                               "TMPDIR": NSTemporaryDirectory()]
        process.environment?["TOMORROWSTAR_NATIVE_LAUNCH_NONCE"] = nonce
        if let root = launch.syntheticRoot {
            process.environment?["HOME"] = root.appendingPathComponent("home").path
            process.environment?["TMPDIR"] = root.appendingPathComponent("tmp").path
        } else {
            for name in ["TOMORROWSTAR_CODEX_EXECUTABLE", "TOMORROWSTAR_MATCH_CONTEXT_BYTES",
                         "TOMORROWSTAR_MATERIAL_CONTEXT_BYTES"] {
                if let value = ProcessInfo.processInfo.environment[name] {
                    process.environment?[name] = value
                }
            }
        }
        process.standardInput = input
        process.standardOutput = output
        process.standardError = FileHandle.nullDevice
        let logger = exitLog
        process.terminationHandler = { ended in
            logger?.record("backend_exited", childPID: ended.processIdentifier,
                exitCode: ended.terminationReason == .exit ? ended.terminationStatus : nil,
                signal: ended.terminationReason == .uncaughtSignal ? ended.terminationStatus : nil)
            DispatchQueue.main.async {
                if self.backend === ended && !self.quitting {
                    self.backend = nil
                    self.failedStart()
                }
            }
        }
        backend = process
        control = input
        do {
            try process.run()
            logger?.record("backend_started", childPID: process.processIdentifier)
            sendNativeHostReceipt(kind: "sample")
        } catch {
            logger?.record("backend_launch_failed")
            backend = nil
            nativeLaunchNonce = nil
            failedStart()
            return
        }
        DispatchQueue.global(qos: .userInitiated).async {
            var line = Data()
            while line.count < 4096 {
                let bytes = output.fileHandleForReading.availableData
                if bytes.isEmpty { break }
                line.append(bytes)
                if line.contains(10) { break }
            }
            let result = (try? JSONSerialization.jsonObject(with: line)) as? [String: Any]
            let failureReason = BackendStartupFailure.reason(from: result)
            if result?["status"] as? String == "error" {
                logger?.record("backend_readiness_failed", reason: failureReason,
                    childPID: process.processIdentifier)
            }
            DispatchQueue.main.async {
                guard self.backend === process, !self.quitting else { return }
                guard result?["status"] as? String == "ready", let raw = result?["url"] as? String,
                      let url = URL(string: raw), url.scheme == "http", url.host == "127.0.0.1",
                      url.port != nil else {
                    if result?["status"] as? String != "error" {
                        logger?.record("backend_readiness_failed", reason: failureReason,
                            childPID: process.processIdentifier)
                    }
                    self.stopBackend(reason: failureReason)
                    self.failedStart(reason: failureReason)
                    return
                }
                self.address = url
                self.startPipelineSignals(process: process, address: url)
                self.save(workspace)
                self.message.isHidden = true
                self.web.isHidden = false
                self.web.load(URLRequest(url: url))
                // Content-free diagnostics for launch and shutdown acceptance.
                print("TomorrowStar ready: \(url.absoluteString)")
                fflush(stdout)
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 20) {
            if self.backend === process && self.address == nil {
                self.stopBackend(reason: "startup_deadline")
                self.failedStart()
            }
        }
    }

    private func save(_ workspace: Workspace) {
        guard let launch = launch, launch.canChangeWorkspace else { return }
        do {
            try launch.saveWorkspace(workspace)
        } catch {
            settingsSaveFailed()
        }
    }

    private func settingsSaveFailed() {
        let alert = NSAlert()
        alert.messageText = "工作台设置未能保存"
        alert.informativeText = "本次可以继续使用。请稍后重新保存设置。"
        alert.beginSheetModal(for: window)
    }

    private func invalidConfiguration() {
        message.isHidden = false
        message.stringValue = "文件夹配置无效。请修正配置文件后重新启动；现有材料准备记录未更改。"
    }

    private func failedStart(reason: String = "backend-unavailable") {
        address = nil
        web.isHidden = true
        message.isHidden = false
        if launch?.canChangeWorkspace != true {
            message.stringValue = "合成验收未能启动。请检查指定目录及合成配置；此模式不会使用常规数据文件夹。"
            return
        }
        message.stringValue = BackendStartupFailure.message(for: reason)
        let alert = NSAlert()
        alert.messageText = "未能启动工作台"
        alert.informativeText = BackendStartupFailure.message(for: reason)
        if BackendStartupFailure.canChooseFolders(for: reason) {
            alert.addButton(withTitle: "选择文件夹")
        }
        alert.addButton(withTitle: "稍后")
        alert.beginSheetModal(for: window) { response in
            if response == .alertFirstButtonReturn && BackendStartupFailure.canChooseFolders(for: reason) {
                self.chooseFolders()
            }
        }
    }

    private func stopBackend(reason: String = "backend_stop_requested") {
        pipelineTimer?.invalidate()
        pipelineTimer = nil
        let request = pipelineRequest
        pipelineRequest = nil
        request?.cancel()
        NSApp.dockTile.badgeLabel = nil
        guard let process = backend else { return }
        backend = nil
        nativeLaunchNonce = nil
        nativeReceiptSequence = 0
        let logger = exitLog
        logger?.record("parent_pipe_close_requested", reason: reason, childPID: process.processIdentifier)
        try? control?.fileHandleForWriting.close()
        control = nil
        DispatchQueue.global().asyncAfter(deadline: .now() + 2) {
            if process.isRunning {
                logger?.record("backend_terminate_requested", childPID: process.processIdentifier, signal: SIGTERM)
                process.terminate()
            }
        }
        DispatchQueue.global().asyncAfter(deadline: .now() + 4) {
            if process.isRunning {
                logger?.record("backend_kill_requested", childPID: process.processIdentifier, signal: SIGKILL)
                kill(process.processIdentifier, SIGKILL)
            }
        }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !quitting else { return .terminateNow }
        exitLog?.record("native_quit_requested")
        withSavedChanges(cancelled: {
            self.exitLog?.record("native_quit_cancelled")
            sender.reply(toApplicationShouldTerminate: false)
        }) {
            self.quitting = true
            self.exitLog?.record("native_quit_approved")
            self.stopBackend(reason: "native_quit_approved")
            sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    func applicationWillTerminate(_ notification: Notification) {
        exitLog?.record("native_will_terminate")
        stopBackend(reason: "native_will_terminate")
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        exitLog?.record("native_window_close_requested")
        NSApp.terminate(nil)
        return false
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)
        return true
    }

    private func local(_ url: URL) -> Bool {
        guard let address = address else { return false }
        return url.scheme == address.scheme && url.host == address.host && url.port == address.port
    }

    private func openExternal(_ url: URL) {
        if launch?.canOpenExternal(url) == true { NSWorkspace.shared.open(url) }
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { decisionHandler(.cancel); return }
        if local(url) {
            decisionHandler(action.shouldPerformDownload ? .download : .allow)
        } else {
            decisionHandler(.cancel)
            if action.navigationType == .linkActivated { openExternal(url) }
        }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url {
            if local(url) { web.load(URLRequest(url: url)) } else { openExternal(url) }
        }
        return nil
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = parameters.allowsDirectories
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { response in
            completionHandler(response == .OK ? panel.urls : nil)
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage text: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = text
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        guard let url = response.url, local(url), url.path == "/api/export.csv" else {
            completionHandler(nil)
            return
        }
        let panel = NSSavePanel()
        panel.title = "导出投递记录"
        panel.nameFieldStringValue = "TomorrowStar-applications.csv"
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let destination = panel.url else { completionHandler(nil); return }
            let temporary = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent(UUID().uuidString + ".csv")
            self.downloads[ObjectIdentifier(download)] = (temporary, destination)
            completionHandler(temporary)
        }
    }

    func downloadDidFinish(_ download: WKDownload) {
        guard let paths = downloads.removeValue(forKey: ObjectIdentifier(download)) else { return }
        defer { try? FileManager.default.removeItem(at: paths.temporary) }
        do { try Data(contentsOf: paths.temporary).write(to: paths.destination, options: .atomic) }
        catch { showExportError() }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        if let paths = downloads.removeValue(forKey: ObjectIdentifier(download)) {
            try? FileManager.default.removeItem(at: paths.temporary)
            showExportError()
        }
    }

    private func showExportError() {
        let alert = NSAlert()
        alert.messageText = "CSV 未能保存"
        alert.informativeText = "请检查目标文件夹的写入权限，再次导出。"
        alert.beginSheetModal(for: window)
    }
}

let application = NSApplication.shared
let backgroundCheck = BackgroundCheckLaunch.requested(in: CommandLine.arguments)
if backgroundCheck { application.setActivationPolicy(.prohibited) }
let delegate: NSApplicationDelegate = backgroundCheck
    ? BackgroundCheckDelegate() : AppDelegate()
application.delegate = delegate
application.run()
