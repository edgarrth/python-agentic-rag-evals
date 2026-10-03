from pe.axiz.payments_evals_lab.evals.classic import bleu_score, rouge_l, self_consistency
from pe.axiz.payments_evals_lab.evals.retrieval import ndcg_at_k, reciprocal_rank
from pe.axiz.payments_evals_lab.evals.voice import boundary_f1, wer


def test_classic_metrics_are_bounded() -> None:
    assert 0 <= bleu_score("a b c d", "a b c d") <= 1
    assert rouge_l("uno dos tres", "uno dos tres") == 1
    assert self_consistency(["pago aprobado", "pago aprobado"]) == 1


def test_retrieval_metrics() -> None:
    retrieved = ["a", "b", "c"]
    relevant = {"b", "c"}
    assert reciprocal_rank(retrieved, relevant) == 0.5
    assert 0 < ndcg_at_k(retrieved, relevant, 3) <= 1


def test_voice_metrics() -> None:
    assert wer("hola mundo", "hola mundo") == 0
    assert wer("hola mundo", "hola cruel mundo") > 0
    assert boundary_f1([100, 200], [105, 198], 20) == 1
