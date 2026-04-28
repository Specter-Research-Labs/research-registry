// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "LeniaSwarm",
    platforms: [.macOS(.v15)],
    products: [
        .library(name: "LeniaCore", targets: ["LeniaCore"]),
        .library(name: "LeniaArchive", targets: ["LeniaArchive"]),
        .library(name: "LeniaVisuals", targets: ["LeniaVisuals"]),
        .library(name: "LeniaCLIKit", targets: ["LeniaCLIKit"]),
        .executable(name: "LeniaCLI", targets: ["LeniaCLI"]),
        .executable(name: "LeniaStudio", targets: ["LeniaStudio"]),
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-distributed-actors.git", branch: "main"),
        .package(url: "https://github.com/apple/swift-argument-parser.git", from: "1.3.0"),
        .package(url: "https://github.com/ml-explore/mlx-swift", from: "0.21.0"),
        .package(url: "https://github.com/apple/swift-log.git", from: "1.5.0"),
    ],
    targets: [
        .target(
            name: "LeniaCore",
            dependencies: [
                .product(name: "DistributedCluster", package: "swift-distributed-actors"),
                .product(name: "MLX", package: "mlx-swift"),
                .product(name: "MLXFast", package: "mlx-swift"),
                .product(name: "MLXRandom", package: "mlx-swift"),
                .product(name: "MLXFFT", package: "mlx-swift"),
                .product(name: "Logging", package: "swift-log"),
            ],
            path: "Sources/LeniaCore"
        ),
        .target(
            name: "LeniaVisuals",
            dependencies: [
                "LeniaCore",
            ],
            path: "Sources/LeniaVisuals",
            resources: [.process("Resources")]
        ),
        .target(
            name: "LeniaArchive",
            dependencies: [
                "LeniaCore",
            ],
            path: "Sources/LeniaArchive",
            linkerSettings: [
                .linkedLibrary("sqlite3"),
            ]
        ),
        .target(
            name: "LeniaCLIKit",
            dependencies: [
                "LeniaCore",
                "LeniaArchive",
                "LeniaVisuals",
                .product(name: "DistributedCluster", package: "swift-distributed-actors"),
                .product(name: "ArgumentParser", package: "swift-argument-parser"),
                .product(name: "Logging", package: "swift-log"),
            ],
            path: "Sources/LeniaCLI",
            linkerSettings: [
                .linkedLibrary("sqlite3"),
            ]
        ),
        .executableTarget(
            name: "LeniaCLI",
            dependencies: [
                "LeniaCLIKit",
            ],
            path: "Sources/LeniaCLIExec"
        ),
        .executableTarget(
            name: "LeniaStudio",
            dependencies: [
                "LeniaCore",
                "LeniaArchive",
                "LeniaVisuals",
                .product(name: "DistributedCluster", package: "swift-distributed-actors"),
                .product(name: "MLX", package: "mlx-swift"),
            ],
            path: "Sources/LeniaStudio",
            resources: [.process("Resources")],
            linkerSettings: [
                .linkedLibrary("sqlite3"),
            ]
        ),
        .testTarget(
            name: "LeniaCoreTests",
            dependencies: [
                "LeniaCore",
                .product(name: "MLX", package: "mlx-swift"),
                .product(name: "MLXFFT", package: "mlx-swift"),
            ],
            path: "Tests/LeniaCoreTests"
        ),
        .testTarget(
            name: "LeniaCLITests",
            dependencies: [
                "LeniaCLIKit",
                "LeniaCore",
                "LeniaArchive",
            ],
            path: "Tests/LeniaCLITests"
        ),
        .testTarget(
            name: "LeniaStudioTests",
            dependencies: [
                "LeniaStudio",
                "LeniaCore",
                "LeniaVisuals",
            ],
            path: "Tests/LeniaStudioTests"
        ),
    ]
)
