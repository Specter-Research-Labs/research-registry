#include "material_memory.h"
#include "scenarios.h"

#include <Jolt/Jolt.h>
#include <Jolt/Core/Factory.h>
#include <Jolt/Core/JobSystemThreadPool.h>
#include <Jolt/Core/StreamWrapper.h>
#include <Jolt/Core/TempAllocator.h>
#include <Jolt/Physics/Body/BodyCreationSettings.h>
#include <Jolt/Physics/Collision/Shape/BoxShape.h>
#include <Jolt/Physics/PhysicsSystem.h>
#include <Jolt/Renderer/DebugRendererRecorder.h>
#include <Jolt/RegisterTypes.h>

#include <algorithm>
#include <cstdarg>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using namespace JPH;

namespace jmm {
namespace {

enum class BodyLayout {
    kLine,
    kStaggered,
};

struct RunConfig {
    ScenarioKind scenario;
    PolicyMode policy;
    ComputeBackend backend;
    enum class MemoryMode {
        kOff,
        kOn,
        kInertialControl,
    };
    MemoryMode memory_mode;
    BodyLayout layout = BodyLayout::kLine;
    std::string memory_variant = "baseline";
    int seed;
    int steps;
    float dt;
    MemoryUpdateParams memory_params;
    std::string out_path;
    std::string jor_out_path;
};

namespace Layers {
constexpr ObjectLayer kNonMoving = 0;
constexpr ObjectLayer kMoving = 1;
constexpr ObjectLayer kNumLayers = 2;
} // namespace Layers

namespace BroadPhaseLayers {
constexpr BroadPhaseLayer kNonMoving(0);
constexpr BroadPhaseLayer kMoving(1);
constexpr uint kNumLayers = 2;
} // namespace BroadPhaseLayers

class ObjectLayerPairFilterImpl final : public ObjectLayerPairFilter {
  public:
    bool ShouldCollide(ObjectLayer in_object1, ObjectLayer in_object2) const override {
        if (in_object1 == Layers::kNonMoving) {
            return in_object2 == Layers::kMoving;
        }
        if (in_object1 == Layers::kMoving) {
            return true;
        }
        return false;
    }
};

class BPLayerInterfaceImpl final : public BroadPhaseLayerInterface {
  public:
    BPLayerInterfaceImpl() {
        object_to_broadphase_[Layers::kNonMoving] = BroadPhaseLayers::kNonMoving;
        object_to_broadphase_[Layers::kMoving] = BroadPhaseLayers::kMoving;
    }

    uint GetNumBroadPhaseLayers() const override { return BroadPhaseLayers::kNumLayers; }

    BroadPhaseLayer GetBroadPhaseLayer(ObjectLayer in_layer) const override {
        return object_to_broadphase_[in_layer];
    }

#if defined(JPH_EXTERNAL_PROFILE) || defined(JPH_PROFILE_ENABLED)
    const char *GetBroadPhaseLayerName(BroadPhaseLayer in_layer) const override {
        if (in_layer == BroadPhaseLayers::kNonMoving) {
            return "NON_MOVING";
        }
        if (in_layer == BroadPhaseLayers::kMoving) {
            return "MOVING";
        }
        return "UNKNOWN";
    }
#endif

  private:
    BroadPhaseLayer object_to_broadphase_[Layers::kNumLayers];
};

class ObjectVsBroadPhaseLayerFilterImpl final : public ObjectVsBroadPhaseLayerFilter {
  public:
    bool ShouldCollide(ObjectLayer in_layer1, BroadPhaseLayer in_layer2) const override {
        if (in_layer1 == Layers::kNonMoving) {
            return in_layer2 == BroadPhaseLayers::kMoving;
        }
        if (in_layer1 == Layers::kMoving) {
            return true;
        }
        return false;
    }
};

static void TraceImpl(const char *in_fmt, ...) {
    va_list list;
    va_start(list, in_fmt);
    char buffer[1024];
    vsnprintf(buffer, sizeof(buffer), in_fmt, list);
    va_end(list);
    std::cerr << buffer << "\n";
}

std::string EscapeJSONString(const std::string &input) {
    std::ostringstream out;
    for (const char ch : input) {
        switch (ch) {
        case '\\':
            out << "\\\\";
            break;
        case '"':
            out << "\\\"";
            break;
        case '\n':
            out << "\\n";
            break;
        default:
            out << ch;
            break;
        }
    }
    return out.str();
}

std::string LayoutName(BodyLayout layout) {
    switch (layout) {
    case BodyLayout::kLine:
        return "line";
    case BodyLayout::kStaggered:
        return "staggered";
    }
    return "unknown";
}

void WriteFloatArrayJSON(std::ofstream &stream, const std::vector<float> &values) {
    stream << "[";
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            stream << ",";
        }
        stream << values[i];
    }
    stream << "]";
}

