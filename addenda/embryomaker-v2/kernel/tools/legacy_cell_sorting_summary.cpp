#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <array>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "em2/api/legacy_cell_sorting_run.hpp"

namespace {

int parse_seed(const char* value, const char* name) {
  try {
    return std::stoi(value);
  } catch (const std::exception&) {
    std::cerr << "invalid " << name << '\n';
    std::exit(EXIT_FAILURE);
  }
}

int parse_int(const char* value, const char* name) {
  try {
    return std::stoi(value);
  } catch (const std::exception&) {
    std::cerr << "invalid " << name << '\n';
    std::exit(EXIT_FAILURE);
  }
}

std::vector<int> load_cell_types_file(const std::filesystem::path& path) {
  std::ifstream input(path);
  if (!input) {
    std::cerr << "invalid cell types file\n";
    std::exit(EXIT_FAILURE);
  }

  std::vector<int> cell_types;
  int value = 0;
  while (input >> value) {
    cell_types.push_back(value);
  }
  if (!input.eof()) {
    std::cerr << "invalid cell types file\n";
    std::exit(EXIT_FAILURE);
  }
  return cell_types;
}

std::vector<std::array<double, 3>> load_node_positions_file(const std::filesystem::path& path) {
  std::ifstream input(path);
  if (!input) {
    std::cerr << "invalid node positions file\n";
    std::exit(EXIT_FAILURE);
  }

  std::vector<std::array<double, 3>> positions;
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
  while (input >> x >> y >> z) {
    positions.push_back({x, y, z});
  }
  if (!input.eof()) {
    std::cerr << "invalid node positions file\n";
    std::exit(EXIT_FAILURE);
  }
  return positions;
}

std::array<std::int32_t, em2::kGFortranSeedWordCount> load_noise_seed_words_file(
    const std::filesystem::path& path) {
  std::ifstream input(path);
  if (!input) {
    std::cerr << "invalid noise seed words file\n";
    std::exit(EXIT_FAILURE);
  }

  std::array<std::int32_t, em2::kGFortranSeedWordCount> seed_words{};
  for (std::size_t index = 0; index < seed_words.size(); ++index) {
    if (!(input >> seed_words[index])) {
      std::cerr << "invalid noise seed words file\n";
      std::exit(EXIT_FAILURE);
    }
  }
  std::int32_t extra = 0;
  if (input >> extra) {
    std::cerr << "invalid noise seed words file\n";
    std::exit(EXIT_FAILURE);
  }
  if (!input.eof()) {
    std::cerr << "invalid noise seed words file\n";
    std::exit(EXIT_FAILURE);
  }
  return seed_words;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 2) {
    std::cerr
        << "usage: em2_legacy_cell_sorting_summary <steps> [initial-seed] [noise-seed]"
        << " [--cell-types-file PATH] [--node-positions-file PATH]"
        << " [--noise-seed-words-file PATH]\n";
    return EXIT_FAILURE;
  }

  int arg_index = 1;
  const int steps = parse_int(argv[arg_index], "steps");
  arg_index += 1;

  int initial_seed = -11111;
  if (arg_index < argc && !std::string_view(argv[arg_index]).starts_with("--")) {
    initial_seed = parse_seed(argv[arg_index], "initial seed");
    arg_index += 1;
  }

  std::optional<int> noise_seed;
  if (arg_index < argc && !std::string_view(argv[arg_index]).starts_with("--")) {
    noise_seed = parse_seed(argv[arg_index], "noise seed");
    arg_index += 1;
  }

  std::optional<std::vector<int>> initial_cell_types;
  std::optional<std::vector<std::array<double, 3>>> initial_node_positions;
  std::optional<std::array<std::int32_t, em2::kGFortranSeedWordCount>> noise_seed_words;
  while (arg_index < argc) {
    if ((arg_index + 1) >= argc) {
      std::cerr
          << "usage: em2_legacy_cell_sorting_summary <steps> [initial-seed] [noise-seed]"
          << " [--cell-types-file PATH] [--node-positions-file PATH]"
          << " [--noise-seed-words-file PATH]\n";
      return EXIT_FAILURE;
    }
    const std::string_view option = argv[arg_index];
    if (option == "--cell-types-file") {
      initial_cell_types = load_cell_types_file(argv[arg_index + 1]);
    } else if (option == "--node-positions-file") {
      initial_node_positions = load_node_positions_file(argv[arg_index + 1]);
    } else if (option == "--noise-seed-words-file") {
      noise_seed_words = load_noise_seed_words_file(argv[arg_index + 1]);
    } else {
      std::cerr
          << "usage: em2_legacy_cell_sorting_summary <steps> [initial-seed] [noise-seed]"
          << " [--cell-types-file PATH] [--node-positions-file PATH]"
          << " [--noise-seed-words-file PATH]\n";
      return EXIT_FAILURE;
    }
    arg_index += 2;
  }

  const em2::LegacyCellSortingRunResult result = em2::run_legacy_cell_sorting(
      em2::LegacyCellSortingRunConfig{
          .initial_seed = initial_seed,
          .noise_seed = noise_seed,
          .noise_seed_words = noise_seed_words,
          .initial_node_positions = initial_node_positions,
          .initial_cell_types = initial_cell_types,
          .steps = steps,
      });

  const em2::LegacyTrajectorySummary& summary = result.summary;
  std::cout << "steps: " << summary.steps << '\n';
  std::cout << "node_count: " << summary.node_count << '\n';
  std::cout << "cell_count: " << summary.cell_count << '\n';
  std::cout << "contact_count: " << summary.contact_count << '\n';
  std::cout << "max_distance_from_origin: " << summary.max_distance_from_origin << '\n';
  std::cout << "mean_distance_from_origin: " << summary.mean_distance_from_origin << '\n';
  std::cout << "mean_neighbor_count: " << summary.mean_neighbor_count << '\n';
  std::cout << "type1_cell_count: " << summary.type1_cell_count << '\n';
  std::cout << "type2_cell_count: " << summary.type2_cell_count << '\n';
  std::cout << "total_noise_attempts: " << summary.total_noise_attempts << '\n';
  std::cout << "total_noise_accepted: " << summary.total_noise_accepted << '\n';
  std::cout << "total_noise_rejected: " << summary.total_noise_rejected << '\n';
  std::cout << "total_noise_zero_displacement: " << summary.total_noise_zero_displacement << '\n';

  return EXIT_SUCCESS;
}
