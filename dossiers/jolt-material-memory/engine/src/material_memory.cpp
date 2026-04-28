#include "material_memory.h"

#include <algorithm>
#include <stdexcept>

namespace jmm {

std::unique_ptr<MaterialMemoryUpdater>
CreateMetalMaterialMemoryUpdater(std::size_t body_count, const MemoryUpdateParams &params, std::string &error);

namespace {

float ClampValue(float value, float lo, float hi) {
    return std::min(std::max(value, lo), hi);
}

class CPUMaterialMemoryUpdater final : public MaterialMemoryUpdater {
  public:
    CPUMaterialMemoryUpdater(std::size_t body_count, const MemoryUpdateParams &params)
        : params_(params), contact_memory_(body_count, 0.0f), strain_memory_(body_count, 0.0f) {}

    std::string backend_name() const override { return "cpu"; }

    void update(const std::vector<float> &strain,
                const std::vector<float> &contact,
                MaterialBuffers &buffers) override {
        if (strain.size() != contact_memory_.size() || contact.size() != contact_memory_.size()) {
            throw std::invalid_argument("strain/contact size mismatch for material update");
        }
        if (buffers.friction.size() != contact_memory_.size() ||
            buffers.stiffness.size() != contact_memory_.size() ||
            buffers.plasticity.size() != contact_memory_.size()) {
            throw std::invalid_argument("material buffer size mismatch");
        }

        for (std::size_t i = 0; i < contact_memory_.size(); ++i) {
            contact_memory_[i] = params_.contact_decay * contact_memory_[i] + contact[i];
            strain_memory_[i] = params_.strain_decay * strain_memory_[i] + strain[i];

            const float next_friction =
                buffers.friction[i] + params_.friction_gain * contact_memory_[i] * params_.dt -
                params_.friction_relax * (buffers.friction[i] - params_.base_friction) * params_.dt;

            const float next_stiffness =
                buffers.stiffness[i] + params_.stiffness_gain * strain_memory_[i] * params_.dt -
                params_.stiffness_relax * (buffers.stiffness[i] - params_.base_stiffness) * params_.dt;

            const float next_plastic =
                buffers.plasticity[i] * params_.plastic_decay +
                params_.plastic_gain * strain[i] * contact_memory_[i];

            buffers.friction[i] =
                ClampValue(next_friction, params_.min_friction, params_.max_friction);
            buffers.stiffness[i] =
                ClampValue(next_stiffness, params_.min_stiffness, params_.max_stiffness);
            buffers.plasticity[i] = ClampValue(next_plastic, 0.0f, params_.max_plastic);
        }
    }

  private:
    MemoryUpdateParams params_;
    std::vector<float> contact_memory_;
    std::vector<float> strain_memory_;
};

} // namespace

void ResetMaterialBuffers(std::size_t body_count,
                          const MemoryUpdateParams &params,
                          MaterialBuffers &buffers) {
    buffers.friction.assign(body_count, params.base_friction);
    buffers.stiffness.assign(body_count, params.base_stiffness);
    buffers.plasticity.assign(body_count, 0.0f);
}

std::unique_ptr<MaterialMemoryUpdater>
CreateMaterialMemoryUpdater(ComputeBackend backend, std::size_t body_count, const MemoryUpdateParams &params) {
    if (body_count == 0) {
        throw std::invalid_argument("body_count must be non-zero");
    }

    if (backend == ComputeBackend::kCPU) {
        return std::make_unique<CPUMaterialMemoryUpdater>(body_count, params);
    }

    std::string error;
    auto updater = CreateMetalMaterialMemoryUpdater(body_count, params, error);
    if (!updater) {
        throw std::runtime_error("Metal backend unavailable: " + error);
    }
    return updater;
}

} // namespace jmm

#if !defined(__APPLE__)
namespace jmm {
std::unique_ptr<MaterialMemoryUpdater>
CreateMetalMaterialMemoryUpdater(std::size_t, const MemoryUpdateParams &, std::string &error) {
    error = "Metal backend requires macOS";
    return nullptr;
}
} // namespace jmm
#endif
