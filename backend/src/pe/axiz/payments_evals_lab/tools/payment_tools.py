from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pe.axiz.payments_evals_lab.rag.service import RagService
from pe.axiz.payments_evals_lab.repositories.payment_repository import PaymentRepository
from pe.axiz.payments_evals_lab.tools.registry import ToolDefinition, ToolRegistry


class GetTransactionArgs(BaseModel):
    transaction_id: str = Field(pattern=r"^TX-[0-9]{4}$")


class AuthorizationCodeArgs(BaseModel):
    code: str = Field(min_length=2, max_length=3)


class SearchKnowledgeArgs(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    strategy: Literal["native", "hybrid", "graphrag", "raglight", "lightrag"] = "hybrid"
    top_k: int = Field(default=5, ge=1, le=10)


class SearchRelationshipsArgs(BaseModel):
    entity: str = Field(min_length=2, max_length=120)
    relationship: str | None = Field(default=None, max_length=80)
    depth: int = Field(default=2, ge=1, le=4)


class CreateCaseDraftArgs(BaseModel):
    transaction_id: str = Field(pattern=r"^TX-[0-9]{4}$")
    reason: str = Field(min_length=5, max_length=500)
    priority: Literal["low", "medium", "high", "critical"] = "medium"


class PaymentTools:
    def __init__(self, repository: PaymentRepository, rag_service: RagService) -> None:
        self.repository = repository
        self.rag_service = rag_service

    def get_transaction(self, transaction_id: str) -> dict:
        transaction = self.repository.get_transaction(transaction_id)
        if transaction is None:
            return {"found": False, "transaction_id": transaction_id}
        return {"found": True, **transaction.model_dump(mode="json")}

    def lookup_authorization_code(self, code: str) -> dict:
        item = self.repository.get_authorization_code(code)
        if item is None:
            return {"found": False, "code": code}
        return {"found": True, **item.model_dump(mode="json")}

    async def search_payment_knowledge(self, query: str, strategy: str, top_k: int) -> dict:
        contexts = await self.rag_service.retrieve(query=query, strategy=strategy, top_k=top_k)
        return {"contexts": [item.model_dump(mode="json") for item in contexts]}

    async def search_payment_relationships(self, entity: str, relationship: str | None, depth: int) -> dict:
        return await self.rag_service.relationships(entity=entity, relationship=relationship, depth=depth)

    def create_case_draft(self, transaction_id: str, reason: str, priority: str) -> dict:
        return {
            "draft": True,
            "case_id": f"DRAFT-{transaction_id}",
            "transaction_id": transaction_id,
            "reason": reason,
            "priority": priority,
            "status": "not_submitted",
        }


def build_tool_registry(repository: PaymentRepository, rag_service: RagService) -> ToolRegistry:
    tools = PaymentTools(repository, rag_service)
    registry = ToolRegistry()
    registry.register(ToolDefinition("get_transaction", "Recupera una transacción sintética", GetTransactionArgs, tools.get_transaction))
    registry.register(ToolDefinition("lookup_authorization_code", "Interpreta un código de autorización", AuthorizationCodeArgs, tools.lookup_authorization_code))
    registry.register(ToolDefinition("search_payment_knowledge", "Consulta el corpus de pagos", SearchKnowledgeArgs, tools.search_payment_knowledge))
    registry.register(ToolDefinition("search_payment_relationships", "Consulta relaciones del grafo", SearchRelationshipsArgs, tools.search_payment_relationships))
    registry.register(ToolDefinition("create_case_draft", "Genera un borrador no destructivo", CreateCaseDraftArgs, tools.create_case_draft))
    return registry
