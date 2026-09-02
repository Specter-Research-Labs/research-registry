import Foundation
import MLX

public struct UnseenObstacleResponseProtocol: Codable, Sendable {
    public let checkpointSteps: Int
    public let headingWindow: Int
    public let continuationSteps: Int
    public let metricStride: Int
    public let obstacleRadiusBodyRatio: Float
    public let obstacleGapBodyRatio: Float
    public let lateralOffsetBodyRatio: Float
    public let matterThreshold: Float
    public let contactDistance: Float
    public let survivalMassFraction: Float
    public let minimumHeadingDisplacement: Float
    public let minimumPostDisplacement: Float
    public let minimumLargestComponentMassFraction: Float
    public let maximumBodyR99GridFraction: Float
    public let maximumBodyScaleRatio: Float
    public let minimumInitialClearance: Float
    public let obstacleBoundaryMargin: Float
    public let obstaclePotentialHeight: Float

    public init(
        checkpointSteps: Int = 160,
        headingWindow: Int = 40,
        continuationSteps: Int = 400,
        metricStride: Int = 1,
        obstacleRadiusBodyRatio: Float = 0.5,
        obstacleGapBodyRatio: Float = 0.15,
        lateralOffsetBodyRatio: Float = 0.5,
        matterThreshold: Float = 0.05,
        contactDistance: Float = 1.5,
        survivalMassFraction: Float = 0.8,
        minimumHeadingDisplacement: Float = 2,
        minimumPostDisplacement: Float = 2,
        minimumLargestComponentMassFraction: Float = 0.8,
        maximumBodyR99GridFraction: Float = 0.1875,
        maximumBodyScaleRatio: Float = 2,
        minimumInitialClearance: Float = 2,
        obstacleBoundaryMargin: Float = 2,
        obstaclePotentialHeight: Float = 30
    ) {
        self.checkpointSteps = checkpointSteps
        self.headingWindow = headingWindow
        self.continuationSteps = continuationSteps
        self.metricStride = metricStride
        self.obstacleRadiusBodyRatio = obstacleRadiusBodyRatio
        self.obstacleGapBodyRatio = obstacleGapBodyRatio
        self.lateralOffsetBodyRatio = lateralOffsetBodyRatio
        self.matterThreshold = matterThreshold
        self.contactDistance = contactDistance
        self.survivalMassFraction = survivalMassFraction
        self.minimumHeadingDisplacement = minimumHeadingDisplacement
        self.minimumPostDisplacement = minimumPostDisplacement
        self.minimumLargestComponentMassFraction = minimumLargestComponentMassFraction
        self.maximumBodyR99GridFraction = maximumBodyR99GridFraction
        self.maximumBodyScaleRatio = maximumBodyScaleRatio
        self.minimumInitialClearance = minimumInitialClearance
        self.obstacleBoundaryMargin = obstacleBoundaryMargin
        self.obstaclePotentialHeight = obstaclePotentialHeight
    }

    enum CodingKeys: String, CodingKey {
        case checkpointSteps = "checkpoint_steps"
        case headingWindow = "heading_window"
        case continuationSteps = "continuation_steps"
        case metricStride = "metric_stride"
        case obstacleRadiusBodyRatio = "obstacle_radius_body_ratio"
        case obstacleGapBodyRatio = "obstacle_gap_body_ratio"
        case lateralOffsetBodyRatio = "lateral_offset_body_ratio"
        case matterThreshold = "matter_threshold"
        case contactDistance = "contact_distance"
        case survivalMassFraction = "survival_mass_fraction"
        case minimumHeadingDisplacement = "minimum_heading_displacement"
        case minimumPostDisplacement = "minimum_post_displacement"
        case minimumLargestComponentMassFraction = "minimum_largest_component_mass_fraction"
        case maximumBodyR99GridFraction = "maximum_body_r99_grid_fraction"
        case maximumBodyScaleRatio = "maximum_body_scale_ratio"
        case minimumInitialClearance = "minimum_initial_clearance"
        case obstacleBoundaryMargin = "obstacle_boundary_margin"
        case obstaclePotentialHeight = "obstacle_potential_height"
    }
}

public struct UnseenObstacleSpecimen: Sendable {
    public let specimenId: String
    public let lifeId: String
    public let family: String?
    public let mapId: String?
    public let ruleId: String?
    public let initSeed: Int

