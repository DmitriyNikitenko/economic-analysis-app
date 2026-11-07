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

# Модели таблиц графа
@dataclass
class Capacity:
    domain: str
    role: str
    capacity: float


@dataclass
class Subject:
    id: str
    name: str | None
    kind: str
    lon: float
    lat: float
    address: str | None
    district_id: str | None
    capacities: list[Capacity] = field(default_factory=list)   # по одной записи на домен


@dataclass
class Edge:
    id: str
    domain: str
    from_id: str    # субъект со стороны спроса
    to_id: str      # субъект со стороны предложения
    distance_km: float
    weight: float   


@dataclass
class District:
    id: str
    name: str
    geom: dict  # GeoJSON-полигон границы