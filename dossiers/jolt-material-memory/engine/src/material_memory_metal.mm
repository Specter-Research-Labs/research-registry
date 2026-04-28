#include "material_memory.h"

#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <string>

#import <Foundation/Foundation.h>
#import <Metal/Metal.h>

namespace jmm {

namespace {

struct MetalParams {
    float dt;

    float base_friction;
    float base_stiffness;

    float friction_gain;
    float stiffness_gain;
    float plastic_gain;

    float friction_relax;
    float stiffness_relax;

    float contact_decay;
    float strain_decay;
    float plastic_decay;

    float min_friction;
    float max_friction;
    float min_stiffness;
    float max_stiffness;
    float max_plastic;

    uint32_t count;
};

const char *kKernelSource = R"METAL(
#include <metal_stdlib>
using namespace metal;

struct MetalParams {
    float dt;

    float base_friction;
    float base_stiffness;

    float friction_gain;
    float stiffness_gain;
    float plastic_gain;

    float friction_relax;
    float stiffness_relax;

    float contact_decay;
    float strain_decay;
    float plastic_decay;

    float min_friction;
    float max_friction;
    float min_stiffness;
    float max_stiffness;
    float max_plastic;

    uint count;
};

kernel void update_material(
    device const float *strain [[buffer(0)]],
    device const float *contact [[buffer(1)]],
    device float *friction [[buffer(2)]],
    device float *stiffness [[buffer(3)]],
    device float *plasticity [[buffer(4)]],
    device float *contact_memory [[buffer(5)]],
    device float *strain_memory [[buffer(6)]],
    constant MetalParams &params [[buffer(7)]],
    uint gid [[thread_position_in_grid]]) {
    if (gid >= params.count) {
        return;
    }

    contact_memory[gid] = params.contact_decay * contact_memory[gid] + contact[gid];
    strain_memory[gid] = params.strain_decay * strain_memory[gid] + strain[gid];

    const float next_friction = friction[gid] + params.friction_gain * contact_memory[gid] * params.dt -
        params.friction_relax * (friction[gid] - params.base_friction) * params.dt;

    const float next_stiffness = stiffness[gid] + params.stiffness_gain * strain_memory[gid] * params.dt -
        params.stiffness_relax * (stiffness[gid] - params.base_stiffness) * params.dt;

    const float next_plastic = plasticity[gid] * params.plastic_decay +
        params.plastic_gain * strain[gid] * contact_memory[gid];

    friction[gid] = clamp(next_friction, params.min_friction, params.max_friction);
    stiffness[gid] = clamp(next_stiffness, params.min_stiffness, params.max_stiffness);
    plasticity[gid] = clamp(next_plastic, 0.0f, params.max_plastic);
}
)METAL";

class MetalMaterialMemoryUpdater final : public MaterialMemoryUpdater {
  public:
    MetalMaterialMemoryUpdater(std::size_t count, const MemoryUpdateParams &params)
        : count_(count), params_(params), initialized_state_(false) {
        @autoreleasepool {
            device_ = MTLCreateSystemDefaultDevice();
            if (device_ == nil) {
                throw std::runtime_error("No Metal device available");
            }

            queue_ = [device_ newCommandQueue];
            if (queue_ == nil) {
                throw std::runtime_error("Failed to create Metal command queue");
            }

            NSError *error = nil;
            NSString *source = [NSString stringWithUTF8String:kKernelSource];
            id<MTLLibrary> library = [device_ newLibraryWithSource:source options:nil error:&error];
            if (library == nil) {
                const char *message = error != nil ? [[error localizedDescription] UTF8String]
                                                   : "unknown Metal library error";
                throw std::runtime_error(std::string("Metal shader compilation failed: ") + message);
            }

            id<MTLFunction> function = [library newFunctionWithName:@"update_material"];
            if (function == nil) {
                throw std::runtime_error("Metal function update_material not found");
            }

            pipeline_ = [device_ newComputePipelineStateWithFunction:function error:&error];
            if (pipeline_ == nil) {
                const char *message = error != nil ? [[error localizedDescription] UTF8String]
                                                   : "unknown Metal pipeline error";
                throw std::runtime_error(std::string("Failed to create Metal pipeline: ") + message);
            }

            const NSUInteger bytes = sizeof(float) * count_;
            strain_buffer_ = [device_ newBufferWithLength:bytes options:MTLResourceStorageModeShared];
            contact_buffer_ = [device_ newBufferWithLength:bytes options:MTLResourceStorageModeShared];
            friction_buffer_ = [device_ newBufferWithLength:bytes options:MTLResourceStorageModeShared];
            stiffness_buffer_ = [device_ newBufferWithLength:bytes options:MTLResourceStorageModeShared];
            plasticity_buffer_ = [device_ newBufferWithLength:bytes options:MTLResourceStorageModeShared];
            contact_memory_buffer_ =
                [device_ newBufferWithLength:bytes options:MTLResourceStorageModeShared];
            strain_memory_buffer_ =
                [device_ newBufferWithLength:bytes options:MTLResourceStorageModeShared];
            params_buffer_ = [device_ newBufferWithLength:sizeof(MetalParams)
                                                  options:MTLResourceStorageModeShared];

            if (strain_buffer_ == nil || contact_buffer_ == nil || friction_buffer_ == nil ||
                stiffness_buffer_ == nil || plasticity_buffer_ == nil ||
                contact_memory_buffer_ == nil || strain_memory_buffer_ == nil || params_buffer_ == nil) {
                throw std::runtime_error("Failed to allocate Metal buffers");
            }

            std::memset([contact_memory_buffer_ contents], 0, bytes);
            std::memset([strain_memory_buffer_ contents], 0, bytes);
        }
    }

