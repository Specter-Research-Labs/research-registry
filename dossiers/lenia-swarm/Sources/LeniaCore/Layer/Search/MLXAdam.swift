import Foundation
import MLX

/// Adam optimizer over a list of `MLXArray` parameter tensors, for gradient
/// descent through MLX autograd (distinct from the `[Float]` `Adam` used by the
/// ES gradient estimate). Supports a per-parameter learning rate so callers can
/// give, e.g., the initialization field a different rate than the rule tensors.
struct MLXAdam {
    private var m: [MLXArray]
    private var v: [MLXArray]
    private let learningRates: [Float]
    private let beta1: Float
    private let beta2: Float
    private let eps: Float
    private var stepCount: Int = 0

    init(
        paramShapes: [[Int]],
        learningRates: [Float],
        beta1: Float = 0.9,
        beta2: Float = 0.999,
        eps: Float = 1e-8
    ) {
        precondition(
            paramShapes.count == learningRates.count,
            "MLXAdam requires one learning rate per parameter tensor."
        )
        self.m = paramShapes.map { MLX.zeros($0) }
        self.v = paramShapes.map { MLX.zeros($0) }
        self.learningRates = learningRates
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
    }

    init(
        paramShapes: [[Int]],
        learningRate: Float,
        beta1: Float = 0.9,
        beta2: Float = 0.999,
        eps: Float = 1e-8
    ) {
        self.init(
            paramShapes: paramShapes,
            learningRates: Array(repeating: learningRate, count: paramShapes.count),
            beta1: beta1,
            beta2: beta2,
            eps: eps
        )
    }

    /// Returns the updated parameters. Gradient entries missing from `gradients`
    /// (MLX omits disconnected arguments) are treated as zero, so their moments
    /// stay at zero and the corresponding parameter is left unchanged.
    mutating func step(params: [MLXArray], gradients: [MLXArray]) -> [MLXArray] {
        stepCount += 1
        let t = Float(stepCount)
        let bias1 = 1 - Foundation.pow(beta1, t)
        let bias2 = 1 - Foundation.pow(beta2, t)
        var updated: [MLXArray] = []
        updated.reserveCapacity(params.count)
        for index in 0..<params.count {
            let grad = index < gradients.count ? gradients[index] : MLX.zeros(params[index].shape)
            m[index] = MLXArray(beta1) * m[index] + MLXArray(1 - beta1) * grad
            v[index] = MLXArray(beta2) * v[index] + MLXArray(1 - beta2) * (grad * grad)
            let mHat = m[index] / MLXArray(bias1)
            let vHat = v[index] / MLXArray(bias2)
            let denom = MLX.sqrt(vHat) + MLXArray(eps)
            updated.append(params[index] - MLXArray(learningRates[index]) * mHat / denom)
        }
        return updated
    }
}
