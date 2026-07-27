// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PhotoCenterMenuBar",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "PhotoCenterMenuBar", targets: ["PhotoCenterMenuBar"])
    ],
    targets: [
        .executableTarget(
            name: "PhotoCenterMenuBar",
            linkerSettings: [
                .linkedFramework("Photos")
            ]
        )
    ]
)
