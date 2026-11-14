import math
from typing import Sequence
from backend.economy.models import Subject, Edge, District
from shapely.geometry import shape, Point


def validate_export_data(
        subjects: Sequence[Subject],
        edges: Sequence[Edge],
        districts: Sequence[District],
        enabled_domains: list[str]
) -> None:
    active_domains = set(enabled_domains)

    subject_ids = set()
    district_ids = set()
    edge_ids = set()

    for d in districts:
        if d.id in district_ids:
            raise ValueError(f"Duplicate district ID '{d.id}'")
        district_ids.add(d.id)

    subject_capacities = {}
    for s in subjects:
        if s.id in subject_ids:
            raise ValueError(f"Duplicate subject ID '{s.id}'")
        if s.district_id and s.district_id not in district_ids:
            raise ValueError(f"Entity '{s.id}' references an unknown district '{s.district_id}'")

        subject_ids.add(s.id)
        subject_capacities[s.id] = {}

        for c in s.capacities:
            if c.domain not in active_domains:
                raise ValueError(f"Entity '{s.id}' contains a disabled domain '{c.domain}'")
            if c.capacity <= 0:
                raise ValueError(f"Subject '{s.id}' has capacity ({c.capacity}) <= 0 for '{c.domain}'")

            subject_capacities[s.id][c.domain] = c.role

    outgoing_stats = {}
    for e in edges:
        if e.id in edge_ids:
            raise ValueError(f"Duplicate edge ID '{e.id}'")
        edge_ids.add(e.id)

        if e.from_id not in subject_ids or e.to_id not in subject_ids:
            raise ValueError(
                f"Edge '{e.id}' references a non-existent node (from={e.from_id}, to={e.to_id})")

        if e.domain not in active_domains:
            raise ValueError(f"Edge '{e.id}' contains a disabled domain '{e.domain}'")

        if not (0 < e.weight <= 1):
            raise ValueError(f"Weight of edge '{e.id}' ({e.weight}) is outside the range (0, 1]")

        from_role = subject_capacities[e.from_id].get(e.domain)
        to_role = subject_capacities[e.to_id].get(e.domain)

        if from_role != "demand":
            raise ValueError(
                f"'from_id' '{e.from_id}' in edge '{e.id}' is not 'demand' (actual value: {from_role})")
        if to_role != "supply":
            raise ValueError(
                f"'to_id' '{e.to_id}' in edge '{e.id}' is not 'supply' (actual value: {to_role})")

        out_key = (e.from_id, e.domain)
        if out_key not in outgoing_stats:
            outgoing_stats[out_key] = {"weight": 0.0, "count": 0}
        outgoing_stats[out_key]["weight"] += e.weight
        outgoing_stats[out_key]["count"] += 1

    for s in subjects:
        for c in s.capacities:
            if c.role == "demand":
                out_key = (s.id, c.domain)
                stats = outgoing_stats.get(out_key, {"weight": 0.0, "count": 0})

                if stats["count"] > 0 and not math.isclose(stats["weight"], 1.0, rel_tol=1e-9, abs_tol=1e-9):
                    raise ValueError(
                        f"For '{s.id}' and '{c.domain}', the sum of outgoing weights = {stats['weight']}; 1.0 was expected.")

    district_polygons = {d.id: shape(d.geom) for d in districts}
    for s in subjects:
        if s.district_id and s.district_id in district_polygons:
            poly = district_polygons[s.district_id]
            pt = Point(s.lon, s.lat)
            if not poly.contains(pt):
                raise ValueError(f"Entity '{s.id}' is outside its district '{s.district_id}'")