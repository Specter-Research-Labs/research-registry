import XCTest
@testable import LeniaCore

final class UnseenObstacleResponseTests: XCTestCase {
    func testImplementationGuardAcceptsFlowLeniaAndRejectsAdditiveLenia() {
        XCTAssertTrue(unseenObstacleSupportsImplementationMode("flowlenia_2022_paper_equations"))
        XCTAssertTrue(unseenObstacleSupportsImplementationMode("flowlenia_2022_colab"))
        XCTAssertFalse(unseenObstacleSupportsImplementationMode("qd24_additive_v1"))
        XCTAssertFalse(unseenObstacleSupportsImplementationMode("custom"))
        XCTAssertNoThrow(try validateUnseenObstacleImplementationMode("flowlenia_2022_paper_equations"))
        XCTAssertThrowsError(try validateUnseenObstacleImplementationMode("qd24_additive_v1")) { error in
            guard case UnseenObstacleResponseError.unsupportedImplementation(let mode) = error else {
                return XCTFail("unexpected error: \(error)")
            }
            XCTAssertEqual(mode, "qd24_additive_v1")
        }
    }

    func testLargestBodyUsesPeriodicEightNeighborConnectivityAndCircularCentroid() throws {
        var values = [Float](repeating: 0, count: 8 * 8)
        values[7 * 8 + 3] = 1
        values[0 * 8 + 3] = 1
        values[4 * 8 + 4] = 0.2

        let periodic = try XCTUnwrap(unseenObstacleLargestBody(
            values: values,
            width: 8,
            height: 8,
            threshold: 0.1,
            periodic: true
        ))
        let wall = try XCTUnwrap(unseenObstacleLargestBody(
            values: values,
            width: 8,
            height: 8,
            threshold: 0.1,
            periodic: false
        ))

        XCTAssertEqual(periodic.indices.count, 2)
        XCTAssertEqual(periodic.mass, 2, accuracy: 1e-6)
        XCTAssertEqual(periodic.massFraction, 2 / 2.2, accuracy: 1e-6)
        XCTAssertEqual(periodic.center.x, 7.5, accuracy: 1e-4)
        XCTAssertEqual(periodic.center.y, 3, accuracy: 1e-4)
        XCTAssertEqual(periodic.radius95, 0.5, accuracy: 1e-4)
        XCTAssertEqual(periodic.radius99, 0.5, accuracy: 1e-4)
        XCTAssertEqual(wall.indices.count, 1)
    }

    func testLargestBodyScaleIgnoresDisconnectedRemoteDebris() throws {
        var values = [Float](repeating: 0, count: 16 * 16)
        for x in 7...9 {
            for y in 7...9 {
                values[x * 16 + y] = 1
            }
        }
        values[0] = 0.5

        let body = try XCTUnwrap(unseenObstacleLargestBody(
            values: values,
            width: 16,
            height: 16,
            threshold: 0.1,
            periodic: false
        ))

        XCTAssertEqual(body.indices.count, 9)
        XCTAssertEqual(body.center.x, 8, accuracy: 1e-6)
        XCTAssertEqual(body.center.y, 8, accuracy: 1e-6)
        XCTAssertEqual(body.radius95, Float(2).squareRoot(), accuracy: 1e-6)
        XCTAssertEqual(body.radius99, Float(2).squareRoot(), accuracy: 1e-6)
        XCTAssertEqual(body.massFraction, 9 / 9.5, accuracy: 1e-6)
    }

    func testPlacementRejectsClippedWallDiskButAllowsWrappedTorusDisk() {
        XCTAssertFalse(unseenObstaclePlacementFits(
            center: (x: 4, y: 16),
            radius: 4,
            margin: 1,
            width: 32,
            height: 32,
            periodic: false
        ))
        XCTAssertTrue(unseenObstaclePlacementFits(
            center: (x: 4, y: 16),
            radius: 4,
            margin: 1,
            width: 32,
            height: 32,
            periodic: true
        ))
        XCTAssertFalse(unseenObstaclePlacementFits(
            center: (x: 16, y: 16),
            radius: 15,
            margin: 1,
            width: 32,
            height: 32,
            periodic: true
        ))
    }

