from backend.economy.repository import Repository
from backend.economy.models import Edge


def update_edges(repo: Repository, edges: list[Edge], active_domains: list[str]) -> None:
    for domain in active_domains:
        repo.delete_edges_by_domain(domain)

    if edges:
        repo.insert_edges(edges)