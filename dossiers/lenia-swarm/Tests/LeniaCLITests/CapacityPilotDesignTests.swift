import Foundation
import LeniaCore
import XCTest
@testable import LeniaCLIKit

final class CapacityPilotDesignTests: XCTestCase {
    private var directory: URL!

    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent("capacity-design-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try FileManager.default.removeItem(at: directory)
    }

    private func sha(_ url: URL) throws -> String { ProvenanceDigest.sha256Hex(try Data(contentsOf: url)) }

    /// A 64 x 64 two-channel wall runtime: the cpu engine needs power-of-two sides and the paper profile fixes the patch at 40.
    private func runtimeFile() throws -> [String: Any] {
        let config: [String: Any] = [
            "backend": "cpu", "profile": "paper", "grid": ["sx": 64, "sy": 64], "channels": 2,
            "connectivity": [[1, 1], [1, 1]], "flow": ["dt": 0.2, "n": 2, "theta_A": 2.0],
            "reintegration": ["dd": 5, "sigma": 0.65, "border": "wall"],
            "implementation": ["mode": "flowlenia_2022_paper_equations"],
            "parameter_embedding": ["enabled": false, "mix": "avg"],
            "params": ["mode": "random", "seed": 0,
                       "ranges": ["r": [0.2, 1.0], "b": [0.0, 1.0], "w": [0.01, 0.5], "a": [0.0, 1.0], "m": [0.05, 0.5],
                                  "s": [0.001, 0.2], "h": [0.0, 1.0], "R": [2.0, 25.0]]],
            "init": ["seed": 0, "patches": [["center": [32, 32], "size": 40]], "a_uniform": ["low": 0, "high": 1]],
            "run": ["steps": 64], "interventions": [],
        ]
        let url = directory.appendingPathComponent("runtime.json")
        try JSONSerialization.data(withJSONObject: config, options: [.sortedKeys]).write(to: url)
        return ["path": "runtime.json", "sha256": try sha(url)]
    }

    private func design(_ edit: (inout [String: Any]) throws -> Void = { _ in }) throws -> URL {
        let row = [0.5, 0.5, 0.5]
        var design: [String: Any] = [
            "runtime": ["config": try runtimeFile(), "backend": "cpu", "border": "wall"],
            "bodies": [[
                "specimen_id": "tiny", "init_seed": 0,
                "params": ["R": 6, "r": [0.42, 0.55, 0.68, 0.81], "m": [0.12, 0.16, 0.2, 0.24],
                           "s": [0.035, 0.04, 0.045, 0.05], "h": [0.3, 0.4, 0.5, 0.6],
                           "a": [row, row, row, row], "b": Array(repeating: [1, 0, 0], count: 4),
                           "w": Array(repeating: [0.16, 0.2, 0.16], count: 4)],
            ]],
            "study": ["kind": "write-release", "checkpoint_steps": 32, "write_mode": "positive", "write_dose": 0.04,
                      "release_steps": 64],
            "ensemble": ["members": 3, "perturbed_cells": 1, "seed": 7],
            "repeat_check": ["members": 3],
            "outcomes": [
                "continuous": [
                    ["name": "path", "measure": "centroid_path", "branches": ["release"], "from_step": 0, "to_step": 64],
                    ["name": "coherence", "measure": "min_coherence", "branches": ["release"], "from_step": 0, "to_step": 64],
                ],
                "binary": [["name": "held", "all": [["outcome": "coherence", "op": ">=", "value": 0.5]]]],
            ],
        ]
        try edit(&design)
        let url = directory.appendingPathComponent("design.json")
        try JSONSerialization.data(withJSONObject: design, options: [.sortedKeys, .prettyPrinted]).write(to: url)
        return url
    }

    private func assertRejected(_ message: String, file: StaticString = #filePath, line: UInt = #line,
                                _ edit: (inout [String: Any]) throws -> Void) throws {
        let url = try design(edit)
        XCTAssertThrowsError(try CapacityPilotDesign.load(url), file: file, line: line) { error in
            XCTAssertTrue("\(error)".contains(message), "\(error)", file: file, line: line)
        }
    }

    private func set(_ design: inout [String: Any], _ section: String, _ key: String, _ value: Any?) {
        var object = design[section] as! [String: Any]
        object[key] = value
        design[section] = object
    }

    private func setBody(_ design: inout [String: Any], _ key: String, _ value: Any?) {
        var bodies = design["bodies"] as! [[String: Any]]
        bodies[0][key] = value
        design["bodies"] = bodies
    }

    func testDesignParsesStudyEnsembleAndOutcomes() throws {
        let plan = try CapacityPilotDesign.load(try design())
        XCTAssertEqual(plan.backend, .cpu)
        XCTAssertEqual(plan.members, 3)
        XCTAssertEqual(plan.repeatMembers, 3)
        XCTAssertEqual(plan.bodies.map(\.id), ["tiny"])
        XCTAssertEqual(plan.bodies[0].runtime.sx, 64)
        XCTAssertEqual(plan.study.branches.map(\.name), ["release"])
        XCTAssertEqual(plan.continuous.map(\.name), ["path", "coherence"])
        XCTAssertEqual(plan.binary.map(\.name), ["held"])
        XCTAssertEqual(plan.inputs.count, 2)
    }