    public init(
        specimenId: String,
        lifeId: String,
        family: String? = nil,
        mapId: String? = nil,
        ruleId: String? = nil,
        initSeed: Int
    ) {
        self.specimenId = specimenId
        self.lifeId = lifeId
        self.family = family
        self.mapId = mapId
        self.ruleId = ruleId
        self.initSeed = initSeed
    }
}

public enum UnseenObstacleBranch: String, Codable, Sendable, CaseIterable {
    case sham
    case ahead
    case left
    case right
}

public struct UnseenObstacleResponseRecord: Codable, Sendable {
    public let specimenId: String
    public let lifeId: String
    public let family: String?
    public let mapId: String?
    public let ruleId: String?
    public let initSeed: Int
    public let branch: UnseenObstacleBranch
    public let exposed: Bool
    public let completed: Bool
    public let calibrationPassed: Bool
    public let failureReason: String?
    public let survived: Bool
    public let contact: Bool
    public let timeToContact: Int?
    public let targetEncounterStep: Int?
    public let shamPredictedClearance: Float?
    public let minClearance: Float?
    public let turnAngle: Float?
    public let lateralDisplacement: Float?
    public let retainedMass: Float
    public let checkpointStep: Int
    public let continuationSteps: Int
    public let checkpointMass: Float
    public let finalMass: Float
    public let checkpointCenterX: Float?
    public let checkpointCenterY: Float?
    public let checkpointHeadingX: Float?
    public let checkpointHeadingY: Float?
    public let finalCenterX: Float?
    public let finalCenterY: Float?
    public let obstacleCenterX: Float?
    public let obstacleCenterY: Float?
    public let bodyRadius: Float?
    public let bodyRadiusR99: Float?
    public let checkpointLargestComponentMassFraction: Float?
    public let finalLargestComponentMassFraction: Float?
    public let finalBodyRadius: Float?
    public let finalBodyRadiusR99: Float?
    public let postDisplacement: Float?
    public let obstacleRadius: Float?

    enum CodingKeys: String, CodingKey {
        case specimenId = "specimen_id"
        case lifeId = "life_id"
        case family
        case mapId = "map_id"
        case ruleId = "rule_id"
        case initSeed = "init_seed"
        case branch
        case exposed
        case completed
        case calibrationPassed = "calibration_passed"
        case failureReason = "failure_reason"
        case survived
        case contact
        case timeToContact = "time_to_contact"
        case targetEncounterStep = "target_encounter_step"
        case shamPredictedClearance = "sham_predicted_clearance"
        case minClearance = "min_clearance"
        case turnAngle = "turn_angle"
        case lateralDisplacement = "lateral_displacement"
        case retainedMass = "retained_mass"
        case checkpointStep = "checkpoint_step"
        case continuationSteps = "continuation_steps"
        case checkpointMass = "checkpoint_mass"
        case finalMass = "final_mass"
        case checkpointCenterX = "checkpoint_center_x"
        case checkpointCenterY = "checkpoint_center_y"
        case checkpointHeadingX = "checkpoint_heading_x"
        case checkpointHeadingY = "checkpoint_heading_y"
        case finalCenterX = "final_center_x"
        case finalCenterY = "final_center_y"
        case obstacleCenterX = "obstacle_center_x"
        case obstacleCenterY = "obstacle_center_y"
        case bodyRadius = "body_radius"
        case bodyRadiusR99 = "body_radius_r99"
        case checkpointLargestComponentMassFraction = "checkpoint_largest_component_mass_fraction"
        case finalLargestComponentMassFraction = "final_largest_component_mass_fraction"
        case finalBodyRadius = "final_body_radius"
        case finalBodyRadiusR99 = "final_body_radius_r99"
        case postDisplacement = "post_displacement"
        case obstacleRadius = "obstacle_radius"
    }
}

public enum UnseenObstacleResponseError: LocalizedError {
    case invalidProtocol(String)
    case unsupportedImplementation(String)

    public var errorDescription: String? {
        switch self {
        case .invalidProtocol(let message):
            return "Invalid unseen-obstacle protocol: \(message)"
        case .unsupportedImplementation(let mode):
            return "Unsupported unseen-obstacle implementation mode: \(mode). The wall-potential assay currently requires Flow-Lenia equations."
        }
    }
}

public final class UnseenObstacleResponseHarness {
    private let simulator: FlowLeniaInteractiveSimulator
    private let protocolConfig: UnseenObstacleResponseProtocol
    private let periodic: Bool

