from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(slots=True)
class RoutingDecision:
    intent: str
    strategy: str
    confidence: float
    out_of_domain: bool = False


class AdaptiveRouter:
    """Router explícito y evaluable para intención y estrategia de recuperación."""

    PAYMENT_STEMS = (
        "pag", "payment", "transaccion", "autoriz", "rechaz", "declin", "aprobad", "pending", "pendient",
        "acquirer", "adquir", "issuer", "emisor", "concili", "reconcil", "chargeback", "pci", "token",
        "idempot", "timeout", "reint", "cobrar", "merchant", "comercio", "tarjeta", "visa", "mastercard",
        "settlement", "liquidac", "refund", "reembolso", "revers", "fraud", "contracargo", "iso8583",
    )

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.lower())
        ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", ascii_text).strip()

    def _is_payment_domain(self, lowered: str) -> bool:
        compact = lowered.replace(" ", "")
        return (
            any(stem in lowered for stem in self.PAYMENT_STEMS)
            or "tx-" in lowered
            or "codigo 91" in lowered
            or "iso8583" in compact
        )

    def decide(self, question: str) -> RoutingDecision:
        lowered = self._normalize(question)
        if not self._is_payment_domain(lowered):
            return RoutingDecision(intent="out_of_domain", strategy="native", confidence=0.93, out_of_domain=True)

        # Consultas de catálogo/colección de transacciones: no requieren un TX concreto.
        if "transaccion" in lowered and any(term in lowered for term in ("tipo", "tipos", "clase", "clases", "estado", "estados", "existen")):
            return RoutingDecision(intent="transaction_catalog", strategy="native", confidence=0.95)
        if "transaccion" in lowered and any(
            term in lowered
            for term in ("rechaz", "declin", "aprobad", "pendient", "pending", "revers", "lista", "listar", "muestra", "dime las")
        ) and "tx-" not in lowered:
            return RoutingDecision(intent="transaction_search", strategy="native", confidence=0.95)

        if "tx-" in lowered:
            return RoutingDecision(intent="transaction_diagnosis", strategy="hybrid", confidence=0.94)
        if any(term in lowered for term in ("relacion", "conecta", "grafo", "acquirer", "issuer")):
            return RoutingDecision(intent="relationship_query", strategy="graphrag", confidence=0.91)
        if "concili" in lowered or "reconcil" in lowered:
            return RoutingDecision(intent="reconciliation", strategy="raglight", confidence=0.90)
        if any(term in lowered for term in ("pci", "token", "idempot")):
            return RoutingDecision(intent="policy_query", strategy="hybrid", confidence=0.89)
        if "transaccion" in lowered:
            return RoutingDecision(intent="transaction_search", strategy="native", confidence=0.88)
        return RoutingDecision(intent="payment_knowledge", strategy="native", confidence=0.84)
