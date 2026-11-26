import uuid
from typing import Sequence

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from backend.config import Config
from backend.economy.models import Edge, Subject
from backend.graph.distances import road_pairs

FLOW_EPS = 1e-7
K_CANDIDATES = 30

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

    # print(f"L-BFGS-B: success={res.success}, итераций={res.nit}, {res.message}")

    return np.maximum(res.x, 0.0)

def kkt_report(x, d_idx, s_idx, dist, sup_caps, dem_caps, radius, a, tp, power, in_k, name=""):
    s = np.bincount(s_idx, weights=x, minlength=len(sup_caps))
    d = np.bincount(d_idx, weights=x, minlength=len(dem_caps))
    rc = (s[s_idx] / sup_caps[s_idx]) ** power + (d[d_idx] / dem_caps[d_idx]) ** power \
         + tp * dist / radius - a
    act = x > FLOW_EPS
    bad = ~act & (rc < -0.01)
    ls, ld = s / sup_caps, d / dem_caps
    print(f"[{name}] пар {len(x):,}, с потоком {act.sum():,}")
    print(f"  загрузка поставщиков s/pc: медиана {np.median(ls):.2f}, p95 {np.percentile(ls, 95):.2f}, max {ls.max():.2f}")
    print(f"  насыщение спроса d/cc:     медиана {np.median(ld):.2f}, p95 {np.percentile(ld, 95):.2f}, max {ld.max():.2f}")
    if act.any():
        print(f"  макс |rc| у активных пар: {np.abs(rc[act]).max():.4f} (должно быть ~0)")
    print(f"  выгодные, но неиспользуемые пары: {bad.sum():,} (из них вне K-отбора {(bad & ~in_k).sum():,})")

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

        dem_ll = np.array([[s.lon, s.lat] for s, _ in demands])
        sup_ll = np.array([[s.lon, s.lat] for s, _ in supplies])

        d_idx, s_idx, dist = road_pairs(dem_ll, sup_ll, radius)
        if len(dist) == 0:
            continue

        # для каждого потребителя оставляем K_CANDIDATES ближайших по дороге поставщиков
        df = pd.DataFrame({"d": d_idx, "s": s_idx, "dist": dist})
        # df = df.sort_values("dist").groupby("d").head(K_CANDIDATES)
        by_d = df.sort_values("dist").groupby("d").head(K_CANDIDATES)
        by_s = df.sort_values("dist").groupby("s").head(K_CANDIDATES)
        df = pd.concat([by_d, by_s]).drop_duplicates(["d", "s"])
        pos = df.index.to_numpy()

        dem_indices = df["d"].to_numpy(dtype=int)
        sup_indices = df["s"].to_numpy(dtype=int)
        dist_arr = df["dist"].to_numpy(dtype=float)

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

        by_demand: dict[int, list[tuple[int, float, float]]] = {}
        for idx, flow in enumerate(flows):
            if flow > FLOW_EPS:
                j = int(dem_indices[idx])
                i = int(sup_indices[idx])
                by_demand.setdefault(j, []).append((i, float(dist_arr[idx]), float(flow)))

        for j, items in by_demand.items():
            items.sort(key=lambda t: t[2], reverse=True)   # самые сильные потоки первыми
            total_d = sum(flow for _, _, flow in items)     # нормировка после отбора, сумма весов = 1
            if total_d <= 0:
                continue

            dem_node = demands[j][0]
            for i, dist, flow in items:
                sup_node = supplies[i][0]
                edges.append(
                    Edge(
                        id=f"{domain_id}:{dem_node.id}:{sup_node.id}",
                        domain=domain_id,
                        from_id=dem_node.id,
                        to_id=sup_node.id,
                        distance_km=round(dist, 3),
                        weight=flow / total_d,
                    )
                )

    return edges