from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from pe.axiz.payments_evals_lab.config.settings import get_settings
from pe.axiz.payments_evals_lab.rag.corpus import load_corpus
from pe.axiz.payments_evals_lab.rag.embeddings import HashingEmbedding


def wait_for(name: str, probe, attempts: int = 40, delay: float = 1.0) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            probe()
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(delay)
    raise RuntimeError(f"{name} no quedó disponible: {last_error}")


def seed_qdrant() -> int:
    from qdrant_client import QdrantClient, models

    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, timeout=5.0)
    wait_for("Qdrant", lambda: client.get_collections())
    collections = {item.name for item in client.get_collections().collections}
    if settings.qdrant_collection not in collections:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=models.VectorParams(size=settings.embedding_dimensions, distance=models.Distance.COSINE),
        )

    embedder = HashingEmbedding(settings.embedding_dimensions)
    chunks = load_corpus(settings.datasets_dir / "knowledge", embedder)
    points = [
        models.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.id)),
            vector=chunk.vector,
            payload={"chunk_id": chunk.id, "source": chunk.source, "text": chunk.text, "entities": chunk.entities},
        )
        for chunk in chunks
    ]
    if points:
        client.upsert(collection_name=settings.qdrant_collection, points=points, wait=True)
    client.close()
    return len(points)


def seed_memgraph() -> int:
    from neo4j import GraphDatabase

    settings = get_settings()
    auth = (settings.memgraph_user, settings.memgraph_password) if settings.memgraph_user else None
    driver = GraphDatabase.driver(settings.memgraph_uri, auth=auth)
    wait_for("Memgraph", lambda: driver.verify_connectivity())
    relationships = json.loads((settings.datasets_dir / "evals" / "graph_relationships.json").read_text(encoding="utf-8"))
    with driver.session() as session:
        for row in relationships:
            relationship = row["relationship"].upper()
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", relationship):
                raise ValueError(f"Tipo de relación inválido: {relationship}")
            query = f"""
            MERGE (a:PaymentEntity {{name: $source}})
            MERGE (b:PaymentEntity {{name: $target}})
            MERGE (a)-[r:{relationship}]->(b)
            SET r.seed = true
            """
            session.run(query, source=row["source"], target=row["target"]).consume()
    driver.close()
    return len(relationships)


def main() -> None:
    qdrant_count = seed_qdrant()
    graph_count = seed_memgraph()
    print(json.dumps({"qdrant_chunks": qdrant_count, "memgraph_relationships": graph_count, "status": "seeded"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