    public init(runtimeConfig: LeniaRuntimeConfig, protocol protocolConfig: UnseenObstacleResponseProtocol) throws {
        try validateUnseenObstacleImplementationMode(runtimeConfig.implementation.mode)
        guard protocolConfig.checkpointSteps > 0 else {
            throw UnseenObstacleResponseError.invalidProtocol("checkpointSteps must be positive")
        }
        guard protocolConfig.headingWindow > 0,
              protocolConfig.headingWindow < protocolConfig.checkpointSteps else {
            throw UnseenObstacleResponseError.invalidProtocol("headingWindow must be between zero and checkpointSteps")
        }
        guard protocolConfig.continuationSteps > 0, protocolConfig.metricStride == 1 else {
            throw UnseenObstacleResponseError.invalidProtocol("continuationSteps must be positive and metricStride must be 1 for event-complete geometry")
        }
        guard protocolConfig.obstacleRadiusBodyRatio > 0,
              protocolConfig.obstacleGapBodyRatio >= 0,
              protocolConfig.lateralOffsetBodyRatio >= 0 else {
            throw UnseenObstacleResponseError.invalidProtocol("obstacle body ratios must be non-negative and radius ratio must be positive")
        }
        guard protocolConfig.matterThreshold > 0,
              protocolConfig.contactDistance >= 0,
              (0...1).contains(protocolConfig.survivalMassFraction),
              protocolConfig.minimumHeadingDisplacement > 0,
              protocolConfig.minimumPostDisplacement > 0,
              (0...1).contains(protocolConfig.minimumLargestComponentMassFraction),
              protocolConfig.maximumBodyR99GridFraction > 0,
              protocolConfig.maximumBodyR99GridFraction < 0.5,
              protocolConfig.maximumBodyScaleRatio >= 1,
              protocolConfig.minimumInitialClearance >= 0,
              protocolConfig.obstacleBoundaryMargin >= 0,
              protocolConfig.obstaclePotentialHeight > 0 else {
            throw UnseenObstacleResponseError.invalidProtocol("measurement, coherence, placement, and potential thresholds are out of range")
        }
        self.simulator = FlowLeniaInteractiveSimulator(runtimeConfig: runtimeConfig)
        self.protocolConfig = protocolConfig
        self.periodic = runtimeConfig.border == "torus"
    }

