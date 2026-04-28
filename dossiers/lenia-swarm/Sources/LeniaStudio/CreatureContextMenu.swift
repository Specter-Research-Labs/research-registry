import AppKit
import SwiftUI
import LeniaCore

struct CreatureContextMenu: View {
    let seed: Int
    var savedCreature: SavedCreature? = nil
    var onPreview: (() -> Void)? = nil
    var onAddToComparison: (() -> Void)? = nil
    var revealPath: String? = nil

    var body: some View {
        Button("Copy Seed") {
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(String(seed), forType: .string)
        }

        if let onPreview {
            Button("Preview") { onPreview() }
        }

        if let saved = savedCreature {
            Divider()
            Button("Copy Config") {
                CreatureExport.copyConfigToClipboard(for: saved)
            }
            Button("Save Config...") {
                _ = CreatureExport.saveConfigToFile(for: saved)
            }
        }

        if let onAddToComparison {
            Divider()
            Button("Add to Comparison") { onAddToComparison() }
        }

        if let path = revealPath {
            Divider()
            Button("Reveal in Finder") {
                NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
            }
        }
    }
}
