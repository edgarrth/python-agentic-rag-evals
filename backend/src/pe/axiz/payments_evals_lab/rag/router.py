from __future__ import annotations

from dataclasses import dataclass

from pe.axiz.payments_evals_lab.rag.embeddings import tokenize


@dataclass(slots=True)
class RoutingDecision:
    intent: str
    strategy: str
    confidence: float
    out_of_domain: bool = False


class AdaptiveRouter:
    """Router explícito y evaluable para intención y estrategia de recuperación."""

    PAYMENT_TERMS = {
        "pago", "payment", "transacción", "transaccion", "autorización", "autorizacion", "rechazo",
        "acquirer", "adquirente", "issuer", "emisor", "conciliación", "conciliacion", "chargeback",
        "pci", "token", "idempotencia", "idempotency", "timeout", "reintento", "reintentar", "cobrar", "iso", "tx-1007", "tx-1008", "merchant",
    }

    def decide(self, question: str) -> RoutingDecision:
        tokens = set(tokenize(question))
        lowered = question.lower()
        overlap = len(tokens & self.PAYMENT_TERMS)
        if overlap == 0 and not any(term in lowered for term in ("tx-", "código 91", "codigo 91")):
            return RoutingDecision(intent="out_of_domain", strategy="native", confidence=0.93, out_of_domain=True)
        if "tx-" in lowered or "transacción" in lowered or "transaccion" in lowered:
            return RoutingDecision(intent="transaction_diagnosis", strategy="hybrid", confidence=0.94)
        if any(term in lowered for term in ("relación", "relacion", "conecta", "grafo", "acquirer", "issuer")):
            return RoutingDecision(intent="relationship_query", strategy="graphrag", confidence=0.91)
        if "concili" in lowered or "reconcil" in lowered:
            return RoutingDecision(intent="reconciliation", strategy="raglight", confidence=0.90)
        if any(term in lowered for term in ("pci", "token", "idempot")):
            return RoutingDecision(intent="policy_query", strategy="hybrid", confidence=0.89)
        return RoutingDecision(intent="payment_knowledge", strategy="native", confidence=min(0.88, 0.62 + overlap * 0.05))
