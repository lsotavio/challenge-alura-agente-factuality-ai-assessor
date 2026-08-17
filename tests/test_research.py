import sys
from types import SimpleNamespace

from src.research import build_queries, search_claim, source_quality
from src.schemas import EvidenceItem


def test_build_queries_includes_task_context():
    queries = build_queries("temperatura média de 24C", "clima em Cidade Aurora", "", "15/03/2025")
    assert "Aurora" in queries[0]
    assert "temperatura" in queries[0]


def test_build_queries_keeps_distinctive_amount_for_fact_checking():
    queries = build_queries(
        "A anuidade para novos inscritos é de R$ 480,00 em 2025.",
        "anuidade conselho profissional alfa 2025",
    )
    assert queries[0].startswith("anuidade conselho profissional alfa 2025")
    assert any('"480,00"' in query for query in queries)


def test_search_has_safe_fallback(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "ddgs":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    result = search_claim("test claim", "test query", max_results=2)
    assert result["results"]
    assert result["results"][0]["source"] == "manual_fallback"
    assert result["errors"]


def test_search_result_can_be_marked_as_uncertain_candidate():
    item = EvidenceItem(url="https://example.com", title="Example", snippet="Snippet", relation="context", source_quality="uncertain")
    assert item.source_quality == "uncertain"
    assert item.relation == "context"


def test_authority_is_independent_of_locale():
    assert source_quality("https://www.noaa.gov/ocean-facts") == "primary_authoritative"
    assert source_quality("https://www.nhl.com/news/example") == "primary_authoritative"


def test_temporal_search_rejects_current_page_without_task_date(monkeypatch):
    class FakeDDGS:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def text(self, *args, **kwargs):
            return [
                {
                    "title": "Previsão do tempo em Cidade Aurora hoje",
                    "href": "https://example.com/clima/cidade-aurora",
                    "body": "Temperatura e chuva em Cidade Aurora nesta semana.",
                },
                {
                    "title": "Previsão emitida em 15/03/2025 para Cidade Aurora",
                    "href": "https://example.gov.br/arquivo/2025/03/15/cidade-aurora",
                    "body": "Boletim histórico de 15 de março de 2025.",
                },
            ]

        def extract(self, *args, **kwargs):
            return {"content": "Boletim histórico emitido em 15/03/2025."}

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    result = search_claim(
        "Previsão de chuva com temperatura média de 24°C.",
        "clima em Cidade Aurora",
        response_date="15/03/2025",
        max_results=2,
        max_queries=1,
        temporal_date="15/03/2025",
    )
    urls = [item["url"] for item in result["results"]]
    assert urls == ["https://example.gov.br/arquivo/2025/03/15/cidade-aurora"]


def test_irrelevant_sports_sources_are_rejected_for_award_claim(monkeypatch):
    class FakeDDGS:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def text(self, *args, **kwargs):
            return [
                {
                    "title": "Copa do Mundo FIFA 2026",
                    "href": "https://www.fifa.com/world-cup-2026",
                    "body": "Tabela de jogos da competição em 2026.",
                },
                {
                    "title": "Helena Duarte wins the national research award",
                    "href": "https://www.gov.br/pesquisa/premio-nacional-2026",
                    "body": "Helena Duarte beat finalists Marcos Lima and Renata Alves.",
                },
                {
                    "title": "Duarte, Lima and Alves named award finalists",
                    "href": "https://www.gov.br/pesquisa/finalistas-2026",
                    "body": "Helena Duarte, Marcos Lima and Renata Alves are the three finalists.",
                },
            ]

        def extract(self, *args, **kwargs):
            return {"content": "Helena Duarte won the 2026 award ahead of Marcos Lima and Renata Alves."}

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    result = search_claim(
        "Helena Duarte superou os finalistas Marcos Lima e Renata Alves.",
        "Helena Duarte venceu o Prêmio Nacional de Pesquisa de 2026?",
        max_results=4,
    )
    urls = [item["url"] for item in result["results"]]
    assert urls[0] == "https://www.gov.br/pesquisa/premio-nacional-2026"
    assert all("fifa.com" not in url for url in urls)
    assert result["results"][0]["source_quality"] == "primary_authoritative"
    assert "Helena Duarte won" in result["results"][0]["excerpt"]


def test_first_party_general_web_page_is_extracted_before_rating(monkeypatch):
    class FakeDDGS:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def text(self, *args, **kwargs):
            return [{
                "title": "Contato | Clínica Horizonte",
                "href": "https://clinicahorizonte.example/contato/",
                "body": "Telefone e WhatsApp para atendimento.",
            }]

        def extract(self, *args, **kwargs):
            return {"content": "WhatsApp 00 90000-2000. Telefone 00 3000-1000."}

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    result = search_claim(
        "Telefone 00 3000-1000 WhatsApp 00 90000-1000",
        "telefone Clínica Horizonte",
        max_results=3,
    )

    assert result["results"][0]["source_quality"] == "general_web"
    assert "90000-2000" in result["results"][0]["excerpt"]
    assert "3000-1000" in result["results"][0]["excerpt"]
