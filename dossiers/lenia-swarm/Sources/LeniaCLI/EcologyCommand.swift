import ArgumentParser
import Accelerate
import CoreGraphics
import Foundation
import ImageIO
import LeniaCore
import SQLite3
import UniformTypeIdentifiers

struct EcologyCommand: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "ecology",
        abstract: "Export ecology parameter-space data from a compendium database"
    )

    @Option(name: [.customLong("db"), .customLong("db-path")], help: "SQLite compendium DB path")
    var dbPath: String

    @Option(name: .shortAndLong, help: "Output directory for ecology artifacts")
    var output: String = "outputs/ecology"

    @Flag(name: .long, help: "Include unstable entries")
    var includeUnstable: Bool = false

    @Option(name: .long, help: "Limit number of exported rows")
    var limit: Int?

    @Flag(name: .long, help: "Generate a mu-sigma scatter plot PNG")
    var plot: Bool = false

    @Option(name: .long, help: "Plot width in pixels")
    var plotWidth: Int = 1200

    @Option(name: .long, help: "Plot height in pixels")
    var plotHeight: Int = 800

    @Flag(name: .long, help: "Compute PCA(2) projection of genotype vectors")
    var pca: Bool = false

    @Option(name: .long, help: "Maximum number of rows to use for PCA")
    var pcaMaxRows: Int = 2000

    func run() throws {
        let resolvedOutput = try resolveArtifactPath(output, dossier: dossierName)
        let outputURL = URL(fileURLWithPath: resolvedOutput, isDirectory: true)
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)

        let datePrefix = EcologyCommand.datePrefix()
        let dataURL = outputURL.appendingPathComponent("\(datePrefix)-ecology-embedding.jsonl")
        let pcaURL = outputURL.appendingPathComponent("\(datePrefix)-ecology-pca2.jsonl")
        let summaryURL = outputURL.appendingPathComponent("\(datePrefix)-ecology-summary.json")
        let plotURL = outputURL.appendingPathComponent("\(datePrefix)-ecology-mu-sigma.png")

        let db = try SQLiteDB(path: (dbPath as NSString).expandingTildeInPath)
        guard try db.tableExists("compendium_meta") else {
            throw EcologyError.missingTable("compendium_meta")
        }
        let schemaVersion = try db.scalarInt("SELECT schema_version FROM compendium_meta LIMIT 1")
        if schemaVersion != compendiumSchemaVersion {
            throw EcologyError.schemaMismatch(found: schemaVersion, expected: compendiumSchemaVersion)
        }
        guard try db.tableExists("creatures") else {
            throw EcologyError.missingTable("creatures")
        }
        let creatureCount = try db.scalarInt("SELECT COUNT(*) FROM creatures")
        guard creatureCount > 0 else {
            throw EcologyError.emptyTable("creatures")
        }
        let sql = Self.buildQuery(includeUnstable: includeUnstable, limit: limit)
        let stmt = try db.prepare(sql)
        defer { sqlite3_finalize(stmt) }

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let decoder = JSONDecoder()

        FileManager.default.createFile(atPath: dataURL.path, contents: nil)
        let handle = try FileHandle(forWritingTo: dataURL)
        defer { try? handle.close() }

        var exported = 0
        var muSigmaPoints: [PlotPoint] = []
        var pcaRecords: [PCARecord] = []
        if pca {
            if pcaMaxRows <= 1 {
                throw ValidationError("pca_max_rows must be > 1")
            }
            pcaRecords.reserveCapacity(min(pcaMaxRows, max(creatureCount, 0)))
        }
        while sqlite3_step(stmt) == SQLITE_ROW {
            let record = try Self.readRecord(stmt: stmt, decoder: decoder)
            let data = try encoder.encode(record)
            handle.write(data)
            handle.write(Data([0x0A]))
            exported += 1
            if plot, record.muSigma.count == 2 {
                muSigmaPoints.append(PlotPoint(x: record.muSigma[0], y: record.muSigma[1]))
            }
            if pca, pcaRecords.count < pcaMaxRows {
                pcaRecords.append(PCARecord(
                    id: record.id,
                    runId: record.runId,
                    taxonomyFamilyId: record.taxonomyFamilyId,
                    taxonomyGenusId: record.taxonomyGenusId,
                    taxonomySpeciesId: record.taxonomySpeciesId,
                    genotypeVector: record.genotypeVector
                ))
            }
        }

        var pcaFilePath: String? = nil
        if pca {
            if pcaRecords.count < 2 {
                throw ValidationError("PCA requires at least 2 rows; got \(pcaRecords.count).")
            }
            let projected = try Self.computePCA2(records: pcaRecords)
            FileManager.default.createFile(atPath: pcaURL.path, contents: nil)
            let pcaHandle = try FileHandle(forWritingTo: pcaURL)
            defer { try? pcaHandle.close() }
            for row in projected {
                let data = try encoder.encode(row)
                pcaHandle.write(data)
                pcaHandle.write(Data([0x0A]))
            }
            pcaFilePath = pcaURL.path
        }

        var plotFilePath: String? = nil
        if plot {
            try Self.writeMuSigmaPlot(
                points: muSigmaPoints,
                width: plotWidth,
                height: plotHeight,
                outputURL: plotURL
            )
            plotFilePath = plotURL.path
        }

        let summary = EcologySummary(
            exportedCount: exported,
            includeUnstable: includeUnstable,
            limit: limit,
            dataFile: dataURL.path,
            pcaFile: pcaFilePath,
            plotFile: plotFilePath
        )
        let summaryData = try encoder.encode(summary)
        try summaryData.write(to: summaryURL)
    }

    private static func buildQuery(includeUnstable: Bool, limit: Int?) -> String {
        var sql = """
        SELECT id, run_id, is_stable, score, genotype_json,
               taxonomy_family_id, taxonomy_genus_id, taxonomy_species_id,
               mass_mean, gyration, center_velocity, velocity_x, velocity_y, heading_rad, complexity_mean
        FROM creatures
        """
        if !includeUnstable {
            sql += " WHERE is_stable = 1"
        }
        sql += " ORDER BY COALESCE(score, -1.0e30) DESC, id ASC"
        if let limit {
            sql += " LIMIT \(limit)"
        }
        return sql
    }

    private static func readRecord(stmt: OpaquePointer, decoder: JSONDecoder) throws -> EcologyRecord {
        guard let idC = sqlite3_column_text(stmt, 0),
              let runIdC = sqlite3_column_text(stmt, 1),
              let genotypeC = sqlite3_column_text(stmt, 4) else {
            throw EcologyError.invalidRow
        }

        let id = String(cString: idC)
        let runId = String(cString: runIdC)
        let isStable = sqlite3_column_int(stmt, 2) != 0
        let score = columnDouble(stmt, index: 3)
        let genotypeJSON = String(cString: genotypeC)

        let familyId = columnText(stmt, index: 5)
        let genusId = columnText(stmt, index: 6)
        let speciesId = columnText(stmt, index: 7)

        let massMean = columnDouble(stmt, index: 8)
        let gyration = columnDouble(stmt, index: 9)
        let centerVelocity = columnDouble(stmt, index: 10)
        let velocityX = columnDouble(stmt, index: 11)
        let velocityY = columnDouble(stmt, index: 12)
        let headingRad = columnDouble(stmt, index: 13)
        let complexityMean = columnDouble(stmt, index: 14)

        let params = try decodeKernelParams(genotypeJSON, decoder: decoder)
        let kernels = try canonicalizeKernels(params)
        let genotypeVector = flattenVector(kernels: kernels, R: params.R)

        let muSigma = [meanValues(params.m), meanValues(params.s)]
        let betaSummary = BetaSummary(
            rMean: meanValues(params.r),
            bMean: meanNested(params.b),
            bMax: maxNested(params.b),
            wMean: meanNested(params.w),
            wMax: maxNested(params.w),
            aMean: meanNested(params.a),
            aMax: maxNested(params.a),
            R: params.R
        )

        let metrics = EcologyMetrics(
            massMean: massMean.map(Float.init),
            gyration: gyration.map(Float.init),
            centerVelocity: centerVelocity.map(Float.init),
            velocityX: velocityX.map(Float.init),
            velocityY: velocityY.map(Float.init),
            headingRad: headingRad.map(Float.init),
            complexityMean: complexityMean.map(Float.init)
        )

        return EcologyRecord(
            id: id,
            runId: runId,
            isStable: isStable,
            score: score.map(Float.init),
            taxonomyFamilyId: familyId,
            taxonomyGenusId: genusId,
            taxonomySpeciesId: speciesId,
            kernelCount: kernels.count,
            muSigma: muSigma,
            betaSummary: betaSummary,
            genotypeVector: genotypeVector,
            metrics: metrics
        )
    }

    private static func decodeKernelParams(_ raw: String, decoder: JSONDecoder) throws -> KernelParams {
        guard let data = raw.data(using: .utf8) else {
            throw EcologyError.invalidParams("genotype_json is not UTF-8")
        }
        return try decoder.decode(KernelParams.self, from: data)
    }

    private static func canonicalizeKernels(_ params: KernelParams) throws -> [EcologyKernelParams] {
        let count = params.r.count
        guard params.m.count == count,
              params.s.count == count,
              params.h.count == count,
              params.b.count == count,
              params.w.count == count,
              params.a.count == count else {
            throw EcologyError.invalidParams("kernel arrays have inconsistent lengths")
        }
        guard count > 0 else {
            throw EcologyError.invalidParams("no kernels present")
        }

        var kernels: [EcologyKernelParams] = []
        kernels.reserveCapacity(count)
        for idx in 0..<count {
            let kernel = EcologyKernelParams(
                r: params.r[idx],
                m: params.m[idx],
                s: params.s[idx],
                h: params.h[idx],
                b: params.b[idx],
                w: params.w[idx],
                a: params.a[idx]
            )
            kernels.append(kernel)
        }

        kernels.sort { $0.signature < $1.signature }
        return kernels
    }

    private static func flattenVector(kernels: [EcologyKernelParams], R: Float) -> [Float] {
        var vector: [Float] = []
        for kernel in kernels {
            vector.append(kernel.r)
            vector.append(kernel.m)
            vector.append(kernel.s)
            vector.append(kernel.h)
            vector.append(contentsOf: kernel.b)
            vector.append(contentsOf: kernel.w)
            vector.append(contentsOf: kernel.a)
        }
        vector.append(R)
        return vector
    }

    private static func writeMuSigmaPlot(points: [PlotPoint], width: Int, height: Int, outputURL: URL) throws {
        if width <= 0 || height <= 0 {
            throw EcologyError.invalidParams("plot dimensions must be > 0")
        }

        let renderer = CGContext(
            data: nil,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: width * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        )
        guard let context = renderer else {
            throw EcologyError.invalidParams("failed to create image context")
        }

        context.setFillColor(CGColor(red: 0.04, green: 0.04, blue: 0.06, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))

        let padding: CGFloat = 60
        let plotWidth = CGFloat(width) - 2 * padding
        let plotHeight = CGFloat(height) - 2 * padding
        let originX = padding
        let originY = padding

        let xs = points.map(\.x)
        let ys = points.map(\.y)
        let minX = xs.min() ?? 0
        let maxX = xs.max() ?? 1
        let minY = ys.min() ?? 0
        let maxY = ys.max() ?? 1

        let spanX = max(maxX - minX, 1e-6)
        let spanY = max(maxY - minY, 1e-6)

        func plotPixel(x: Int, y: Int) {
            let rect = CGRect(x: x, y: y, width: 1, height: 1)
            context.fill(rect)
        }

        // Density overlay: coarse 2D histogram behind points for quick niche inspection.
        // This is intentionally simple (no KDE) so it stays deterministic and dependency-free.
        let binsX = min(160, max(24, Int(plotWidth / 12)))
        let binsY = min(120, max(18, Int(plotHeight / 12)))
        var hist = [Int](repeating: 0, count: binsX * binsY)
        for point in points {
            let nx = (point.x - minX) / spanX
            let ny = (point.y - minY) / spanY
            let bx = min(max(Int(nx * Float(binsX)), 0), binsX - 1)
            let by = min(max(Int(ny * Float(binsY)), 0), binsY - 1)
            hist[by * binsX + bx] += 1
        }
        let maxCount = hist.max() ?? 0
        if maxCount > 0 {
            let binW = plotWidth / CGFloat(binsX)
            let binH = plotHeight / CGFloat(binsY)
            for by in 0..<binsY {
                for bx in 0..<binsX {
                    let c = hist[by * binsX + bx]
                    if c == 0 { continue }
                    let norm = CGFloat(c) / CGFloat(maxCount)
                    let alpha = 0.08 + 0.45 * pow(norm, 0.65)
                    context.setFillColor(CGColor(red: 0.22, green: 0.56, blue: 0.86, alpha: alpha))
                    let rect = CGRect(
                        x: originX + CGFloat(bx) * binW,
                        y: originY + CGFloat(by) * binH,
                        width: binW,
                        height: binH
                    )
                    context.fill(rect)
                }
            }
        }

        context.setFillColor(CGColor(red: 0.94, green: 0.78, blue: 0.24, alpha: 0.9))
        for point in points {
            let normX = CGFloat((point.x - minX) / spanX)
            let normY = CGFloat((point.y - minY) / spanY)
            let px = Int(originX + normX * plotWidth)
            let py = Int(originY + normY * plotHeight)
            for dx in -1...1 {
                for dy in -1...1 {
                    plotPixel(x: px + dx, y: py + dy)
                }
            }
        }

        context.setStrokeColor(CGColor(red: 0.42, green: 0.42, blue: 0.46, alpha: 1))
        context.setLineWidth(2)
        context.stroke(CGRect(x: originX, y: originY, width: plotWidth, height: plotHeight))

        guard let image = context.makeImage() else {
            throw EcologyError.invalidParams("failed to render plot image")
        }

        guard let destination = CGImageDestinationCreateWithURL(outputURL as CFURL, UTType.png.identifier as CFString, 1, nil) else {
            throw EcologyError.invalidParams("failed to write plot image")
        }
        CGImageDestinationAddImage(destination, image, nil)
        if !CGImageDestinationFinalize(destination) {
            throw EcologyError.invalidParams("failed to write plot image")
        }
    }

    private static func datePrefix() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone.current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    private static func computePCA2(records: [PCARecord]) throws -> [PCA2Row] {
        guard let first = records.first else { throw PCAError.empty }
        let d = first.genotypeVector.count
        guard d > 0 else { throw PCAError.empty }
        for r in records {
            if r.genotypeVector.count != d { throw PCAError.inconsistentLength }
        }

        let n = records.count

        var mean = [Float](repeating: 0, count: d)
        for r in records {
            vDSP_vadd(mean, 1, r.genotypeVector, 1, &mean, 1, vDSP_Length(d))
        }
        var invN = Float(1.0 / Double(n))
        vDSP_vsmul(mean, 1, &invN, &mean, 1, vDSP_Length(d))

        // X is row-major (n x d) after centering.
        var X = [Float](repeating: 0, count: n * d)
        for (i, r) in records.enumerated() {
            let base = i * d
            for j in 0..<d {
                X[base + j] = r.genotypeVector[j] - mean[j]
            }
        }

        // Cov = (X^T X) / (n-1). We'll compute d x d in column-major for LAPACK.
        var cov = [Float](repeating: 0, count: d * d)
        cblas_sgemm(
            CblasRowMajor,
            CblasTrans,
            CblasNoTrans,
            Int32(d),
            Int32(d),
            Int32(n),
            1.0,
            X,
            Int32(d),
            X,
            Int32(d),
            0.0,
            &cov,
            Int32(d)
        )
        var invNm1 = Float(1.0 / Double(max(n - 1, 1)))
        vDSP_vsmul(cov, 1, &invNm1, &cov, 1, vDSP_Length(d * d))

        // Convert cov from row-major to column-major in-place copy for LAPACK ssyev.
        var a = [Float](repeating: 0, count: d * d)
        for r in 0..<d {
            for c in 0..<d {
                a[c * d + r] = cov[r * d + c]
            }
        }

        var w = [Float](repeating: 0, count: d)
        var jobz: Int8 = 86 // 'V'
        var uplo: Int8 = 85 // 'U'
        var n32 = Int32(d)
        var lda = n32
        var lwork = Int32(-1)
        var workQuery: Float = 0
        var info: Int32 = 0
        ssyev_(&jobz, &uplo, &n32, &a, &lda, &w, &workQuery, &lwork, &info)
        if info != 0 { throw PCAError.lapackFailed(info) }
        lwork = Int32(workQuery)
        var work = [Float](repeating: 0, count: Int(lwork))
        ssyev_(&jobz, &uplo, &n32, &a, &lda, &w, &work, &lwork, &info)
        if info != 0 { throw PCAError.lapackFailed(info) }

        // Eigenvalues ascending; take top-2 eigenvectors from the end.
        let pc1 = d - 1
        let pc2 = d - 2
        var V = [Float](repeating: 0, count: d * 2)
        for r in 0..<d {
            V[r * 2 + 0] = a[pc1 * d + r]
            V[r * 2 + 1] = a[pc2 * d + r]
        }

        // Y = X * V (n x 2), row-major.
        var Y = [Float](repeating: 0, count: n * 2)
        cblas_sgemm(
            CblasRowMajor,
            CblasNoTrans,
            CblasNoTrans,
            Int32(n),
            2,
            Int32(d),
            1.0,
            X,
            Int32(d),
            V,
            2,
            0.0,
            &Y,
            2
        )

        var rows: [PCA2Row] = []
        rows.reserveCapacity(n)
        for i in 0..<n {
            let base = i * 2
            rows.append(PCA2Row(
                id: records[i].id,
                runId: records[i].runId,
                taxonomyFamilyId: records[i].taxonomyFamilyId,
                taxonomyGenusId: records[i].taxonomyGenusId,
                taxonomySpeciesId: records[i].taxonomySpeciesId,
                pca2: [Y[base + 0], Y[base + 1]]
            ))
        }
        return rows
    }
}

