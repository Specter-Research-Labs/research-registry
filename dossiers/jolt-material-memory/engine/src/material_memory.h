#pragma once

#include <cstddef>
#include <memory>
#include <string>
#include <vector>

namespace jmm {

enum class ComputeBackend {
    kCPU,
    kMetal,
};

struct MemoryUpdateParams {
    float dt = 1.0f / 60.0f;

    float base_friction = 0.45f;
    float base_stiffness = 18.0f;

    float friction_gain = 0.08f;
    float stiffness_gain = 0.20f;
    float plastic_gain = 0.03f;

    float friction_relax = 0.24f;
    float stiffness_relax = 0.18f;

    float contact_decay = 0.92f;
    float strain_decay = 0.90f;
    float plastic_decay = 0.985f;

    float min_friction = 0.08f;
    float max_friction = 1.35f;
    float min_stiffness = 4.0f;
    float max_stiffness = 64.0f;
    float max_plastic = 5.0f;
};

struct MaterialBuffers {
    std::vector<float> friction;
    std::vector<float> stiffness;
    std::vector<float> plasticity;

    [[nodiscard]] std::size_t size() const { return friction.size(); }
};

class MaterialMemoryUpdater {
  public:
    virtual ~MaterialMemoryUpdater() = default;

    virtual std::string backend_name() const = 0;

    virtual void update(const std::vector<float> &strain,
                        const std::vector<float> &contact,
                        MaterialBuffers &buffers) = 0;
};

std::unique_ptr<MaterialMemoryUpdater>
CreateMaterialMemoryUpdater(ComputeBackend backend, std::size_t body_count, const MemoryUpdateParams &params);

void ResetMaterialBuffers(std::size_t body_count,
                          const MemoryUpdateParams &params,
                          MaterialBuffers &buffers);

} // namespace jmm
