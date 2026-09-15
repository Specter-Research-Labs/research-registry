import MLX
import XCTest
@testable import LeniaCore

final class FlowLeniaSpatialConventionTests: XCTestCase {
    override func setUpWithError() throws {
        try LeniaMetalLibrarySupport.ensureAvailable()
    }

    func testSobelHasPositiveDerivativeInArrayAxisOrder() {
        let sx = 9, sy = 12
        for boundary in ["zero_pad", "periodic"] {
            for axis in 0..<2 {
                for sign: Float in [-1, 1] {
                    let values = (0..<sx).flatMap { x in
                        (0..<sy).map { y in sign * Float(axis == 0 ? x : y) }
                    }
                    let field = MLXArray(values).reshaped([1, sx, sy, 1])
                    let gradient = sobelBatched(field, gradientBoundary: boundary)
                    XCTAssertEqual(gradient[0, 4, 5, axis, 0].item(Float.self), 8 * sign, accuracy: 1e-6)
                    XCTAssertEqual(gradient[0, 4, 5, 1 - axis, 0].item(Float.self), 0, accuracy: 1e-6)
                }
            }
        }
    }

    func testTransportMovesAlongItsOwnAxisIncludingRectangularEdges() {
        let sx = 9, sy = 12
        let pos = flowSensorimotorPosGrid(sx: sx, sy: sy)
        for torus in [false, true] {
            for axis in 0..<2 {
                for sign in [-1, 1] {
                    for edge in [false, true] {
                        var start = [4, 5]
                        if edge { start[axis] = sign < 0 ? 0 : (axis == 0 ? sx : sy) - 1 }
                        var values = [Float](repeating: 0, count: sx * sy)
                        values[start[0] * sy + start[1]] = 1
                        var flow = [Float](repeating: 0, count: sx * sy * 2)
                        for i in 0..<(sx * sy) { flow[i * 2 + axis] = Float(sign) }
                        let result = reintegrationBatched(MLXArray(values).reshaped([1, sx, sy, 1]),
                            F: MLXArray(flow).reshaped([1, sx, sy, 2, 1]), posGrid: pos,
                            dt: 1, dd: 2, sigma: 0.5, useTorus: torus, sx: sx, sy: sy).asArray(Float.self)
                        var target = start
                        let limit = axis == 0 ? sx : sy
                        target[axis] = torus ? (start[axis] + sign + limit) % limit : min(limit - 1, max(0, start[axis] + sign))
                        XCTAssertEqual(result[target[0] * sy + target[1]], 1, accuracy: 1e-6,
                                       "torus=\(torus), axis=\(axis), sign=\(sign), edge=\(edge)")
                        XCTAssertEqual(result.reduce(0, +), 1, accuracy: 1e-6)
                    }
                }
            }
        }
    }
}