private struct EcologyRecord: Codable {
    let id: String
    let runId: String
    let isStable: Bool
    let score: Float?
    let taxonomyFamilyId: String?
    let taxonomyGenusId: String?
    let taxonomySpeciesId: String?
    let kernelCount: Int
    let muSigma: [Float]
    let betaSummary: BetaSummary
    let genotypeVector: [Float]
    let metrics: EcologyMetrics
}

private struct BetaSummary: Codable {
    let rMean: Float
    let bMean: Float
    let bMax: Float
    let wMean: Float
    let wMax: Float
    let aMean: Float
    let aMax: Float
    let R: Float
}

private struct EcologyMetrics: Codable {
    let massMean: Float?
    let gyration: Float?
    let centerVelocity: Float?
    let velocityX: Float?
    let velocityY: Float?
    let headingRad: Float?
    let complexityMean: Float?
}

private struct EcologySummary: Codable {
    let exportedCount: Int
    let includeUnstable: Bool
    let limit: Int?
    let dataFile: String
    let pcaFile: String?
    let plotFile: String?
}

private struct PlotPoint {
    let x: Float
    let y: Float
}

private struct PCARecord {
    let id: String
    let runId: String
    let taxonomyFamilyId: String?
    let taxonomyGenusId: String?
    let taxonomySpeciesId: String?
    let genotypeVector: [Float]
}

