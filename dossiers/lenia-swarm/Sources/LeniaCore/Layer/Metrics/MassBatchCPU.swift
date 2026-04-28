import MLX

struct MassBatchCPU: Sendable {
    let flat: [Float]
    let batch: Int
    let height: Int
    let width: Int
    let sampleSize: Int
}

func materializeMassBatch(_ massMap: MLXArray) -> MassBatchCPU {
    eval(massMap)
    let shape = massMap.shape
    let batch: Int
    let height: Int
    let width: Int
    if shape.count == 3 {
        batch = shape[0]
        height = shape[1]
        width = shape[2]
    } else if shape.count == 2 {
        batch = 1
        height = shape[0]
        width = shape[1]
    } else {
        fatalError("massMap must have 2 or 3 dimensions, got shape: \(shape)")
    }

    let flat = massMap.asArray(Float.self)
    let sampleSize = height * width
    if flat.count != batch * sampleSize {
        fatalError("massMap size mismatch: expected \(batch * sampleSize), got \(flat.count)")
    }

    return MassBatchCPU(
        flat: flat,
        batch: batch,
        height: height,
        width: width,
        sampleSize: sampleSize
    )
}