    public func run(specimen: UnseenObstacleSpecimen) -> [UnseenObstacleResponseRecord] {
        simulator.clearCircularWallPotential()
        simulator.clearHardObstacle()
        let initial = simulator.makeInitialState(seedOverride: specimen.initSeed)
        let headingState = simulator.step(
            initial,
            count: protocolConfig.checkpointSteps - protocolConfig.headingWindow
        )
        let checkpoint = simulator.step(headingState, count: protocolConfig.headingWindow)
        let headingFrame = measure(state: headingState)
        let checkpointFrame = measure(state: checkpoint)

        guard let headingBody = headingFrame.body,
              let checkpointBody = checkpointFrame.body,
              checkpointFrame.totalMass > 0 else {
            return failedCalibrationRecords(
                specimen: specimen,
                checkpoint: checkpointFrame,
                reason: "no_thresholded_component_at_checkpoint"
            )
        }

        let minimumComponentFraction = protocolConfig.minimumLargestComponentMassFraction
        guard headingBody.massFraction >= minimumComponentFraction,
              checkpointBody.massFraction >= minimumComponentFraction else {
            return failedCalibrationRecords(
                specimen: specimen,
                checkpoint: checkpointFrame,
                reason: "insufficient_largest_component_mass_fraction"
            )
        }
        let maximumR99 = Float(min(simulator.runtimeConfig.sx, simulator.runtimeConfig.sy))
            * protocolConfig.maximumBodyR99GridFraction
        guard checkpointBody.radius99 <= maximumR99 else {
            return failedCalibrationRecords(
                specimen: specimen,
                checkpoint: checkpointFrame,
                reason: "body_r99_exceeds_grid_fraction"
            )
        }
        let preCheckpointScaleRatio = checkpointBody.radius99 / max(headingBody.radius99, 1e-6)
        guard preCheckpointScaleRatio <= protocolConfig.maximumBodyScaleRatio,
              preCheckpointScaleRatio >= 1 / protocolConfig.maximumBodyScaleRatio else {
            return failedCalibrationRecords(
                specimen: specimen,
                checkpoint: checkpointFrame,
                reason: "unstable_body_scale_before_checkpoint"
            )
        }

        let headingDelta = displacement(
            from: headingBody.center,
            to: checkpointBody.center,
            width: simulator.runtimeConfig.sx,
            height: simulator.runtimeConfig.sy,
            periodic: periodic
        )
        let headingMagnitude = hypot(headingDelta.x, headingDelta.y)
        guard headingMagnitude >= max(protocolConfig.minimumHeadingDisplacement, 1e-6) else {
            return failedCalibrationRecords(
                specimen: specimen,
                checkpoint: checkpointFrame,
                reason: "insufficient_pre_checkpoint_motion"
            )
        }

        let heading = (x: headingDelta.x / headingMagnitude, y: headingDelta.y / headingMagnitude)
        let normal = (x: -heading.y, y: heading.x)
        let bodyRadius = max(checkpointBody.radius95, 1)
        let obstacleRadius = bodyRadius * protocolConfig.obstacleRadiusBodyRatio
        let obstacleGap = bodyRadius * protocolConfig.obstacleGapBodyRatio
        let lateralOffset = bodyRadius * protocolConfig.lateralOffsetBodyRatio
        let shamRun = runBranch(
            .sham,
            checkpoint: checkpoint,
            checkpointBody: checkpointBody,
            checkpointCenter: checkpointBody.center,
            heading: heading,
            obstacleCenter: nil,
            obstacleRadius: obstacleRadius,
            captureTrajectory: true
        )
        let requiredInitialClearance = max(obstacleGap, protocolConfig.minimumInitialClearance)
        guard let intercept = unseenObstacleFindShamPredictedIntercept(
            checkpointBody: checkpointBody,
            samples: shamRun.trajectory,
            normal: normal,
            obstacleRadius: obstacleRadius,
            lateralOffset: lateralOffset,
            minimumInitialClearance: requiredInitialClearance,
            contactDistance: protocolConfig.contactDistance,
            boundaryMargin: protocolConfig.obstacleBoundaryMargin,
            width: simulator.runtimeConfig.sx,
            height: simulator.runtimeConfig.sy,
            periodic: periodic
        ) else {
            return failedCalibrationRecords(
                specimen: specimen,
                checkpoint: checkpointFrame,
                reason: "no_valid_sham_predicted_intercept"
            )
        }

        var provisional: [BranchRun] = [shamRun]
        provisional.reserveCapacity(UnseenObstacleBranch.allCases.count)
        for branch in [UnseenObstacleBranch.ahead, .left, .right] {
            provisional.append(runBranch(
                branch,
                checkpoint: checkpoint,
                checkpointBody: checkpointBody,
                checkpointCenter: checkpointBody.center,
                heading: heading,
                obstacleCenter: intercept.centers[branch],
                obstacleRadius: obstacleRadius
            ))
        }

        let shamFinalCenter = provisional.first(where: { $0.branch == .sham })?.finalFrame.body?.center
        return provisional.map { branchRun in
            let lateralDisplacement: Float?
            if branchRun.branch == .sham {
                lateralDisplacement = 0
            } else if let shamFinalCenter, let branchCenter = branchRun.finalFrame.body?.center {
                let difference = displacement(
                    from: shamFinalCenter,
                    to: branchCenter,
                    width: simulator.runtimeConfig.sx,
                    height: simulator.runtimeConfig.sy,
                    periodic: periodic
                )
                lateralDisplacement = difference.x * normal.x + difference.y * normal.y
            } else {
                lateralDisplacement = nil
            }
            return materializeRecord(
                specimen: specimen,
                branchRun: branchRun,
                checkpointFrame: checkpointFrame,
                checkpointCenter: checkpointBody.center,
                heading: heading,
                targetEncounterStep: intercept.step,
                shamPredictedClearance: intercept.predictedClearances[branchRun.branch],
                lateralDisplacement: lateralDisplacement
            )
        }
    }

    private struct FrameMeasurement {
        let totalMass: Float
        let body: UnseenObstacleBodyMeasurement?
        let values: [Float]
    }

    private struct BranchRun {
        let branch: UnseenObstacleBranch
        let obstacleCenter: (x: Float, y: Float)?
        let obstacleRadius: Float?
        let finalFrame: FrameMeasurement
        let contact: Bool
        let timeToContact: Int?
        let minimumClearance: Float?
        let turnAngle: Float?
        let postDisplacement: Float?
        let trajectory: [UnseenObstacleShamSample]
    }

    private func measure(state: FlowLeniaInteractiveState) -> FrameMeasurement {
        let matterMap = simulator.matterMap(for: state)
        eval(matterMap)
        let values = matterMap.asArray(Float.self)
        let mass = values.reduce(0, +)
        return FrameMeasurement(
            totalMass: mass,
            body: unseenObstacleLargestBody(
                values: values,
                width: simulator.runtimeConfig.sx,
                height: simulator.runtimeConfig.sy,
                threshold: protocolConfig.matterThreshold,
                periodic: periodic
            ),
            values: values
        )
    }

