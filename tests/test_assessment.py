from datetime import date

from src.assessment import plan_assessment
from src.schemas import FactualityInput, Task


def _task(query: str, response: str, target: str, response_date: str = "") -> Task:
    return Task(task_type="factuality", factuality=FactualityInput(
        user_query=query,
        response=response,
        target_sentence=target,
        response_date=response_date,
    ))


def test_past_weather_forecast_gets_one_bounded_temporal_search():
    task = _task(
        "clima em Cidade de Teste",
        "Previsão para hoje e próximos dias.",
        "Fim de semana com chuva e temperatura média de 27°C.",
        "18/02/2026",
    )
    plan = plan_assessment(task, today=date(2026, 8, 18))
    assert plan.mode == "limited_temporal"
    assert plan.max_queries == 1
    assert plan.max_results == 2


def test_weather_without_evaluation_date_is_not_searched_in_a_loop():
    task = _task("clima dores", "Previsão para amanhã.", "Chuva rápida com máxima de 27°C.")
    plan = plan_assessment(task, today=date(2026, 8, 18))
    assert plan.mode == "limited_temporal"
    assert "no reliable evaluation date" in plan.reason


def test_verifiable_sports_claim_keeps_standard_research():
    task = _task(
        "Helena Duarte venceu o Prêmio Nacional de Pesquisa?",
        "Helena Duarte recebeu o principal prêmio da área.",
        "A organização anunciou Helena Duarte como vencedora em 2 de junho de 2026.",
        "02/06/2026",
    )
    plan = plan_assessment(task, today=date(2026, 8, 18))
    assert plan.mode == "standard"
    assert plan.max_queries == 2
    assert plan.max_results == 4
