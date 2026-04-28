#include "scenarios.h"

#include <algorithm>
#include <stdexcept>

namespace jmm {

namespace {

constexpr float kBlindDriveLimit = 38.0f;
constexpr float kPulseStartFraction = 0.20f;
constexpr float kPulseEndFraction = 0.37f;
constexpr float kDamageStepFraction = 0.55f;
constexpr float kCompetingSecondPulseStartFraction = 0.52f;
constexpr float kCompetingSecondPulseEndFraction = 0.68f;

constexpr float kImprintPulseGoalX = 2.2f;
constexpr float kImprintTailGoalX = 1.2f;
constexpr float kImprintPulseDrive = 32.0f;

constexpr float kHysteresisDriveAmplitude = 30.0f;

constexpr float kDamageGoalX = 1.8f;
constexpr float kDamageInitialDrive = 24.0f;
constexpr float kDamageRecoveryDrive = 8.0f;

constexpr float kCompetingFirstGoalX = 2.1f;
constexpr float kCompetingSecondGoalX = -2.1f;
constexpr float kCompetingFirstDrive = 30.0f;
constexpr float kCompetingSecondDrive = -30.0f;

float Clamp01(float value) {
    return std::clamp(value, 0.0f, 1.0f);
}

float TriangleWave(float progress) {
    const float p = Clamp01(progress);
    if (p < 0.5f) {
        return -1.0f + 4.0f * p;
    }
    return 3.0f - 4.0f * p;
}

} // namespace

ScenarioKind ParseScenario(const std::string &value) {
    if (value == "imprint") {
        return ScenarioKind::kImprintRetention;
    }
    if (value == "hysteresis") {
        return ScenarioKind::kReversalHysteresis;
    }
    if (value == "damage") {
        return ScenarioKind::kDamageRelearning;
    }
    if (value == "competing_targets") {
        return ScenarioKind::kCompetingTargets;
    }
    throw std::invalid_argument("Unsupported scenario: " + value);
}

PolicyMode ParsePolicy(const std::string &value) {
    if (value == "directed") {
        return PolicyMode::kDirected;
    }
    if (value == "blind") {
        return PolicyMode::kBlind;
    }
    throw std::invalid_argument("Unsupported policy: " + value);
}

std::string ScenarioName(ScenarioKind scenario) {
    switch (scenario) {
    case ScenarioKind::kImprintRetention:
        return "imprint";
    case ScenarioKind::kReversalHysteresis:
        return "hysteresis";
    case ScenarioKind::kDamageRelearning:
        return "damage";
    case ScenarioKind::kCompetingTargets:
        return "competing_targets";
    }
    return "unknown";
}

std::string PolicyName(PolicyMode policy) {
    switch (policy) {
    case PolicyMode::kDirected:
        return "directed";
    case PolicyMode::kBlind:
        return "blind";
    }
    return "unknown";
}

ScenarioParameters DescribeScenario(ScenarioKind scenario, int total_steps) {
    if (total_steps <= 0) {
        throw std::invalid_argument("total_steps must be positive");
    }

    ScenarioParameters out;
    out.blind_drive_limit = kBlindDriveLimit;
    out.pulse_start_step = static_cast<int>(kPulseStartFraction * static_cast<float>(total_steps));
    out.pulse_end_step = static_cast<int>(kPulseEndFraction * static_cast<float>(total_steps));
    out.second_pulse_start_step = static_cast<int>(
        kCompetingSecondPulseStartFraction * static_cast<float>(total_steps));
    out.second_pulse_end_step = static_cast<int>(
        kCompetingSecondPulseEndFraction * static_cast<float>(total_steps));
    out.damage_step = static_cast<int>(kDamageStepFraction * static_cast<float>(total_steps));

    switch (scenario) {
    case ScenarioKind::kImprintRetention:
        out.imprint_pulse_goal_x = kImprintPulseGoalX;
        out.imprint_tail_goal_x = kImprintTailGoalX;
        out.imprint_pulse_drive = kImprintPulseDrive;
        break;
    case ScenarioKind::kReversalHysteresis:
        out.hysteresis_drive_amplitude = kHysteresisDriveAmplitude;
        break;
    case ScenarioKind::kDamageRelearning:
        out.damage_goal_x = kDamageGoalX;
        out.damage_initial_drive = kDamageInitialDrive;
        out.damage_recovery_drive = kDamageRecoveryDrive;
        break;
    case ScenarioKind::kCompetingTargets:
        out.competing_first_goal_x = kCompetingFirstGoalX;
        out.competing_second_goal_x = kCompetingSecondGoalX;
        out.competing_first_drive = kCompetingFirstDrive;
        out.competing_second_drive = kCompetingSecondDrive;
        break;
    }

    return out;
}

ScenarioStep ComputeScenarioStep(ScenarioKind scenario,
                                 PolicyMode policy,
                                 int step,
                                 int total_steps,
                                 std::mt19937 &rng) {
    const ScenarioParameters params = DescribeScenario(scenario, total_steps);
    ScenarioStep out;
    std::uniform_real_distribution<float> blind_drive(
        -params.blind_drive_limit, params.blind_drive_limit);
    const float progress = total_steps == 1
                               ? 0.0f
                               : static_cast<float>(step) / static_cast<float>(total_steps - 1);

    switch (scenario) {
    case ScenarioKind::kImprintRetention: {
        out.goal_x = 0.0f;
        if (step >= params.pulse_start_step && step < params.pulse_end_step) {
            out.goal_x = params.imprint_pulse_goal_x;
            out.drive_signal = params.imprint_pulse_drive;
        } else if (step >= params.pulse_end_step) {
            out.goal_x = params.imprint_tail_goal_x;
            out.drive_signal = 0.0f;
        }
        break;
    }
    case ScenarioKind::kReversalHysteresis: {
        const float wave = TriangleWave(progress);
        out.drive_signal = params.hysteresis_drive_amplitude * wave;
        out.goal_x = 0.0f;
        break;
    }
    case ScenarioKind::kDamageRelearning: {
        out.goal_x = params.damage_goal_x;
        if (step < params.pulse_end_step) {
            out.drive_signal = params.damage_initial_drive;
        } else {
            out.drive_signal = params.damage_recovery_drive;
        }
        out.trigger_damage = (step == params.damage_step);
        break;
    }
    case ScenarioKind::kCompetingTargets: {
        out.goal_x = 0.0f;
        if (step >= params.pulse_start_step && step < params.pulse_end_step) {
            out.goal_x = params.competing_first_goal_x;
            out.drive_signal = params.competing_first_drive;
        } else if (step >= params.second_pulse_start_step &&
                   step < params.second_pulse_end_step) {
            out.goal_x = params.competing_second_goal_x;
            out.drive_signal = params.competing_second_drive;
        } else if (step >= params.second_pulse_end_step) {
            out.goal_x = params.competing_second_goal_x;
            out.drive_signal = 0.0f;
        }
        break;
    }
    }

    if (policy == PolicyMode::kBlind) {
        out.drive_signal = blind_drive(rng);
    }

    return out;
}

} // namespace jmm