    private func runBranch(
        _ branch: UnseenObstacleBranch,
        checkpoint: FlowLeniaInteractiveState,
        checkpointBody: UnseenObstacleBodyMeasurement,
        checkpointCenter: (x: Float, y: Float),
        heading: (x: Float, y: Float),
        obstacleCenter: (x: Float, y: Float)?,
        obstacleRadius: Float,
        captureTrajectory: Bool = false
    ) -> BranchRun {
        if let obstacleCenter {
            simulator.setCircularWallPotential(
                centerX: obstacleCenter.x,
                centerY: obstacleCenter.y,
                radius: obstacleRadius,
                height: protocolConfig.obstaclePotentialHeight
            )
        } else {
            simulator.clearCircularWallPotential()
        }

        var state = checkpoint
        var elapsed = 0
        var minimumClearance: Float? = obstacleCenter.flatMap { center in
            return unseenObstacleMinimumClearance(
                indices: checkpointBody.indices,
                obstacleCenter: center,
                obstacleRadius: obstacleRadius,
                width: simulator.runtimeConfig.sx,
                height: simulator.runtimeConfig.sy,
                periodic: periodic
            )
        }
        var contact = false
        var timeToContact: Int?
        var trajectory: [UnseenObstacleShamSample] = []
        if captureTrajectory {
            trajectory.reserveCapacity(protocolConfig.continuationSteps)
        }
        while elapsed < protocolConfig.continuationSteps {
            state = simulator.step(state, count: 1)
            elapsed += 1
            if let obstacleCenter {
                let frame = measure(state: state)
                let clearance = frame.body.flatMap { body in
                    unseenObstacleMinimumClearance(
                    indices: body.indices,
                    obstacleCenter: obstacleCenter,
                    obstacleRadius: obstacleRadius,
                    width: simulator.runtimeConfig.sx,
                    height: simulator.runtimeConfig.sy,
                    periodic: periodic
                )
                }
                if let clearance {
                    minimumClearance = min(minimumClearance ?? clearance, clearance)
                    if !contact, clearance <= protocolConfig.contactDistance {
                        contact = true
                        timeToContact = elapsed
                    }
                }
            } else if captureTrajectory, let body = measure(state: state).body {
                trajectory.append(UnseenObstacleShamSample(step: elapsed, body: body))
            }
        }
        let finalFrame = measure(state: state)
        let turnAngle: Float?
        let postDisplacement: Float?
        if let finalCenter = finalFrame.body?.center {
            let finalDisplacement = displacement(
                from: checkpointCenter,
                to: finalCenter,
                width: simulator.runtimeConfig.sx,
                height: simulator.runtimeConfig.sy,
                periodic: periodic
            )
            let finalMagnitude = hypot(finalDisplacement.x, finalDisplacement.y)
            postDisplacement = finalMagnitude
            if finalMagnitude >= protocolConfig.minimumPostDisplacement {
                let finalDirection = (
                    x: finalDisplacement.x / finalMagnitude,
                    y: finalDisplacement.y / finalMagnitude
                )
                turnAngle = atan2(
                    heading.x * finalDirection.y - heading.y * finalDirection.x,
                    heading.x * finalDirection.x + heading.y * finalDirection.y
                )
            } else {
                turnAngle = nil
            }
        } else {
            turnAngle = nil
            postDisplacement = nil
        }
        return BranchRun(
            branch: branch,
            obstacleCenter: obstacleCenter,
            obstacleRadius: obstacleCenter == nil ? nil : obstacleRadius,
            finalFrame: finalFrame,
            contact: contact,
            timeToContact: timeToContact,
            minimumClearance: minimumClearance,
            turnAngle: turnAngle,
            postDisplacement: postDisplacement,
            trajectory: trajectory
        )
    }