    func testClearanceUsesToroidalDistance() throws {
        let wall = try XCTUnwrap(unseenObstacleMinimumClearance(
            indices: [31 * 32 + 10],
            obstacleCenter: (x: 1, y: 10),
            obstacleRadius: 1,
            width: 32,
            height: 32,
            periodic: false
        ))
        let torus = try XCTUnwrap(unseenObstacleMinimumClearance(
            indices: [31 * 32 + 10],
            obstacleCenter: (x: 1, y: 10),
            obstacleRadius: 1,
            width: 32,
            height: 32,
            periodic: true
        ))

        XCTAssertEqual(wall, 29, accuracy: 1e-6)
        XCTAssertEqual(torus, 1, accuracy: 1e-6)
    }

    func testShamPredictedInterceptChoosesFirstInitiallyClearFutureEncounter() throws {
        let width = 64
        let checkpoint = UnseenObstacleBodyMeasurement(
            mass: 1,
            massFraction: 1,
            center: (x: 10, y: 10),
            radius95: 0,
            radius99: 0,
            indices: [10 * width + 10]
        )
        let samples = [
            UnseenObstacleShamSample(
                step: 10,
                body: UnseenObstacleBodyMeasurement(
                    mass: 1,
                    massFraction: 1,
                    center: (x: 12, y: 10),
                    radius95: 0,
                    radius99: 0,
                    indices: [12 * width + 10]
                )
            ),
            UnseenObstacleShamSample(
                step: 20,
                body: UnseenObstacleBodyMeasurement(
                    mass: 1,
                    massFraction: 1,
                    center: (x: 20, y: 10),
                    radius95: 0,
                    radius99: 0,
                    indices: [20 * width + 10]
                )
            ),
        ]

        let intercept = try XCTUnwrap(unseenObstacleFindShamPredictedIntercept(
            checkpointBody: checkpoint,
            samples: samples,
            normal: (x: 0, y: 1),
            obstacleRadius: 2,
            lateralOffset: 2,
            minimumInitialClearance: 2,
            contactDistance: 0,
            boundaryMargin: 1,
            width: width,
            height: width,
            periodic: false
        ))

        XCTAssertEqual(intercept.step, 20)
        XCTAssertEqual(try XCTUnwrap(intercept.centers[.ahead]).x, 20, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(intercept.centers[.left]).y, 12, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(intercept.centers[.right]).y, 8, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(intercept.predictedClearances[.ahead]), -2, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(intercept.predictedClearances[.left]), 0, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(intercept.predictedClearances[.right]), 0, accuracy: 1e-6)
    }

    func testShamPredictedInterceptFailsWhenTravelCannotClearCheckpointBody() {
        let width = 32
        let body = UnseenObstacleBodyMeasurement(
            mass: 1,
            massFraction: 1,
            center: (x: 10, y: 10),
            radius95: 0,
            radius99: 0,
            indices: [10 * width + 10]
        )
        let slow = UnseenObstacleShamSample(
            step: 100,
            body: UnseenObstacleBodyMeasurement(
                mass: 1,
                massFraction: 1,
                center: (x: 11, y: 10),
                radius95: 0,
                radius99: 0,
                indices: [11 * width + 10]
            )
        )

        XCTAssertNil(unseenObstacleFindShamPredictedIntercept(
            checkpointBody: body,
            samples: [slow],
            normal: (x: 0, y: 1),
            obstacleRadius: 2,
            lateralOffset: 1,
            minimumInitialClearance: 2,
            contactDistance: 0,
            boundaryMargin: 1,
            width: width,
            height: width,
            periodic: false
        ))
    }
}
