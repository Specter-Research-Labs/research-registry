# Physics

## Purpose

In this dossier, "physics" means space-time properties of pattern persistence under the Flow Lenia update.

## Visual Anchors from This Corpus

Translational regime example (`crossmap`, seed `0`):

![Crossmap translational exemplar](./assets/examples/crossmap-magma.webp)

Constrained/meandering regime example (`nnea`, seed `0`):

![NNEA meandering exemplar](./assets/examples/nnea-magma.webp)

## Terms

- `persist`: a pattern remains recognizable across many update steps.
- `invariant`: a pattern identity survives controlled changes (for example small perturbations).
- `perturbation`: a deliberate small change to state or parameters.
- `regime`: a recurring dynamical mode, such as fast translation vs low-displacement meandering.

## What We Measure Today

Operationally, the current corpus separates regimes with trajectory statistics:

- `center_velocity`: mean translational speed of the center of mass.
- `path_length / displacement`: near `1` implies straight transport; larger values imply meander/looping motion.

Current anchored examples:

- `crossmap-128-local-20260227-153007`, seed `0`: `center_velocity=0.01027`, `path/displacement=1.0026`.
- `nnea-128-local-20260227-153006`, seed `0`: `center_velocity=0.00009`, `path/displacement=9.1293`.

## What Is Still Conceptual

Prior Lenia literature mentions invariance under scale/transform/deformation. In this dossier, those are research goals, not yet formalized benchmark suites.

Physics is currently partially operationalized:

- motion regime separation: implemented,
- full invariance test battery (scale/flip/rotate/deformation): not implemented.

## Related Docs

- runtime implementation map: `../internals/FlowLeniaImplementationMap.md`
- artifact contract: `../contracts/ArtifactLayout.md`
- morphology interpretation: `Morphology.md`