    private func materializeRecord(
        specimen: UnseenObstacleSpecimen,
        branchRun: BranchRun,
        checkpointFrame: FrameMeasurement,
        checkpointCenter: (x: Float, y: Float),
        heading: (x: Float, y: Float),
        targetEncounterStep: Int,
        shamPredictedClearance: Float?,
        lateralDisplacement: Float?
    ) -> UnseenObstacleResponseRecord {
        let retainedMass = checkpointFrame.totalMass > 0
            ? branchRun.finalFrame.totalMass / checkpointFrame.totalMass
            : 0
        let checkpointBody = checkpointFrame.body
        let finalBody = branchRun.finalFrame.body
        let scaleRatio = finalBody.map { $0.radius99 / max(checkpointBody?.radius99 ?? 0, 1e-6) }
        let survived = retainedMass >= protocolConfig.survivalMassFraction
            && (finalBody?.massFraction ?? 0) >= protocolConfig.minimumLargestComponentMassFraction
            && (scaleRatio ?? .infinity) <= protocolConfig.maximumBodyScaleRatio
        return UnseenObstacleResponseRecord(
            specimenId: specimen.specimenId,
            lifeId: specimen.lifeId,
            family: specimen.family,
            mapId: specimen.mapId,
            ruleId: specimen.ruleId,
            initSeed: specimen.initSeed,
            branch: branchRun.branch,
            exposed: branchRun.branch != .sham,
            completed: true,
            calibrationPassed: true,
            failureReason: nil,
            survived: survived,
            contact: branchRun.contact,
            timeToContact: branchRun.timeToContact,
            targetEncounterStep: targetEncounterStep,
            shamPredictedClearance: shamPredictedClearance,
            minClearance: branchRun.minimumClearance,
            turnAngle: branchRun.turnAngle,
            lateralDisplacement: lateralDisplacement,
            retainedMass: retainedMass,
            checkpointStep: protocolConfig.checkpointSteps,
            continuationSteps: protocolConfig.continuationSteps,
            checkpointMass: checkpointFrame.totalMass,
            finalMass: branchRun.finalFrame.totalMass,
            checkpointCenterX: checkpointCenter.x,
            checkpointCenterY: checkpointCenter.y,
            checkpointHeadingX: heading.x,
            checkpointHeadingY: heading.y,
            finalCenterX: finalBody?.center.x,
            finalCenterY: finalBody?.center.y,
            obstacleCenterX: branchRun.obstacleCenter?.x,
            obstacleCenterY: branchRun.obstacleCenter?.y,
            bodyRadius: checkpointBody?.radius95,
            bodyRadiusR99: checkpointBody?.radius99,
            checkpointLargestComponentMassFraction: checkpointBody?.massFraction,
            finalLargestComponentMassFraction: finalBody?.massFraction,
            finalBodyRadius: finalBody?.radius95,
            finalBodyRadiusR99: finalBody?.radius99,
            postDisplacement: branchRun.postDisplacement,
            obstacleRadius: branchRun.obstacleRadius
        )
    }

    private func failedCalibrationRecords(
        specimen: UnseenObstacleSpecimen,
        checkpoint: FrameMeasurement,
        reason: String
    ) -> [UnseenObstacleResponseRecord] {
        UnseenObstacleBranch.allCases.map { branch in
            UnseenObstacleResponseRecord(
                specimenId: specimen.specimenId,
                lifeId: specimen.lifeId,
                family: specimen.family,
                mapId: specimen.mapId,
                ruleId: specimen.ruleId,
                initSeed: specimen.initSeed,
                branch: branch,
                exposed: branch != .sham,
                completed: false,
                calibrationPassed: false,
                failureReason: reason,
                survived: false,
                contact: false,
                timeToContact: nil,
                targetEncounterStep: nil,
                shamPredictedClearance: nil,
                minClearance: nil,
                turnAngle: nil,
                lateralDisplacement: nil,
                retainedMass: 0,
                checkpointStep: protocolConfig.checkpointSteps,
                continuationSteps: protocolConfig.continuationSteps,
                checkpointMass: checkpoint.totalMass,
                finalMass: checkpoint.totalMass,
                checkpointCenterX: checkpoint.body?.center.x,
                checkpointCenterY: checkpoint.body?.center.y,
                checkpointHeadingX: nil,
                checkpointHeadingY: nil,
                finalCenterX: checkpoint.body?.center.x,
                finalCenterY: checkpoint.body?.center.y,
                obstacleCenterX: nil,
                obstacleCenterY: nil,
                bodyRadius: checkpoint.body?.radius95,
                bodyRadiusR99: checkpoint.body?.radius99,
                checkpointLargestComponentMassFraction: checkpoint.body?.massFraction,
                finalLargestComponentMassFraction: checkpoint.body?.massFraction,
                finalBodyRadius: checkpoint.body?.radius95,
                finalBodyRadiusR99: checkpoint.body?.radius99,
                postDisplacement: nil,
                obstacleRadius: nil
            )
        }
    }
}

