import Foundation
import zlib

public enum FieldCodecError: Error, CustomStringConvertible {
    case retiredEncoding(String)
    case unknownEncoding(String)
    case invalidBase64
    case corruptStream(Int32)
    case lengthMismatch(expected: Int)

    public var description: String {
        switch self {
        case .retiredEncoding(let encoding):
            return "Field encoding \"\(encoding)\" is retired; rewrite the files with `uv run lenia-swarm-analysis compact <root>` (from dossiers/lenia-swarm) to convert them to \"\(FieldCodec.encoding)\"."
        case .unknownEncoding(let encoding):
            return "Unknown field encoding \"\(encoding)\"; the only supported encoding is \"\(FieldCodec.encoding)\"."
        case .invalidBase64:
            return "Field data is not valid base64."
        case .corruptStream(let status):
            return "Field data is not a valid zlib stream (zlib status \(status))."
        case .lengthMismatch(let expected):
            return "Field data does not inflate to the \(expected) bytes its shape requires."
        }
    }
}

/// Little-endian float32 values, split into four byte planes (every byte 0, then every byte 1, ...),
/// then compressed as a zlib stream (RFC 1950, with header and adler32). Python's stdlib `zlib`
/// reads it directly; Apple's COMPRESSION_ZLIB would emit raw deflate, so libz is used instead.
/// Byte-plane order groups the near-constant exponent bytes, which is where the savings come from.
public enum FieldCodec {
    public static let encoding = "f32le-shuffle-zlib"
    static let retiredEncodings: Set<String> = ["f32le"]
    static let compressionLevel: Int32 = 9

    public static func validate(encoding: String) throws {
        if encoding == Self.encoding {
            return
        }
        if retiredEncodings.contains(encoding) {
            throw FieldCodecError.retiredEncoding(encoding)
        }
        throw FieldCodecError.unknownEncoding(encoding)
    }

    public static func encode(rawLittleEndianFloat32 raw: Data) -> String {
        precondition(raw.count % 4 == 0, "Field byte count \(raw.count) is not a multiple of 4.")
        let shuffled = shuffle(raw)
        var destinationLength = compressBound(uLong(shuffled.count))
        var compressed = Data(count: Int(destinationLength))
        let status = compressed.withUnsafeMutableBytes { destination in
            shuffled.withUnsafeBytes { source in
                compress2(
                    destination.bindMemory(to: Bytef.self).baseAddress,
                    &destinationLength,
                    source.bindMemory(to: Bytef.self).baseAddress,
                    uLong(shuffled.count),
                    compressionLevel
                )
            }
        }
        precondition(status == Z_OK, "zlib compress2 failed with status \(status).")
        compressed.count = Int(destinationLength)
        return compressed.base64EncodedString()
    }

    public static func decode(base64 text: String, byteCount: Int) throws -> Data {
        guard let compressed = Data(base64Encoded: text) else {
            throw FieldCodecError.invalidBase64
        }
        var shuffled = Data(count: byteCount)
        var destinationLength = uLong(byteCount)
        var sourceLength = uLong(compressed.count)
        let status = shuffled.withUnsafeMutableBytes { destination in
            compressed.withUnsafeBytes { source in
                uncompress2(
                    destination.bindMemory(to: Bytef.self).baseAddress,
                    &destinationLength,
                    source.bindMemory(to: Bytef.self).baseAddress,
                    &sourceLength
                )
            }
        }
        // Z_BUF_ERROR means the stream holds more than byteCount bytes or ends early.
        if status == Z_BUF_ERROR {
            throw FieldCodecError.lengthMismatch(expected: byteCount)
        }
        guard status == Z_OK else {
            throw FieldCodecError.corruptStream(status)
        }
        guard Int(destinationLength) == byteCount, Int(sourceLength) == compressed.count else {
            throw FieldCodecError.lengthMismatch(expected: byteCount)
        }
        return unshuffle(shuffled)
    }

    static func shuffle(_ raw: Data) -> Data {
        let count = raw.count / 4
        var out = Data(count: raw.count)
        raw.withUnsafeBytes { source in
            out.withUnsafeMutableBytes { destination in
                let src = source.bindMemory(to: UInt8.self)
                let dst = destination.bindMemory(to: UInt8.self)
                for index in 0..<count {
                    dst[index] = src[4 * index]
                    dst[count + index] = src[4 * index + 1]
                    dst[2 * count + index] = src[4 * index + 2]
                    dst[3 * count + index] = src[4 * index + 3]
                }
            }
        }
        return out
    }

    static func unshuffle(_ shuffled: Data) -> Data {
        let count = shuffled.count / 4
        var out = Data(count: shuffled.count)
        shuffled.withUnsafeBytes { source in
            out.withUnsafeMutableBytes { destination in
                let src = source.bindMemory(to: UInt8.self)
                let dst = destination.bindMemory(to: UInt8.self)
                for index in 0..<count {
                    dst[4 * index] = src[index]
                    dst[4 * index + 1] = src[count + index]
                    dst[4 * index + 2] = src[2 * count + index]
                    dst[4 * index + 3] = src[3 * count + index]
                }
            }
        }
        return out
    }
}
