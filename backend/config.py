# Чтение общего конфига config/region.yaml

from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1] # корень репозитория
CONFIG_PATH = ROOT / "config" / "region.yaml"

DOMAINS = ("money", "labor", "goods")
LAYERS = ("objects", "roles", "edges") 

class ConfigError(ValueError):
    pass

@dataclass(frozen=True)
class DomainConfig:
    id: str
    label: str
    enabled: bool
    radius_km: float
    beta: float

@dataclass(frozen=True)
class LayerConfig:
    id: str
    label: str
    enabled: bool

@dataclass(frozen=True)
class Paths:
    db: Path
    raw: Path
    classified: Path
    rules: Path
    frontend_data: Path

@dataclass(frozen=True)
class Config:
    region_id: str
    region_name: str
    crs: str
    place: str | None
    test_bbox: tuple[float, float, float, float]
    paths: Paths
    low_data_threshold: int
    domains: dict[str, DomainConfig]
    layers: tuple[LayerConfig, ...]
    show_all_domains_option: bool

    @property
    def enabled_domains(self) -> list[str]:
        return [d.id for d in self.domains.values() if d.enabled]

def _require(data: dict, key: str, where: str):
    if key not in data:
        raise ConfigError(f"{where}: нет обязательного поля '{key}'")
    return data[key]

def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path

def _parse_domain(domain_id: str, raw: dict) -> DomainConfig:
    domain = f"domains.{domain_id}"
    radius = float(_require(raw, "radius_km", domain))
    beta = float(_require(raw, "beta", domain))
    if radius <= 0:
        raise ConfigError(f"{domain}.radius_km должен быть > 0, сейчас {radius}")
    if beta <= 0:
        raise ConfigError(f"{domain}.beta должен быть > 0, сейчас {beta}")
    return DomainConfig(
        id=domain_id,
        label=str(_require(raw, "label", domain)),
        enabled=bool(_require(raw, "enabled", domain)),
        radius_km=radius,
        beta=beta,
    )


def load_config(path: str | Path = CONFIG_PATH) -> Config:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: ожидается YAML-словарь")

    region = _require(data, "region", "конфиг")
    raw_paths = _require(data, "paths", "конфиг")
    raw_domains = _require(data, "domains", "конфиг")

    unknown = set(raw_domains) - set(DOMAINS)
    missing = set(DOMAINS) - set(raw_domains)
    if unknown:
        raise ConfigError(f"domains: неизвестные домены {sorted(unknown)}, допустимы {list(DOMAINS)}")
    if missing:
        raise ConfigError(f"domains: не описаны домены {sorted(missing)}")

    layers = []
    for raw in _require(data, "layers", "конфиг"):
        layer_id = _require(raw, "id", "layers[]")
        if layer_id not in LAYERS:
            raise ConfigError(f"layers: неизвестный слой '{layer_id}', допустимы {list(LAYERS)}")
        layers.append(LayerConfig(layer_id, str(_require(raw, "label", "layers[]")), bool(raw.get("enabled", True))))

    bbox = tuple(float(v) for v in _require(region, "test_bbox", "region"))
    if len(bbox) != 4 or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        raise ConfigError(f"region.test_bbox: ожидается [min_lon, min_lat, max_lon, max_lat], сейчас {list(bbox)}")

    return Config(
        region_id=str(_require(region, "id", "region")),
        region_name=str(_require(region, "name", "region")),
        crs=str(region.get("crs", "EPSG:4326")),
        place=region.get("place") or None,
        test_bbox=bbox,
        paths=Paths(**{key: _path(_require(raw_paths, key, "paths"))
                       for key in ("db", "raw", "classified", "rules", "frontend_data")}),
        low_data_threshold=int(_require(data, "low_data_threshold", "конфиг")),
        domains={d: _parse_domain(d, raw_domains[d]) for d in DOMAINS},
        layers=tuple(layers),
        show_all_domains_option=bool(data.get("show_all_domains_option", True)),
    )


@lru_cache(maxsize=1)
def get_config() -> Config:
    return load_config() # конфиг читается один раз за запуск