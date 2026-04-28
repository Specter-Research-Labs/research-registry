#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "em2/model/legacy_invagination.hpp"

namespace {

std::vector<em2::LegacyInvaginationBootstrapNode> load_bootstrap_file(
    const std::filesystem::path& path) {
  std::ifstream input(path);
  if (!input) {
    std::cerr << "invalid bootstrap file\n";
    std::exit(EXIT_FAILURE);
  }

  std::vector<em2::LegacyInvaginationBootstrapNode> nodes;
  em2::LegacyInvaginationBootstrapNode node{};
  while (
      input >> node.x >> node.y >> node.z >> node.eqd >> node.add >> node.cod >> node.grd >>
      node.pld >> node.vod >> node.pla >> node.kvol >> node.tipus >> node.icel >> node.altre >>
      node.marge >> node.talone >> node.fix >> node.gene1 >> node.gene2) {
    nodes.push_back(node);
  }
  if (!input.eof() || nodes.empty()) {
    std::cerr << "invalid bootstrap file\n";
    std::exit(EXIT_FAILURE);
  }
  return nodes;
}

void load_saved_neighbors_file(
    const std::filesystem::path& path,
    std::vector<int>& offsets,
    std::vector<int>& indices) {
  std::ifstream input(path);
  if (!input) {
    std::cerr << "invalid saved neighbors file\n";
    std::exit(EXIT_FAILURE);
  }

  offsets.clear();
  indices.clear();
  offsets.push_back(0);
  std::string line;
  while (std::getline(input, line)) {
    if (line.empty()) {
      continue;
    }
    std::istringstream row(line);
    int node_index = 0;
    if (!(row >> node_index)) {
      std::cerr << "invalid saved neighbors file\n";
      std::exit(EXIT_FAILURE);
    }
    int neighbor = 0;
    while (row >> neighbor) {
      indices.push_back(neighbor);
    }
    offsets.push_back(static_cast<int>(indices.size()));
  }
  if (!input.eof()) {
    std::cerr << "invalid saved neighbors file\n";
    std::exit(EXIT_FAILURE);
  }
}

std::vector<int> parse_int_csv(const std::string_view text) {
  std::vector<int> values;
  std::size_t cursor = 0;
  while (cursor <= text.size()) {
    const std::size_t comma = text.find(',', cursor);
    const std::size_t end = comma == std::string_view::npos ? text.size() : comma;
    if (end == cursor) {
      throw std::invalid_argument("empty csv token");
    }
    values.push_back(std::stoi(std::string(text.substr(cursor, end - cursor))));
    if (comma == std::string_view::npos) {
      break;
    }
    cursor = comma + 1;
  }
  if (values.empty()) {
    throw std::invalid_argument("empty csv");
  }
  return values;
}

std::vector<em2::LegacyInvaginationPairTracePair> parse_pair_csv(
    const std::string_view text) {
  std::vector<em2::LegacyInvaginationPairTracePair> values;
  std::size_t cursor = 0;
  while (cursor <= text.size()) {
    const std::size_t comma = text.find(',', cursor);
    const std::size_t end = comma == std::string_view::npos ? text.size() : comma;
    if (end == cursor) {
      throw std::invalid_argument("empty csv token");
    }
    const std::string_view token = text.substr(cursor, end - cursor);
    const std::size_t colon = token.find(':');
    if (colon == std::string_view::npos || colon == 0 || colon == (token.size() - 1)) {
      throw std::invalid_argument("invalid pair token");
    }
    values.push_back(em2::LegacyInvaginationPairTracePair{
        .source_node = std::stoi(std::string(token.substr(0, colon))),
        .target_node = std::stoi(std::string(token.substr(colon + 1))),
    });
    if (comma == std::string_view::npos) {
      break;
    }
    cursor = comma + 1;
  }
  if (values.empty()) {
    throw std::invalid_argument("empty csv");
  }
  return values;
}

std::string_view pair_trace_stage_name(const int stage) {
  switch (stage) {
    case 1:
      return "k1";
    case 2:
      return "k2";
    case 3:
      return "k3";
    case 4:
      return "k4";
    default:
      return "unknown";
  }
}

std::string_view pair_trace_branch_name(const int branch_code) {
  switch (branch_code) {
    case 0:
      return "none";
    case 1:
      return "same_posca_pos";
    case 2:
      return "same_posca_nonpos_mc0";
    case 3:
      return "same_posca_nonpos_mc";
    case 4:
      return "diff_posca_neg";
    default:
      return "unknown";
  }
}

std::string_view pair_trace_reject_name(const int reject_code) {
  switch (reject_code) {
    case 0:
      return "none";
    case 1:
      return "distance";
    case 2:
      return "missing_other";
    case 3:
      return "non_epithelial";
    case 4:
      return "mc_norm";
    case 5:
      return "diff_posca_nonneg";
    case 6:
      return "dotp";
    case 7:
      return "spring_norm";
    case 8:
      return "ddd_cutoff";
    case 9:
      return "vertical_cutoff";
    case 10:
      return "lateral_cutoff";
    default:
      return "unknown";
  }
}

void print_usage() {
  std::cerr << "usage: em2_legacy_invagination_summary --bootstrap-file PATH"
            << " [--target-rtime FLOAT | --steps INT]"
            << " [--original-bootstrap-file PATH] [--positions-out PATH]"
            << " [--state-out PATH] [--trace-out PATH]"
            << " [--saved-neighbors-in PATH]"
            << " [--saved-neighbors-out PATH]"
            << " [--rk-stage-out PATH]"
            << " [--component-trace-out PATH] [--component-trace-nodes CSV]"
            << " [--pair-trace-nodes CSV] [--pair-trace-pairs CSV]"
            << " [--pair-trace-out PATH]\n";
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 3 || std::string_view(argv[1]) != "--bootstrap-file") {
    print_usage();
    return EXIT_FAILURE;
  }

