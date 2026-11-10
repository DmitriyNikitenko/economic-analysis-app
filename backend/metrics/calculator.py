# Расчёт метрик графа: число узлов, рёбер и средняя степень по районам и региону
# Модуль не знает про базу данных: на вход получает списки, на выход отдаёт строки метрик
from collections import Counter
from backend.economy.models import Edge, Metric, Subject

ALL = "all"

def compute_metrics(
    subjects: list[Subject],
    edges: list[Edge],
    district_ids: list[str],
    domains: list[str],
    low_data_threshold: int,
) -> list[Metric]:
    # Возвращает строки для таблицы metrics: сначала регион, потом районы
    # Для каждой области считаются отдельные домены из domains и общий расчёт 
    edges = [e for e in edges if e.domain in domains]
    # Узел это пара (субъект, домен)
    nodes = {(s.id, c.domain) for s in subjects for c in s.capacities if c.domain in domains}
    district_of = {s.id: s.district_id for s in subjects}

    rows: list[Metric] = []
    for scope, district_id in [("region", None)] + [("district", d) for d in district_ids]:
        for domain in [*domains, ALL]:
            rows.append(_compute_row(
                scope, district_id, domain, nodes, edges, district_of, low_data_threshold))
    return rows


def _compute_row(
    scope: str,
    district_id: str | None,
    domain: str,
    nodes: set[tuple[str, str]],
    edges: list[Edge],
    district_of: dict[str, str | None],
    threshold: int,
) -> Metric:
    # Узлы и рёбра выбранного домена
    domain_nodes = {subject_id for subject_id, d in nodes if domain == ALL or d == domain}
    domain_edges = [e for e in edges if domain == ALL or e.domain == domain]

    # Степень считаем по всем рёбрам домена: ребро входит в степень обоих концов
    degree: Counter[str] = Counter()
    for e in domain_edges:
        for end in (e.from_id, e.to_id):
            if end not in domain_nodes:
                raise ValueError(
                    f"Ребро {e.from_id} -> {e.to_id} ведёт к узлу, "
                    f"которого нет среди участников домена")
            degree[end] += 1

    # Выбираем узлы области
    if scope == "region":
        area_nodes = domain_nodes
    else:
        area_nodes = {s for s in domain_nodes if district_of[s] == district_id}

    # Ребро принадлежит области, если хотя бы один его конец лежит в ней
    area_edge_count = sum(
        1 for e in domain_edges if e.from_id in area_nodes or e.to_id in area_nodes)

    node_count = len(area_nodes)
    avg_degree = sum(degree[s] for s in area_nodes) / node_count if node_count else 0.0

    return Metric(
        scope=scope,
        district_id=district_id,
        domain=domain,
        node_count=node_count,
        edge_count=area_edge_count,
        avg_degree=avg_degree,
        low_data=node_count < threshold,
    )