BodyLayout ParseLayout(const std::string &value) {
    if (value == "line") {
        return BodyLayout::kLine;
    }
    if (value == "staggered") {
        return BodyLayout::kStaggered;
    }
    throw std::invalid_argument("Unsupported layout: " + value);
}

std::string BuildRunID(const RunConfig &cfg) {
    std::string memory_mode = "memory_off";
    if (cfg.memory_mode == RunConfig::MemoryMode::kOn) {
        memory_mode = "memory_on";
    } else if (cfg.memory_mode == RunConfig::MemoryMode::kInertialControl) {
        memory_mode = "memory_inertial_control";
    }
    std::ostringstream out;
    out << ScenarioName(cfg.scenario) << "_" << PolicyName(cfg.policy) << "_"
        << memory_mode << "_" << LayoutName(cfg.layout) << "_" << cfg.memory_variant << "_"
        << (cfg.backend == ComputeBackend::kMetal ? "metal" : "cpu") << "_seed" << cfg.seed;
    return out.str();
}

void WriteStepJSON(std::ofstream &stream,
                   const std::string &run_id,
                   const RunConfig &cfg,
                   int step,
                   const ScenarioStep &scenario,
                   float energy,
                   float goal_distance,
                   float com_x,
                   float com_var_x,
                   float mean_speed,
                   int contact_count,
                   float friction_mean,
                   float stiffness_mean,
                   float plastic_mean,
                   const std::vector<float> &body_positions,
                   const std::vector<float> &strain,
                   const std::vector<float> &contact,
                   const MaterialBuffers &buffers) {
    stream << std::fixed << std::setprecision(6)
           << "{"
           << "\"record_type\":\"step\","
           << "\"run_id\":\"" << EscapeJSONString(run_id) << "\","
           << "\"seed\":" << cfg.seed << ","
           << "\"scenario\":\"" << ScenarioName(cfg.scenario) << "\","
           << "\"policy\":\"" << PolicyName(cfg.policy) << "\","
           << "\"memory_mode\":\"";
    if (cfg.memory_mode == RunConfig::MemoryMode::kOn) {
        stream << "on";
    } else if (cfg.memory_mode == RunConfig::MemoryMode::kInertialControl) {
        stream << "inertial_control";
    } else {
        stream << "off";
    }
    stream << "\","
           << "\"backend\":\"" << (cfg.backend == ComputeBackend::kMetal ? "metal" : "cpu")
           << "\","
           << "\"layout\":\"" << LayoutName(cfg.layout) << "\","
           << "\"memory_variant\":\"" << EscapeJSONString(cfg.memory_variant) << "\","
           << "\"step\":" << step << ","
           << "\"goal_x\":" << scenario.goal_x << ","
           << "\"drive_signal\":" << scenario.drive_signal << ","
           << "\"energy\":" << energy << ","
           << "\"goal_distance\":" << goal_distance << ","
           << "\"com_x\":" << com_x << ","
           << "\"com_var_x\":" << com_var_x << ","
           << "\"mean_speed\":" << mean_speed << ","
           << "\"contact_count\":" << contact_count << ","
           << "\"friction_mean\":" << friction_mean << ","
           << "\"stiffness_mean\":" << stiffness_mean << ","
           << "\"plastic_strain_mean\":" << plastic_mean << ","
           << "\"state_vector\":[" << com_x << "," << com_var_x << "," << mean_speed << "],"
           << "\"body_positions\":";
    WriteFloatArrayJSON(stream, body_positions);
    stream << ","
           << "\"body_strain\":";
    WriteFloatArrayJSON(stream, strain);
    stream << ","
           << "\"body_contact\":";
    WriteFloatArrayJSON(stream, contact);
    stream << ","
           << "\"body_friction\":";
    WriteFloatArrayJSON(stream, buffers.friction);
    stream << ","
           << "\"body_stiffness\":";
    WriteFloatArrayJSON(stream, buffers.stiffness);
    stream << ","
           << "\"body_plasticity\":";
    WriteFloatArrayJSON(stream, buffers.plasticity);
    stream
           << "}" << '\n';
}