  std::optional<double> target_rtime;
  std::optional<int> steps;
  std::optional<std::filesystem::path> original_bootstrap_file;
  std::optional<std::filesystem::path> positions_out;
  std::optional<std::filesystem::path> state_out;
  std::optional<std::filesystem::path> trace_out;
  std::optional<std::filesystem::path> saved_neighbors_in;
  std::optional<std::filesystem::path> saved_neighbors_out;
  std::optional<std::filesystem::path> rk_stage_out;
  std::optional<std::filesystem::path> component_trace_out;
  std::optional<std::vector<int>> component_trace_nodes;
  std::optional<std::vector<int>> pair_trace_nodes;
  std::optional<std::vector<em2::LegacyInvaginationPairTracePair>> pair_trace_pairs;
  std::optional<std::filesystem::path> pair_trace_out;
  int arg_index = 3;
  while (arg_index < argc) {
    if ((arg_index + 1) >= argc) {
      print_usage();
      return EXIT_FAILURE;
    }

    const std::string_view option = argv[arg_index];
    if (option == "--target-rtime") {
      try {
        target_rtime = std::stod(argv[arg_index + 1]);
      } catch (const std::exception&) {
        std::cerr << "invalid target rtime\n";
        return EXIT_FAILURE;
      }
    } else if (option == "--steps") {
      try {
        steps = std::stoi(argv[arg_index + 1]);
      } catch (const std::exception&) {
        std::cerr << "invalid step count\n";
        return EXIT_FAILURE;
      }
      if (*steps < 0) {
        std::cerr << "invalid step count\n";
        return EXIT_FAILURE;
      }
    } else if (option == "--original-bootstrap-file") {
      original_bootstrap_file = std::filesystem::path(argv[arg_index + 1]);
    } else if (option == "--positions-out") {
      positions_out = std::filesystem::path(argv[arg_index + 1]);
    } else if (option == "--state-out") {
      state_out = std::filesystem::path(argv[arg_index + 1]);
    } else if (option == "--trace-out") {
      trace_out = std::filesystem::path(argv[arg_index + 1]);
    } else if (option == "--saved-neighbors-in") {
      saved_neighbors_in = std::filesystem::path(argv[arg_index + 1]);
    } else if (option == "--saved-neighbors-out") {
      saved_neighbors_out = std::filesystem::path(argv[arg_index + 1]);
    } else if (option == "--rk-stage-out") {
      rk_stage_out = std::filesystem::path(argv[arg_index + 1]);
    } else if (option == "--component-trace-out") {
      component_trace_out = std::filesystem::path(argv[arg_index + 1]);
    } else if (option == "--component-trace-nodes") {
      try {
        component_trace_nodes = parse_int_csv(argv[arg_index + 1]);
      } catch (const std::exception&) {
        std::cerr << "invalid component trace node list\n";
        return EXIT_FAILURE;
      }
    } else if (option == "--pair-trace-nodes") {
      try {
        pair_trace_nodes = parse_int_csv(argv[arg_index + 1]);
      } catch (const std::exception&) {
        std::cerr << "invalid pair trace node list\n";
        return EXIT_FAILURE;
      }
    } else if (option == "--pair-trace-pairs") {
      try {
        pair_trace_pairs = parse_pair_csv(argv[arg_index + 1]);
      } catch (const std::exception&) {
        std::cerr << "invalid pair trace pair list\n";
        return EXIT_FAILURE;
      }
    } else if (option == "--pair-trace-out") {
      pair_trace_out = std::filesystem::path(argv[arg_index + 1]);
    } else {
      print_usage();
      return EXIT_FAILURE;
    }
    arg_index += 2;
  }

