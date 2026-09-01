---
title: "A brain model could not tell us whether a Lenia creature looked alive"
release: "published"
provenance: "assistant-drafted"
source_id: "A-014"
toc: true
---

# A brain model could not tell us whether a Lenia creature looked alive

_4–8 May 2026 · Negative methodological result._

Flow Lenia organisms were already described by sixteen measurements of their shape and motion. We wondered whether a model trained to predict human brain activity from video could add something those measurements missed. If videos of different synthetic organisms produced different responses in regions associated with biological motion and visual form, perhaps that response could become a new coordinate in the morphospace.

The model was TRIBE v2. Before showing it any Lenia creatures, we gave it six deliberately unusual videos and confirmed that its predictions did not collapse to a constant output. That was a useful engineering check, but it established only that the model responded to unfamiliar images. It did not establish what those responses meant.

The more revealing control was a synthetic point-light walker, chosen because biological motion should have made it an easy positive example. The predicted response in the superior temporal sulcus moved in the wrong direction. We could have searched for a different control until the expected pattern appeared, but that would have left the central interpretation untouched and untested. Instead, we stopped calling the output a measure of “lifelikeness.” TRIBE predicts fMRI responses; it does not report whether a viewer thinks an object is alive.

A narrower use remained possible: treat each predicted regional response as an unnamed descriptive score, then ask whether it supplied information beyond the sixteen existing measurements. Before running the real comparison, we tested that data path with synthetic responses for five known specimens. The test confirmed that a response could be matched to the correct organism and compared with its measured shape and motion. It did not test whether TRIBE's responses were scientifically meaningful.

The first real comparison then ran into a provenance problem. The morphospace database identified specimens, while the existing video library identified scenes and archive cells. There was no dependable mapping between them. A response could not be joined back to the exact organism whose geometry and motion had been measured. The correct next step was therefore not a larger model run, but a replay-and-render pipeline that generated each video from a chosen specimen ID.

The investigation therefore yielded no defensible brain-based measure of synthetic life. A future comparison would need videos generated from known specimen IDs, a biologically meaningful control and an interpretation grounded in what TRIBE actually predicts.
