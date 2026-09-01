import Foundation
import XCTest
@testable import LeniaCLIKit

final class ObstacleResponseCommandTests: XCTestCase {
    func testCorpusRowDecodesCompendiumReplayPayloads() throws {
        let genotype = """
        {"R":12,"r":[0.5],"b":[[1]],"w":[[0.2]],"a":[[0.3]],"m":[0.15],"s":[0.02],"h":[1]}
        """
        let initialCondition = """
        {"seed":41,"patches":[{"center":[16,16],"size":8}],"a_uniform":{"low":0.2,"high":0.8},"p_uniform":null,"state_patch":null,"p_state_patch":null}
        """
        let payload: [String: Any] = [
            "specimen_id": "specimen-1",
            "life_id": "life-41",
            "family": "97b",
            "map_id": "historical-12d",
            "rule_id": "rule-1",
            "genotype_json": genotype,
            "initial_condition_json": initialCondition,
        ]
        let data = try JSONSerialization.data(withJSONObject: payload)

        let row = try JSONDecoder().decode(CorpusRow.self, from: data)

        XCTAssertEqual(row.specimenId, "specimen-1")
        XCTAssertEqual(row.lifeId, "life-41")
        XCTAssertEqual(row.family, "97b")
        XCTAssertEqual(row.mapId, "historical-12d")
        XCTAssertEqual(row.ruleId, "rule-1")
        XCTAssertEqual(row.params.R, 12)
        XCTAssertEqual(row.initialCondition?.seed, 41)
        XCTAssertEqual(row.initSeed, 41)
    }

    func testCorpusRowRejectsConflictingReplaySeed() throws {
        let genotype: [String: Any] = [
            "R": 12,
            "r": [0.5],
            "b": [[1.0]],
            "w": [[0.2]],
            "a": [[0.3]],
            "m": [0.15],
            "s": [0.02],
            "h": [1.0],
        ]
        let initialCondition: [String: Any] = [
            "seed": 41,
            "patches": [["center": [16, 16], "size": 8]],
            "a_uniform": ["low": 0.2, "high": 0.8],
            "p_uniform": NSNull(),
            "state_patch": NSNull(),
            "p_state_patch": NSNull(),
        ]
        let payload: [String: Any] = [
            "specimen_id": "specimen-1",
            "genotype_json": genotype,
            "initial_condition_json": initialCondition,
            "init_seed": 42,
        ]
        let data = try JSONSerialization.data(withJSONObject: payload)

        XCTAssertThrowsError(try JSONDecoder().decode(CorpusRow.self, from: data))
    }

    func testCorpusRowDecodesFrozenNestedReplay() throws {
        let payload = """
        {
          "specimen_id": "frozen-1",
          "life_id": "life-7",
          "replay": {
            "genotype": {"R":12,"r":[0.5],"b":[[1]],"w":[[0.2]],"a":[[0.3]],"m":[0.15],"s":[0.02],"h":[1]},
            "initial_condition": {"seed":7,"patches":[{"center":[16,16],"size":8}],"a_uniform":{"low":0.2,"high":0.8},"p_uniform":null,"state_patch":null,"p_state_patch":null}
          }
        }
        """

        let row = try JSONDecoder().decode(CorpusRow.self, from: Data(payload.utf8))

        XCTAssertEqual(row.specimenId, "frozen-1")
        XCTAssertEqual(row.params.R, 12)
        XCTAssertEqual(row.initialCondition?.seed, 7)
        XCTAssertEqual(row.initSeed, 7)
    }
}