  const std::vector<em2::LegacyInvaginationBootstrapNode> bootstrap_nodes = load_bootstrap_file(argv[2]);
  if (target_rtime.has_value() && steps.has_value()) {
    std::cerr << "target rtime and steps are mutually exclusive\n";
    return EXIT_FAILURE;
  }
  if (original_bootstrap_file.has_value() && !steps.has_value()) {
    std::cerr << "original bootstrap file requires steps\n";
    return EXIT_FAILURE;
  }
  if (saved_neighbors_in.has_value() && !steps.has_value()) {
    std::cerr << "saved neighbors input requires steps\n";
    return EXIT_FAILURE;
  }
  if (component_trace_nodes.has_value() && !steps.has_value()) {
    std::cerr << "component trace nodes require steps\n";
    return EXIT_FAILURE;
  }
  if (pair_trace_nodes.has_value() && !steps.has_value()) {
    std::cerr << "pair trace nodes require steps\n";
    return EXIT_FAILURE;
  }
  if (pair_trace_pairs.has_value() && !steps.has_value()) {
    std::cerr << "pair trace pairs require steps\n";
    return EXIT_FAILURE;
  }
  if (pair_trace_out.has_value() && !steps.has_value()) {
    std::cerr << "pair trace output requires steps\n";
    return EXIT_FAILURE;
  }
  if (pair_trace_out.has_value() &&
      !pair_trace_nodes.has_value() &&
      !pair_trace_pairs.has_value()) {
    std::cerr << "pair trace output requires pair trace filter\n";
    return EXIT_FAILURE;
  }

  std::optional<std::vector<em2::LegacyInvaginationBootstrapNode>> original_bootstrap_nodes;
  if (original_bootstrap_file.has_value()) {
    original_bootstrap_nodes = load_bootstrap_file(*original_bootstrap_file);
  }

  em2::LegacyInvaginationState state = em2::build_legacy_invagination_state(bootstrap_nodes);
  if (target_rtime.has_value()) {
    state = em2::run_legacy_invagination(bootstrap_nodes, *target_rtime);
  } else if (steps.has_value()) {
    if (component_trace_nodes.has_value()) {
      state.diagnostic_component_nodes = *component_trace_nodes;
    }
    if (pair_trace_nodes.has_value()) {
      state.diagnostic_pair_nodes = *pair_trace_nodes;
    }
    if (pair_trace_pairs.has_value()) {
      state.diagnostic_pair_pairs = *pair_trace_pairs;
    }
    if (saved_neighbors_in.has_value()) {
      load_saved_neighbors_file(
          *saved_neighbors_in,
          state.saved_epithelial_neighbor_offsets,
          state.saved_epithelial_neighbor_indices);
      if (state.saved_epithelial_neighbor_offsets.size() != (state.nodes.size() + 1U)) {
        std::cerr << "saved neighbors file size drifted\n";
        return EXIT_FAILURE;
      }
    }
    const std::vector<em2::LegacyInvaginationBootstrapNode>& original_nodes =
        original_bootstrap_nodes.has_value() ? *original_bootstrap_nodes : bootstrap_nodes;
    state = em2::run_legacy_invagination_steps_from_state_with_original(
        std::move(state),
        original_nodes,
        *steps);
  }
  const em2::LegacyInvaginationSummary summary =
      em2::summarize_legacy_invagination_state(state);

