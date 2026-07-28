import Foundation

enum PhotoCenterPlanAction: String, Decodable {
    case mirror
    case quarantine

    var title: String {
        switch self {
        case .mirror:
            return "镜像到 NAS"
        case .quarantine:
            return "移入隔离池"
        }
    }

    var systemImage: String {
        switch self {
        case .mirror:
            return "arrow.down.to.line"
        case .quarantine:
            return "archivebox"
        }
    }
}

struct PhotoCenterPlanItem: Identifiable, Decodable, Equatable {
    let id: String
    let action: PhotoCenterPlanAction
    let actionLabel: String
    let relativePath: String
    let originalFilename: String
    let bytes: Int
    let sha256: String
    let sourceKind: String?
    let sourcePath: String?
    let assetLocalIdentifier: String?
    let resourceIndex: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case action
        case actionLabel = "action_label"
        case relativePath = "relative_path"
        case originalFilename = "original_filename"
        case bytes
        case sha256
        case sourceKind = "source_kind"
        case sourcePath = "source_path"
        case assetLocalIdentifier = "asset_local_identifier"
        case resourceIndex = "resource_index"
    }

    var shortHash: String {
        String(sha256.prefix(12))
    }
}

struct PhotoCenterPlanDetails: Decodable, Equatable {
    let planID: String
    let items: [PhotoCenterPlanItem]

    enum CodingKeys: String, CodingKey {
        case planID = "plan_id"
        case items
    }

    var mirrorItems: [PhotoCenterPlanItem] {
        items.filter { $0.action == .mirror }
    }

    var quarantineItems: [PhotoCenterPlanItem] {
        items.filter { $0.action == .quarantine }
    }
}
