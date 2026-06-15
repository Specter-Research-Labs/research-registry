import Foundation
import CoreGraphics
import MetalKit
import LeniaCore

public struct LeniaFieldFrame: Sendable {
    public let step: Int
    public let width: Int
    public let height: Int
    public let bytes: Data?
    public let sharedField: LeniaMetalFieldSurface?

    public init(
        step: Int,
        width: Int,
        height: Int,
        bytes: Data? = nil,
        sharedField: LeniaMetalFieldSurface? = nil
    ) {
        self.step = step
        self.width = width
        self.height = height
        self.bytes = bytes
        self.sharedField = sharedField
    }

    public init(snapshot: FlowSandboxSnapshot) {
        self.init(
            step: snapshot.step,
            width: snapshot.width,
            height: snapshot.height,
            bytes: snapshot.bytes,
            sharedField: snapshot.sharedField
        )
    }
}

public struct LeniaLabStageTransform: Equatable, Sendable {
    public var zoom: CGFloat = 1.0
    public var offset: CGSize = .zero

    public static let minZoom: CGFloat = 0.5
    public static let maxZoom: CGFloat = 20.0

    public init(zoom: CGFloat = 1.0, offset: CGSize = .zero) {
        self.zoom = zoom
        self.offset = offset
    }

    public static func clampedZoom(_ zoom: CGFloat) -> CGFloat {
        min(max(zoom, minZoom), maxZoom)
    }

    public func imageRect(viewSize: CGSize, gridSize: CGSize) -> CGRect {
        let baseScale = min(viewSize.width / gridSize.width, viewSize.height / gridSize.height)
        let scaledWidth = gridSize.width * baseScale * zoom
        let scaledHeight = gridSize.height * baseScale * zoom
        let originX = (viewSize.width - scaledWidth) / 2 + offset.width
        let originY = (viewSize.height - scaledHeight) / 2 + offset.height
        return CGRect(x: originX, y: originY, width: scaledWidth, height: scaledHeight)
    }

    public func gridPoint(for point: CGPoint, viewSize: CGSize, gridSize: Int) -> SIMD2<Int>? {
        let rect = imageRect(viewSize: viewSize, gridSize: CGSize(width: gridSize, height: gridSize))
        guard rect.contains(point) else { return nil }
        let localX = (point.x - rect.minX) / rect.width
        let localY = (point.y - rect.minY) / rect.height
        let gridX = min(gridSize - 1, max(0, Int(localX * CGFloat(gridSize))))
        let gridY = min(gridSize - 1, max(0, Int(localY * CGFloat(gridSize))))
        return SIMD2<Int>(gridX, gridY)
    }

    public func panned(by delta: CGSize) -> LeniaLabStageTransform {
        LeniaLabStageTransform(
            zoom: zoom,
            offset: CGSize(
                width: offset.width + delta.width,
                height: offset.height + delta.height
            )
        )
    }

    public func zoomed(
        to proposedZoom: CGFloat,
        around anchor: CGPoint?,
        viewSize: CGSize,
        gridSize: Int
    ) -> LeniaLabStageTransform {
        let nextZoom = Self.clampedZoom(proposedZoom)
        guard gridSize > 0 else {
            return LeniaLabStageTransform(zoom: nextZoom, offset: offset)
        }

        let gridSizeValue = CGSize(width: gridSize, height: gridSize)
        let previousRect = imageRect(viewSize: viewSize, gridSize: gridSizeValue)
        let fallbackAnchor = CGPoint(x: previousRect.midX, y: previousRect.midY)
        let pivot = anchor.map { previousRect.contains($0) ? $0 : fallbackAnchor } ?? fallbackAnchor
        let normalizedX = (pivot.x - previousRect.minX) / max(previousRect.width, 1)
        let normalizedY = (pivot.y - previousRect.minY) / max(previousRect.height, 1)

        var updated = LeniaLabStageTransform(zoom: nextZoom, offset: offset)
        let nextRect = updated.imageRect(viewSize: viewSize, gridSize: gridSizeValue)
        let shiftedPoint = CGPoint(
            x: nextRect.minX + normalizedX * nextRect.width,
            y: nextRect.minY + normalizedY * nextRect.height
        )
        updated.offset.width += pivot.x - shiftedPoint.x
        updated.offset.height += pivot.y - shiftedPoint.y
        return updated
    }
}

public final class LeniaMetalFieldRenderer: NSObject, MTKViewDelegate {
    private struct Vertex {
        var position: SIMD2<Float>
        var texCoord: SIMD2<Float>
    }

    private struct Uniforms {
        var renderMode: UInt32
        var channelCount: UInt32
        var gridSize: SIMD2<Float>
        var lightStrength: Float
        var rimStrength: Float
    }

