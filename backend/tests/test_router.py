from pe.axiz.payments_evals_lab.rag.router import AdaptiveRouter


def test_router_payment_and_ood() -> None:
    router = AdaptiveRouter()
    payment = router.decide("Revisa TX-1007 y explica el rechazo")
    assert payment.intent == "transaction_diagnosis"
    assert payment.strategy == "hybrid"
    ood = router.decide("¿Cuál es la capital de Francia?")
    assert ood.out_of_domain is True
    assert ood.intent == "out_of_domain"
