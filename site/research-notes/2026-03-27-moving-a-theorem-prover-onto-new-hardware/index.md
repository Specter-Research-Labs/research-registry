---
title: "What it took to move a theorem prover off the Mac"
release: "published"
provenance: "assistant-drafted"
source_id: "D-002"
toc: true
---

# What it took to move a theorem prover off the Mac

_26–27 March 2026 · Infrastructure investigation. DeepSeek inference was brought up on one Tenstorrent QuietBox workstation; this note does not imply that the server processes are still running._

Wonton used a 1.3-billion-parameter DeepSeek model to propose the next step in Lean proofs. The model ran through MLX, which made good use of Apple silicon but tied that part of the experiment to a Mac. The destination was one Tenstorrent QuietBox workstation containing four N300 cards, with two Wormhole chips on each card. Moving the model there promised more parallel proof searches and a cleaner way to serve inference to several workers at once.

The first question was whether the hardware and serving stack worked at all. A supported Qwen3-8B model loaded successfully, generated text on the Wormhole chips, and answered through an OpenAI-compatible API on the same machine. This showed that the drivers, container and serving path could work together. DeepSeek Coder was small enough for the hardware and close enough to a familiar transformer architecture to load, but it failed where the model was divided across the two chips of an N300 card.

Trying one chip instead exposed the complementary problem. The model itself loaded, but its attention cache exhausted the available memory partway through the 24 layers. DeepSeek used sixteen key-value heads rather than the smaller grouped arrangement assumed by the existing configuration, so the cache was substantially larger. One chip could run the code but could not hold the intended serving setup. The two-chip run supplied enough memory, but failed because an attention projection had been divided incorrectly.

Tracing the tensors located the fault. Each chip produced an attention output 1,024 values wide, while the projection weight presented to it was still 2,048 values wide. The generic two-dimensional sharding rule was wrong for this multi-head-attention case. Sharding that weight along the correct dimension allowed all 24 layers to allocate their caches, complete warm-up and answer a real request. The model returned a Lean rewrite tactic rather than generic text, completing the first end-to-end check.

We then ran four independent DeepSeek server processes on that one QuietBox, one process per N300 card. Each process used the card's two Wormhole chips. This was more useful for Wonton than combining all eight chips into one large device: proof attempts are independent, so the four cards could work on four batches concurrently.

The episode changed how we thought about “model support.” Parameter count was not the difficult part. The obstacle was an assumption about how attention weights should be split across chips—an assumption hidden by the model families that had previously exercised the code. It also explains why later Wonton records refer to a DeepSeek endpoint without meaning an external provider: the endpoint was simply the API presented by a model running on the QuietBox.
