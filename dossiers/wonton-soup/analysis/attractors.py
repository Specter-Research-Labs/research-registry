from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform


@dataclass
class AttractorCluster:
    cluster_id: int
    members: list[str]
    representative: str
    internal_ged_avg: float
    internal_ged_max: float

    def serialize(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "members": self.members,
            "representative": self.representative,
            "internal_ged_avg": self.internal_ged_avg,
            "internal_ged_max": self.internal_ged_max,
        }


@dataclass
class AttractorAnalysis:
    theorem_name: str
    n_clusters: int
    clusters: list[AttractorCluster]
    inter_cluster_distances: dict[tuple[int, int], float]

    def serialize(self) -> dict:
        return {
            "theorem_name": self.theorem_name,
            "n_clusters": self.n_clusters,
            "clusters": [c.serialize() for c in self.clusters],
            "inter_cluster_distances": {
                f"{k[0]}-{k[1]}": v for k, v in self.inter_cluster_distances.items()
            },
        }


def cluster_proof_structures(
    ged_matrix: dict[str, dict[str, float | None]],
    distance_threshold: float = 3.0,
    theorem_name: str = "",
    missing_distance: float = 100.0,
) -> AttractorAnalysis:
    variants = sorted(ged_matrix.keys())
    n = len(variants)

    if n < 2:
        if n == 1:
            return AttractorAnalysis(
                theorem_name=theorem_name,
                n_clusters=1,
                clusters=[
                    AttractorCluster(
                        cluster_id=1,
                        members=variants,
                        representative=variants[0],
                        internal_ged_avg=0.0,
                        internal_ged_max=0.0,
                    )
                ],
                inter_cluster_distances={},
            )
        return AttractorAnalysis(
            theorem_name=theorem_name,
            n_clusters=0,
            clusters=[],
            inter_cluster_distances={},
        )

    dist_matrix = np.zeros((n, n))
    for i, v1 in enumerate(variants):
        for j in range(i + 1, n):
            d1 = ged_matrix.get(v1, {}).get(variants[j])
            d2 = ged_matrix.get(variants[j], {}).get(v1)
            if d1 is None and d2 is None:
                d = missing_distance
            elif d1 is None:
                d = d2
            elif d2 is None:
                d = d1
            else:
                d = (d1 + d2) / 2 if d1 != d2 else d1
            dist_matrix[i, j] = d
            dist_matrix[j, i] = d

    condensed = squareform(dist_matrix)
    linkage_matrix = linkage(condensed, method="average")
    cluster_labels = fcluster(linkage_matrix, t=distance_threshold, criterion="distance")

    clusters_dict: dict[int, list[str]] = {}
    for variant, label in zip(variants, cluster_labels):
        label_int = int(label)
        if label_int not in clusters_dict:
            clusters_dict[label_int] = []
        clusters_dict[label_int].append(variant)

    clusters = []
    for cluster_id, members in sorted(clusters_dict.items()):
        if len(members) == 1:
            representative = members[0]
            internal_avg = 0.0
            internal_max = 0.0
        else:
            member_indices = [variants.index(m) for m in members]
            internal_dists = []
            for i in member_indices:
                for j in member_indices:
                    if i < j:
                        internal_dists.append(dist_matrix[i, j])
            internal_avg = float(np.mean(internal_dists))
            internal_max = float(np.max(internal_dists))

            best_rep = None
            best_sum = float("inf")
            for m in members:
                mi = variants.index(m)
                dist_sum = sum(dist_matrix[mi, variants.index(other)] for other in members)
                if dist_sum < best_sum:
                    best_sum = dist_sum
                    best_rep = m
            representative = best_rep or members[0]

        clusters.append(
            AttractorCluster(
                cluster_id=cluster_id,
                members=members,
                representative=representative,
                internal_ged_avg=round(internal_avg, 3),
                internal_ged_max=round(internal_max, 3),
            )
        )

    inter_cluster: dict[tuple[int, int], float] = {}
    for c1 in clusters:
        for c2 in clusters:
            if c1.cluster_id < c2.cluster_id:
                dists = []
                for m1 in c1.members:
                    for m2 in c2.members:
                        dists.append(dist_matrix[variants.index(m1), variants.index(m2)])
                inter_cluster[(c1.cluster_id, c2.cluster_id)] = round(float(np.mean(dists)), 3)

    return AttractorAnalysis(
        theorem_name=theorem_name,
        n_clusters=len(clusters),
        clusters=clusters,
        inter_cluster_distances=inter_cluster,
    )
