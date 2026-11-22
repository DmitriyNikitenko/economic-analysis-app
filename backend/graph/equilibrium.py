import uuid
from typing import Sequence

import numpy as np
from scipy.optimize import minimize

from backend.config import Config
from backend.economy.models import Edge, Subject
from backend.graph.engine import distance

FLOW_EPS = 1e-7


def solve_flows(
    supply_caps: np.ndarray,
    demand_caps: np.ndarray,
    sup_idx: np.ndarray,
    dem_idx: np.ndarray,
    transport_costs: np.ndarray,
    max_price: float = 2.0,
    power: int = 4,
) -> np.ndarray:
    # Находит равновесные потоки x_ij >= 0 для кандидатских пар (поставщик, потребитель)
    n_pairs = len(transport_costs)
    if n_pairs == 0:
        return np.empty(0, dtype=float)

    n_sup = len(supply_caps)
    n_dem = len(demand_caps)

    def obj_and_grad(x: np.ndarray) -> tuple[float, np.ndarray]:
        s = np.bincount(sup_idx, weights=x, minlength=n_sup)
        d = np.bincount(dem_idx, weights=x, minlength=n_dem)

        p_marginal = (s / supply_caps) ** power
        r_drop = (d / demand_caps) ** power

        cost_sup = np.sum(s * p_marginal) / (power + 1)
        cost_dem = np.sum(d * r_drop) / (power + 1)
        cost_flow = np.dot(transport_costs - max_price, x)

        loss = float(cost_sup + cost_dem + cost_flow)
        grad = p_marginal[sup_idx] + r_drop[dem_idx] + transport_costs - max_price
        return loss, grad

    res = minimize(
        obj_and_grad,
        x0=np.zeros(n_pairs, dtype=float),
        method="L-BFGS-B",
        jac=True,
        bounds=[(0.0, None)] * n_pairs,
        options={"ftol": 1e-12, "gtol": 1e-8},
    )
    return np.maximum(res.x, 0.0)


def build_equilibrium_edges(subjects: Sequence[Subject], config: Config) -> list[Edge]:
    # Строит направленный граф (demand -> supply) на основе пространственного равновесия цен
    edges: list[Edge] = []

    for domain_id in config.enabled_domains:
        dom_cfg = config.domains[domain_id]
        radius = dom_cfg.radius_km
        if radius <= 0:
            continue

        graph_cfg = getattr(config, "graph", None)
        max_price = getattr(dom_cfg, "max_price", getattr(graph_cfg, "max_price", 2.0))
        transport_price = getattr(dom_cfg, "transport_price", getattr(graph_cfg, "transport_price", 1.0))
        power = getattr(dom_cfg, "power", getattr(graph_cfg, "power", 4))

        demands: list[tuple[Subject, float]] = []
        supplies: list[tuple[Subject, float]] = []

        for s in subjects:
            for c in s.capacities:
                if c.domain == domain_id and c.capacity > 0:
                    if c.role == "demand":
                        demands.append((s, c.capacity))
                    elif c.role == "supply":
                        supplies.append((s, c.capacity))

        if not demands or not supplies:
            continue

        sup_indices: list[int] = []
        dem_indices: list[int] = []
        dists: list[float] = []

        for j, (dem_node, _) in enumerate(demands):
            for i, (sup_node, _) in enumerate(supplies):
                dist = distance(dem_node.lon, dem_node.lat, sup_node.lon, sup_node.lat)
                if dist <= radius:
                    sup_indices.append(i)
                    dem_indices.append(j)
                    dists.append(dist)

        if not dists:
            continue

        dist_arr = np.array(dists, dtype=float)
        transport_costs = transport_price * (dist_arr / radius)

        flows = solve_flows(
            supply_caps=np.array([cap for _, cap in supplies], dtype=float),
            demand_caps=np.array([cap for _, cap in demands], dtype=float),
            sup_idx=np.array(sup_indices, dtype=int),
            dem_idx=np.array(dem_indices, dtype=int),
            transport_costs=transport_costs,
            max_price=max_price,
            power=power,
        )

        # Группируем ненулевые потоки по потребителям и нормируем вес (weight = x_ij / d_j)
        by_demand: dict[int, list[tuple[int, float, float]]] = {}
        for idx, flow in enumerate(flows):
            if flow > FLOW_EPS:
                j = dem_indices[idx]
                i = sup_indices[idx]
                by_demand.setdefault(j, []).append((i, dists[idx], float(flow)))

        for j, items in by_demand.items():
            total_d = sum(flow for _, _, flow in items)
            if total_d <= 0:
                continue

            dem_node = demands[j][0]
            for i, dist, flow in items:
                sup_node = supplies[i][0]
                edges.append(
                    Edge(
                        id=str(uuid.uuid4()),
                        domain=domain_id,
                        from_id=dem_node.id,
                        to_id=sup_node.id,
                        distance_km=round(dist, 3),
                        weight=flow / total_d,
                    )
                )

    return edges