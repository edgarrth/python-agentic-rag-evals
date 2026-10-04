from pe.axiz.payments_evals_lab.rag.router import AdaptiveRouter


def test_router_payment_and_ood() -> None:
    router = AdaptiveRouter()
    payment = router.decide("Revisa TX-1007 y explica el rechazo")
    assert payment.intent == "transaction_diagnosis"
    assert payment.strategy == "hybrid"
    ood = router.decide("¿Cuál es la capital de Francia?")
    assert ood.out_of_domain is True
    assert ood.intent == "out_of_domain"


def test_router_accepts_plural_transaction_queries() -> None:
    router = AdaptiveRouter()
    catalog = router.decide("¿Qué tipos de transacciones existen?")
    assert catalog.out_of_domain is False
    assert catalog.intent == "transaction_catalog"

    declined = router.decide("Dime las transacciones rechazadas")
    assert declined.out_of_domain is False
    assert declined.intent == "transaction_search"
