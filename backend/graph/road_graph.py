import osmnx as ox
from pathlib import Path
from backend.config import get_config

ROAD_PATH = Path("data/processed/road_drive.graphml")
PAD = 0.03  # отступ вокруг bbox, чтобы пути у края не обрезались

def get_road_bbox(cfg):
    """
    Возвращает bbox для дорожного графа.

    Если в конфиге задан test_bbox — использует его с отступом.
    Если test_bbox отсутствует — возвращает None,
    чтобы загрузить граф для всей области.
    """

    if cfg.test_bbox is None:
        return None

    x0, y0, x1, y1 = cfg.test_bbox

    return (
        x0 - PAD,
        y0 - PAD,
        x1 + PAD,
        y1 + PAD,
    )

def build_road_graph():
    """
    Загружает автомобильную дорожную сеть OSM
    и сохраняет её в GraphML.
    """

    cfg = get_config()

    # Не загружаем повторно, если граф уже существует
    if ROAD_PATH.exists():
        print(f"Дорожный граф уже существует: {ROAD_PATH}")
        return ox.load_graphml(ROAD_PATH)

    bbox = get_road_bbox(cfg)

    if bbox is not None:
        G = ox.graph_from_bbox(
            bbox=bbox,
            network_type="all",
            simplify=True,
        )
    else:
        G = ox.graph_from_place(
            cfg.place,
            network_type="all",
            simplify=True,
        )

    ROAD_PATH.parent.mkdir(parents=True, exist_ok=True)
    ox.save_graphml(G, ROAD_PATH)

    print(f"Дорожный граф сохранён: {ROAD_PATH}")

    return G

if __name__ == "__main__":
    build_road_graph()