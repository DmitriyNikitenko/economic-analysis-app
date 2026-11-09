from dataclasses import dataclass, field

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
    capacities: list[Capacity] = field(default_factory=list)  # по одной записи на домен


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


@dataclass
class Metric:
    scope: str  # district или region
    district_id: str | None 
    domain: str
    node_count: int
    edge_count: int
    avg_degree: float
    low_data: bool