void WriteSummaryJSON(std::ofstream &stream,
                      const std::string &run_id,
                      const RunConfig &cfg,
                      double cumulative_goal_distance,
                      double cumulative_energy,
                      int first_goal_step,
                      bool damage_applied) {
    const bool reached_goal = first_goal_step >= 0;
    const int steps_to_goal = reached_goal ? first_goal_step + 1 : cfg.steps;
    const double tau_time = static_cast<double>(steps_to_goal) * static_cast<double>(cfg.dt);
    const double tau_proxy = cumulative_goal_distance + 0.05 * cumulative_energy;

    stream << std::fixed << std::setprecision(6)
           << "{"
           << "\"record_type\":\"summary\","
           << "\"run_id\":\"" << EscapeJSONString(run_id) << "\","
           << "\"seed\":" << cfg.seed << ","
           << "\"scenario\":\"" << ScenarioName(cfg.scenario) << "\","
           << "\"policy\":\"" << PolicyName(cfg.policy) << "\","
           << "\"memory_mode\":\"";
    if (cfg.memory_mode == RunConfig::MemoryMode::kOn) {
        stream << "on";
    } else if (cfg.memory_mode == RunConfig::MemoryMode::kInertialControl) {
        stream << "inertial_control";
    } else {
        stream << "off";
    }
    stream << "\","
           << "\"backend\":\"" << (cfg.backend == ComputeBackend::kMetal ? "metal" : "cpu")
           << "\","
           << "\"layout\":\"" << LayoutName(cfg.layout) << "\","
           << "\"memory_variant\":\"" << EscapeJSONString(cfg.memory_variant) << "\","
           << "\"tau_proxy\":" << tau_proxy << ","
           << "\"tau_time\":" << tau_time << ","
           << "\"steps_to_goal\":" << steps_to_goal << ","
           << "\"reached_goal\":" << (reached_goal ? "true" : "false") << ","
           << "\"damage_applied\":" << (damage_applied ? "true" : "false")
           << "}" << '\n';
}

void WriteMetaJSON(std::ofstream &stream,
                   const std::string &run_id,
                   const RunConfig &cfg,
                   int body_count,
                   const std::string &updater_name,
                   const MemoryUpdateParams &memory_params,
                   const ScenarioParameters &scenario_params) {
    stream << std::fixed << std::setprecision(6)
           << "{"
           << "\"record_type\":\"meta\","
           << "\"run_id\":\"" << EscapeJSONString(run_id) << "\","
           << "\"scenario\":\"" << ScenarioName(cfg.scenario) << "\","
           << "\"policy\":\"" << PolicyName(cfg.policy) << "\","
           << "\"memory_mode\":\"";
    if (cfg.memory_mode == RunConfig::MemoryMode::kOn) {
        stream << "on";
    } else if (cfg.memory_mode == RunConfig::MemoryMode::kInertialControl) {
        stream << "inertial_control";
    } else {
        stream << "off";
    }
    stream << "\","
           << "\"backend\":\"" << (cfg.backend == ComputeBackend::kMetal ? "metal" : "cpu")
           << "\","
           << "\"layout\":\"" << LayoutName(cfg.layout) << "\","
           << "\"memory_variant\":\"" << EscapeJSONString(cfg.memory_variant) << "\","
           << "\"steps\":" << cfg.steps << ","
           << "\"dt\":" << cfg.dt << ","
           << "\"body_count\":" << body_count << ","
           << "\"updater\":\"" << EscapeJSONString(updater_name) << "\","
           << "\"memory_params\":{"
           << "\"base_friction\":" << memory_params.base_friction << ","
           << "\"base_stiffness\":" << memory_params.base_stiffness << ","
           << "\"friction_gain\":" << memory_params.friction_gain << ","
           << "\"stiffness_gain\":" << memory_params.stiffness_gain << ","
           << "\"plastic_gain\":" << memory_params.plastic_gain << ","
           << "\"friction_relax\":" << memory_params.friction_relax << ","
           << "\"stiffness_relax\":" << memory_params.stiffness_relax << ","
           << "\"contact_decay\":" << memory_params.contact_decay << ","
           << "\"strain_decay\":" << memory_params.strain_decay << ","
           << "\"plastic_decay\":" << memory_params.plastic_decay << ","
           << "\"min_friction\":" << memory_params.min_friction << ","
           << "\"max_friction\":" << memory_params.max_friction << ","
           << "\"min_stiffness\":" << memory_params.min_stiffness << ","
           << "\"max_stiffness\":" << memory_params.max_stiffness << ","
           << "\"max_plastic\":" << memory_params.max_plastic
           << "},"
           << "\"scenario_params\":{"
           << "\"blind_drive_limit\":" << scenario_params.blind_drive_limit << ","
           << "\"pulse_start_step\":" << scenario_params.pulse_start_step << ","
           << "\"pulse_end_step\":" << scenario_params.pulse_end_step << ","
           << "\"second_pulse_start_step\":" << scenario_params.second_pulse_start_step << ","
           << "\"second_pulse_end_step\":" << scenario_params.second_pulse_end_step << ","
           << "\"damage_step\":" << scenario_params.damage_step << ","
           << "\"imprint_pulse_goal_x\":" << scenario_params.imprint_pulse_goal_x << ","
           << "\"imprint_tail_goal_x\":" << scenario_params.imprint_tail_goal_x << ","
           << "\"imprint_pulse_drive\":" << scenario_params.imprint_pulse_drive << ","
           << "\"hysteresis_drive_amplitude\":" << scenario_params.hysteresis_drive_amplitude
           << ","
           << "\"damage_goal_x\":" << scenario_params.damage_goal_x << ","
           << "\"damage_initial_drive\":" << scenario_params.damage_initial_drive << ","
           << "\"damage_recovery_drive\":" << scenario_params.damage_recovery_drive << ","
           << "\"competing_first_goal_x\":" << scenario_params.competing_first_goal_x << ","
           << "\"competing_second_goal_x\":" << scenario_params.competing_second_goal_x << ","
           << "\"competing_first_drive\":" << scenario_params.competing_first_drive << ","
           << "\"competing_second_drive\":" << scenario_params.competing_second_drive
           << "}"
           << "}" << '\n';
}

