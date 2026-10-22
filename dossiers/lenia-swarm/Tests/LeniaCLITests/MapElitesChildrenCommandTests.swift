import Foundation
import XCTest
@testable import LeniaCLIKit

final class MapElitesChildrenCommandTests: XCTestCase {
    func testChildSeedsDependOnCellIdAndIndexOnly() {
        let seed = mapElitesChildSeed(specSeed: 20_261_022, cell: "params-0p1", index: 7)
        XCTAssertEqual(seed, mapElitesChildSeed(specSeed: 20_261_022, cell: "params-0p1", index: 7))
        XCTAssertNotEqual(seed, mapElitesChildSeed(specSeed: 20_261_022, cell: "params-0p1", index: 8))
        XCTAssertNotEqual(seed, mapElitesChildSeed(specSeed: 20_261_022, cell: "patch-0p1", index: 7))
        XCTAssertNotEqual(seed, mapElitesChildSeed(specSeed: 20_261_023, cell: "params-0p1", index: 7))
    }

    func testSpecDecodesSnakeCaseKeysAndSelfPairing() throws {
        let json = """
        {
          "run_id": "search-g0",
          "seed": 11,
          "lineages": [{"id": "a", "run_dir": "runs/a", "parents": ["0F6E31B1-6A43-4C9B-9E0B-8A7D2C1F4E55"]}],
          "cells": [{"id": "zero", "pairing": "self", "mutate": "both", "sigma": 0, "line_sigma": 0,
                     "children": 4, "start": 0, "lineages": ["a"]}]
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let spec = try decoder.decode(MapElitesChildrenSpec.self, from: Data(json.utf8))
        XCTAssertEqual(spec.lineages.first?.runDir, "runs/a")
        XCTAssertEqual(spec.cells.first?.pairing, .same)
        XCTAssertEqual(spec.cells.first?.mutate, .both)
        XCTAssertEqual(spec.cells.first?.lineSigma, 0)
    }
}