    std::string backend_name() const override { return "metal"; }

    void update(const std::vector<float> &strain,
                const std::vector<float> &contact,
                MaterialBuffers &buffers) override {
        if (strain.size() != count_ || contact.size() != count_) {
            throw std::invalid_argument("Metal updater input size mismatch");
        }
        if (buffers.friction.size() != count_ || buffers.stiffness.size() != count_ ||
            buffers.plasticity.size() != count_) {
            throw std::invalid_argument("Metal updater material buffer size mismatch");
        }

        @autoreleasepool {
            const NSUInteger bytes = sizeof(float) * count_;
            std::memcpy([strain_buffer_ contents], strain.data(), bytes);
            std::memcpy([contact_buffer_ contents], contact.data(), bytes);

            if (!initialized_state_) {
                std::memcpy([friction_buffer_ contents], buffers.friction.data(), bytes);
                std::memcpy([stiffness_buffer_ contents], buffers.stiffness.data(), bytes);
                std::memcpy([plasticity_buffer_ contents], buffers.plasticity.data(), bytes);
                initialized_state_ = true;
            }

            MetalParams kernel_params{};
            kernel_params.dt = params_.dt;
            kernel_params.base_friction = params_.base_friction;
            kernel_params.base_stiffness = params_.base_stiffness;
            kernel_params.friction_gain = params_.friction_gain;
            kernel_params.stiffness_gain = params_.stiffness_gain;
            kernel_params.plastic_gain = params_.plastic_gain;
            kernel_params.friction_relax = params_.friction_relax;
            kernel_params.stiffness_relax = params_.stiffness_relax;
            kernel_params.contact_decay = params_.contact_decay;
            kernel_params.strain_decay = params_.strain_decay;
            kernel_params.plastic_decay = params_.plastic_decay;
            kernel_params.min_friction = params_.min_friction;
            kernel_params.max_friction = params_.max_friction;
            kernel_params.min_stiffness = params_.min_stiffness;
            kernel_params.max_stiffness = params_.max_stiffness;
            kernel_params.max_plastic = params_.max_plastic;
            kernel_params.count = static_cast<uint32_t>(count_);
            std::memcpy([params_buffer_ contents], &kernel_params, sizeof(MetalParams));

            id<MTLCommandBuffer> command_buffer = [queue_ commandBuffer];
            if (command_buffer == nil) {
                throw std::runtime_error("Failed to allocate Metal command buffer");
            }

            id<MTLComputeCommandEncoder> encoder = [command_buffer computeCommandEncoder];
            if (encoder == nil) {
                throw std::runtime_error("Failed to create Metal compute encoder");
            }

            [encoder setComputePipelineState:pipeline_];
            [encoder setBuffer:strain_buffer_ offset:0 atIndex:0];
            [encoder setBuffer:contact_buffer_ offset:0 atIndex:1];
            [encoder setBuffer:friction_buffer_ offset:0 atIndex:2];
            [encoder setBuffer:stiffness_buffer_ offset:0 atIndex:3];
            [encoder setBuffer:plasticity_buffer_ offset:0 atIndex:4];
            [encoder setBuffer:contact_memory_buffer_ offset:0 atIndex:5];
            [encoder setBuffer:strain_memory_buffer_ offset:0 atIndex:6];
            [encoder setBuffer:params_buffer_ offset:0 atIndex:7];

            const NSUInteger threads_per_group = std::min<NSUInteger>(pipeline_.maxTotalThreadsPerThreadgroup, 128);
            MTLSize group_size = MTLSizeMake(threads_per_group, 1, 1);
            MTLSize grid_size = MTLSizeMake(count_, 1, 1);
            [encoder dispatchThreads:grid_size threadsPerThreadgroup:group_size];
            [encoder endEncoding];

            [command_buffer commit];
            [command_buffer waitUntilCompleted];

            if (command_buffer.status == MTLCommandBufferStatusError) {
                NSError *error = command_buffer.error;
                const char *message = error != nil ? [[error localizedDescription] UTF8String]
                                                   : "unknown command buffer failure";
                throw std::runtime_error(std::string("Metal command execution failed: ") + message);
            }

            std::memcpy(buffers.friction.data(), [friction_buffer_ contents], bytes);
            std::memcpy(buffers.stiffness.data(), [stiffness_buffer_ contents], bytes);
            std::memcpy(buffers.plasticity.data(), [plasticity_buffer_ contents], bytes);
        }
    }

  private:
    std::size_t count_;
    MemoryUpdateParams params_;
    bool initialized_state_;

    id<MTLDevice> device_;
    id<MTLCommandQueue> queue_;
    id<MTLComputePipelineState> pipeline_;

    id<MTLBuffer> strain_buffer_;
    id<MTLBuffer> contact_buffer_;
    id<MTLBuffer> friction_buffer_;
    id<MTLBuffer> stiffness_buffer_;
    id<MTLBuffer> plasticity_buffer_;
    id<MTLBuffer> contact_memory_buffer_;
    id<MTLBuffer> strain_memory_buffer_;
    id<MTLBuffer> params_buffer_;
};

} // namespace

std::unique_ptr<MaterialMemoryUpdater>
CreateMetalMaterialMemoryUpdater(std::size_t body_count,
                                 const MemoryUpdateParams &params,
                                 std::string &error) {
    try {
        return std::make_unique<MetalMaterialMemoryUpdater>(body_count, params);
    } catch (const std::exception &exc) {
        error = exc.what();
        return nullptr;
    }
}

} // namespace jmm
