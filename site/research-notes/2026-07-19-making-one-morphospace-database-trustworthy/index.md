---
title: "How to retire 281 GB without losing the experiment"
release: "published"
provenance: "assistant-drafted"
source_id: "D-003"
toc: true
---

# How to retire 281 GB without losing the experiment

_19 July–1 August 2026 · Data-integrity investigation._

Morphospace runs had accumulated into a 281 GB archive, and we wanted to replace it with one compact database containing the material still needed for analysis and replay. That required more than copying rows. The source archive could be retired only after the replacement had demonstrated that it preserved the necessary provenance and replay data.

An earlier read-only audit had shown that most suspicious records were incomplete rather than empty. Across 1,363,395 creatures, 6,968 lacked replay material, but only 45 met the strict near-empty criteria used to flag obvious garbage. Most of the collection remained usable. A missing replay, an incomplete record and an empty simulation were different failures; treating them as one deletion category would have discarded evidence merely because its provenance needed repair. The audit therefore recommended quarantine and spot checks rather than automatic removal.

The first full proof run reached the largest merge and then spent hours trying to construct replay records. After 6 hours and 50 minutes it stopped safely. One query had attempted to assemble complete documents for 1.36 million creatures before returning even its first row, consuming 88 GiB of temporary disk space along the way.

Because the proof procedure kept verification separate from mutation, the run preserved enough evidence to diagnose the scaling problem while leaving the production database byte-for-byte unchanged.

We then changed the order of work. The revised query selected and sorted only the small catalog fields first. Full documents were fetched later, in indexed batches, and only for the IDs actually needed. With that arrangement, the database projected all 1,363,395 creatures in 3.229 seconds without spilling to disk. A separate hydration sample retrieved 90,010 unique documents for 20,480 rows in 24.341 seconds.

None of those timings, by themselves, made deletion safe. The proof procedure treated the identity of the code, the identity of the source archive, the running process, the completion receipts, the database files and the final quiet period as separate facts to verify. A partial run could leave behind useful diagnostic evidence, but it could not authorize removal of the original. By the end of this period, the replacement path was fast enough to test seriously; the 281 GB source remained intact.
