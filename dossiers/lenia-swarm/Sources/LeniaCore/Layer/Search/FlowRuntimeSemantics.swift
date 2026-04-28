import Foundation
import MLX

public func flowExcludedMassChannels(
    channels: Int,
    chemotaxis: ChemotaxisConfig?,
    food: FoodConfig?,
    additionalExcludedChannels: [Int] = []
) -> Set<Int> {
    var excluded: Set<Int> = []
    if let chemotaxis, chemotaxis.enabled, !chemotaxis.include_in_mass {
        excluded.insert(chemotaxis.channel_index)
    }
    if let food, food.enabled, !food.include_in_mass {
        excluded.insert(food.channel_index)
    }
    excluded.formUnion(additionalExcludedChannels)
    return excluded.filter { $0 >= 0 && $0 < channels }
}

public func flowCreatureChannels(
    channels: Int,
    chemotaxis: ChemotaxisConfig?,
    food: FoodConfig?,
    additionalExcludedChannels: [Int] = []
) -> [Int] {
    let excluded = flowExcludedMassChannels(
        channels: channels,
        chemotaxis: chemotaxis,
        food: food,
        additionalExcludedChannels: additionalExcludedChannels
    )
    let included = (0..<channels).filter { !excluded.contains($0) }
    return included.isEmpty ? Array(0..<channels) : included
}

func flowMatterWeights(
    channels: Int,
    excludedChannels: Set<Int>
) -> [Float]? {
    guard !excludedChannels.isEmpty else {
        return nil
    }
    return (0..<channels).map { excludedChannels.contains($0) ? 0.0 : 1.0 }
}

func flowMatterMap(
    _ state: MLXArray,
    excludedChannels: Set<Int>
) -> MLXArray {
    if excludedChannels.isEmpty {
        return state.sum(axis: -1)
    }

    let channels = state.shape.last ?? 0
    var parts: [MLXArray] = []
    parts.reserveCapacity(channels)
    switch state.shape.count {
    case 3:
        for channel in 0..<channels where !excludedChannels.contains(channel) {
            parts.append(state[0..., 0..., channel])
        }
    case 4:
        for channel in 0..<channels where !excludedChannels.contains(channel) {
            parts.append(state[0..., 0..., 0..., channel])
        }
    default:
        preconditionFailure("flowMatterMap expects rank-3 or rank-4 state.")
    }

    if parts.isEmpty {
        return MLXArray.zeros(Array(state.shape.dropLast()))
    }
    if parts.count == 1 {
        return parts[0]
    }
    return MLX.stacked(parts, axis: -1).sum(axis: -1)
}

func overwriteFieldChannel(
    _ state: MLXArray,
    field: MLXArray,
    channelIndex: Int
) -> MLXArray {
    let channels = state.shape.last ?? 0
    precondition(channels > 0, "state must have at least one channel")
    precondition(channelIndex >= 0 && channelIndex < channels, "channelIndex out of bounds")

    let replacement: MLXArray
    if field.shape.count == state.shape.count {
        replacement = field
    } else if field.shape.count == state.shape.count - 1 {
        replacement = field.expandedDimensions(axis: -1)
    } else {
        preconditionFailure("field rank must match state rank or be one lower")
    }

    if channels == 1 {
        return replacement.shape == state.shape ? replacement : MLX.broadcast(replacement, to: state.shape)
    }

    var maskShape = Array(repeating: 1, count: state.shape.count)
    maskShape[maskShape.count - 1] = channels
    var maskValues = [Float](repeating: 0.0, count: channels)
    maskValues[channelIndex] = 1.0
    let replaceMask = MLXArray(maskValues).reshaped(maskShape)
    let keepMask = MLXArray(Float(1.0)) - replaceMask
    let replacementBroadcast = replacement.shape == state.shape ? replacement : MLX.broadcast(replacement, to: state.shape)
    return state * keepMask + replacementBroadcast * replaceMask
}
