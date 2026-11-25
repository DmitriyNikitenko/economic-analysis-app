from collections import defaultdict
from functools import lru_cache

import networkx as nx
import numpy as np
import osmnx as ox
from tqdm import tqdm

from backend.graph.road_graph import ROAD_PATH

@lru_cache(maxsize=1)
def _graph():
    return ox.convert.to_undirected(ox.load_graphml(ROAD_PATH))


def road_pairs(dem_ll, sup_ll, radius_km):
    """Возвращает (индекс потребителя, индекс поставщика, дорожное расстояние в км)."""
    G = _graph()
    dem_nodes = ox.distance.nearest_nodes(G, dem_ll[:, 0], dem_ll[:, 1])
    sup_nodes = ox.distance.nearest_nodes(G, sup_ll[:, 0], sup_ll[:, 1])

    # Дейкстру запускаем из той стороны, где объектов меньше
    sup_is_src = len(sup_nodes) <= len(dem_nodes)
    src, dst = (sup_nodes, dem_nodes) if sup_is_src else (dem_nodes, sup_nodes)

    dst_by_node = defaultdict(list)
    for k, n in enumerate(dst):
        dst_by_node[n].append(k)

    rows = []
    for a, node in enumerate(tqdm(src, desc="дорожные расстояния")):
        reach = nx.single_source_dijkstra_path_length(
            G, node, cutoff=radius_km * 1000, weight="length")
        for n2, length in reach.items():
            for b in dst_by_node.get(n2, ()):
                rows.append((a, b, length / 1000))

    if not rows:
        return np.empty(0, int), np.empty(0, int), np.empty(0)
    a, b, d = (np.array(x) for x in zip(*rows))
    return (b, a, d) if sup_is_src else (a, b, d)