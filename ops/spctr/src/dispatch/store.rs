use async_trait::async_trait;

use crate::dispatch::types::{
    HealthSnapshot, JobCompletion, JobRecord, JobSpec, JobState, LedgerEntryRecord,
    LedgerEntryReservation, RunnerRecord, RunnerRegistration, ZulipContext,
};

#[async_trait]
pub trait DispatchStore: Send + Sync {
    async fn create_queued_job(
        &self,
        job_spec: JobSpec,
        zulip: ZulipContext,
    ) -> anyhow::Result<JobRecord>;
    async fn get_job(&self, job_id: &str) -> anyhow::Result<Option<JobRecord>>;
    async fn clone_job(&self, original_id: &str) -> anyhow::Result<Option<JobRecord>>;
    async fn request_cancel(&self, job_id: &str) -> anyhow::Result<Option<JobRecord>>;
    async fn register_runner(&self, runner: RunnerRegistration) -> anyhow::Result<RunnerRecord>;
    async fn claim_next_job(&self, runner_id: &str) -> anyhow::Result<Option<JobRecord>>;
    async fn heartbeat_runner_job(
        &self,
        runner_id: &str,
        job_id: &str,
    ) -> anyhow::Result<Option<JobRecord>>;
    async fn complete_job(
        &self,
        runner_id: &str,
        job_id: &str,
        completion: JobCompletion,
    ) -> anyhow::Result<Option<JobRecord>>;
    async fn fail_job(
        &self,
        runner_id: &str,
        job_id: &str,
        completion: JobCompletion,
    ) -> anyhow::Result<Option<JobRecord>>;
    async fn cancel_job(
        &self,
        runner_id: &str,
        job_id: &str,
        completion: JobCompletion,
    ) -> anyhow::Result<Option<JobRecord>>;
    async fn list_recent_jobs(
        &self,
        limit: usize,
        states: &[JobState],
    ) -> anyhow::Result<Vec<JobRecord>>;
    async fn list_runners(&self) -> anyhow::Result<Vec<RunnerRecord>>;
    async fn health_snapshot(&self) -> anyhow::Result<HealthSnapshot>;
    async fn reserve_github_delivery(
        &self,
        delivery_id: &str,
        event_name: &str,
    ) -> anyhow::Result<bool>;
    async fn reserve_ledger_entry(
        &self,
        entry: LedgerEntryReservation,
    ) -> anyhow::Result<LedgerEntryRecord>;
    async fn mark_ledger_entry_posted(
        &self,
        entry_id: &str,
        zulip_message_id: Option<i64>,
    ) -> anyhow::Result<Option<LedgerEntryRecord>>;
    async fn mark_ledger_entry_failed(
        &self,
        entry_id: &str,
    ) -> anyhow::Result<Option<LedgerEntryRecord>>;
}
