# Расчёт метрик графа: число узлов, рёбер и средняя степень по районам и региону
# Модуль не знает про базу данных: на вход получает списки, на выход отдаёт строки метрик
from collections import Counter

from backend.economy.models import Edge, Metric, Subject

ALL = "all"


class _Stats:
    # Накопленные счётчики одного домена. district: None здесь не район, а узлы без района
    def __init__(self) -> None:
        self.nodes_by_district: Counter = Counter()  # район -> число узлов
        self.degree_by_district: Counter = Counter()  # район -> сумма степеней его узлов
        self.edges_by_district: Counter = Counter()  # район -> число рёбер, затрагивающих район
        self.node_count = 0
        self.edge_count = 0


def compute_metrics(
    subjects: list[Subject],
    edges: list[Edge],
    district_ids: list[str],
    domains: list[str],
    low_data_threshold: int,
) -> list[Metric]:
    # Возвращает строки для таблицы metrics: сначала регион, потом районы
    # Для каждой области считаются отдельные домены из domains и общий расчёт
    district_of = {s.id: s.district_id for s in subjects}
    keys = [*domains, ALL]
    stats = {key: _Stats() for key in keys}
    participants: dict[str, set[str]] = {key: set() for key in keys}  # домен -> id его узлов

    # Узел это пара (субъект, домен); в ALL один субъект считается один раз
    for s in subjects:
        for c in s.capacities:
            if c.domain in stats:
                participants[c.domain].add(s.id)
                participants[ALL].add(s.id)
    for key in keys:
        for subject_id in participants[key]:
            stats[key].nodes_by_district[district_of[subject_id]] += 1
        stats[key].node_count = len(participants[key])

    # Один проход по всем рёбрам: каждое ребро учитывается в своём домене и в ALL
    for e in edges:
        for end in (e.from_id, e.to_id):
            if end not in participants[ALL] or (e.domain in stats and end not in participants[e.domain]):
                raise ValueError(
                    f"Ребро {e.from_id} -> {e.to_id} (домен {e.domain}) ведёт к узлу, "
                    f"которого нет среди участников домена")
        # ребро затрагивает район, если хотя бы один его конец в нём; сам район считаем один раз
        touched = {district_of[e.from_id], district_of[e.to_id]}
        for key in ((e.domain, ALL) if e.domain in stats else (ALL,)):
            st = stats[key]
            st.edge_count += 1
            st.degree_by_district[district_of[e.from_id]] += 1
            st.degree_by_district[district_of[e.to_id]] += 1
            for district in touched:
                st.edges_by_district[district] += 1

    rows: list[Metric] = []
    for scope, district_id in [("region", None)] + [("district", d) for d in district_ids]:
        for key in keys:
            rows.append(_make_row(scope, district_id, key, stats[key], low_data_threshold))
    return rows


def _make_row(scope: str, district_id: str | None, domain: str, st: _Stats, threshold: int) -> Metric:
    if scope == "region":
        node_count, edge_count = st.node_count, st.edge_count
        degree_sum = 2 * st.edge_count  # каждое ребро входит в степень обоих концов
    else:
        node_count = st.nodes_by_district[district_id]
        edge_count = st.edges_by_district[district_id]
        degree_sum = st.degree_by_district[district_id]
    return Metric(
        scope=scope,
        district_id=district_id,
        domain=domain,
        node_count=node_count,
        edge_count=edge_count,
        avg_degree=degree_sum / node_count if node_count else 0.0,
        low_data=node_count < threshold,
    )