    public var lightStrength: Float = 0.85
    public var rimStrength: Float = 0.35
    private var channelCount: UInt32 = 1

    private let device: MTLDevice
    private let commandQueue: MTLCommandQueue
    private let pipelineState: MTLRenderPipelineState
    private let samplerState: MTLSamplerState
    private let vertexBuffer: MTLBuffer

    private var texture: MTLTexture?
    private var textureBuffer: MTLBuffer?
    private var textureBufferIdentity: ObjectIdentifier?
    private var textureSize: CGSize = .zero
    private var texturePixelFormat: MTLPixelFormat = .r8Unorm

    public var transform = LeniaLabStageTransform()
    public var renderMode: LeniaRenderMode = .smoothMagma
    public var viewSize: CGSize = .zero

    public init(device: MTLDevice) {
        self.device = device
        guard let commandQueue = device.makeCommandQueue() else {
            preconditionFailure("Lenia visuals require a Metal command queue")
        }
        self.commandQueue = commandQueue

        let library = Self.makeShaderLibrary(device: device)
        guard let vertexFunction = library.makeFunction(name: "labStageVertex"),
              let fragmentFunction = library.makeFunction(name: "labStageFragment") else {
            preconditionFailure("LeniaShaders.metallib is missing lab stage functions")
        }

        let pipelineDescriptor = MTLRenderPipelineDescriptor()
        pipelineDescriptor.vertexFunction = vertexFunction
        pipelineDescriptor.fragmentFunction = fragmentFunction
        pipelineDescriptor.colorAttachments[0].pixelFormat = .bgra8Unorm

        do {
            pipelineState = try device.makeRenderPipelineState(descriptor: pipelineDescriptor)
        } catch {
            preconditionFailure("Failed to create Lenia visuals render pipeline: \(error)")
        }

        let samplerDescriptor = MTLSamplerDescriptor()
        samplerDescriptor.minFilter = .linear
        samplerDescriptor.magFilter = .linear
        samplerDescriptor.sAddressMode = .clampToEdge
        samplerDescriptor.tAddressMode = .clampToEdge
        guard let samplerState = device.makeSamplerState(descriptor: samplerDescriptor) else {
            preconditionFailure("Failed to create Lenia visuals sampler state")
        }
        self.samplerState = samplerState

        guard let vertexBuffer = device.makeBuffer(
            length: MemoryLayout<Vertex>.stride * 4,
            options: .storageModeShared
        ) else {
            preconditionFailure("Failed to allocate Lenia visuals vertex buffer")
        }
        self.vertexBuffer = vertexBuffer
    }

    public func update(frame: LeniaFieldFrame?) {
        guard let frame else {
            texture = nil
            textureBuffer = nil
            textureBufferIdentity = nil
            textureSize = .zero
            return
        }

        let size = CGSize(width: frame.width, height: frame.height)
        channelCount = 1
        if let sharedField = frame.sharedField,
           let buffer = sharedField.metalBuffer(on: device, noCopy: true) ?? sharedField.metalBuffer(on: device, noCopy: false) {
            let bufferIdentity = ObjectIdentifier(buffer as AnyObject)
            if texture == nil
                || textureSize != size
                || texturePixelFormat != .r32Float
                || textureBufferIdentity != bufferIdentity {
                let descriptor = MTLTextureDescriptor.texture2DDescriptor(
                    pixelFormat: .r32Float,
                    width: frame.width,
                    height: frame.height,
                    mipmapped: false
                )
                descriptor.usage = .shaderRead
                texture = buffer.makeTexture(
                    descriptor: descriptor,
                    offset: 0,
                    bytesPerRow: frame.width * MemoryLayout<Float>.stride
                )
                textureBuffer = buffer
                textureBufferIdentity = bufferIdentity
                textureSize = size
                texturePixelFormat = .r32Float
            }
            return
        }

        guard let bytes = frame.bytes else {
            texture = nil
            textureBuffer = nil
            textureBufferIdentity = nil
            textureSize = .zero
            return
        }

        if texture == nil || textureSize != size || texturePixelFormat != .r8Unorm {
            let descriptor = MTLTextureDescriptor.texture2DDescriptor(
                pixelFormat: .r8Unorm,
                width: frame.width,
                height: frame.height,
                mipmapped: false
            )
            descriptor.usage = .shaderRead
            descriptor.storageMode = .shared
            texture = device.makeTexture(descriptor: descriptor)
            textureSize = size
            texturePixelFormat = .r8Unorm
        }
        textureBuffer = nil
        textureBufferIdentity = nil

        bytes.withUnsafeBytes { bytes in
            guard let baseAddress = bytes.baseAddress else { return }
            texture?.replace(
                region: MTLRegionMake2D(0, 0, frame.width, frame.height),
                mipmapLevel: 0,
                withBytes: baseAddress,
                bytesPerRow: frame.width
            )
        }
    }

