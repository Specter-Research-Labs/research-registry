import Foundation

public enum LeniaArtifactBundleKind: String, Codable, Sendable {
    case strictReplayBundleV1 = "strict_replay_bundle_v1"
    case qd24PaperReplayBundleV1 = "qd24_paper_replay_bundle_v1"
    case sensorimotor24PaperReplayBundleV1 = "sensorimotor24_paper_replay_bundle_v1"
    case flowLeniaEcology2025ArenaReplayBundleV1 = "flowlenia_ecology2025_arena_replay_bundle_v1"
}

public enum LeniaRuntimeFamily: String, Codable, Sendable {
    case flowLenia = "flow_lenia"
    case qd24Paper = "qd24_paper"
    case sensorimotor24Paper = "sensorimotor24_paper"
    case unknown = "unknown"
}

public enum LeniaArtifactCapability: String, Codable, Sendable, CaseIterable {
    case archive = "archive"
    case warehouseIngest = "warehouse_ingest"
    case replay = "replay"
    case topology = "topology"
    case intervention = "intervention"
    case media = "media"
}

public struct LeniaTrajectoryFrame: Codable, Sendable {
    public let step: Int
    public let width: Int
    public let height: Int
    public let bytes: Data
    public let foodBytes: Data?

    public init(step: Int, width: Int, height: Int, bytes: Data, foodBytes: Data? = nil) {
        self.step = step
        self.width = width
        self.height = height
        self.bytes = bytes
        self.foodBytes = foodBytes
    }
}
