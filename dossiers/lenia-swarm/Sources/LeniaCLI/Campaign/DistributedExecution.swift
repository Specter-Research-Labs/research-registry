import ArgumentParser
import DistributedCluster
import Foundation
import LeniaCore
import Logging

enum CampaignExecutionMode {
    case local
    case distributed(CampaignWorkerPool)
}

extension LeniaCampaignPhaseType {
    var runsOnCampaignWorkers: Bool {
        switch self {
        case .sweep, .interventionBattery, .ecology:
            return true
        case .qd, .imgep, .curiosity:
            return false
        }
    }
}

func validateDistributedCampaignPhases(_ phases: [LeniaCampaignPhaseConfig]) throws {
    let unsupported = phases.filter { !$0.type.runsOnCampaignWorkers }
    guard unsupported.isEmpty else {
        let names = unsupported.map { "'\($0.name)' (type=\($0.type.rawValue))" }.joined(separator: ", ")
        throw ValidationError(
            "--distributed runs only sweep, intervention-battery and ecology phases on workers; these phases would run in-process: \(names). Remove them or run without --distributed."
        )
    }
}

actor CampaignWorkerPool {
    private struct ConnectedWorker {
        let worker: LeniaWorker
        let status: WorkerStatus
    }

    static let workerWaitSeconds = 120

    private let system: ClusterSystem
    private let logger: Logger
    private let runContext: RunContext
    private var workers: [LeniaWorker] = []
    private var listener: Task<Void, Never>?

    init(system: ClusterSystem, logger: Logger, runContext: RunContext) {
        self.system = system
        self.logger = logger
        self.runContext = runContext
    }

    func start(minWorkers: Int) async throws {
        let clusterSystem = system
        listener = Task {
            for await worker in await clusterSystem.receptionist.listing(of: .leniaWorkers) {
                await self.add(worker)
            }
        }
        var waited = 0
        while workers.count < minWorkers {
            guard waited < Self.workerWaitSeconds else {
                throw ValidationError(
                    "Timed out after \(Self.workerWaitSeconds)s waiting for \(minWorkers) campaign worker(s); \(workers.count) joined."
                )
            }
            try await Task.sleep(for: .seconds(1))
            waited += 1
        }
        for worker in workers {
            try await worker.updateRunContext(runContext)
        }
    }

    func stop() {
        listener?.cancel()
        listener = nil
    }

    private func add(_ worker: LeniaWorker) {
        guard !workers.contains(where: { $0.id == worker.id }) else {
            return
        }
        workers.append(worker)
        logger.info("Campaign worker joined: \(worker.id) (\(workers.count) connected)")
    }

    func execute(jobs: [LeniaCampaignJob]) async throws -> [LeniaCampaignJobExecution] {
        var connected: [ConnectedWorker] = []
        for worker in workers {
            connected.append(ConnectedWorker(worker: worker, status: try await worker.getStatus()))
        }
        connected.sort { $0.status.workerId < $1.status.workerId }
        guard !connected.isEmpty else {
            throw ValidationError("No campaign workers are connected.")
        }
        for job in jobs where !connected.contains(where: { workerSupportsCampaignJob($0.status, job: job) }) {
            let available = connected.map { worker in
                let capabilities = worker.status.capabilities
                return "\(worker.status.workerId) (search \(capabilities.canonicalSearchBackends.map(\.rawValue)), flow-lenia \(capabilities.canonicalFlowLeniaBackends.map(\.rawValue)))"
            }
            throw ValidationError(
                "No connected worker supports campaign job \(job.runID) (backend \(job.backendRequest)); workers: \(available.joined(separator: ", "))."
            )
        }

        let queue = CampaignJobQueue(jobs: jobs)
        let logger = self.logger
        var slots = [LeniaCampaignJobExecution?](repeating: nil, count: jobs.count)
        try await withThrowingTaskGroup(of: [(Int, LeniaCampaignJobExecution)].self) { group in
            for remote in connected {
                group.addTask {
                    var finished: [(Int, LeniaCampaignJobExecution)] = []
                    while let index = await queue.reserve(for: remote.status) {
                        let job = jobs[index]
                        logger.info("Dispatching campaign job \(index + 1)/\(jobs.count) \(job.runID) to \(remote.status.workerId)")
                        do {
                            finished.append((index, try await remote.worker.processCampaignJob(job)))
                        } catch {
                            // A worker that failed once is not trusted with further jobs in this phase,
                            // so one broken node cannot turn the whole queue into failed records.
                            logger.error("Campaign job \(job.runID) failed on \(remote.status.workerId): \(error)")
                            finished.append((index, failedLeniaCampaignJobExecution(
                                job,
                                workerID: remote.status.workerId,
                                errorMessage: String(describing: error)
                            )))
                            break
                        }
                    }
                    return finished
                }
            }
            for try await batch in group {
                for (index, execution) in batch {
                    slots[index] = execution
                }
            }
        }

        return jobs.enumerated().map { index, job in
            slots[index] ?? failedLeniaCampaignJobExecution(
                job,
                workerID: nil,
                errorMessage: "Not dispatched: every worker able to run it failed earlier in this phase."
            )
        }
    }
}

private actor CampaignJobQueue {
    private let jobs: [LeniaCampaignJob]
    private var pending: [Int]

    init(jobs: [LeniaCampaignJob]) {
        self.jobs = jobs
        self.pending = Array(jobs.indices)
    }

    func reserve(for status: WorkerStatus) -> Int? {
        guard let position = pending.firstIndex(where: { workerSupportsCampaignJob(status, job: jobs[$0]) }) else {
            return nil
        }
        return pending.remove(at: position)
    }
}
