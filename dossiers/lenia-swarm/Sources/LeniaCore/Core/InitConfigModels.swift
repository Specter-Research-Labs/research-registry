import Foundation

public struct PatchConfig: Codable, Sendable {
    public let center: [Int]
    public let size: Int

    public init(center: [Int], size: Int) {
        self.center = center
        self.size = size
    }
}

public struct WorldState: Sendable {
    public let width: Int
    public let height: Int
    public let channels: Int
    public let values: [Float]

    public init(width: Int, height: Int, channels: Int, values: [Float]) {
        self.width = width
        self.height = height
        self.channels = channels
        self.values = values
    }

    public func toInitStatePatch(center: [Int]) -> InitStatePatchConfig {
        InitStatePatchConfig(center: center, width: width, height: height, channels: channels, values: values)
    }
}

/// `data` holds raw little-endian float32 bytes in memory; the JSON form always carries
/// `FieldCodec.encoding`, so every config, terminal state and library entry shares one field format.
public struct InitStatePatchConfig: Codable, Sendable {
    public let center: [Int]
    public let width: Int
    public let height: Int
    public let channels: Int
    public let data: Data

    private enum CodingKeys: String, CodingKey {
        case center, width, height, channels, encoding, data
    }

    public init(
        center: [Int],
        width: Int,
        height: Int,
        channels: Int,
        data: Data
    ) {
        self.center = center
        self.width = width
        self.height = height
        self.channels = channels
        self.data = data
    }

    public init(
        center: [Int],
        width: Int,
        height: Int,
        channels: Int,
        values: [Float]
    ) {
        self.init(
            center: center,
            width: width,
            height: height,
            channels: channels,
            data: initStatePatchData(values)
        )
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        center = try container.decode([Int].self, forKey: .center)
        width = try container.decode(Int.self, forKey: .width)
        height = try container.decode(Int.self, forKey: .height)
        channels = try container.decode(Int.self, forKey: .channels)
        let encoding = try container.decode(String.self, forKey: .encoding)
        let byteCount = width * height * channels * MemoryLayout<Float>.size
        do {
            try FieldCodec.validate(encoding: encoding)
            data = try FieldCodec.decode(base64: try container.decode(String.self, forKey: .data), byteCount: byteCount)
        } catch let error as FieldCodecError {
            throw DecodingError.dataCorruptedError(forKey: .data, in: container, debugDescription: error.description)
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(center, forKey: .center)
        try container.encode(width, forKey: .width)
        try container.encode(height, forKey: .height)
        try container.encode(channels, forKey: .channels)
        try container.encode(FieldCodec.encoding, forKey: .encoding)
        try container.encode(FieldCodec.encode(rawLittleEndianFloat32: data), forKey: .data)
    }

    public var valueCount: Int {
        data.count / MemoryLayout<Float>.size
    }

    public func decodedValues() -> [Float] {
        decodeInitStatePatchData(data)
    }

    public func toWorldState() -> WorldState {
        WorldState(width: width, height: height, channels: channels, values: decodedValues())
    }
}

public struct UniformRange: Codable, Sendable {
    public let low: Float
    public let high: Float

    public init(low: Float, high: Float) {
        self.low = low
        self.high = high
    }
}

public struct InitConfig: Codable, Sendable {
    public let seed: Int
    public let patches: [PatchConfig]
    public let a_uniform: UniformRange
    public let p_uniform: UniformRange?
    public let state_patch: InitStatePatchConfig?
    public let p_state_patch: InitStatePatchConfig?

    public init(
        seed: Int,
        patches: [PatchConfig],
        a_uniform: UniformRange,
        p_uniform: UniformRange?,
        state_patch: InitStatePatchConfig? = nil,
        p_state_patch: InitStatePatchConfig? = nil
    ) {
        self.seed = seed
        self.patches = patches
        self.a_uniform = a_uniform
        self.p_uniform = p_uniform
        self.state_patch = state_patch
        self.p_state_patch = p_state_patch
    }
}

public struct RunConfig: Codable, Sendable {
    public let steps: Int

    public init(steps: Int) {
        self.steps = steps
    }
}

private func initStatePatchData(_ values: [Float]) -> Data {
    var data = Data(capacity: values.count * MemoryLayout<Float>.size)
    for value in values {
        var littleEndian = value.bitPattern.littleEndian
        withUnsafeBytes(of: &littleEndian) { rawBytes in
            data.append(contentsOf: rawBytes)
        }
    }
    return data
}

private func decodeInitStatePatchData(_ data: Data) -> [Float] {
    let bytes = Array(data)
    precondition(bytes.count % MemoryLayout<Float>.size == 0, "init.state_patch.data must hold whole float32 values.")
    var values: [Float] = []
    values.reserveCapacity(bytes.count / MemoryLayout<Float>.size)
    for offset in stride(from: 0, to: bytes.count, by: MemoryLayout<Float>.size) {
        let word =
            UInt32(bytes[offset]) |
            (UInt32(bytes[offset + 1]) << 8) |
            (UInt32(bytes[offset + 2]) << 16) |
            (UInt32(bytes[offset + 3]) << 24)
        values.append(Float(bitPattern: UInt32(littleEndian: word)))
    }
    return values
}