struct UnseenObstacleBodyMeasurement {
    let mass: Float
    let massFraction: Float
    let center: (x: Float, y: Float)
    let radius95: Float
    let radius99: Float
    let indices: [Int]
}

struct UnseenObstacleShamSample {
    let step: Int
    let body: UnseenObstacleBodyMeasurement
}

struct UnseenObstacleShamIntercept {
    let step: Int
    let centers: [UnseenObstacleBranch: (x: Float, y: Float)]
    let predictedClearances: [UnseenObstacleBranch: Float]
}

func unseenObstacleSupportsImplementationMode(_ mode: String) -> Bool {
    mode == "flowlenia_2022_paper_equations" || mode == "flowlenia_2022_colab"
}

func validateUnseenObstacleImplementationMode(_ mode: String) throws {
    guard unseenObstacleSupportsImplementationMode(mode) else {
        throw UnseenObstacleResponseError.unsupportedImplementation(mode)
    }
}

func unseenObstacleFindShamPredictedIntercept(
    checkpointBody: UnseenObstacleBodyMeasurement,
    samples: [UnseenObstacleShamSample],
    normal: (x: Float, y: Float),
    obstacleRadius: Float,
    lateralOffset: Float,
    minimumInitialClearance: Float,
    contactDistance: Float,
    boundaryMargin: Float,
    width: Int,
    height: Int,
    periodic: Bool
) -> UnseenObstacleShamIntercept? {
    let branches: [UnseenObstacleBranch] = [.ahead, .left, .right]
    for sample in samples.sorted(by: { $0.step < $1.step }) {
        var centers: [UnseenObstacleBranch: (x: Float, y: Float)] = [:]
        var predictedClearances: [UnseenObstacleBranch: Float] = [:]
        var valid = true
        for branch in branches {
            let lateral: Float
            switch branch {
            case .ahead, .sham: lateral = 0
            case .left: lateral = lateralOffset
            case .right: lateral = -lateralOffset
            }
            var center = (
                x: sample.body.center.x + normal.x * lateral,
                y: sample.body.center.y + normal.y * lateral
            )
            if periodic {
                center.x = wrapped(center.x, period: Float(width))
                center.y = wrapped(center.y, period: Float(height))
            }
            guard unseenObstaclePlacementFits(
                center: center,
                radius: obstacleRadius,
                margin: boundaryMargin,
                width: width,
                height: height,
                periodic: periodic
            ), let initialClearance = unseenObstacleMinimumClearance(
                indices: checkpointBody.indices,
                obstacleCenter: center,
                obstacleRadius: obstacleRadius,
                width: width,
                height: height,
                periodic: periodic
            ), initialClearance >= minimumInitialClearance,
            let predictedClearance = unseenObstacleMinimumClearance(
                indices: sample.body.indices,
                obstacleCenter: center,
                obstacleRadius: obstacleRadius,
                width: width,
                height: height,
                periodic: periodic
            ), predictedClearance <= contactDistance else {
                valid = false
                break
            }
            centers[branch] = center
            predictedClearances[branch] = predictedClearance
        }
        if valid {
            return UnseenObstacleShamIntercept(
                step: sample.step,
                centers: centers,
                predictedClearances: predictedClearances
            )
        }
    }
    return nil
}

func wrapped(_ coordinate: Float, period: Float) -> Float {
    let remainder = coordinate.truncatingRemainder(dividingBy: period)
    return remainder >= 0 ? remainder : remainder + period
}

func periodicDelta(_ value: Float, period: Float) -> Float {
    var delta = value
    if delta > period / 2 { delta -= period }
    if delta < -period / 2 { delta += period }
    return delta
}

func displacement(
    from start: (x: Float, y: Float),
    to end: (x: Float, y: Float),
    width: Int,
    height: Int,
    periodic: Bool
) -> (x: Float, y: Float) {
    var dx = end.x - start.x
    var dy = end.y - start.y
    if periodic {
        dx = periodicDelta(dx, period: Float(width))
        dy = periodicDelta(dy, period: Float(height))
    }
    return (dx, dy)
}

