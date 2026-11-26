from typing import Sequence
import numpy as np

from backend.economy.models import Subject, Edge
from backend.config import Config
from backend.graph.distances import road_pairs

MIN_VISIBLE_DISTANCE = 0.05


def build_gravity_edges(subjects: Sequence[Subject], config: Config) -> list[Edge]:
    # Строит направленный граф по гравитационной модели
    edges: list[Edge] = []

    for domain_id in config.enabled_domains:
        dom_cfg = config.domains[domain_id]
        radius = dom_cfg.radius_km
        beta = dom_cfg.beta

        demands = []
        supplies = []

        # Разделяем спрос и предложение
        for s in subjects:
            for c in s.capacities:
                if c.domain == domain_id:
                    if c.role == "demand":
                        demands.append(s)
                    elif c.role == "supply" and c.capacity > 0:
                        supplies.append((s, c.capacity))

        if not demands or not supplies:
            continue

        dem_ll = np.array([[s.lon, s.lat] for s in demands])
        sup_ll = np.array([[s.lon, s.lat] for s, _ in supplies])
        sup_cap = np.array([cap for _, cap in supplies])

        d_idx, s_idx, dist = road_pairs(dem_ll, sup_ll, radius)

        if len(dist) == 0:
            continue

        raw = sup_cap[s_idx] * np.maximum(dist, MIN_VISIBLE_DISTANCE) ** -beta
        weights = raw / np.bincount(d_idx, weights=raw, minlength=len(demands))[d_idx]

        dem_ids = [s.id for s in demands]
        sup_ids = [s.id for s, _ in supplies]

        for d, s, dist_km, w in zip(
            d_idx.tolist(),
            s_idx.tolist(),
            np.round(dist, 3).tolist(),
            weights.tolist(),
        ):
            from_id = dem_ids[d]
            to_id = sup_ids[s]
            edges.append(Edge(
                id=f"{domain_id}:{from_id}:{to_id}",
                domain=domain_id,
                from_id=from_id,
                to_id=to_id,
                distance_km=dist_km,
                weight=w,
            ))

    return edges