    public func renderImage(
        frame: LeniaFieldFrame,
        renderMode: LeniaRenderMode,
        outputSize: CGSize
    ) -> CGImage? {
        guard frame.width > 0, frame.height > 0 else { return nil }
        let pixelWidth = max(1, Int(outputSize.width.rounded()))
        let pixelHeight = max(1, Int(outputSize.height.rounded()))

        update(frame: frame)
        return renderCurrentTexture(renderMode: renderMode, pixelWidth: pixelWidth, pixelHeight: pixelHeight)
    }

    public func renderMultiChannelImage(
        rgbaValues: [Float],
        channels: Int,
        width: Int,
        height: Int,
        renderMode: LeniaRenderMode,
        outputSize: CGSize
    ) -> CGImage? {
        guard width > 0, height > 0 else { return nil }
        precondition(channels >= 1 && channels <= 4, "Lenia renderer supports 1...4 channels, got \(channels)")
        precondition(
            rgbaValues.count == width * height * 4,
            "Multi-channel field must be packed RGBA: expected \(width * height * 4), got \(rgbaValues.count)"
        )
        let pixelWidth = max(1, Int(outputSize.width.rounded()))
        let pixelHeight = max(1, Int(outputSize.height.rounded()))

        updateMultiChannel(rgbaValues: rgbaValues, width: width, height: height, channels: channels)
        return renderCurrentTexture(renderMode: renderMode, pixelWidth: pixelWidth, pixelHeight: pixelHeight)
    }

    private func renderCurrentTexture(
        renderMode: LeniaRenderMode,
        pixelWidth: Int,
        pixelHeight: Int
    ) -> CGImage? {
        self.renderMode = renderMode
        self.transform = .init()
        self.viewSize = CGSize(width: pixelWidth, height: pixelHeight)

        guard texture != nil,
              let outputTexture = makeOutputTexture(width: pixelWidth, height: pixelHeight),
              let commandBuffer = commandQueue.makeCommandBuffer() else {
            return nil
        }

        let renderPassDescriptor = MTLRenderPassDescriptor()
        renderPassDescriptor.colorAttachments[0].texture = outputTexture
        renderPassDescriptor.colorAttachments[0].loadAction = .clear
        renderPassDescriptor.colorAttachments[0].storeAction = .store
        renderPassDescriptor.colorAttachments[0].clearColor = MTLClearColor(
            red: 0.01,
            green: 0.01,
            blue: 0.02,
            alpha: 0
        )

        guard encodeDraw(
            commandBuffer: commandBuffer,
            renderPassDescriptor: renderPassDescriptor,
            viewSize: CGSize(width: pixelWidth, height: pixelHeight),
            rect: transform.imageRect(
                viewSize: CGSize(width: pixelWidth, height: pixelHeight),
                gridSize: textureSize
            )
        ) else {
            return nil
        }

        commandBuffer.commit()
        commandBuffer.waitUntilCompleted()
        guard commandBuffer.status == .completed else { return nil }
        return Self.makeImage(texture: outputTexture, width: pixelWidth, height: pixelHeight)
    }

    private func updateMultiChannel(rgbaValues: [Float], width: Int, height: Int, channels: Int) {
        let size = CGSize(width: width, height: height)
        if texture == nil || textureSize != size || texturePixelFormat != .rgba32Float {
            let descriptor = MTLTextureDescriptor.texture2DDescriptor(
                pixelFormat: .rgba32Float,
                width: width,
                height: height,
                mipmapped: false
            )
            descriptor.usage = .shaderRead
            descriptor.storageMode = .shared
            texture = device.makeTexture(descriptor: descriptor)
            textureSize = size
            texturePixelFormat = .rgba32Float
        }
        textureBuffer = nil
        channelCount = UInt32(channels)

        rgbaValues.withUnsafeBytes { bytes in
            guard let baseAddress = bytes.baseAddress else { return }
            texture?.replace(
                region: MTLRegionMake2D(0, 0, width, height),
                mipmapLevel: 0,
                withBytes: baseAddress,
                bytesPerRow: width * MemoryLayout<Float>.stride * 4
            )
        }
    }

