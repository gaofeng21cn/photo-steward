import Foundation
import Photos

struct ResourcePayload: Encodable {
    let asset_local_identifier: String
    let asset_uuid: String
    let media_type: Int
    let media_subtypes: UInt64
    let creation_date: String?
    let modification_date: String?
    let resource_index: Int
    let resource_type: Int
    let original_filename: String
    let uniform_type_identifier: String?
    let file_size: Int64?
}

struct ExportPayload: Encodable {
    let output_path: String
}

struct BatchRequest: Decodable {
    let request_id: String
    let asset_local_identifier: String
    let resource_index: Int
    let output_path: String
}

struct BatchResponse: Encodable {
    let request_id: String
    let output_path: String?
    let error: String?
}

func requestAuthorization() {
    let semaphore = DispatchSemaphore(value: 0)
    var status: PHAuthorizationStatus = .notDetermined
    PHPhotoLibrary.requestAuthorization(for: .readWrite) { newStatus in
        status = newStatus
        semaphore.signal()
    }
    _ = semaphore.wait(timeout: .now() + 60)
    guard status == .authorized || status == .limited else {
        fputs("photos authorization unavailable: \(status.rawValue)\n", stderr)
        exit(1)
    }
}

func isoString(_ date: Date?) -> String? {
    guard let date else { return nil }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: date)
}

func fileSize(of resource: PHAssetResource) -> Int64? {
    if let number = resource.value(forKey: "fileSize") as? NSNumber {
        return number.int64Value
    }
    if let value = resource.value(forKey: "fileSize") as? NSString {
        return Int64(value as String)
    }
    return nil
}

func encodeLine<T: Encodable>(_ payload: T) {
    let encoder = JSONEncoder()
    guard let data = try? encoder.encode(payload),
          let line = String(data: data, encoding: .utf8) else {
        fputs("json encode failed\n", stderr)
        exit(1)
    }
    print(line)
}

func fetchAsset(localIdentifier: String) -> PHAsset {
    let result = PHAsset.fetchAssets(withLocalIdentifiers: [localIdentifier], options: nil)
    guard let asset = result.firstObject else {
        fputs("asset not found: \(localIdentifier)\n", stderr)
        exit(1)
    }
    return asset
}

func listResources() {
    let assets = PHAsset.fetchAssets(with: nil)
    assets.enumerateObjects { asset, _, _ in
        let assetUUID = asset.localIdentifier.split(separator: "/").first.map(String.init) ?? asset.localIdentifier
        let resources = PHAssetResource.assetResources(for: asset)
        for (index, resource) in resources.enumerated() {
            let payload = ResourcePayload(
                asset_local_identifier: asset.localIdentifier,
                asset_uuid: assetUUID,
                media_type: asset.mediaType.rawValue,
                media_subtypes: UInt64(asset.mediaSubtypes.rawValue),
                creation_date: isoString(asset.creationDate),
                modification_date: isoString(asset.modificationDate),
                resource_index: index,
                resource_type: resource.type.rawValue,
                original_filename: resource.originalFilename,
                uniform_type_identifier: resource.uniformTypeIdentifier,
                file_size: fileSize(of: resource)
            )
            encodeLine(payload)
        }
    }
}

func exportResource(localIdentifier: String, resourceIndex: Int, outputPath: String) {
    let asset = fetchAsset(localIdentifier: localIdentifier)
    let resources = PHAssetResource.assetResources(for: asset)
    guard resourceIndex >= 0 && resourceIndex < resources.count else {
        fputs("resource index out of range\n", stderr)
        exit(1)
    }
    let resource = resources[resourceIndex]
    let outputURL = URL(fileURLWithPath: outputPath)
    try? FileManager.default.removeItem(at: outputURL)
    try? FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    let options = PHAssetResourceRequestOptions()
    options.isNetworkAccessAllowed = true

    let semaphore = DispatchSemaphore(value: 0)
    var exportError: Error?
    PHAssetResourceManager.default().writeData(for: resource, toFile: outputURL, options: options) { error in
        exportError = error
        semaphore.signal()
    }
    _ = semaphore.wait(timeout: .now() + 3600)
    if let exportError {
        fputs("\(exportError)\n", stderr)
        exit(1)
    }
    encodeLine(ExportPayload(output_path: outputURL.path))
}

func exportBatch(requestFile: String) {
    let requestURL = URL(fileURLWithPath: requestFile)
    let data: Data
    do {
        data = try Data(contentsOf: requestURL)
    } catch {
        fputs("failed to read batch request file\n", stderr)
        exit(1)
    }

    let requests: [BatchRequest]
    do {
        requests = try JSONDecoder().decode([BatchRequest].self, from: data)
    } catch {
        fputs("failed to decode batch request json\n", stderr)
        exit(1)
    }

    for request in requests {
        let assetResult = PHAsset.fetchAssets(withLocalIdentifiers: [request.asset_local_identifier], options: nil)
        guard let asset = assetResult.firstObject else {
            encodeLine(BatchResponse(request_id: request.request_id, output_path: nil, error: "asset not found"))
            continue
        }
        let resources = PHAssetResource.assetResources(for: asset)
        guard request.resource_index >= 0 && request.resource_index < resources.count else {
            encodeLine(BatchResponse(request_id: request.request_id, output_path: nil, error: "resource index out of range"))
            continue
        }

        let resource = resources[request.resource_index]
        let outputURL = URL(fileURLWithPath: request.output_path)
        try? FileManager.default.removeItem(at: outputURL)
        try? FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        let options = PHAssetResourceRequestOptions()
        options.isNetworkAccessAllowed = true

        let semaphore = DispatchSemaphore(value: 0)
        var exportError: Error?
        PHAssetResourceManager.default().writeData(for: resource, toFile: outputURL, options: options) { error in
            exportError = error
            semaphore.signal()
        }
        _ = semaphore.wait(timeout: .now() + 3600)
        if let exportError {
            encodeLine(BatchResponse(request_id: request.request_id, output_path: nil, error: "\(exportError)"))
            continue
        }
        encodeLine(BatchResponse(request_id: request.request_id, output_path: outputURL.path, error: nil))
    }
}

requestAuthorization()

let args = CommandLine.arguments
guard args.count >= 2 else {
    fputs("usage: photos_bridge <list-resources|export-resource> [...]\n", stderr)
    exit(2)
}

switch args[1] {
case "list-resources":
    listResources()
case "export-resource":
    guard args.count == 5, let resourceIndex = Int(args[3]) else {
        fputs("usage: photos_bridge export-resource <asset-local-id> <resource-index> <output-path>\n", stderr)
        exit(2)
    }
    exportResource(localIdentifier: args[2], resourceIndex: resourceIndex, outputPath: args[4])
case "export-batch":
    guard args.count == 3 else {
        fputs("usage: photos_bridge export-batch <request-json>\n", stderr)
        exit(2)
    }
    exportBatch(requestFile: args[2])
default:
    fputs("unknown command: \(args[1])\n", stderr)
    exit(2)
}
