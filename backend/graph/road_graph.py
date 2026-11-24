import osmnx as ox
from pathlib import Path
from backend.config import get_config

ROAD_PATH = Path("data/processed/road_drive.graphml")
PAD = 0.03  # отступ вокруг bbox, чтобы пути у края не обрезались

if __name__ == "__main__":
    x0, y0, x1, y1 = get_config().test_bbox
    G = ox.graph_from_bbox(bbox=(x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD), network_type="all")
    ROAD_PATH.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, ROAD_PATH)
    print(f"Узлов: {len(G.nodes)}, рёбер: {len(G.edges)}")