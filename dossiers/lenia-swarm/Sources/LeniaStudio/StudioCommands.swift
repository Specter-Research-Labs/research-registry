import Foundation
import SwiftUI

let studioInitialDestinationEnvironmentKey = "LENIA_STUDIO_INITIAL_DESTINATION"

enum StudioDestination: String, CaseIterable, Hashable, Identifiable {
    case lab
    case library
    case compare
    case runs

    var id: Self { self }

    var title: String {
        switch self {
        case .lab: "Lab"
        case .library: "Library"
        case .compare: "Compare"
        case .runs: "Runs"
        }
    }

    var systemImage: String {
        switch self {
        case .lab: "waveform.path.ecg.rectangle"
        case .library: "square.grid.2x2"
        case .compare: "rectangle.split.2x1"
        case .runs: "point.3.connected.trianglepath.dotted"
        }
    }

    var shortcutNumber: String {
        switch self {
        case .lab: "1"
        case .library: "2"
        case .compare: "3"
        case .runs: "4"
        }
    }

    var accessibilityHint: String {
        "Show \(title). Command \(shortcutNumber)."
    }
}

enum StudioCommand: Equatable {
    case showDestination(StudioDestination)
    case openClusterConnection
}

func studioInitialDestination(environment: [String: String]) -> StudioDestination {
    guard let value = environment[studioInitialDestinationEnvironmentKey]?
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased(),
        let destination = StudioDestination(rawValue: value)
    else {
        return .lab
    }
    return destination
}

struct StudioCommandEvent: Equatable, Identifiable {
    let id: Int
    let command: StudioCommand
}

final class StudioCommandCenter: ObservableObject {
    @Published private(set) var latestEvent: StudioCommandEvent?
    private var nextEventID = 0

    func send(_ command: StudioCommand) {
        nextEventID += 1
        latestEvent = StudioCommandEvent(id: nextEventID, command: command)
    }
}

func studioDestination(
    current: StudioDestination,
    applying command: StudioCommand
) -> StudioDestination {
    switch command {
    case .showDestination(let destination):
        destination
    case .openClusterConnection:
        current
    }
}

func studioDestinationAfterConnectionChange(
    current: StudioDestination,
    connectionState _: ConnectionState
) -> StudioDestination {
    current
}

struct StudioCommands: Commands {
    let commandCenter: StudioCommandCenter

    var body: some Commands {
        CommandMenu("Navigate") {
            Button("Lab") {
                commandCenter.send(.showDestination(.lab))
            }
            .keyboardShortcut("1", modifiers: .command)

            Button("Library") {
                commandCenter.send(.showDestination(.library))
            }
            .keyboardShortcut("2", modifiers: .command)

            Button("Compare") {
                commandCenter.send(.showDestination(.compare))
            }
            .keyboardShortcut("3", modifiers: .command)

            Button("Runs") {
                commandCenter.send(.showDestination(.runs))
            }
            .keyboardShortcut("4", modifiers: .command)
        }

        CommandMenu("Cluster") {
            Button("Cluster Connection...") {
                commandCenter.send(.openClusterConnection)
            }
            .keyboardShortcut("k", modifiers: [.command, .shift])
        }
    }
}
