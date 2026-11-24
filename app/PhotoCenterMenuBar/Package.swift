// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "PhotoCenterMenuBar",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "PhotoCenterMenuBar", targets: ["PhotoCenterMenuBar"])
    ],
    dependencies: [
        .package(url: "https://github.com/sparkle-project/Sparkle", from: "2.10.1")
    ],
    targets: [
        .executableTarget(
            name: "PhotoCenterMenuBar",
            dependencies: [
                .product(name: "Sparkle", package: "Sparkle")
            ],
            linkerSettings: [
                .unsafeFlags([
                    "-Xlinker", "-rpath", "-Xlinker", "@executable_path/../Frameworks",
                ])
            ]
        )
    ]
)
