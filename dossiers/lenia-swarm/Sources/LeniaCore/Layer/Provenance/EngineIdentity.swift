import Foundation
#if canImport(Metal)
import Metal
#endif

/// Records the sha256 of every Metal source this process compiled, so a receipt can name the exact shaders a run used.
final class CompiledMetalSourceLedger: @unchecked Sendable {
    static let shared = CompiledMetalSourceLedger()

    private let lock = NSLock()
    private var digests: Set<String> = []

    func record(_ source: String) {
        let digest = ProvenanceDigest.sha256Hex(source)
        lock.lock()
        digests.insert(digest)
        lock.unlock()
    }

    func snapshot() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return digests.sorted()
    }
}

public enum CompiledMetalSources {
    public static func sha256s() -> [String] {
        CompiledMetalSourceLedger.shared.snapshot()
    }
}

/// Names the code that produced a record. Runtime shader text interpolates each run's grid and rule
/// constants, so engine_id hashes the generators evaluated over a fixed reference grid instead;
/// the receipt keeps the exact per-run digests separately.
public struct LeniaEngineIdentity: Codable, Sendable, Equatable {
    public static let shortLength = 16

    public let engineID: String
    public let backend: FlowLeniaComputeBackend
    public let metalReferenceSourcesSha256: String?
    public let metalCompileOptions: [String: String]?
    public let cEngineSha256: String

    enum CodingKeys: String, CodingKey {
        case engineID = "engine_id"
        case backend
        case metalReferenceSourcesSha256 = "metal_reference_sources_sha256"
        case metalCompileOptions = "metal_compile_options"
        case cEngineSha256 = "c_engine_sha256"
    }

    public init(backend: FlowLeniaComputeBackend, buildInfo: LeniaBuildInfo) {
        #if canImport(Metal)
        let metalSources: String? = Self.metalReferenceSourcesSha256
        let options: [String: String]? = FlowLeniaMetalFullPipeline.compileOptionsDescriptor
        #else
        let metalSources: String? = nil
        let options: [String: String]? = nil
        #endif
        let optionText = options.map { values in
            values.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: ";")
        } ?? "none"
        let material = [
            "lenia-engine-v1",
            "backend=\(backend.rawValue)",
            "metal_reference_sources=\(metalSources ?? "none")",
            "metal_compile_options=\(optionText)",
            "c_engine=\(buildInfo.cEngineSha256)",
        ].joined(separator: "\n")
        self.engineID = String(ProvenanceDigest.sha256Hex(material).prefix(Self.shortLength))
        self.backend = backend
        self.metalReferenceSourcesSha256 = metalSources
        self.metalCompileOptions = options
        self.cEngineSha256 = buildInfo.cEngineSha256
    }

    /// Engine id per backend raw value, as workers advertise them and controllers check them.
    public static func engineIDs(for backends: [FlowLeniaComputeBackend], buildInfo: LeniaBuildInfo) -> [String: String] {
        Dictionary(uniqueKeysWithValues: Set(backends).map {
            ($0.rawValue, LeniaEngineIdentity(backend: $0, buildInfo: buildInfo).engineID)
        })
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        engineID = try container.decode(String.self, forKey: .engineID)
        backend = try container.decode(FlowLeniaComputeBackend.self, forKey: .backend)
        metalReferenceSourcesSha256 = try container.decodeNullable(String.self, forKey: .metalReferenceSourcesSha256)
        metalCompileOptions = try container.decodeNullable([String: String].self, forKey: .metalCompileOptions)
        cEngineSha256 = try container.decode(String.self, forKey: .cEngineSha256)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(engineID, forKey: .engineID)
        try container.encode(backend, forKey: .backend)
        try container.encode(metalReferenceSourcesSha256, forKey: .metalReferenceSourcesSha256)
        try container.encode(metalCompileOptions, forKey: .metalCompileOptions)
        try container.encode(cEngineSha256, forKey: .cEngineSha256)
    }

    #if canImport(Metal)
    static let metalReferenceSourcesSha256: String = {
        let digests = referenceMetalSources().map { ProvenanceDigest.sha256Hex($0) }
        return ProvenanceDigest.sha256Hex(digests.joined(separator: "\n"))
    }()

    private struct ReferenceVariant {
        var side = 128
        var channelCount = 2
        var useTorus = true
        var alphaMode = "per_channel"
        var flowClip = "params_only"
        var fieldMode = FlowLeniaParameterFieldMode.kernelGain
        var reintegrateParams = true
        var mix = FlowLeniaMetalFullPipeline.ParameterMixMode.average
        var n = 2
    }

    /// One variant per value of every branch the generators take, plus the clip/field-mode cross because the clip rule reads both.
    private static func referenceVariants() -> [ReferenceVariant] {
        var variants = [ReferenceVariant()]
        func vary(_ change: (inout ReferenceVariant) -> Void) {
            var variant = ReferenceVariant()
            change(&variant)
            variants.append(variant)
        }
        vary { $0.side = 12 }
        vary { $0.side = 12; $0.useTorus = false }
        for channels in [1, 3] { vary { $0.channelCount = channels } }
        vary { $0.useTorus = false }
        vary { $0.alphaMode = "mass" }
        for clip in ["none", "params_only", "always"] {
            for mode in [FlowLeniaParameterFieldMode.kernelGain, .localizedGrowthParameters] {
                vary { $0.flowClip = clip; $0.fieldMode = mode }
            }
        }
        vary { $0.reintegrateParams = false }
        vary { $0.mix = .stochastic }
        for n in [0, 1, 3, 4, 5] { vary { $0.n = n } }
        return variants
    }

    private static func referenceMetalSources() -> [String] {
        let kernelCount = 3
        let batchCount = 2
        let dt: Float = 0.2
        let dd = 5
        let sigma: Float = 0.65
        let thetaA: Float = 2.0
        let referenceThreadgroupMemory = 32768
        var sources: [String] = []
        for variant in referenceVariants() {
            let localTorus = FlowLeniaFieldLayout.usesLocalTorusDistance(
                sx: variant.side,
                sy: variant.side,
                dd: dd,
                maxAdvection: Float(dd) - sigma,
                useTorus: variant.useTorus
            )
            let parameterCount = variant.fieldMode.parameterCount(kernelCount: kernelCount)
            sources.append(FlowLeniaMetalFullPipeline.kernelSource(
                kernelCount: kernelCount,
                parameterCount: parameterCount,
                batchCount: batchCount,
                channelCount: variant.channelCount,
                kernelBatchCount: 1,
                summaryPartialGroupCount: FlowLeniaMetalFullPipeline.summaryPartialGroupCount(sx: variant.side, sy: variant.side),
                sx: variant.side,
                sy: variant.side,
                dt: dt,
                dd: dd,
                sigma: sigma,
                thetaA: thetaA,
                n: variant.n,
                useTorus: variant.useTorus,
                alphaMode: variant.alphaMode,
                flowClip: variant.flowClip,
                parameterFieldMode: variant.fieldMode,
                reintegrateParams: variant.reintegrateParams,
                parameterMixMode: variant.mix,
                spectralPlan: FlowLeniaSpectralPlan(
                    sx: variant.side,
                    sy: variant.side,
                    channelCount: variant.channelCount,
                    maxThreadgroupMemory: referenceThreadgroupMemory
                ),
                reintegrateTile: localTorus && !variant.reintegrateParams ? 16 : nil
            ))
            sources.append(FlowLeniaMetalAncestryTracer.kernelSource(
                batchCount: batchCount,
                channelCount: variant.channelCount,
                founderCount: 2,
                sx: variant.side,
                sy: variant.side,
                dt: dt,
                dd: dd,
                sigma: sigma,
                useTorus: variant.useTorus
            ))
            sources.append(FlowLeniaMetalFullStateRunner.wallMaskKernelSource(
                parameterCount: parameterCount,
                channelCount: variant.channelCount,
                batchCount: batchCount,
                sx: variant.side,
                sy: variant.side
            ))
        }
        sources.append(FlowLeniaMetalPhantom.kernelSource)
        sources.append(FlowSandboxMetalRuntimeState.kernelSource(parameterCount: kernelCount, sx: 128, sy: 128))
        return sources
    }
    #endif
}