private struct PCA2Row: Codable {
    let id: String
    let runId: String
    let taxonomyFamilyId: String?
    let taxonomyGenusId: String?
    let taxonomySpeciesId: String?
    let pca2: [Float]
}

private enum PCAError: Error, CustomStringConvertible {
    case empty
    case inconsistentLength
    case lapackFailed(Int32)

    var description: String {
        switch self {
        case .empty:
            return "PCA requires non-empty genotype vectors"
        case .inconsistentLength:
            return "PCA requires all genotype vectors to have the same length"
        case .lapackFailed(let code):
            return "LAPACK eigen decomposition failed (info=\(code))"
        }
    }
}

private struct EcologyKernelParams {
    let r: Float
    let m: Float
    let s: Float
    let h: Float
    let b: [Float]
    let w: [Float]
    let a: [Float]

    var signature: KernelSignature {
        KernelSignature(
            r: r,
            m: m,
            s: s,
            h: h,
            bMean: meanValues(b),
            bMax: b.max() ?? 0,
            wMean: meanValues(w),
            wMax: w.max() ?? 0,
            aMean: meanValues(a),
            aMax: a.max() ?? 0
        )
    }
}

private struct KernelSignature: Comparable {
    let r: Float
    let m: Float
    let s: Float
    let h: Float
    let bMean: Float
    let bMax: Float
    let wMean: Float
    let wMax: Float
    let aMean: Float
    let aMax: Float