float Mean(const std::vector<float> &values) {
    if (values.empty()) {
        return 0.0f;
    }
    const float total = std::accumulate(values.begin(), values.end(), 0.0f);
    return total / static_cast<float>(values.size());
}

Vec3 PositionFromBuffer(const std::vector<float> &body_positions, std::size_t index) {
    const std::size_t base = index * 3;
    return Vec3(
        body_positions[base], body_positions[base + 1], body_positions[base + 2]);
}

Color LinkColor(const RunConfig &cfg,
                const MaterialBuffers &buffers,
                std::size_t left_index,
                std::size_t right_index) {
    if (cfg.memory_mode != RunConfig::MemoryMode::kOn) {
        return cfg.memory_mode == RunConfig::MemoryMode::kInertialControl ? Color(96, 162, 255)
                                                                          : Color(158, 164, 176);
    }

    const float plastic_mean =
        0.5f * (buffers.plasticity[left_index] + buffers.plasticity[right_index]);
    const float normalized = std::clamp(
        plastic_mean / std::max(1.0e-6f, cfg.memory_params.max_plastic), 0.0f, 1.0f);
    return Color::sGreenRedGradient(normalized);
}

#ifdef JPH_DEBUG_RENDERER
void DrawRecordingOverlay(DebugRenderer &renderer,
                          const RunConfig &cfg,
                          const ScenarioStep &scenario,
                          const std::vector<float> &body_positions,
                          const MaterialBuffers &buffers,
                          const std::vector<Vec3> &com_trail) {
    constexpr float kLinkRadius = 0.075f;
    constexpr float kGoalArrowHeight = 0.85f;

    for (std::size_t i = 0; i + 1 < body_positions.size() / 3; ++i) {
        const Vec3 left = PositionFromBuffer(body_positions, i);
        const Vec3 right = PositionFromBuffer(body_positions, i + 1);
        const Vec3 delta = right - left;
        const float length = delta.Length();
        if (length <= 1.0e-4f) {
            continue;
        }

        const Vec3 midpoint = 0.5f * (left + right);
        const Quat rotation = Quat::sFromTo(Vec3::sAxisY(), delta / length);
        const Mat44 transform = Mat44::sRotationTranslation(rotation, midpoint);
        const float half_height = std::max(0.0f, 0.5f * length - kLinkRadius);

        renderer.DrawCapsule(
            transform,
            half_height,
            kLinkRadius,
            LinkColor(cfg, buffers, i, i + 1),
            DebugRenderer::ECastShadow::On,
            DebugRenderer::EDrawMode::Solid);
    }

    if (std::abs(scenario.goal_x) > 1.0e-4f) {
        const RVec3 goal_base(scenario.goal_x, 0.12f, 0.0f);
        const RVec3 goal_tip(scenario.goal_x, kGoalArrowHeight, 0.0f);
        renderer.DrawArrow(goal_base, goal_tip, Color::sOrange, 0.22f);
        renderer.DrawMarker(goal_tip, Color::sYellow, 0.12f);
    }

    for (std::size_t i = 1; i < com_trail.size(); ++i) {
        renderer.DrawLine(
            RVec3(com_trail[i - 1]),
            RVec3(com_trail[i]),
            Color(Color::sCyan, 180));
    }
}
#endif