    func testDesignRejectsAmbiguousOrInconsistentFields() throws {
        try assertRejected("design.study: unknown keys horizon") { set(&$0, "study", "horizon", 128) }
        try assertRejected("design: unknown keys extra") { $0["extra"] = true }
        try assertRejected("design.study.release_steps: required") { set(&$0, "study", "release_steps", nil) }
        try assertRejected("design.ensemble.members: expected an integer") { set(&$0, "ensemble", "members", "3") }
        try assertRejected("design.runtime.backend: must be mlx, metal-full or cpu") { set(&$0, "runtime", "backend", "metal") }
        try assertRejected("design.runtime.config: runtime.json has sha256") {
            set(&$0, "runtime", "config", ["path": "runtime.json", "sha256": String(repeating: "0", count: 64)])
        }
        try assertRejected("design.repeat_check.members: must lie in 1...3") { set(&$0, "repeat_check", "members", 4) }
        try assertRejected("design.study.kind: unknown study") { set(&$0, "study", "kind", "wobble") }
        try assertRejected("design.study.release_steps: must be a non-negative multiple of 32") {
            set(&$0, "study", "release_steps", 40)
        }
        try assertRejected("emits no branch challenge") {
            set(&$0, "outcomes", "continuous", [["name": "path", "measure": "centroid_path", "branches": ["challenge"],
                                                 "from_step": 0, "to_step": 64]])
            set(&$0, "outcomes", "binary", [])
        }
        try assertRejected("design.bodies[0].diameter: required by a centroid_path_diameters outcome") {
            set(&$0, "outcomes", "continuous", [["name": "path", "measure": "centroid_path_diameters", "branches": ["release"],
                                                 "from_step": 0, "to_step": 64]])
            set(&$0, "outcomes", "binary", [])
        }
        try assertRejected("design.bodies[0].field: unused") {
            let url = self.directory.appendingPathComponent("field.f32")
            try Data(count: 64 * 64 * 2 * 4).write(to: url)
            setBody(&$0, "field", ["path": "field.f32", "sha256": try self.sha(url)])
        }
        try assertRejected("needs backend metal-full; the cpu engine has no phantom field") {
            $0["study"] = ["kind": "development", "horizon": 64,
                           "phantom": ["source": "static", "pressure": true, "field": ["path": "x", "sha256": "y"]]]
            set(&$0, "outcomes", "continuous", [])
            set(&$0, "outcomes", "binary", [])
        }
        try assertRejected("needs backend metal-full; the cpu engine has no founder-mass transport") {
            $0["study"] = ["kind": "development", "horizon": 64,
                           "ancestry": ["founders": 1, "export_steps": [0], "labels": ["path": "x", "sha256": "y"]]]
            set(&$0, "outcomes", "continuous", [])
            set(&$0, "outcomes", "binary", [])
        }
        try assertRejected("write-release needs at least two channels and a wall border") { set(&$0, "runtime", "border", "torus") }
    }

    func testDesignRunRepeatsBitForBitOnCPU() throws {
        let url = try design()
        let first = directory.appendingPathComponent("first")
        let second = directory.appendingPathComponent("second")
        let output = try runLeniaCLI(arguments: ["discover", "capacity-pilot", "--design", url.path, "--output", first.path])
        XCTAssertTrue(output.contains("repeat check cpu: "))
        try runLeniaCLI(arguments: ["discover", "capacity-pilot", "--design", url.path, "--output", second.path])

        XCTAssertEqual(try Data(contentsOf: first.appendingPathComponent("design.json")), try Data(contentsOf: url))
        let receipt = try String(contentsOf: first.appendingPathComponent("receipt.json"), encoding: .utf8)
        XCTAssertTrue(receipt.contains(try sha(url)))

        for member in 0..<3 {
            let a = first.appendingPathComponent("tiny/member-\(member)")
            let b = second.appendingPathComponent("tiny/member-\(member)")
            let names = try FileManager.default.contentsOfDirectory(atPath: a.path).sorted()
            XCTAssertEqual(names, try FileManager.default.contentsOfDirectory(atPath: b.path).sorted())
            XCTAssertTrue(names.contains("release-step-64.f32"))
            for name in names {
                XCTAssertEqual(try sha(a.appendingPathComponent(name)), try sha(b.appendingPathComponent(name)), "member-\(member)/\(name)")
            }
        }
        XCTAssertNotEqual(try sha(first.appendingPathComponent("tiny/member-0/release-step-64.f32")),
                          try sha(first.appendingPathComponent("tiny/member-1/release-step-64.f32")))
        XCTAssertEqual(try sha(first.appendingPathComponent("ensemble.json")), try sha(second.appendingPathComponent("ensemble.json")))

        let summary = try XCTUnwrap(JSONSerialization.jsonObject(
            with: Data(contentsOf: first.appendingPathComponent("ensemble.json"))) as? [String: Any])
        let repeatCheck = try XCTUnwrap(summary["repeatCheck"] as? [String: Any])
        XCTAssertEqual(repeatCheck["matchRate"] as? Double, 1)
        let conditions = try XCTUnwrap(summary["conditions"] as? [[String: Any]])
        XCTAssertEqual(conditions.count, 1)
        XCTAssertEqual((conditions[0]["members"] as? [Any])?.count, 3)
        let held = try XCTUnwrap((conditions[0]["probabilities"] as? [String: Any])?["held"] as? [String: Any])
        XCTAssertEqual((held["defined"] as? Int).map { $0 + (held["undefined"] as! Int) }, 3)
        XCTAssertNotNil(summary["variance"] as? [String: Any])

        XCTAssertThrowsError(try runLeniaCLI(arguments: ["discover", "capacity-pilot", "--design", url.path, "--output", first.path]))
    }
}