func unseenObstacleLargestBody(
    values: [Float],
    width: Int,
    height: Int,
    threshold: Float,
    periodic: Bool
) -> UnseenObstacleBodyMeasurement? {
    precondition(width > 0 && height > 0 && values.count == width * height)
    var visited = [Bool](repeating: false, count: values.count)
    var largestIndices: [Int] = []
    var largestMass: Float = 0

    for start in values.indices where !visited[start] && values[start] >= threshold {
        visited[start] = true
        var queue = [start]
        var cursor = 0
        var indices: [Int] = []
        var componentMass: Float = 0
        while cursor < queue.count {
            let index = queue[cursor]
            cursor += 1
            indices.append(index)
            componentMass += values[index]
            let x = index / height
            let y = index % height
            for dx in -1...1 {
                for dy in -1...1 where dx != 0 || dy != 0 {
                    var nx = x + dx
                    var ny = y + dy
                    if periodic {
                        nx = (nx + width) % width
                        ny = (ny + height) % height
                    } else if nx < 0 || nx >= width || ny < 0 || ny >= height {
                        continue
                    }
                    let neighbor = nx * height + ny
                    if !visited[neighbor], values[neighbor] >= threshold {
                        visited[neighbor] = true
                        queue.append(neighbor)
                    }
                }
            }
        }
        if componentMass > largestMass {
            largestMass = componentMass
            largestIndices = indices
        }
    }

    guard largestMass > 0, !largestIndices.isEmpty else { return nil }
    let totalMass = values.reduce(Float(0)) { partial, value in
        partial + max(value.isFinite ? value : 0, 0)
    }
    guard totalMass > 0 else { return nil }
    let center = unseenObstacleMassCenter(
        values: values,
        indices: largestIndices,
        width: width,
        height: height,
        periodic: periodic
    )
    let weightedRadii = largestIndices.map { index -> (distance: Float, mass: Float) in
        let delta = displacement(
            from: center,
            to: (Float(index / height), Float(index % height)),
            width: width,
            height: height,
            periodic: periodic
        )
        return (hypot(delta.x, delta.y), values[index])
    }.sorted { left, right in
        if left.distance == right.distance { return left.mass > right.mass }
        return left.distance < right.distance
    }

    func quantileRadius(_ fraction: Float) -> Float {
        let target = largestMass * fraction
        var cumulative: Float = 0
        for sample in weightedRadii {
            cumulative += sample.mass
            if cumulative >= target { return sample.distance }
        }
        return weightedRadii.last?.distance ?? 0
    }
    return UnseenObstacleBodyMeasurement(
        mass: largestMass,
        massFraction: largestMass / totalMass,
        center: center,
        radius95: quantileRadius(0.95),
        radius99: quantileRadius(0.99),
        indices: largestIndices
    )
}

private func unseenObstacleMassCenter(
    values: [Float],
    indices: [Int],
    width: Int,
    height: Int,
    periodic: Bool
) -> (x: Float, y: Float) {
    let mass = max(indices.reduce(Float(0)) { $0 + values[$1] }, 1e-8)
    if !periodic {
        let x = indices.reduce(Float(0)) { $0 + Float($1 / height) * values[$1] } / mass
        let y = indices.reduce(Float(0)) { $0 + Float($1 % height) * values[$1] } / mass
        return (x, y)
    }

    func circularCoordinate(period: Int, coordinate: (Int) -> Int) -> Float {
        let scale = 2 * Float.pi / Float(period)
        var sine: Float = 0
        var cosine: Float = 0
        for index in indices {
            let angle = Float(coordinate(index)) * scale
            sine += sin(angle) * values[index]
            cosine += cos(angle) * values[index]
        }
        var angle = atan2(sine, cosine)
        if angle < 0 { angle += 2 * Float.pi }
        return angle / scale
    }
    return (
        circularCoordinate(period: width) { $0 / height },
        circularCoordinate(period: height) { $0 % height }
    )
}

func unseenObstaclePlacementFits(
    center: (x: Float, y: Float),
    radius: Float,
    margin: Float,
    width: Int,
    height: Int,
    periodic: Bool
) -> Bool {
    let extent = radius + margin
    if periodic {
        return extent < Float(min(width, height)) / 2
    }
    return center.x - extent >= 0
        && center.y - extent >= 0
        && center.x + extent <= Float(width - 1)
        && center.y + extent <= Float(height - 1)
}

func unseenObstacleMinimumClearance(
    indices: [Int],
    obstacleCenter: (x: Float, y: Float),
    obstacleRadius: Float,
    width: Int,
    height: Int,
    periodic: Bool
) -> Float? {
    var minimum: Float?
    for index in indices {
        let delta = displacement(
            from: obstacleCenter,
            to: (Float(index / height), Float(index % height)),
            width: width,
            height: height,
            periodic: periodic
        )
        let clearance = hypot(delta.x, delta.y) - obstacleRadius
        minimum = min(minimum ?? clearance, clearance)
    }
    return minimum
}
