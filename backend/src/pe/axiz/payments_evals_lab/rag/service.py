from __future__ import annotations

import json
import math
import time
from collections import Counter
from pathlib import Path
from typing import Any

from pe.axiz.payments_evals_lab.config.settings import Settings
from pe.axiz.payments_evals_lab.domain.models import RetrievedContext
from pe.axiz.payments_evals_lab.rag.corpus import CorpusChunk, load_corpus
from pe.axiz.payments_evals_lab.rag.embeddings import HashingEmbedding, cosine_similarity, tokenize


def _lexical_score(query: str, text: str) -> float:
    q = Counter(tokenize(query))
    d = Counter(tokenize(text))
    if not q or not d:
        return 0.0
    overlap = sum(min(count, d[token]) for token, count in q.items())
    return overlap / max(1, sum(q.values()))


def _rrf(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


class RagService:
    """Capa común para Native, Hybrid, GraphRAG, RAGLight y LightRAG."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embedder = HashingEmbedding(settings.embedding_dimensions)
        self.corpus = load_corpus(settings.datasets_dir / "knowledge", self.embedder)
        self._relationships = self._load_relationship_fixtures(settings.datasets_dir / "evals" / "graph_relationships.json")

    @staticmethod
    def _load_relationship_fixtures(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    async def retrieve(self, query: str, strategy: str, top_k: int = 5) -> list[RetrievedContext]:
        top_k = min(top_k, self.settings.max_top_k)
        strategy = strategy.lower()
        if strategy == "auto":
            strategy = self.route_strategy(query)
        if strategy == "native":
            return await self._native(query, top_k)
        if strategy == "hybrid":
            return await self._hybrid(query, top_k)
        if strategy == "graphrag":
            return await self._graphrag(query, top_k)
        if strategy == "raglight":
            return await self._raglight(query, top_k)
        if strategy == "lightrag":
            return await self._lightrag(query, top_k)
        raise ValueError(f"Estrategia RAG no soportada: {strategy}")

    def route_strategy(self, query: str) -> str:
        lowered = query.lower()
        if any(word in lowered for word in ("relación", "relacion", "conecta", "acquirer", "issuer", "grafo", "multi-hop")):
            return "graphrag"
        if any(word in lowered for word in ("exacto", "código", "codigo", "iso", "pci", "91", "05")):
            return "hybrid"
        if len(tokenize(query)) <= 7:
            return "native"
        return "hybrid"

    async def _native(self, query: str, top_k: int) -> list[RetrievedContext]:
        query_vector = self.embedder.encode(query)
        remote = await self._qdrant_search(query_vector, top_k)
        if remote:
            return remote
        ranked = sorted(
            ((cosine_similarity(query_vector, chunk.vector), chunk) for chunk in self.corpus),
            key=lambda item: item[0],
            reverse=True,
        )[:top_k]
        return [self._context(chunk, score, rank=index + 1, raw_score=score, strategy="native") for index, (score, chunk) in enumerate(ranked)]

    async def _hybrid(self, query: str, top_k: int) -> list[RetrievedContext]:
        query_vector = self.embedder.encode(query)
        dense = sorted(
            ((cosine_similarity(query_vector, chunk.vector), chunk) for chunk in self.corpus),
            key=lambda item: item[0],
            reverse=True,
        )
        lexical = sorted(
            ((_lexical_score(query, chunk.text), chunk) for chunk in self.corpus),
            key=lambda item: item[0],
            reverse=True,
        )
        fused: dict[str, dict[str, Any]] = {}
        for rank, (score, chunk) in enumerate(dense[: max(top_k * 4, 20)], start=1):
            fused.setdefault(chunk.id, {"chunk": chunk, "rrf": 0.0, "dense": score, "lexical": 0.0})["rrf"] += _rrf(rank)
        for rank, (score, chunk) in enumerate(lexical[: max(top_k * 4, 20)], start=1):
            entry = fused.setdefault(chunk.id, {"chunk": chunk, "rrf": 0.0, "dense": 0.0, "lexical": score})
            entry["rrf"] += _rrf(rank)
            entry["lexical"] = score
        ranked = sorted(fused.values(), key=lambda item: item["rrf"], reverse=True)[:top_k]
        max_rrf = ranked[0]["rrf"] if ranked else 1.0
        return [
            self._context(
                item["chunk"],
                item["rrf"] / max_rrf,
                rank=index + 1,
                raw_score=item["dense"],
                rerank_score=item["lexical"],
                strategy="hybrid",
            )
            for index, item in enumerate(ranked)
        ]

    async def _graphrag(self, query: str, top_k: int) -> list[RetrievedContext]:
        hybrid = await self._hybrid(query, max(top_k, 6))
        query_tokens = set(tokenize(query))
        related_entities = set()
        for rel in self._relationships:
            terms = set(tokenize(" ".join(rel.values())))
            if query_tokens & terms:
                related_entities.update((rel["source"], rel["target"]))
        reranked = []
        for context in hybrid:
            graph_match = len(related_entities.intersection(context.entities))
            score = context.score + min(0.25, graph_match * 0.08)
            context.score = score
            context.metadata["graph_matches"] = graph_match
            context.metadata["strategy"] = "graphrag"
            reranked.append(context)
        reranked.sort(key=lambda item: item.score, reverse=True)
        for rank, item in enumerate(reranked[:top_k], start=1):
            item.rank = rank
        return reranked[:top_k]

    async def _raglight(self, query: str, top_k: int) -> list[RetrievedContext]:
        # Clasificación ligera de la consulta y recuperación enfocada por clase temática.
        theme = self._query_theme(query)
        candidates = [chunk for chunk in self.corpus if theme in chunk.source] or self.corpus
        query_vector = self.embedder.encode(query)
        ranked = sorted(
            ((0.72 * cosine_similarity(query_vector, chunk.vector) + 0.28 * _lexical_score(query, chunk.text), chunk) for chunk in candidates),
            key=lambda item: item[0],
            reverse=True,
        )[:top_k]
        return [self._context(chunk, score, rank=i + 1, raw_score=score, strategy="raglight", theme=theme) for i, (score, chunk) in enumerate(ranked)]

    async def _lightrag(self, query: str, top_k: int) -> list[RetrievedContext]:
        # Recuperación ligera que fusiona entidades del grafo y similitud vectorial sin índice adicional.
        native = await self._native(query, max(top_k * 2, 6))
        query_tokens = set(tokenize(query))
        for item in native:
            entity_bonus = sum(1 for entity in item.entities if set(tokenize(entity)) & query_tokens) * 0.06
            item.score = min(1.0, item.score + entity_bonus)
            item.metadata["entity_bonus"] = entity_bonus
            item.metadata["strategy"] = "lightrag"
        native.sort(key=lambda item: item.score, reverse=True)
        return native[:top_k]

    def _query_theme(self, query: str) -> str:
        lowered = query.lower()
        if "concili" in lowered or "reconcil" in lowered:
            return "reconciliation"
        if "pci" in lowered or "token" in lowered:
            return "pci"
        if "idempot" in lowered:
            return "idempotency"
        if "código" in lowered or "codigo" in lowered or "rechaz" in lowered:
            return "authorization"
        return "payment"

    async def relationships(self, entity: str, relationship: str | None = None, depth: int = 2) -> dict[str, Any]:
        remote = await self._memgraph_relationships(entity, relationship, depth)
        if remote is not None:
            return remote
        entity_lower = entity.lower()
        rows = [
            rel
            for rel in self._relationships
            if entity_lower in rel["source"].lower() or entity_lower in rel["target"].lower()
            if relationship is None or relationship.lower() in rel["relationship"].lower()
        ]
        return {"entity": entity, "depth": depth, "relationships": rows, "source": "fixture-fallback"}

    async def _qdrant_search(self, vector: list[float], top_k: int) -> list[RetrievedContext]:
        try:
            from qdrant_client import AsyncQdrantClient
        except ImportError:
            return []
        try:
            client = AsyncQdrantClient(url=self.settings.qdrant_url, timeout=1.5)
            points = await client.query_points(
                collection_name=self.settings.qdrant_collection,
                query=vector,
                limit=top_k,
                with_payload=True,
            )
            result = []
            for rank, point in enumerate(points.points, start=1):
                payload = point.payload or {}
                result.append(
                    RetrievedContext(
                        id=str(point.id),
                        source=str(payload.get("source", "unknown")),
                        text=str(payload.get("text", "")),
                        score=float(point.score),
                        raw_score=float(point.score),
                        rank=rank,
                        entities=list(payload.get("entities", [])),
                        metadata={"strategy": "native", "backend": "qdrant"},
                    )
                )
            await client.close()
            return result
        except Exception:  # noqa: BLE001
            return []

    async def _memgraph_relationships(self, entity: str, relationship: str | None, depth: int) -> dict[str, Any] | None:
        try:
            from neo4j import AsyncGraphDatabase
        except ImportError:
            return None
        driver = None
        try:
            driver = AsyncGraphDatabase.driver(
                self.settings.memgraph_uri,
                auth=(self.settings.memgraph_user, self.settings.memgraph_password) if self.settings.memgraph_user else None,
            )
            query = """
            MATCH (a)-[r]->(b)
            WHERE toLower(a.name) CONTAINS toLower($entity) OR toLower(b.name) CONTAINS toLower($entity)
            RETURN a.name AS source, type(r) AS relationship, b.name AS target
            LIMIT 30
            """
            async with driver.session() as session:
                result = await session.run(query, entity=entity)
                rows = [record.data() async for record in result]
            if relationship:
                rows = [row for row in rows if relationship.lower() in row["relationship"].lower()]
            return {"entity": entity, "depth": depth, "relationships": rows, "source": "memgraph"}
        except Exception:  # noqa: BLE001
            return None
        finally:
            if driver is not None:
                await driver.close()

    @staticmethod
    def _context(chunk: CorpusChunk, score: float, rank: int, raw_score: float, strategy: str, **metadata: Any) -> RetrievedContext:
        return RetrievedContext(
            id=chunk.id,
            source=chunk.source,
            text=chunk.text,
            score=float(score),
            raw_score=float(raw_score),
            rank=rank,
            entities=chunk.entities,
            metadata={"strategy": strategy, **metadata},
        )