RunConfig ParseArgs(int argc, char **argv) {
    std::unordered_map<std::string, std::string> options;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (!arg.starts_with("--")) {
            throw std::invalid_argument("Unexpected positional argument: " + arg);
        }
        if (i + 1 >= argc) {
            throw std::invalid_argument("Missing value for argument: " + arg);
        }
        options[arg.substr(2)] = argv[++i];
    }

    const std::vector<std::string> required = {
        "scenario", "policy", "backend", "memory", "seed", "steps", "dt", "out"};
    for (const std::string &key : required) {
        if (!options.contains(key)) {
            throw std::invalid_argument("Missing required argument --" + key);
        }
    }

    RunConfig cfg{};
    cfg.scenario = ParseScenario(options.at("scenario"));
    cfg.policy = ParsePolicy(options.at("policy"));

    const std::string backend = options.at("backend");
    if (backend == "cpu") {
        cfg.backend = ComputeBackend::kCPU;
    } else if (backend == "metal") {
        cfg.backend = ComputeBackend::kMetal;
    } else {
        throw std::invalid_argument("Unsupported backend: " + backend);
    }

    const std::string memory_mode = options.at("memory");
    if (memory_mode == "on") {
        cfg.memory_mode = RunConfig::MemoryMode::kOn;
    } else if (memory_mode == "off") {
        cfg.memory_mode = RunConfig::MemoryMode::kOff;
    } else if (memory_mode == "inertial_control") {
        cfg.memory_mode = RunConfig::MemoryMode::kInertialControl;
    } else {
        throw std::invalid_argument("Unsupported memory mode: " + memory_mode);
    }

    cfg.seed = std::stoi(options.at("seed"));
    cfg.steps = std::stoi(options.at("steps"));
    cfg.dt = std::stof(options.at("dt"));
    cfg.layout = options.contains("layout") ? ParseLayout(options.at("layout")) : BodyLayout::kLine;
    if (options.contains("memory-variant")) {
        cfg.memory_variant = options.at("memory-variant");
    }
    cfg.memory_params.dt = cfg.dt;
    if (options.contains("plastic-gain")) {
        cfg.memory_params.plastic_gain = std::stof(options.at("plastic-gain"));
    }
    if (options.contains("plastic-decay")) {
        cfg.memory_params.plastic_decay = std::stof(options.at("plastic-decay"));
    }
    if (options.contains("max-plastic")) {
        cfg.memory_params.max_plastic = std::stof(options.at("max-plastic"));
    }
    cfg.out_path = options.at("out");
    if (options.contains("jor-out")) {
        cfg.jor_out_path = options.at("jor-out");
    }

    if (cfg.steps <= 0) {
        throw std::invalid_argument("--steps must be positive");
    }
    if (cfg.dt <= 0.0f) {
        throw std::invalid_argument("--dt must be positive");
    }
    if (cfg.memory_params.plastic_gain < 0.0f) {
        throw std::invalid_argument("--plastic-gain must be non-negative");
    }
    if (cfg.memory_params.plastic_decay < 0.0f || cfg.memory_params.plastic_decay > 1.0f) {
        throw std::invalid_argument("--plastic-decay must be in [0, 1]");
    }
    if (cfg.memory_params.max_plastic <= 0.0f) {
        throw std::invalid_argument("--max-plastic must be positive");
    }

    return cfg;
}

