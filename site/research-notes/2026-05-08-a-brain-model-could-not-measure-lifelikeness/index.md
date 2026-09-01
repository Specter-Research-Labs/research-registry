---
title: "A brain model could not tell us whether a Lenia creature looked alive"
release: "published"
provenance: "assistant-drafted"
source_id: "A-014"
toc: true
---

# A brain model could not tell us whether a Lenia creature looked alive

_4–8 May 2026 · Negative methodological result. We verified the video-to-model path, but no interpretable real-specimen comparison was completed._

Flow Lenia organisms were already described by sixteen measurements of their shape and motion. We wondered whether a model trained to predict human brain activity from video could add something those measurements missed. If videos of different synthetic organisms produced different responses in regions associated with biological motion and visual form, perhaps that response could become a new coordinate in the morphospace.

The model was TRIBE v2. Before showing it any Lenia creatures, we gave it six deliberately unusual videos and confirmed that its predictions did not collapse to a constant output. That was a useful engineering check, but it established only that the model responded to unfamiliar images. It did not establish what those responses meant.

The more revealing control was a synthetic point-light walker, chosen because biological motion should have made it an easy positive example. The predicted response in the superior temporal sulcus moved in the wrong direction. We could have searched for a different control until the expected pattern appeared, but that would have left the central interpretation untouched and untested. Instead, we stopped calling the output a measure of “lifelikeness.” TRIBE predicts fMRI responses; it does not report whether a viewer thinks an object is alive.

A narrower use remained possible. We could treat each predicted regional response as an unnamed descriptive score, compare it across Lenia videos, and keep it only if it supplied information not already present in the sixteen existing measurements. A fake-client run proved that the plumbing worked from video through model output, specimen lookup and correlation. It linked five specimens and produced the expected matrix, but five fabricated rows cannot support a scientific conclusion.

The first real comparison then ran into a provenance problem. The morphospace database identified specimens, while the existing video library identified scenes and archive cells. There was no dependable mapping between them. A response could not be joined back to the exact organism whose geometry and motion had been measured. The correct next step was therefore not a larger model run, but a replay-and-render pipeline that generated each video from a chosen specimen ID.

This investigation produced no brain-based score of synthetic life. Its useful result was deciding not to manufacture one from a responsive but unvalidated model. An appealing anatomical label could not rescue the failed control. Any future use of TRIBE would need specimen-level lineage, a defensible comparison set and an interpretation no stronger than the experiment warrants.
