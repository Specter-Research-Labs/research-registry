---
title: "Can a brain-response model measure lifelikeness?"
release: "published"
provenance: "assistant-drafted"
source_id: "A-014"
toc: true
---

# Can a brain-response model measure lifelikeness?

_4–8 May 2026 · Negative methodological result._

Flow Lenia organisms were already described by sixteen measurements of their shape and motion. We wondered whether a model trained to predict human brain activity from video could add something those measurements missed. If videos of different synthetic organisms produced different responses in regions associated with biological motion and visual form, perhaps that response could become a new coordinate in the morphospace.

Before showing TRIBE v2 any Lenia creatures, we gave it six deliberately unusual videos and checked that its predictions did not collapse to a constant output. That established that the model responded to unfamiliar images, but left the harder part untouched: what would a difference between those predicted responses tell us about the creatures?

The more revealing control was a synthetic point-light walker, chosen because biological motion should have made it an easy positive example. The predicted response in the superior temporal sulcus moved in the wrong direction. We could have searched for a different control until the expected pattern appeared, but that would have left the central interpretation untouched and untested. Instead, we stopped calling the output a measure of “lifelikeness.” TRIBE predicts fMRI responses; it does not report whether a viewer thinks an object is alive.

A narrower use remained possible: treat each predicted regional response as an unnamed descriptive score, then ask whether it supplied information beyond the sixteen existing measurements. Before running the real comparison, we tested that data path with synthetic responses for five known specimens. The test confirmed that a response could be matched to the correct organism and compared with its measured shape and motion. It did not test whether TRIBE's responses were scientifically meaningful.

The first real comparison ran into a more basic problem: the morphospace database identified specimens, while the video library identified scenes and archive cells, with no dependable mapping between them. Even an informative model response could not be joined back to the exact organism whose geometry and motion we had measured, so we needed a replay-and-render pipeline that began with a chosen specimen ID before a larger model run could answer the question.

The investigation therefore yielded no defensible brain-based measure of synthetic life. A future comparison would need videos generated from known specimen IDs, a biologically meaningful control and an interpretation grounded in what TRIBE actually predicts.