    static func < (lhs: KernelSignature, rhs: KernelSignature) -> Bool {
        let left = [lhs.r, lhs.m, lhs.s, lhs.h, lhs.bMean, lhs.bMax, lhs.wMean, lhs.wMax, lhs.aMean, lhs.aMax]
        let right = [rhs.r, rhs.m, rhs.s, rhs.h, rhs.bMean, rhs.bMax, rhs.wMean, rhs.wMax, rhs.aMean, rhs.aMax]
        for (l, r) in zip(left, right) {
            if l < r { return true }
            if l > r { return false }
        }
        return false
    }
}

private enum EcologyError: Error, CustomStringConvertible {
    case invalidRow
    case invalidParams(String)
    case schemaMismatch(found: Int, expected: Int)
    case missingTable(String)
    case emptyTable(String)

    var description: String {
        switch self {
        case .invalidRow:
            return "Invalid row in compendium export"
        case .invalidParams(let message):
            return "Invalid KernelParams: \(message)"
        case .schemaMismatch(let found, let expected):
            return "Compendium schema version \(found) does not match expected \(expected). Rebuild or re-index the compendium."
        case .missingTable(let table):
            return "Missing \(table) table in compendium database"
        case .emptyTable(let table):
            return "Compendium database has no rows in \(table)"
        }
    }
}

