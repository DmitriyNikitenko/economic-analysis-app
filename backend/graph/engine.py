import math
import uuid
from typing import Sequence
import numpy as np
import pandas as pd

from backend.economy.models import Subject, Edge
from backend.config import Config
from backend.graph.distances import road_pairs

MIN_VISIBLE_DISTANCE = 0.05

def distance(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    # Вычисляет расстояние между двумя точками на сфере (Земле) в километрах
    r = 6371.0

    lon1_rad = math.radians(lon1)
    lon2_rad = math.radians(lon2)
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    x1, x2 = math.cos(lon1_rad) * math.cos(lat1_rad), math.cos(lon2_rad) * math.cos(lat2_rad)
    y1, y2 = math.cos(lat1_rad) * math.sin(lon1_rad), math.cos(lat2_rad) * math.sin(lon2_rad)
    z1, z2 = math.sin(lat1_rad), math.sin(lat2_rad)

    c = x1*x2 + y1*y2 + z1*z2
    c_safe = max(-1.0, min(1.0, c))
    m = math.acos(c_safe)
    return r * m


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
                    elif c.role == "supply":
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

        df = pd.DataFrame({
            "d": d_idx,
            "s": s_idx,
            "dist": dist,
            "raw": raw,
        })

        df["w"] = (
            df["raw"] /
            df.groupby("d")["raw"].transform("sum")
        )

        for r in df.itertuples():
            edges.append(Edge(
                id=f"{domain_id}:{demands[r.d].id}:{supplies[r.s][0].id}",
                domain=domain_id,
                from_id=demands[r.d].id,
                to_id=supplies[r.s][0].id,
                distance_km=round(float(r.dist), 3),
                weight=float(r.w),
            ))

        # # Поиск связей для каждого узла спроса
        # for demand_node in demands:
        #     candidates = []
        #     sum_raw_weights = 0.0

        #     for supply_node, supply_capacity in supplies:
        #         dist = distance(
        #             demand_node.lon, demand_node.lat,
        #             supply_node.lon, supply_node.lat
        #         )

        #         if dist <= radius:
        #             # Защита от деления на ноль, если координаты совпали
        #             safe_dist = max(dist, MIN_VISIBLE_DISTANCE)

        #             # Гравитационная формула
        #             raw_weight = supply_capacity * (safe_dist ** -beta)

        #             candidates.append((supply_node.id, dist, raw_weight))
        #             sum_raw_weights += raw_weight

        #     # Нормализация (сумма весов исходящих рёбер = 1.0)
        #     if sum_raw_weights > 0:
        #         for supply_id, dist, raw_w in candidates:
        #             normalized_weight = raw_w / sum_raw_weights

        #             edges.append(Edge(
        #                 id=str(uuid.uuid4()),
        #                 domain=domain_id,
        #                 from_id=demand_node.id,
        #                 to_id=supply_id,
        #                 distance_km=round(dist, 3),
        #                 weight=normalized_weight
        #             ))

    return edges