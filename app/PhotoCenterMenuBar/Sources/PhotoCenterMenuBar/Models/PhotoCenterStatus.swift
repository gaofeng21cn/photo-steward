import Foundation

enum PhotoCenterHealth: Equatable {
    case healthy
    case attention
    case error
    case unknown

    var displayName: String {
        switch self {
        case .healthy:
            return "健康"
        case .attention:
            return "待审/需关注"
        case .error:
            return "异常"
        case .unknown:
            return "未知"
        }
    }
}

enum PhotoCenterExecution: Equatable {
    case idle
    case refreshing
    case creatingPlan
    case applying

    var displayName: String {
        switch self {
        case .idle:
            return "空闲"
        case .refreshing:
            return "正在读取状态"
        case .creatingPlan:
            return "正在生成计划"
        case .applying:
            return "正在执行已批准计划"
        }
    }
}

struct PhotoCenterJobSummary: Decodable, Equatable {
    let mirrorCount: Int?
    let mirrorBytes: Int?
    let deleteCount: Int?
    let deleteBytes: Int?
    let unresolvedCount: Int?

    enum CodingKeys: String, CodingKey {
        case mirrorCount = "mirror_count"
        case mirrorBytes = "mirror_bytes"
        case deleteCount = "delete_count"
        case deleteBytes = "delete_bytes"
        case unresolvedCount = "unresolved_count"
    }
}

struct PhotoCenterJobStatus: Decodable, Equatable {
    let status: String?
    let finishedAt: String?
    let lastSuccessAt: String?
    let lastAttemptAt: String?
    let pendingPlanDir: String?
    let message: String?
    let consecutiveFailures: Int?
    let summary: PhotoCenterJobSummary?

    enum CodingKeys: String, CodingKey {
        case status
        case finishedAt = "finished_at"
        case lastSuccessAt = "last_success_at"
        case lastAttemptAt = "last_attempt_at"
        case pendingPlanDir = "pending_plan_dir"
        case message
        case consecutiveFailures = "consecutive_failures"
        case summary
    }

    var finishedDate: Date? {
        Self.parseISO8601Date(finishedAt)
    }

    var lastSuccessDate: Date? {
        Self.parseISO8601Date(lastSuccessAt)
    }

    var lastAttemptDate: Date? {
        Self.parseISO8601Date(lastAttemptAt)
    }

    var finishedAtDisplay: String {
        Self.displayDate(finishedDate)
    }

    var lastSuccessAtDisplay: String {
        Self.displayDate(lastSuccessDate)
    }

    var lastAttemptAtDisplay: String {
        Self.displayDate(lastAttemptDate)
    }

    var statusDisplay: String {
        switch status?.lowercased() {
        case "success":
            return "成功"
        case "failed":
            return "失败"
        case "partial":
            return "部分完成"
        case "blocked":
            return "已阻塞"
        case "pending":
            return "待审"
        case "running":
            return "执行中"
        default:
            return "未知"
        }
    }

    private static func parseISO8601Date(_ value: String?) -> Date? {
        guard let value, !value.isEmpty else { return nil }

        let fractionalFormatter = ISO8601DateFormatter()
        fractionalFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractionalFormatter.date(from: value) {
            return date
        }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: value)
    }

    private static func displayDate(_ date: Date?) -> String {
        guard let date else { return "暂无" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}

struct PhotoCenterStatusBundle: Decodable, Equatable {
    let jobs: [String: PhotoCenterJobStatus]

    init(jobs: [String: PhotoCenterJobStatus] = [:]) {
        self.jobs = jobs
    }
}

struct PhotoCenterProgressEvent: Decodable {
    let stage: String?
    let assetCount: Int?
    let resourceCountAll: Int?
    let resourceCountSelected: Int?
    let resolvedCount: Int?
    let unresolvedCount: Int?
    let scanned: Int?
    let nasFileCount: Int?

    enum CodingKeys: String, CodingKey {
        case stage
        case assetCount = "asset_count"
        case resourceCountAll = "resource_count_all"
        case resourceCountSelected = "resource_count_selected"
        case resolvedCount = "resolved_count"
        case unresolvedCount = "unresolved_count"
        case scanned
        case nasFileCount = "nas_file_count"
    }

    var progressDetail: String? {
        switch stage {
        case "plan_start":
            return "正在准备同步计划"
        case "load_asset_index":
            return "正在读取照片索引"
        case "asset_index_unavailable":
            return "照片索引不可用，正在继续读取资源"
        case "list_photos_resources":
            return "正在读取照片资源"
        case "photos_resources_listed":
            return count.map { "已读取照片资源：\(Self.displayCount($0))" }
        case "icloud_resource_progress":
            return resolvedCount.map { "正在读取照片资源：\(Self.displayCount($0))" }
        case "icloud_resources_materialized":
            return resolvedCount.map { resolvedCount in
                let unresolved = unresolvedCount ?? 0
                return "照片资源已读取：\(Self.displayCount(resolvedCount))，未解析：\(Self.displayCount(unresolved))"
            }
        case "scan_nas":
            return "正在扫描 NAS 文件"
        case "scan_nas_progress":
            return scanned.map { "正在扫描 NAS 文件：\(Self.displayCount($0))" }
        case "nas_scanned":
            return nasFileCount.map { "已扫描 NAS 文件：\(Self.displayCount($0))" }
        case "plan_done":
            return "正在整理同步差额"
        case "apply_start":
            return "正在执行已批准计划"
        case "apply_done":
            return "Apply 已完成，正在刷新状态"
        default:
            return nil
        }
    }

    private var count: Int? {
        resourceCountSelected ?? resourceCountAll ?? assetCount
    }

    private static func displayCount(_ count: Int) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.numberStyle = .decimal
        return formatter.string(from: NSNumber(value: count)) ?? String(count)
    }
}
