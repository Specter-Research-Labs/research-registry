import XCTest
@testable import LeniaArchive

final class WarehouseBridgeTests: XCTestCase {
    func testWarehouseCLIConcurrentlyDrainsLargeOutputStreams() throws {
        let byteCount = 1_048_576
        let script = """
        /usr/bin/yes x | /usr/bin/head -c \(byteCount)
        /usr/bin/yes y | /usr/bin/head -c \(byteCount) >&2
        """

        let stdout = try runWarehouseCLI(arguments: ["sh", "-c", script])

        XCTAssertEqual(stdout.count, byteCount)
    }
}
