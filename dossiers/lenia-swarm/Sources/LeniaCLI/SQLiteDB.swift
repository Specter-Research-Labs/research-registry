import Foundation
import SQLite3

final class SQLiteDB {
    private let db: OpaquePointer

    init(path: String) throws {
        var handle: OpaquePointer?
        if sqlite3_open(path, &handle) != SQLITE_OK {
            throw SQLiteIndexError.openFailed(path)
        }
        guard let opened = handle else {
            throw SQLiteIndexError.openFailed(path)
        }
        sqlite3_busy_timeout(opened, 30_000)
        self.db = opened
    }

    deinit {
        sqlite3_close(db)
    }

    func exec(_ sql: String) throws {
        if sqlite3_exec(db, sql, nil, nil, nil) != SQLITE_OK {
            throw SQLiteIndexError.sqliteError(message: errorMessage())
        }
    }

    func prepare(_ sql: String) throws -> OpaquePointer {
        var stmt: OpaquePointer?
        if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) != SQLITE_OK {
            throw SQLiteIndexError.sqliteError(message: errorMessage())
        }
        guard let prepared = stmt else {
            throw SQLiteIndexError.sqliteError(message: "Failed to prepare statement")
        }
        return prepared
    }

    func step(_ stmt: OpaquePointer) throws {
        if sqlite3_step(stmt) != SQLITE_DONE {
            throw SQLiteIndexError.sqliteError(message: errorMessage())
        }
    }

    func withImmediateTransaction(_ body: () throws -> Void) throws {
        try exec("BEGIN IMMEDIATE")
        do {
            try body()
            try exec("COMMIT")
        } catch {
            _ = try? exec("ROLLBACK")
            throw error
        }
    }

    func scalarInt(_ sql: String) throws -> Int {
        let stmt = try prepare(sql)
        defer { sqlite3_finalize(stmt) }
        if sqlite3_step(stmt) == SQLITE_ROW {
            return Int(sqlite3_column_int64(stmt, 0))
        }
        return 0
    }

    func changes() -> Int {
        Int(sqlite3_changes(db))
    }

    func tableExists(_ name: String) throws -> Bool {
        let stmt = try prepare("SELECT name FROM sqlite_master WHERE type='table' AND name=? LIMIT 1")
        defer { sqlite3_finalize(stmt) }
        bindText(stmt, index: 1, value: name)
        return sqlite3_step(stmt) == SQLITE_ROW
    }

    func tableColumns(_ table: String) throws -> Set<String> {
        let stmt = try prepare("PRAGMA table_info(\(table))")
        defer { sqlite3_finalize(stmt) }
        var columns: Set<String> = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            guard let nameC = sqlite3_column_text(stmt, 1) else { continue }
            columns.insert(String(cString: nameC))
        }
        return columns
    }

    func bindText(_ stmt: OpaquePointer, index: Int32, value: String?) {
        if let value = value {
            sqlite3_bind_text(stmt, index, value, -1, SQLITE_TRANSIENT)
        } else {
            sqlite3_bind_null(stmt, index)
        }
    }

    func bindInt(_ stmt: OpaquePointer, index: Int32, value: Int?) {
        if let value = value {
            sqlite3_bind_int64(stmt, index, sqlite3_int64(value))
        } else {
            sqlite3_bind_null(stmt, index)
        }
    }

    func bindDouble(_ stmt: OpaquePointer, index: Int32, value: Float?) {
        if let value = value {
            sqlite3_bind_double(stmt, index, Double(value))
        } else {
            sqlite3_bind_null(stmt, index)
        }
    }

    func bindDouble(_ stmt: OpaquePointer, index: Int32, value: Double?) {
        if let value = value {
            sqlite3_bind_double(stmt, index, value)
        } else {
            sqlite3_bind_null(stmt, index)
        }
    }

    func bindBool(_ stmt: OpaquePointer, index: Int32, value: Bool?) {
        if let value = value {
            sqlite3_bind_int(stmt, index, value ? 1 : 0)
        } else {
            sqlite3_bind_null(stmt, index)
        }
    }

    private func errorMessage() -> String {
        if let message = sqlite3_errmsg(db) {
            return String(cString: message)
        }
        return "Unknown SQLite error"
    }
}

enum SQLiteIndexError: Error, CustomStringConvertible {
    case openFailed(String)
    case invalidUTF8(String)
    case sqliteError(message: String)

    var description: String {
        switch self {
        case .openFailed(let path):
            return "Failed to open SQLite DB at \(path)"
        case .invalidUTF8(let path):
            return "Invalid UTF-8 in JSONL file: \(path)"
        case .sqliteError(let message):
            return "SQLite error: \(message)"
        }
    }
}

let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
