import Foundation

/// One per-step developmental sample: the same terminal morphology descriptor used at end-of-run,
/// computed on an intermediate field so a replay produces a trajectory through morphospace rather
/// than only an endpoint. Serialized as one JSONL row per step for the warehouse replay ingest.
public struct MorphospaceDevelopmentSample: Codable, Sendable {
    public let step: Int
    public let centerX: Float
    public let centerY: Float
    public let width: Int
    public let height: Int
    public let terminal: MorphospaceTerminalDescriptor
    /// Opt-in high-fidelity centered field for off-line TDA (resolution and little-endian Float16
    /// base64 payload). nil unless development-field capture was requested; old traces decode as nil.
    public let fieldResolution: Int?
    public let fieldF16Base64: String?

    public init(
        step: Int,
        centerX: Float,
        centerY: Float,
        width: Int,
        height: Int,
        terminal: MorphospaceTerminalDescriptor,
        fieldResolution: Int? = nil,
        fieldF16Base64: String? = nil
    ) {
        self.step = step
        self.centerX = centerX
        self.centerY = centerY
        self.width = width
        self.height = height
        self.terminal = terminal
        self.fieldResolution = fieldResolution
        self.fieldF16Base64 = fieldF16Base64
    }
}

/// Little-endian Float16 bytes, base64-encoded. numpy reads with dtype='<f2'.
private func encodeFloat16Base64(_ values: [Float]) -> String {
    let halfs = values.map { Float16($0) }
    return halfs.withUnsafeBytes { Data($0).base64EncodedString() }
}

/// Compute a development sample from a captured multi-channel field. The field layout matches
/// FrameCapture.stateHandler: cell-major, channel-minor (index = cell * channels + channel).
/// massChannel < 0 sums all channels (the matter field); otherwise selects one channel. Reuses the
/// canonical morphospaceFinalSampleSummary so per-step axes are identical to the terminal axes.
public func morphospaceDevelopmentSample(
    step: Int,
    channels: Int,
    width: Int,
    height: Int,
    values: [Float],
    massChannel: Int,
    occupancyThreshold: Float,
    useTorus: Bool,
    borderMode: String,
    fieldResolution: Int = 0
) -> MorphospaceDevelopmentSample {
    let cellCount = width * height
    var mass = [Float](repeating: 0, count: cellCount)
    if massChannel >= 0 && massChannel < channels {
        for cell in 0..<cellCount {
            mass[cell] = values[cell * channels + massChannel]
        }
    } else {
        for cell in 0..<cellCount {
            let base = cell * channels
            var total: Float = 0
            for c in 0..<channels {
                total += values[base + c]
            }
            mass[cell] = total
        }
    }

    let batchData = MassBatchCPU(
        flat: mass,
        batch: 1,
        height: height,
        width: width,
        sampleSize: cellCount
    )
    let summary = morphospaceFinalSampleSummary(
        materialized: batchData,
        sampleIndex: 0,
        occupancyThreshold: occupancyThreshold,
        useTorus: useTorus
    )

    let terminal = MorphospaceTerminalDescriptor(
        massChannel: massChannel,
        borderMode: borderMode,
        symmetryPolicy: "translation_kernel_permutation_v1",
        fingerprintResolution: summary.fingerprintResolution,
        fingerprintU8: summary.fingerprintU8,
        angularSymmetry: summary.angularSymmetry,
        fingerprintHash12: summary.fingerprintHash12,
        finalMass: summary.finalMass,
        finalOccupancy: summary.finalOccupancy,
        finalGyration: summary.finalGyration,
        momentMass: nil,
        momentVolume: nil,
        momentDensity: nil,
        momentAnisotropy: nil,
        componentCount: nil,
        largestComponentFraction: nil,
        largestComponentAnisotropy: nil,
        hu1: nil,
        hu2: nil,
        hu3: nil,
        hu4: nil,
        hu5: nil,
        hu6: nil,
        hu7: nil,
        flusser1: nil,
        flusser2: nil,
        flusser3: nil,
        flusser4: nil,
        windowMassStd: nil,
        windowOccupancyStd: nil,
        windowGyrationStd: nil,
        isStable: false
    )
    let field = fieldResolution > 0
        ? morphospaceCenteredFloatField(
            sample: mass,
            width: width,
            height: height,
            useTorus: useTorus,
            outputResolution: fieldResolution
        )
        : nil
    return MorphospaceDevelopmentSample(
        step: step,
        centerX: summary.centerX,
        centerY: summary.centerY,
        width: width,
        height: height,
        terminal: terminal,
        fieldResolution: field != nil ? fieldResolution : nil,
        fieldF16Base64: field.map(encodeFloat16Base64)
    )
}