/// The host facts a receipt records next to the engine: which device ran it and on which OS build.
public struct LeniaHostIdentity: Codable, Sendable, Equatable {
    public let device: String
    public let osBuild: String
    public let machineModel: String

    enum CodingKeys: String, CodingKey {
        case device
        case osBuild = "os_build"
        case machineModel = "machine_model"
    }

    public static func current(backend: FlowLeniaComputeBackend) throws -> LeniaHostIdentity {
        #if canImport(Darwin)
        let model = try sysctlString("hw.model")
        let cpu = try sysctlString("machdep.cpu.brand_string")
        #else
        var name = utsname()
        uname(&name)
        let model = withUnsafeBytes(of: &name.machine) { String(decoding: $0.prefix { $0 != 0 }, as: UTF8.self) }
        let cpu = model
        #endif
        let device: String
        switch backend {
        case .cpu:
            device = cpu
        case .metalFull, .mlx:
            #if canImport(Metal)
            guard let metal = MTLCreateSystemDefaultDevice() else {
                throw ProvenanceError.invalidReceipt("backend \(backend.rawValue) needs a Metal device, but none is available")
            }
            device = metal.name
            #else
            device = cpu
            #endif
        }
        return LeniaHostIdentity(
            device: device,
            osBuild: ProcessInfo.processInfo.operatingSystemVersionString,
            machineModel: model
        )
    }

    #if canImport(Darwin)
    private static func sysctlString(_ name: String) throws -> String {
        var size = 0
        guard sysctlbyname(name, nil, &size, nil, 0) == 0, size > 0 else {
            throw ProvenanceError.invalidReceipt("cannot read sysctl \(name)")
        }
        var buffer = [CChar](repeating: 0, count: size)
        guard sysctlbyname(name, &buffer, &size, nil, 0) == 0 else {
            throw ProvenanceError.invalidReceipt("cannot read sysctl \(name)")
        }
        return String(cString: buffer)
    }
    #endif
}