  if (positions_out.has_value()) {
    std::ofstream output(*positions_out);
    if (!output) {
      std::cerr << "invalid positions output path\n";
      return EXIT_FAILURE;
    }
    output << std::setprecision(17);
    for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
      output << state.nodes.x[node_index] << ' ' << state.nodes.y[node_index] << ' '
             << state.nodes.z[node_index] << '\n';
    }
  }
  if (state_out.has_value()) {
    std::ofstream output(*state_out);
    if (!output) {
      std::cerr << "invalid state output path\n";
      return EXIT_FAILURE;
    }
    output << std::setprecision(17);
    for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
      output << state.nodes.x[node_index] << ' ' << state.nodes.y[node_index] << ' '
             << state.nodes.z[node_index] << ' ' << state.nodes.eqd[node_index] << ' '
             << state.nodes.add[node_index] << ' ' << state.nodes.cod[node_index] << ' '
             << state.nodes.grd[node_index] << ' ' << state.nodes.pld[node_index] << ' '
             << state.nodes.vod[node_index] << ' ' << state.nodes.pla[node_index] << ' '
             << state.nodes.kvol[node_index] << ' ' << state.nodes.tipus[node_index] << ' '
             << state.nodes.icel[node_index] << ' ' << state.nodes.altre[node_index] << ' '
             << state.nodes.marge[node_index] << ' ' << state.nodes.talone[node_index] << ' '
             << state.nodes.fix[node_index] << ' '
             << state.genes.expression(node_index, 0) << ' '
             << state.genes.expression(node_index, 1) << '\n';
    }
  }
  if (trace_out.has_value()) {
    std::ofstream output(*trace_out);
    if (!output) {
      std::cerr << "invalid trace output path\n";
      return EXIT_FAILURE;
    }
    output << std::setprecision(17);
    for (const em2::LegacyInvaginationStepTrace& trace : state.step_trace) {
      output << trace.getot << ' ' << trace.rtime_before << ' ' << trace.delta << ' '
             << trace.rtime_after << ' ' << trace.max_force << '\n';
    }
  }
  if (saved_neighbors_out.has_value()) {
    std::ofstream output(*saved_neighbors_out);
    if (!output) {
      std::cerr << "invalid saved neighbors output path\n";
      return EXIT_FAILURE;
    }
    for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
      const std::size_t begin =
          static_cast<std::size_t>(state.saved_epithelial_neighbor_offsets[node_index]);
      const std::size_t end =
          static_cast<std::size_t>(state.saved_epithelial_neighbor_offsets[node_index + 1]);
      output << node_index;
      for (std::size_t offset = begin; offset < end; ++offset) {
        output << ' ' << state.saved_epithelial_neighbor_indices[offset];
      }
      output << '\n';
    }
  }
  if (rk_stage_out.has_value()) {
    if (state.last_k1x.size() != state.nodes.size()) {
      std::cerr << "rk stage output requires at least one step\n";
      return EXIT_FAILURE;
    }
    std::ofstream output(*rk_stage_out);
    if (!output) {
      std::cerr << "invalid rk stage output path\n";
      return EXIT_FAILURE;
    }
    output << std::setprecision(17);
    for (std::size_t node_index = 0; node_index < state.nodes.size(); ++node_index) {
      output << node_index << ' '
             << state.last_k1x[node_index] << ' ' << state.last_k1y[node_index] << ' '
             << state.last_k1z[node_index] << ' '
             << state.last_k2x[node_index] << ' ' << state.last_k2y[node_index] << ' '
             << state.last_k2z[node_index] << ' '
             << state.last_k3x[node_index] << ' ' << state.last_k3y[node_index] << ' '
             << state.last_k3z[node_index] << ' '
             << state.last_k4x[node_index] << ' ' << state.last_k4y[node_index] << ' '
             << state.last_k4z[node_index] << '\n';
    }
  }
  if (component_trace_out.has_value()) {
    auto vector_norm = [](const double x, const double y, const double z) {
      return std::sqrt((x * x) + (y * y) + (z * z));
    };
    std::ofstream output(*component_trace_out);
    if (!output) {
      std::cerr << "invalid component trace output path\n";
      return EXIT_FAILURE;
    }
    output << std::setprecision(17);
    if (component_trace_nodes.has_value()) {
      if (state.last_component_trace.empty()) {
        std::cerr << "component trace output requires at least one traced step\n";
        return EXIT_FAILURE;
      }
      output << "# getot stage stage_label node tipus icel same_side_neighbor_count"
             << " x y z"
             << " spring_x spring_y spring_z spring_norm"
             << " contact_adh_raw_x contact_adh_raw_y contact_adh_raw_z contact_adh_raw_norm"
             << " contact_adh_capped_x contact_adh_capped_y contact_adh_capped_z"
             << " contact_adh_capped_norm"
             << " contact_rep_x contact_rep_y contact_rep_z contact_rep_norm"
             << " torsion_x torsion_y torsion_z torsion_norm"
             << " surface_torsion_x surface_torsion_y surface_torsion_z surface_torsion_norm"
             << " total_x total_y total_z total_norm dex\n";
      for (const em2::LegacyInvaginationComponentTraceEntry& trace : state.last_component_trace) {
        output << trace.getot << ' ' << trace.stage << ' '
               << pair_trace_stage_name(trace.stage) << ' '
               << trace.node << ' ' << trace.tipus << ' ' << trace.icel << ' '
               << trace.same_side_neighbor_count << ' '
               << trace.x << ' ' << trace.y << ' ' << trace.z << ' '
               << trace.spring_x << ' ' << trace.spring_y << ' ' << trace.spring_z << ' '
               << vector_norm(trace.spring_x, trace.spring_y, trace.spring_z) << ' '
               << trace.contact_adh_raw_x << ' ' << trace.contact_adh_raw_y << ' '
               << trace.contact_adh_raw_z << ' '
               << vector_norm(
                      trace.contact_adh_raw_x,
                      trace.contact_adh_raw_y,
                      trace.contact_adh_raw_z)
               << ' '
               << trace.contact_adh_capped_x << ' ' << trace.contact_adh_capped_y << ' '
               << trace.contact_adh_capped_z << ' '
               << vector_norm(
                      trace.contact_adh_capped_x,
                      trace.contact_adh_capped_y,
                      trace.contact_adh_capped_z)
               << ' '
               << trace.contact_rep_x << ' ' << trace.contact_rep_y << ' '
               << trace.contact_rep_z << ' '
               << vector_norm(trace.contact_rep_x, trace.contact_rep_y, trace.contact_rep_z)
               << ' '
               << trace.torsion_x << ' ' << trace.torsion_y << ' ' << trace.torsion_z << ' '
               << vector_norm(trace.torsion_x, trace.torsion_y, trace.torsion_z) << ' '
               << trace.surface_torsion_x << ' ' << trace.surface_torsion_y << ' '
               << trace.surface_torsion_z << ' '
               << vector_norm(
                      trace.surface_torsion_x,
                      trace.surface_torsion_y,
                      trace.surface_torsion_z)
               << ' '
               << trace.total_x << ' ' << trace.total_y << ' ' << trace.total_z << ' '
               << vector_norm(trace.total_x, trace.total_y, trace.total_z) << ' '
               << trace.dex << '\n';
      }
    } else {
      output << "# getot rtime_before delta rtime_after max_force"
             << " max_force_node max_force_tipus max_force_icel"
             << " max_force_same_side_neighbor_count"
             << " max_force_node_x max_force_node_y max_force_node_z"
             << " spring_x spring_y spring_z spring_norm"
             << " contact_adh_raw_x contact_adh_raw_y contact_adh_raw_z contact_adh_raw_norm"
             << " contact_adh_capped_x contact_adh_capped_y contact_adh_capped_z"
             << " contact_adh_capped_norm"
             << " contact_rep_x contact_rep_y contact_rep_z contact_rep_norm"
             << " torsion_x torsion_y torsion_z torsion_norm"
             << " surface_torsion_x surface_torsion_y surface_torsion_z surface_torsion_norm"
             << " total_x total_y total_z total_norm\n";
      for (const em2::LegacyInvaginationStepTrace& trace : state.step_trace) {
        output << trace.getot << ' ' << trace.rtime_before << ' ' << trace.delta << ' '
               << trace.rtime_after << ' ' << trace.max_force << ' '
               << trace.max_force_node << ' ' << trace.max_force_tipus << ' '
               << trace.max_force_icel << ' '
               << trace.max_force_same_side_neighbor_count << ' '
               << trace.max_force_node_x << ' ' << trace.max_force_node_y << ' '
               << trace.max_force_node_z << ' '
               << trace.spring_x << ' ' << trace.spring_y << ' ' << trace.spring_z << ' '
               << vector_norm(trace.spring_x, trace.spring_y, trace.spring_z) << ' '
               << trace.contact_adh_raw_x << ' ' << trace.contact_adh_raw_y << ' '
               << trace.contact_adh_raw_z << ' '
               << vector_norm(
                      trace.contact_adh_raw_x,
                      trace.contact_adh_raw_y,
                      trace.contact_adh_raw_z)
               << ' '
               << trace.contact_adh_capped_x << ' ' << trace.contact_adh_capped_y << ' '
               << trace.contact_adh_capped_z << ' '
               << vector_norm(
                      trace.contact_adh_capped_x,
                      trace.contact_adh_capped_y,
                      trace.contact_adh_capped_z)
               << ' '
               << trace.contact_rep_x << ' ' << trace.contact_rep_y << ' '
               << trace.contact_rep_z << ' '
               << vector_norm(trace.contact_rep_x, trace.contact_rep_y, trace.contact_rep_z)
               << ' '
               << trace.torsion_x << ' ' << trace.torsion_y << ' ' << trace.torsion_z << ' '
               << vector_norm(trace.torsion_x, trace.torsion_y, trace.torsion_z) << ' '
               << trace.surface_torsion_x << ' ' << trace.surface_torsion_y << ' '
               << trace.surface_torsion_z << ' '
               << vector_norm(
                      trace.surface_torsion_x,
                      trace.surface_torsion_y,
                      trace.surface_torsion_z)
               << ' '
               << trace.total_x << ' ' << trace.total_y << ' ' << trace.total_z << ' '
               << vector_norm(trace.total_x, trace.total_y, trace.total_z) << '\n';
      }
    }
  }
  if (pair_trace_out.has_value()) {
    if (state.last_pair_trace.empty()) {
      std::cerr << "pair trace output requires at least one traced step\n";
      return EXIT_FAILURE;
    }
    std::ofstream output(*pair_trace_out);
    if (!output) {
      std::cerr << "invalid pair trace output path\n";
      return EXIT_FAILURE;
    }
    output << std::setprecision(17);
    output << "# getot stage stage_label source_node target_node"
           << " source_tipus target_tipus source_icel target_icel"
           << " source_other_node target_other_node"
           << " same_cell restored_only branch_code branch_label"
           << " reject_code reject_label interacts twoep torsion_active"
           << " distance edge_add reverse_edge_add edge_eqd reverse_edge_eqd"
           << " add_cutoff deqe posca dotp vertical_distance lateral_distance"
           << " fd vertical_projection force_scalar fx fy fz"
           << " source_torsion_y_raw target_torsion_y_raw"
           << " source_surface_torsion_y_raw target_surface_torsion_y_raw"
           << " source_x source_y source_z target_x target_y target_z"
           << " source_other_x source_other_y source_other_z"
           << " target_other_x target_other_y target_other_z"
           << " pair_dx pair_dy pair_dz"
           << " source_other_dx source_other_dy source_other_dz"
           << " target_other_dx target_other_dy target_other_dz"
           << " mcx mcy mcz mc_norm torsion_margin\n";
    for (const em2::LegacyInvaginationPairTraceEntry& entry : state.last_pair_trace) {
      output << entry.getot << ' ' << entry.stage << ' ' << pair_trace_stage_name(entry.stage)
             << ' ' << entry.source_node << ' ' << entry.target_node << ' '
             << entry.source_tipus << ' ' << entry.target_tipus << ' '
             << entry.source_icel << ' ' << entry.target_icel << ' '
             << entry.source_other_node << ' ' << entry.target_other_node << ' '
             << entry.same_cell << ' ' << entry.restored_only << ' '
             << entry.branch_code << ' ' << pair_trace_branch_name(entry.branch_code) << ' '
             << entry.reject_code << ' ' << pair_trace_reject_name(entry.reject_code) << ' '
             << entry.interacts << ' ' << entry.twoep << ' '
             << entry.torsion_active << ' '
             << entry.distance << ' ' << entry.edge_add << ' '
             << entry.reverse_edge_add << ' ' << entry.edge_eqd << ' '
             << entry.reverse_edge_eqd << ' ' << entry.add_cutoff << ' '
             << entry.deqe << ' ' << entry.posca << ' ' << entry.dotp << ' '
             << entry.vertical_distance << ' ' << entry.lateral_distance << ' '
             << entry.fd << ' ' << entry.vertical_projection << ' '
             << entry.force_scalar << ' ' << entry.fx << ' '
             << entry.fy << ' ' << entry.fz << ' '
             << entry.source_torsion_y_raw << ' '
             << entry.target_torsion_y_raw << ' '
             << entry.source_surface_torsion_y_raw << ' '
             << entry.target_surface_torsion_y_raw << ' '
             << entry.source_x << ' ' << entry.source_y << ' ' << entry.source_z << ' '
             << entry.target_x << ' ' << entry.target_y << ' ' << entry.target_z << ' '
             << entry.source_other_x << ' ' << entry.source_other_y << ' '
             << entry.source_other_z << ' '
             << entry.target_other_x << ' ' << entry.target_other_y << ' '
             << entry.target_other_z << ' '
             << entry.pair_dx << ' ' << entry.pair_dy << ' ' << entry.pair_dz << ' '
             << entry.source_other_dx << ' ' << entry.source_other_dy << ' '
             << entry.source_other_dz << ' '
             << entry.target_other_dx << ' ' << entry.target_other_dy << ' '
             << entry.target_other_dz << ' '
             << entry.mcx << ' ' << entry.mcy << ' ' << entry.mcz << ' '
             << entry.mc_norm << ' ' << entry.torsion_margin << '\n';
    }
  }

  std::cout << "getot: " << summary.getot << '\n';
  std::cout << "rtime: " << summary.rtime << '\n';
  std::cout << "node_count: " << summary.node_count << '\n';
  std::cout << "cell_count: " << summary.cell_count << '\n';
  std::cout << "epithelial_node_count: " << summary.epithelial_node_count << '\n';
  std::cout << "apical_node_count: " << summary.apical_node_count << '\n';
  std::cout << "basal_node_count: " << summary.basal_node_count << '\n';
  std::cout << "paired_epithelial_node_count: " << summary.paired_epithelial_node_count << '\n';
  std::cout << "epithelial_cell_count: " << summary.epithelial_cell_count << '\n';
  std::cout << "gene1_positive_node_count: " << summary.gene1_positive_node_count << '\n';
  std::cout << "gene2_positive_node_count: " << summary.gene2_positive_node_count << '\n';
  std::cout << "gene1_positive_cell_count: " << summary.gene1_positive_cell_count << '\n';
  std::cout << "gene2_positive_cell_count: " << summary.gene2_positive_cell_count << '\n';
  std::cout << "polarized_expression_cell_count: " << summary.polarized_expression_cell_count
            << '\n';
  std::cout << "zero_pla_node_count: " << summary.zero_pla_node_count << '\n';
  std::cout << "zero_kvol_node_count: " << summary.zero_kvol_node_count << '\n';
  std::cout << "mean_grd: " << summary.mean_grd << '\n';
  std::cout << "mean_cod: " << summary.mean_cod << '\n';
  std::cout << "mean_pld: " << summary.mean_pld << '\n';
  std::cout << "mean_vod: " << summary.mean_vod << '\n';
  return EXIT_SUCCESS;
}
