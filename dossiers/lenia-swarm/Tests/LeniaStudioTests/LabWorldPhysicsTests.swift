import XCTest
import LeniaCore
@testable import LeniaStudio

final class LabWorldPhysicsTests: XCTestCase {
    func testMissionPresetsHaveDistinctStableEntryIdentities() {
        let presets = buildLabMissionPresets()

        XCTAssertEqual(Set(presets.map(\.entry.id)).count, presets.count)
        XCTAssertEqual(
            presets.map(\.entry.id),
            presets.map { "lab-preset:\($0.id)" }
        )
    }

    func testPhysicsGettersExposeResolvedRuntimeValues() throws {
        let draft = try makePhysicsDraft()
        let params = draft.runtimeConfigValue.params

        XCTAssertEqual(draft.timeStep, draft.runtimeConfigValue.dt)
        XCTAssertEqual(draft.globalRadius, params.R)
        XCTAssertEqual(draft.kernelRelativeRadii, params.r)
        XCTAssertEqual(draft.kernelCenters, params.m)
        XCTAssertEqual(draft.kernelSigmas, params.s)
        XCTAssertEqual(draft.kernelGains, params.h)
        XCTAssertEqual(draft.kernelRelativeRadius(at: 0), params.r[0])
        XCTAssertEqual(draft.kernelCenter(at: 0), params.m[0])
        XCTAssertEqual(draft.kernelSigma(at: 0), params.s[0])
        XCTAssertEqual(draft.kernelGain(at: 0), params.h[0])
        XCTAssertNil(draft.kernelRelativeRadius(at: -1))
        XCTAssertNil(draft.kernelCenter(at: draft.kernelCount))
    }

    func testPhysicsSettersClampToStableEditorRanges() throws {
        var draft = try makePhysicsDraft()

        draft.setTimeStep(-1)
        draft.setGlobalRadius(100)
        draft.setKernelRelativeRadius(100, at: 0)
        draft.setKernelCenter(-1, at: 0)
        draft.setKernelSigma(100, at: 0)
        draft.setKernelGain(-1, at: 0)

        XCTAssertEqual(draft.timeStep, LabWorldDraft.timeStepRange.lowerBound)
        XCTAssertEqual(draft.globalRadius, LabWorldDraft.globalRadiusRange.upperBound)
        XCTAssertEqual(draft.kernelRelativeRadius(at: 0), LabWorldDraft.kernelRelativeRadiusRange.upperBound)
        XCTAssertEqual(draft.kernelCenter(at: 0), LabWorldDraft.kernelCenterRange.lowerBound)
        XCTAssertEqual(draft.kernelSigma(at: 0), LabWorldDraft.kernelSigmaRange.upperBound)
        XCTAssertEqual(draft.kernelGain(at: 0), LabWorldDraft.kernelGainRange.lowerBound)
    }

    func testPhysicsEditsPreserveRestOfRuntimeContract() throws {
        var draft = try makePhysicsDraft()
        let before = draft.runtimeConfigValue
        XCTAssertGreaterThan(before.nbK, 1)
        let untouchedKernel = 1

        draft.setTimeStep(0.125)
        draft.setGlobalRadius(14)
        draft.setKernelRelativeRadius(0.75, at: 0)
        draft.setKernelCenter(0.25, at: 0)
        draft.setKernelSigma(0.04, at: 0)
        draft.setKernelGain(0.65, at: 0)

        let after = draft.runtimeConfigValue
        XCTAssertEqual(after.dt, 0.125)
        XCTAssertEqual(after.params.R, 14)
        XCTAssertEqual(after.params.r[0], 0.75)
        XCTAssertEqual(after.params.m[0], 0.25)
        XCTAssertEqual(after.params.s[0], 0.04)
        XCTAssertEqual(after.params.h[0], 0.65)

        XCTAssertEqual(after.backend, before.backend)
        XCTAssertEqual(after.sx, before.sx)
        XCTAssertEqual(after.sy, before.sy)
        XCTAssertEqual(after.channels, before.channels)
        XCTAssertEqual(after.nbK, before.nbK)
        XCTAssertEqual(after.c0, before.c0)
        XCTAssertEqual(after.c1, before.c1)
        XCTAssertEqual(after.dd, before.dd)
        XCTAssertEqual(after.sigma, before.sigma)
        XCTAssertEqual(after.n, before.n)
        XCTAssertEqual(after.thetaA, before.thetaA)
        XCTAssertEqual(after.border, before.border)
        XCTAssertEqual(after.implementation.mode, before.implementation.mode)
        XCTAssertEqual(after.implementation.gradientBoundary, before.implementation.gradientBoundary)
        XCTAssertEqual(after.implementation.kernelProfile, before.implementation.kernelProfile)
        XCTAssertEqual(after.implementation.growthProfile, before.implementation.growthProfile)
        XCTAssertEqual(after.params.b, before.params.b)
        XCTAssertEqual(after.params.w, before.params.w)
        XCTAssertEqual(after.params.a, before.params.a)
        XCTAssertEqual(after.params.seed, before.params.seed)
        XCTAssertEqual(after.params.r[untouchedKernel], before.params.r[untouchedKernel])
        XCTAssertEqual(after.params.m[untouchedKernel], before.params.m[untouchedKernel])
        XCTAssertEqual(after.params.s[untouchedKernel], before.params.s[untouchedKernel])
        XCTAssertEqual(after.params.h[untouchedKernel], before.params.h[untouchedKernel])
        XCTAssertEqual(after.randomParamRanges?.R, before.randomParamRanges?.R)
        XCTAssertNotNil(after.randomParamRanges)
        XCTAssertEqual(after.initSeed, before.initSeed)
        XCTAssertEqual(after.steps, before.steps)
        XCTAssertEqual(after.parameterEmbedding.enabled, before.parameterEmbedding.enabled)
        XCTAssertEqual(after.parameterEmbedding.mix, before.parameterEmbedding.mix)
    }

    func testInvalidPhysicsEditsAreNoOps() throws {
        var draft = try makePhysicsDraft()
        let before = draft.runtimeConfigValue

        draft.setTimeStep(.nan)
        draft.setGlobalRadius(.infinity)
        draft.setKernelRelativeRadius(0.5, at: -1)
        draft.setKernelCenter(0.2, at: draft.kernelCount)
        draft.setKernelSigma(.nan, at: 0)
        draft.setKernelGain(.infinity, at: 0)

        XCTAssertEqual(draft.runtimeConfigValue.dt, before.dt)
        XCTAssertEqual(draft.runtimeConfigValue.params.R, before.params.R)
        XCTAssertEqual(draft.runtimeConfigValue.params.r, before.params.r)
        XCTAssertEqual(draft.runtimeConfigValue.params.m, before.params.m)
        XCTAssertEqual(draft.runtimeConfigValue.params.s, before.params.s)
        XCTAssertEqual(draft.runtimeConfigValue.params.h, before.params.h)
    }

    private func makePhysicsDraft() throws -> LabWorldDraft {
        let preset = try XCTUnwrap(buildBlankLabMissionPresets().first { $0.id == "paper-2c" })
        return try XCTUnwrap(preset.defaultDraft)
    }
}
