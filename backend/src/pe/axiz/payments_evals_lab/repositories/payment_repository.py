from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from pe.axiz.payments_evals_lab.domain.models import AuthorizationCode, Transaction


class PaymentRepository:
    """Repositorio sintético de pagos cargado desde datasets versionables."""

    def __init__(self, datasets_dir: Path) -> None:
        self._datasets_dir = datasets_dir
        self._lock = RLock()
        self._transactions: dict[str, Transaction] = {}
        self._codes: dict[str, AuthorizationCode] = {}
        self.reload()

    def reload(self) -> None:
        with self._lock:
            tx_path = self._datasets_dir / "evals" / "transactions.json"
            codes_path = self._datasets_dir / "evals" / "authorization_codes.json"
            self._transactions = {
                row["transaction_id"]: Transaction.model_validate(row)
                for row in json.loads(tx_path.read_text(encoding="utf-8"))
            }
            self._codes = {
                row["code"]: AuthorizationCode.model_validate(row)
                for row in json.loads(codes_path.read_text(encoding="utf-8"))
            }

    def get_transaction(self, transaction_id: str) -> Transaction | None:
        return self._transactions.get(transaction_id.upper())

    def get_authorization_code(self, code: str) -> AuthorizationCode | None:
        return self._codes.get(str(code))

    def all_transactions(self) -> list[Transaction]:
        return list(self._transactions.values())

    def list_transactions(self, status: str | None = None, limit: int = 20) -> list[Transaction]:
        items = sorted(self._transactions.values(), key=lambda item: item.created_at, reverse=True)
        if status:
            items = [item for item in items if item.status == status]
        return items[:limit]

    def transaction_summary(self) -> dict[str, object]:
        counts = {status: 0 for status in ("approved", "declined", "pending", "reversed")}
        currencies: set[str] = set()
        networks: set[str] = set()
        for transaction in self._transactions.values():
            counts[transaction.status] = counts.get(transaction.status, 0) + 1
            currencies.add(transaction.currency)
            networks.add(transaction.card_network)
        return {
            "total": len(self._transactions),
            "supported_statuses": ["approved", "declined", "pending", "reversed"],
            "present_statuses": {key: value for key, value in counts.items() if value > 0},
            "currencies": sorted(currencies),
            "card_networks": sorted(networks),
        }
