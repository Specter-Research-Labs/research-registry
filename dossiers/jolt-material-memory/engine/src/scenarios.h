#pragma once

#include <random>
#include <string>

namespace jmm {

enum class ScenarioKind {
    kImprintRetention,
    kReversalHysteresis,
    kDamageRelearning,
    kCompetingTargets,
};

enum class PolicyMode {
    kDirected,
    kBlind,
};

struct ScenarioStep {
    float drive_signal = 0.0f;
    float goal_x = 0.0f;
    bool trigger_damage = false;
};

struct ScenarioParameters {
    float blind_drive_limit = 0.0f;
    int pulse_start_step = -1;
    int pulse_end_step = -1;
    int second_pulse_start_step = -1;
    int second_pulse_end_step = -1;
    int damage_step = -1;
    float imprint_pulse_goal_x = 0.0f;
    float imprint_tail_goal_x = 0.0f;
    float imprint_pulse_drive = 0.0f;
    float hysteresis_drive_amplitude = 0.0f;
    float damage_goal_x = 0.0f;
    float damage_initial_drive = 0.0f;
    float damage_recovery_drive = 0.0f;
    float competing_first_goal_x = 0.0f;
    float competing_second_goal_x = 0.0f;
    float competing_first_drive = 0.0f;
    float competing_second_drive = 0.0f;
};

ScenarioKind ParseScenario(const std::string &value);
PolicyMode ParsePolicy(const std::string &value);
std::string ScenarioName(ScenarioKind scenario);
std::string PolicyName(PolicyMode policy);
ScenarioParameters DescribeScenario(ScenarioKind scenario, int total_steps);

ScenarioStep ComputeScenarioStep(ScenarioKind scenario,
                                 PolicyMode policy,
                                 int step,
                                 int total_steps,
                                 std::mt19937 &rng);

} // namespace jmm
