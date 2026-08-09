import Foundation
import CoreGraphics
import Metal
import SwiftUI
import LeniaCore
import LeniaVisuals
import MLX

actor ThumbnailRenderer {
    static let shared = ThumbnailRenderer()

    private var cache: [UUID: CGImage] = [:]
    private var inFlight: [UUID: Task<CGImage?, Never>] = [:]
    private var organismCache: [String: CGImage] = [:]
    private var organismInFlight: [String: Task<CGImage?, Never>] = [:]
    private let maxCacheSize = 500
    private let thumbnailFieldSize = 64
    private let thumbnailImageSize = 128
    private let metalRenderer: LeniaMetalFieldRenderer

    init() {
        guard let device = MTLCreateSystemDefaultDevice() else {
            preconditionFailure("Lenia Studio thumbnails require a Metal device")
        }
        metalRenderer = LeniaMetalFieldRenderer(device: device)
    }

    func thumbnail(for creature: LeniaCreature) -> CGImage? {
        cache[creature.id]
    }

    func render(creature: LeniaCreature) async -> CGImage? {
        if let cached = cache[creature.id] { return cached }
        if let task = inFlight[creature.id] {
            return await task.value
        }

        let task = Task<CGImage?, Never> { [weak self] in
            guard let self else { return nil }
            await Task.yield()
            return await self.generateThumbnail(creature: creature)
        }
        inFlight[creature.id] = task
        let image = await task.value
        inFlight.removeValue(forKey: creature.id)

        if let image {
            if cache.count >= maxCacheSize {
                let dropCount = maxCacheSize / 4
                let keys = Array(cache.keys.prefix(dropCount))
                for key in keys { cache.removeValue(forKey: key) }
            }
            cache[creature.id] = image
        }

        return image
    }

    func render(config: Track1TaxonomyConfig) async -> CGImage? {
        if let cached = organismCache[config.path] { return cached }
        if let task = organismInFlight[config.path] {
            return await task.value
        }

        let task = Task<CGImage?, Never> { [weak self] in
            guard let self else { return nil }
            return await self.generateOrganismThumbnail(config: config)
        }
        organismInFlight[config.path] = task
        let image = await task.value
        organismInFlight.removeValue(forKey: config.path)
        if let image {
            if organismCache.count >= maxCacheSize {
                for key in Array(organismCache.keys.prefix(maxCacheSize / 4)) {
                    organismCache.removeValue(forKey: key)
                }
            }
            organismCache[config.path] = image
        }
        return image
    }

    private func generateThumbnail(creature: LeniaCreature) async -> CGImage? {
        let stamp = buildSeedCreatureStamp(
            id: creature.id,
            name: creature.sourceNode,
            params: creature.params,
            seed: creature.seed,
            gridSize: thumbnailFieldSize,
            cropThreshold: 0.01,
            padding: 4
        )
        guard !Task.isCancelled else { return nil }

        let field = centeredField(from: stamp, size: thumbnailFieldSize)
        let surface = LeniaMetalFieldSurface(
            field: MLXArray(field).reshaped([thumbnailFieldSize, thumbnailFieldSize]),
            width: thumbnailFieldSize,
            height: thumbnailFieldSize
        )
        let frame = LeniaFieldFrame(
            step: 0,
            width: thumbnailFieldSize,
            height: thumbnailFieldSize,
            sharedField: surface
        )

        return metalRenderer.renderImage(
            frame: frame,
            renderMode: .smoothMagma,
            outputSize: CGSize(width: thumbnailImageSize, height: thumbnailImageSize)
        )
    }

    private func generateOrganismThumbnail(config: Track1TaxonomyConfig) async -> CGImage? {
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: config.path)),
              let runtimeConfig = try? loadRuntimeConfig(from: data),
              let patch = runtimeConfig.statePatch,
              let bytes = organismThumbnailBytes(from: patch) else {
            return nil
        }
        guard !Task.isCancelled else { return nil }
        return metalRenderer.renderImage(
            frame: LeniaFieldFrame(
                step: 0,
                width: patch.width,
                height: patch.height,
                bytes: bytes
            ),
            renderMode: .smoothMagma,
            outputSize: CGSize(width: thumbnailImageSize, height: thumbnailImageSize)
        )
    }

    private nonisolated func centeredField(from stamp: CreatureStamp, size: Int) -> [Float] {
        var field = [Float](repeating: 0, count: size * size)
        let originX = (size - stamp.width) / 2
        let originY = (size - stamp.height) / 2

        for localX in 0..<stamp.width {
            for localY in 0..<stamp.height {
                let worldX = originX + localX
                let worldY = originY + localY
                guard worldX >= 0, worldY >= 0, worldX < size, worldY < size else { continue }
                let sourceIndex = localX * stamp.height + localY
                let targetIndex = worldX * size + worldY
                field[targetIndex] = max(field[targetIndex], stamp.mass[sourceIndex])
            }
        }

        return field
    }
}

func organismThumbnailBytes(from patch: InitStatePatchConfig) -> Data? {
    let decoded = patch.decodedValues()
    guard patch.width > 0,
          patch.height > 0,
          patch.channels > 0,
          decoded.count == patch.width * patch.height * patch.channels else {
        return nil
    }

    var bytes = [UInt8](repeating: 0, count: patch.width * patch.height)
    for x in 0..<patch.width {
        for y in 0..<patch.height {
            let sourcePixel = (x * patch.height + y) * patch.channels
            let matter = (0..<patch.channels).reduce(Float.zero) { total, channel in
                total + decoded[sourcePixel + channel]
            }
            bytes[y * patch.width + x] = UInt8((min(max(matter, 0), 1) * 255).rounded())
        }
    }
    return Data(bytes)
}

struct Track1OrganismThumbnailView: View {
    let config: Track1TaxonomyConfig
    var size: CGFloat = 72

    @State private var thumbnail: CGImage?

    var body: some View {
        ZStack {
            Rectangle().fill(StudioPalette.stageBottom)
            if let thumbnail {
                Image(decorative: thumbnail, scale: 1)
                    .resizable()
                    .interpolation(.high)
                    .scaledToFit()
            } else {
                ProgressView()
                    .controlSize(.small)
                    .tint(StudioPalette.mutedInk)
            }
        }
        .frame(width: size, height: size)
        .clipped()
        .task(id: config.path) {
            thumbnail = nil
            thumbnail = await ThumbnailRenderer.shared.render(config: config)
        }
    }
}