    public func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) {
        viewSize = view.bounds.size
    }

    public func draw(in view: MTKView) {
        guard let renderPassDescriptor = view.currentRenderPassDescriptor,
              let drawable = view.currentDrawable,
              let commandBuffer = commandQueue.makeCommandBuffer() else {
            return
        }

        if texture != nil {
            let rect = transform.imageRect(viewSize: viewSize, gridSize: textureSize)
            _ = encodeDraw(
                commandBuffer: commandBuffer,
                renderPassDescriptor: renderPassDescriptor,
                viewSize: view.bounds.size,
                rect: rect
            )
        } else if let encoder = commandBuffer.makeRenderCommandEncoder(descriptor: renderPassDescriptor) {
            encoder.endEncoding()
        }

        commandBuffer.present(drawable)
        commandBuffer.commit()
    }

    private func encodeDraw(
        commandBuffer: MTLCommandBuffer,
        renderPassDescriptor: MTLRenderPassDescriptor,
        viewSize: CGSize,
        rect: CGRect
    ) -> Bool {
        guard let texture,
              let encoder = commandBuffer.makeRenderCommandEncoder(descriptor: renderPassDescriptor) else {
            return false
        }

        defer {
            encoder.endEncoding()
        }

        let vertices = quadVertices(rect: rect, viewSize: viewSize)
        vertices.withUnsafeBytes { bytes in
            guard let baseAddress = bytes.baseAddress else { return }
            memcpy(vertexBuffer.contents(), baseAddress, bytes.count)
        }

        var uniforms = Uniforms(
            renderMode: renderMode.shaderIndex,
            channelCount: channelCount,
            gridSize: SIMD2<Float>(Float(textureSize.width), Float(textureSize.height)),
            lightStrength: lightStrength,
            rimStrength: rimStrength
        )
        encoder.setRenderPipelineState(pipelineState)
        encoder.setVertexBuffer(vertexBuffer, offset: 0, index: 0)
        encoder.setFragmentTexture(texture, index: 0)
        encoder.setFragmentSamplerState(samplerState, index: 0)
        encoder.setFragmentBytes(&uniforms, length: MemoryLayout<Uniforms>.stride, index: 1)
        encoder.drawPrimitives(type: .triangleStrip, vertexStart: 0, vertexCount: 4)
        return true
    }

    private func quadVertices(rect: CGRect, viewSize: CGSize) -> [Vertex] {
        guard viewSize.width > 0, viewSize.height > 0 else {
            return [
                Vertex(position: .zero, texCoord: SIMD2<Float>(0, 1)),
                Vertex(position: .zero, texCoord: SIMD2<Float>(1, 1)),
                Vertex(position: .zero, texCoord: SIMD2<Float>(0, 0)),
                Vertex(position: .zero, texCoord: SIMD2<Float>(1, 0)),
            ]
        }

        let left = Float((rect.minX / viewSize.width) * 2 - 1)
        let right = Float((rect.maxX / viewSize.width) * 2 - 1)
        let top = Float(1 - (rect.minY / viewSize.height) * 2)
        let bottom = Float(1 - (rect.maxY / viewSize.height) * 2)

        return [
            Vertex(position: SIMD2<Float>(left, bottom), texCoord: SIMD2<Float>(0, 1)),
            Vertex(position: SIMD2<Float>(right, bottom), texCoord: SIMD2<Float>(1, 1)),
            Vertex(position: SIMD2<Float>(left, top), texCoord: SIMD2<Float>(0, 0)),
            Vertex(position: SIMD2<Float>(right, top), texCoord: SIMD2<Float>(1, 0)),
        ]
    }

    private func makeOutputTexture(width: Int, height: Int) -> MTLTexture? {
        let descriptor = MTLTextureDescriptor.texture2DDescriptor(
            pixelFormat: .bgra8Unorm,
            width: width,
            height: height,
            mipmapped: false
        )
        descriptor.usage = [.renderTarget, .shaderRead]
        descriptor.storageMode = .shared
        return device.makeTexture(descriptor: descriptor)
    }

    private static func makeShaderLibrary(device: MTLDevice) -> MTLLibrary {
        do {
            return try device.makeLibrary(URL: LeniaVisualResources.shaderLibraryURL())
        } catch {
            preconditionFailure("Failed to load LeniaShaders.metallib: \(error)")
        }
    }

    private static func makeImage(texture: MTLTexture, width: Int, height: Int) -> CGImage? {
        let bytesPerRow = width * 4
        var bytes = [UInt8](repeating: 0, count: bytesPerRow * height)
        texture.getBytes(
            &bytes,
            bytesPerRow: bytesPerRow,
            from: MTLRegionMake2D(0, 0, width, height),
            mipmapLevel: 0
        )

        let colorSpace = CGColorSpaceCreateDeviceRGB()
        let bitmapInfo = CGBitmapInfo.byteOrder32Little.union(
            CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedFirst.rawValue)
        )

        guard let provider = CGDataProvider(data: Data(bytes) as CFData) else {
            return nil
        }

        return CGImage(
            width: width,
            height: height,
            bitsPerComponent: 8,
            bitsPerPixel: 32,
            bytesPerRow: bytesPerRow,
            space: colorSpace,
            bitmapInfo: bitmapInfo,
            provider: provider,
            decode: nil,
            shouldInterpolate: true,
            intent: .defaultIntent
        )
    }
}
