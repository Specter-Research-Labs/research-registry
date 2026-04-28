import AppKit
import LeniaCore

enum CreatureExport {
    @MainActor
    static func copyConfigToClipboard(for creature: SavedCreature) {
        guard let json = encode(creature) else { return }
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(json, forType: .string)
    }

    @MainActor
    static func saveConfigToFile(for creature: SavedCreature) -> URL? {
        guard let json = encode(creature) else { return nil }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "\(creature.name).json"
        panel.allowedContentTypes = [.json]
        guard panel.runModal() == .OK, let url = panel.url else { return nil }
        do {
            try json.write(to: url, atomically: true, encoding: .utf8)
            return url
        } catch {
            return nil
        }
    }

    private static func encode(_ creature: SavedCreature) -> String? {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        guard let data = try? encoder.encode(creature) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
