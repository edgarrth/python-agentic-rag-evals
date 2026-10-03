from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pe.axiz.payments_evals_lab.rag.embeddings import HashingEmbedding, tokenize


@dataclass(slots=True)
class CorpusChunk:
    id: str
    source: str
    text: str
    entities: list[str]
    vector: list[float]


def extract_entities(text: str) -> list[str]:
    candidates = set(re.findall(r"\b(?:TX-[0-9]{4}|ACQ-[A-Z]+|ISS-[A-Z]+|VISA|MASTERCARD|PCI DSS|ISO 8583|Qdrant|Memgraph)\b", text, flags=re.I))
    return sorted(candidates)


def load_corpus(knowledge_dir: Path, embedder: HashingEmbedding) -> list[CorpusChunk]:
    chunks: list[CorpusChunk] = []
    for path in sorted(knowledge_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        sections = [part.strip() for part in re.split(r"\n(?=##?\s)", text) if part.strip()]
        for index, section in enumerate(sections):
            if len(tokenize(section)) < 8:
                continue
            chunks.append(
                CorpusChunk(
                    id=f"{path.stem}-{index:03d}",
                    source=path.name,
                    text=section,
                    entities=extract_entities(section),
                    vector=embedder.encode(section),
                )
            )
    return chunks
