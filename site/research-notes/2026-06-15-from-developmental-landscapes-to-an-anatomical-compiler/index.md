---
title: "Running morphogenesis in reverse"
release: "published"
provenance: "assistant-drafted"
source_id: "D-003"
toc: true
---

# Running morphogenesis in reverse

_15–20 June 2026 · Research design and first prototype._

Here, “genotype” is the numerical specification of a Flow Lenia rule, which we combine with an initial field and run forward to see what body and behavior develop. That gives us a way to generate forms from compact specifications, but the reverse question is much harder: when we start with the body we want, what in its appearance or development tells us which rule could make it?

The developmental-landscape work began by looking more closely at everything that happens between those endpoints. Instead of reducing each organism to one final row in a descriptor table, we started preserving the fields and trajectories through which it developed. Those records make different questions possible. Do nearby starting points settle into the same kind of body? Where do two developmental paths branch? How large a disturbance is needed to push an organism from one region of the landscape into another?

Before asking any of those questions, replay audits checked the basic prerequisite that a stored trajectory could still reproduce the organism it claimed to describe.

The anatomical-compiler prototype approached the same system from the opposite direction. Given a target body, it searched genotype space for candidates, simulated each candidate forward, and refined the ones whose developed forms came closest. It also examined boundaries where a small change in genotype produced a qualitatively different body. Because several genotypes can lead to similar anatomy, the object being recovered is not necessarily one privileged genetic recipe, but a family of workable recipes.

Together, the two projects sketch a map that can be travelled both ways. One side follows a genotype through development and records where it ends up; the other starts with an anatomy and searches for the genotypes capable of making it. The June prototype established the machinery needed to investigate that loop. It did not yet show that an arbitrary imagined Flow Lenia body can be translated into a reliable genotype.

The later [anatomical-compiler report](/dossiers/lenia-swarm/anatomical-compiler/) separates matching measured descriptors, maintaining a supplied body and recovering known rules.