int Simulate(const RunConfig &cfg) {
    std::filesystem::create_directories(std::filesystem::path(cfg.out_path).parent_path());
    std::ofstream output(cfg.out_path);
    if (!output.is_open()) {
        throw std::runtime_error("Failed to open output file: " + cfg.out_path);
    }

#ifndef JPH_DEBUG_RENDERER
    if (!cfg.jor_out_path.empty()) {
        throw std::runtime_error(
            "This build does not include Jolt debug rendering; --jor-out is unavailable");
    }
#endif

    RegisterDefaultAllocator();
    Trace = TraceImpl;
    Factory::sInstance = new Factory();
    RegisterTypes();

#ifdef JPH_DEBUG_RENDERER
    std::ofstream jor_output;
    std::unique_ptr<StreamOutWrapper> jor_stream;
    std::unique_ptr<DebugRendererRecorder> jor_recorder;
    if (!cfg.jor_out_path.empty()) {
        const std::filesystem::path jor_path(cfg.jor_out_path);
        if (jor_path.has_parent_path()) {
            std::filesystem::create_directories(jor_path.parent_path());
        }
        jor_output.open(jor_path, std::ofstream::out | std::ofstream::binary | std::ofstream::trunc);
        if (!jor_output.is_open()) {
            throw std::runtime_error("Failed to open Jolt recording output file: " +
                                     cfg.jor_out_path);
        }
        jor_stream = std::make_unique<StreamOutWrapper>(jor_output);
        jor_recorder = std::make_unique<DebugRendererRecorder>(*jor_stream);
    }
#endif

    TempAllocatorImpl temp_allocator(10 * 1024 * 1024);
    const uint hw_threads = std::max(1u, std::thread::hardware_concurrency());
    JobSystemThreadPool job_system(cMaxPhysicsJobs, cMaxPhysicsBarriers, hw_threads - 1);

    BPLayerInterfaceImpl broad_phase_layer_interface;
    ObjectVsBroadPhaseLayerFilterImpl object_vs_broadphase_layer_filter;
    ObjectLayerPairFilterImpl object_vs_object_layer_filter;

    PhysicsSystem physics_system;
    physics_system.Init(2048,
                        0,
                        2048,
                        2048,
                        broad_phase_layer_interface,
                        object_vs_broadphase_layer_filter,
                        object_vs_object_layer_filter);
    physics_system.SetGravity(Vec3(0.0f, -9.81f, 0.0f));

    BodyInterface &body_interface = physics_system.GetBodyInterface();

    const BoxShapeSettings floor_shape_settings(Vec3(40.0f, 0.5f, 10.0f));
    const ShapeSettings::ShapeResult floor_shape_result = floor_shape_settings.Create();
    if (floor_shape_result.HasError()) {
        throw std::runtime_error(
            "Failed to create floor shape: " + std::string(floor_shape_result.GetError().c_str()));
    }

    BodyCreationSettings floor_settings(
        floor_shape_result.Get(), RVec3(0.0, -0.5, 0.0), Quat::sIdentity(), EMotionType::Static,
        Layers::kNonMoving);
    body_interface.CreateAndAddBody(floor_settings, EActivation::DontActivate);

    const BoxShapeSettings mover_shape_settings(Vec3(0.23f, 0.23f, 0.23f));
    const ShapeSettings::ShapeResult mover_shape_result = mover_shape_settings.Create();
    if (mover_shape_result.HasError()) {
        throw std::runtime_error(
            "Failed to create mover shape: " + std::string(mover_shape_result.GetError().c_str()));
    }

    constexpr int kBodyCount = 14;
    std::vector<BodyID> body_ids;
    body_ids.reserve(kBodyCount);
    std::vector<float> rest_x;
    rest_x.reserve(kBodyCount);

    const float spacing = 0.55f;
    const float stagger_x_offset = 0.12f;
    const float stagger_y_offset = 0.18f;
    const float center = static_cast<float>(kBodyCount - 1) * 0.5f;
    for (int i = 0; i < kBodyCount; ++i) {
        float x = (static_cast<float>(i) - center) * spacing;
        float y = 0.45f;
        if (cfg.layout == BodyLayout::kStaggered) {
            x += (i % 2 == 0) ? -stagger_x_offset : stagger_x_offset;
            y += (i % 2 == 0) ? 0.0f : stagger_y_offset;
        }
        BodyCreationSettings body_settings(mover_shape_result.Get(),
                                           RVec3(x, y, 0.0f),
                                           Quat::sIdentity(),
                                           EMotionType::Dynamic,
                                           Layers::kMoving);
        body_settings.mFriction = 0.45f;
        body_settings.mRestitution = 0.0f;
        BodyID id = body_interface.CreateAndAddBody(body_settings, EActivation::Activate);
        body_ids.push_back(id);
        rest_x.push_back(x);
    }

    MemoryUpdateParams memory_params = cfg.memory_params;
    memory_params.dt = cfg.dt;
    const ScenarioParameters scenario_params = DescribeScenario(cfg.scenario, cfg.steps);
    MaterialBuffers buffers;
    ResetMaterialBuffers(body_ids.size(), memory_params, buffers);

    auto updater = CreateMaterialMemoryUpdater(cfg.backend, body_ids.size(), memory_params);
    if (cfg.backend == ComputeBackend::kMetal && updater->backend_name() != "metal") {
        throw std::runtime_error("Metal backend requested but not available");
    }

    const std::string run_id = BuildRunID(cfg);
    std::mt19937 rng(static_cast<uint32_t>(cfg.seed));
    std::uniform_int_distribution<int> damage_pick(0, static_cast<int>(body_ids.size() - 1));
    std::uniform_real_distribution<float> kick_dist(-6.0f, 6.0f);

    std::vector<float> strain(body_ids.size(), 0.0f);
    std::vector<float> contact(body_ids.size(), 0.0f);
    std::vector<float> body_positions(body_ids.size() * 3, 0.0f);
    std::vector<Vec3> com_trail;
    com_trail.reserve(96);

    bool damage_applied = false;
    int first_goal_step = -1;
    double cumulative_goal_distance = 0.0;
    double cumulative_energy = 0.0;

    const float rest_center = Mean(rest_x);

    WriteMetaJSON(output,
                  run_id,
                  cfg,
                  kBodyCount,
                  updater->backend_name(),
                  memory_params,
                  scenario_params);

    for (int step = 0; step < cfg.steps; ++step) {
        const ScenarioStep scenario = ComputeScenarioStep(cfg.scenario, cfg.policy, step, cfg.steps, rng);

        for (std::size_t i = 0; i < body_ids.size(); ++i) {
            const BodyID id = body_ids[i];
            const RVec3 pos = body_interface.GetCenterOfMassPosition(id);
            strain[i] = std::abs(static_cast<float>(pos.GetX()) - rest_x[i]);
            contact[i] = pos.GetY() <= 0.26 ? 1.0f : 0.0f;
        }

        if (cfg.memory_mode == RunConfig::MemoryMode::kOn) {
            updater->update(strain, contact, buffers);
        } else {
            ResetMaterialBuffers(body_ids.size(), memory_params, buffers);
        }

        const bool blind_policy = cfg.policy == PolicyMode::kBlind;
        const bool inertial_control = cfg.memory_mode == RunConfig::MemoryMode::kInertialControl;
        std::uniform_real_distribution<float> random_sign(-1.0f, 1.0f);

        for (std::size_t i = 0; i < body_ids.size(); ++i) {
            const BodyID id = body_ids[i];
            const RVec3 pos = body_interface.GetCenterOfMassPosition(id);
            const Vec3 vel = body_interface.GetLinearVelocity(id);
            const float local_target = scenario.goal_x + (rest_x[i] - rest_center);
            const float error = local_target - static_cast<float>(pos.GetX());
            const float plastic_bias = buffers.plasticity[i] * (error >= 0.0f ? 1.0f : -1.0f);
            const float stiffness_delta =
                (buffers.stiffness[i] - memory_params.base_stiffness) / memory_params.base_stiffness;
            const float kp = 2.6f + 0.9f * std::clamp(stiffness_delta, -0.8f, 1.8f);
            const float kd = 1.9f;
            const float drive_term = 0.12f * scenario.drive_signal;
            const float plastic_term = 0.30f * plastic_bias;
            const float directed_accel = kp * error - kd * vel.GetX() + drive_term + plastic_term;

            float control_accel = directed_accel;
            if (blind_policy) {
                const float budget = std::abs(directed_accel);
                const float sign = random_sign(rng) >= 0.0f ? 1.0f : -1.0f;
                control_accel = sign * budget;
            }

            float damping = 0.20f + 0.80f * std::clamp(buffers.friction[i], 0.0f, 1.5f);
            if (inertial_control) {
                damping *= 1.8f;
            }
            float vx = vel.GetX() + control_accel * cfg.dt;
            vx *= std::max(0.0f, 1.0f - damping * cfg.dt);
            if (inertial_control) {
                vx = std::clamp(vx, -6.0f, 6.0f);
            } else {
                vx = std::clamp(vx, -10.0f, 10.0f);
            }

            body_interface.SetFriction(id, buffers.friction[i]);
            body_interface.SetLinearVelocity(id, Vec3(vx, vel.GetY(), vel.GetZ()));
        }

        if (scenario.trigger_damage && !damage_applied) {
            const int damage_events = std::max<int>(2, static_cast<int>(body_ids.size() / 3));
            std::unordered_set<int> touched;
            while (static_cast<int>(touched.size()) < damage_events) {
                touched.insert(damage_pick(rng));
            }
            for (const int idx : touched) {
                const BodyID id = body_ids[static_cast<std::size_t>(idx)];
                body_interface.SetLinearVelocity(id, Vec3(kick_dist(rng), std::abs(kick_dist(rng)), 0.0f));
                buffers.plasticity[static_cast<std::size_t>(idx)] = std::min(
                    memory_params.max_plastic,
                    buffers.plasticity[static_cast<std::size_t>(idx)] + 1.25f);
            }
            damage_applied = true;
        }

        const EPhysicsUpdateError update_error =
            physics_system.Update(cfg.dt, 1, &temp_allocator, &job_system);
        if (update_error != EPhysicsUpdateError::None) {
            throw std::runtime_error("Physics update failed with code " +
                                     std::to_string(static_cast<int>(update_error)));
        }

        float com_x = 0.0f;
        float com_sq = 0.0f;
        float mean_speed = 0.0f;
        int contact_count = 0;

        for (std::size_t i = 0; i < body_ids.size(); ++i) {
            const BodyID id = body_ids[i];
            const RVec3 pos = body_interface.GetCenterOfMassPosition(id);
            const Vec3 vel = body_interface.GetLinearVelocity(id);
            const float x = static_cast<float>(pos.GetX());
            const float y = static_cast<float>(pos.GetY());
            const float z = static_cast<float>(pos.GetZ());
            com_x += x;
            com_sq += x * x;
            mean_speed += vel.Length();
            if (pos.GetY() <= 0.26) {
                ++contact_count;
            }
            body_positions[i * 3 + 0] = x;
            body_positions[i * 3 + 1] = y;
            body_positions[i * 3 + 2] = z;
        }

        com_x /= static_cast<float>(body_ids.size());
        com_sq /= static_cast<float>(body_ids.size());
        mean_speed /= static_cast<float>(body_ids.size());
        const float com_var_x = std::max(0.0f, com_sq - com_x * com_x);
        com_trail.push_back(Vec3(com_x, 0.3f, 0.0f));
        if (com_trail.size() > 72) {
            com_trail.erase(com_trail.begin());
        }

        const float goal_distance = std::abs(com_x - scenario.goal_x);
        const float energy = mean_speed * mean_speed + goal_distance * goal_distance;

        cumulative_goal_distance += static_cast<double>(goal_distance);
        cumulative_energy += static_cast<double>(energy);

        if (first_goal_step < 0 && std::abs(scenario.goal_x) > 0.5f && goal_distance <= 0.35f) {
            first_goal_step = step;
        }

        WriteStepJSON(output,
                      run_id,
                      cfg,
                      step,
                      scenario,
                      energy,
                      goal_distance,
                      com_x,
                      com_var_x,
                      mean_speed,
                      contact_count,
                      Mean(buffers.friction),
                      Mean(buffers.stiffness),
                      Mean(buffers.plasticity),
                      body_positions,
                      strain,
                      contact,
                      buffers);

#ifdef JPH_DEBUG_RENDERER
        if (jor_recorder) {
            BodyManager::DrawSettings draw_settings;
            physics_system.DrawBodies(draw_settings, jor_recorder.get());
            DrawRecordingOverlay(
                *jor_recorder, cfg, scenario, body_positions, buffers, com_trail);
            jor_recorder->EndFrame();
        }
#endif
    }

    WriteSummaryJSON(output,
                     run_id,
                     cfg,
                     cumulative_goal_distance,
                     cumulative_energy,
                     first_goal_step,
                     damage_applied);

    UnregisterTypes();
    delete Factory::sInstance;
    Factory::sInstance = nullptr;

    return 0;
}

} // namespace
} // namespace jmm

int main(int argc, char **argv) {
    try {
        const jmm::RunConfig cfg = jmm::ParseArgs(argc, argv);
        return jmm::Simulate(cfg);
    } catch (const std::exception &exc) {
        std::cerr << "jolt_memory_lab: " << exc.what() << '\n';
        return 2;
    }
}
