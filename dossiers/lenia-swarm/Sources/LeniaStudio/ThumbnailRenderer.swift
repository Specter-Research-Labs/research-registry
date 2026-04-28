import Foundation
import CoreGraphics
import Metal
import LeniaCore
import LeniaVisuals
import MLX

actor ThumbnailRenderer {
    static let shared = ThumbnailRenderer()

    private var cache: [UUID: CGImage] = [:]
    private var pending: Set<UUID> = []
    private let maxCacheSize = 500
    private let warmupSteps = 80
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

    func hasThumbnail(for id: UUID) -> Bool {
        cache[id] != nil
    }

    func render(creature: LeniaCreature) async -> CGImage? {
        if let cached = cache[creature.id] { return cached }
        guard !pending.contains(creature.id) else { return nil }

        pending.insert(creature.id)
        defer { pending.remove(creature.id) }

        let image = await generateThumbnail(creature: creature)

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

    private func generateThumbnail(creature: LeniaCreature) async -> CGImage? {
        let stamp = buildSeedCreatureStamp(
            id: creature.id,
            name: creature.sourceNode,
            params: creature.params,
            seed: creature.seed,
            gridSize: thumbnailFieldSize
        )
        guard !Task.isCancelled else { return nil }

        let field = centeredField(from: stamp, size: thumbnailFieldSize)
        let surface = LeniaMetalFieldSurface(
            field: MLXArray(field).reshaped([thumbnailFieldSize, thumbnailFieldSize]),
            width: thumbnailFieldSize,
            height: thumbnailFieldSize
        )
        let frame = LeniaFieldFrame(
            step: warmupSteps,
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