private func columnDouble(_ stmt: OpaquePointer, index: Int) -> Double? {
    let idx = Int32(index)
    if sqlite3_column_type(stmt, idx) == SQLITE_NULL {
        return nil
    }
    return sqlite3_column_double(stmt, idx)
}

private func columnText(_ stmt: OpaquePointer, index: Int) -> String? {
    let idx = Int32(index)
    guard sqlite3_column_type(stmt, idx) != SQLITE_NULL,
          let text = sqlite3_column_text(stmt, idx) else {
        return nil
    }
    return String(cString: text)
}

private func meanValues(_ values: [Float]) -> Float {
    guard !values.isEmpty else { return 0 }
    return values.reduce(0, +) / Float(values.count)
}

private func meanNested(_ values: [[Float]]) -> Float {
    var total: Float = 0
    var count = 0
    for row in values {
        total += row.reduce(0, +)
        count += row.count
    }
    guard count > 0 else { return 0 }
    return total / Float(count)
}

private func maxNested(_ values: [[Float]]) -> Float {
    var maxValue: Float?
    for row in values {
        if let rowMax = row.max() {
            if let current = maxValue {
                maxValue = max(current, rowMax)
            } else {
                maxValue = rowMax
            }
        }
    }
    return maxValue ?? 0
}
