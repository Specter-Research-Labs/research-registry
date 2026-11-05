import Crypto
import Foundation
import XCTest
@testable import LeniaCore

final class FieldCodecTests: XCTestCase {
    private struct Fixture: Decodable {
        let width: Int
        let height: Int
        let channels: Int
        let raw_f32le_base64: String
        let raw_sha256: String
        let encoding: String
        let data: String
    }

    func testRoundTripPreservesEveryBit() throws {
        let bits: [UInt32] = [0, 0x8000_0000, 1, 0x7F80_0000, 0xFF80_0000, 0x7FC0_0123, 0x3F80_0000]
        let values = bits.map(Float.init(bitPattern:)) + (0..<1001).map { Float($0) * 0.006 - 3 }
        let patch = InitStatePatchConfig(center: [4, 4], width: values.count, height: 1, channels: 1, values: values)
        let decoded = try JSONDecoder().decode(InitStatePatchConfig.self, from: JSONEncoder().encode(patch))
        XCTAssertEqual(decoded.data, patch.data)
        XCTAssertEqual(decoded.decodedValues().map(\.bitPattern), values.map(\.bitPattern))
    }

    func testFixtureIsBitIdenticalWithPython() throws {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "field-codec", withExtension: "json"))
        let fixture = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
        let raw = try XCTUnwrap(Data(base64Encoded: fixture.raw_f32le_base64))
        XCTAssertEqual(SHA256.hash(data: raw).map { String(format: "%02x", $0) }.joined(), fixture.raw_sha256)
        XCTAssertEqual(fixture.encoding, FieldCodec.encoding)

        let decoded = try FieldCodec.decode(base64: fixture.data, byteCount: raw.count)
        XCTAssertEqual(decoded, raw)
        XCTAssertEqual(FieldCodec.encode(rawLittleEndianFloat32: raw), fixture.data)

        let patchJSON = """
        {"center": [0, 0], "width": \(fixture.width), "height": \(fixture.height), "channels": \(fixture.channels),
         "encoding": "\(fixture.encoding)", "data": "\(fixture.data)"}
        """
        let patch = try JSONDecoder().decode(InitStatePatchConfig.self, from: Data(patchJSON.utf8))
        XCTAssertEqual(patch.data, raw)
    }

    func testEncoderWritesTheSingleEncoding() throws {
        let patch = InitStatePatchConfig(center: [1, 1], width: 1, height: 1, channels: 1, values: [1])
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(patch)) as? [String: Any])
        XCTAssertEqual(object["encoding"] as? String, "f32le-shuffle-zlib")
    }

    func testRetiredEncodingNamesTheCompactionCommand() {
        let json = #"{"center": [0, 0], "width": 1, "height": 1, "channels": 1, "encoding": "f32le", "data": "AACAPw=="}"#
        XCTAssertThrowsError(try JSONDecoder().decode(InitStatePatchConfig.self, from: Data(json.utf8))) { error in
            XCTAssertTrue(String(describing: error).contains("lenia-swarm-analysis compact"), "\(error)")
        }
    }

    func testWrongLengthAndUnknownEncodingFail() {
        let two = FieldCodec.encode(rawLittleEndianFloat32: Data(count: 8))
        XCTAssertThrowsError(try FieldCodec.decode(base64: two, byteCount: 12))
        XCTAssertThrowsError(try FieldCodec.decode(base64: two, byteCount: 4))
        XCTAssertThrowsError(try FieldCodec.validate(encoding: "f16"))
    }
}
