# Структуры данных, которые модуль чтения отдаёт генератору GeoJSON
from dataclasses import dataclass, field

@dataclass(frozen=True)
class DomainRole:
    domain: str          # money, labor, goods
    role: str            # supply или demand
    rule: str | None     # по какому правилу присвоена

@dataclass
class OsmObject:
    osm_type: str                    # node, way или relation
    osm_id: int
    tags: dict[str, str]             # исходные теги OSM
    geometry: dict                   # GeoJSON-геометрия, координаты [долгота, широта]
    kind: str | None = None          # bank, settlement, employer, None
    roles: list[DomainRole] = field(default_factory=list)