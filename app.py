from __future__ import annotations

import html
import json
from pathlib import Path

import streamlit as st

from src.evaluator import create_draft
from src.gemini import (
    GeminiUnavailable,
    friendly_gemini_error,
    gemini_configured,
    log_gemini_error,
    merge_review,
    review_with_gemini,
)
from src.highlights import highlighted_fragments
from src.schemas import ClaimInput, FactualityInput, Task
from src.presentation import format_guideline_citation
from src.storage import (
    HistoryImportError,
    create_history_export,
    form_state_from_session,
    import_history_export,
    history_enabled,
    list_sessions,
    save_session,
)


st.set_page_config(page_title="Assistente de Factualidade", page_icon="🔎", layout="wide")
st.markdown("""
<style>
    /* Raterhub Header Styling */
    header[data-testid="stHeader"] {
        background-color: #202124 !important;
        border-top: 5px solid #34a853 !important;
    }
    header[data-testid="stHeader"] * {
        color: #ffffff !important;
    }
    /* Main container top padding adjustment */
    .block-container {
        padding-top: 3rem !important;
    }
    /* Style the title to look more professional */
    h1 {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        color: #202124;
        font-size: 24px !important;
        font-weight: 500 !important;
        padding-bottom: 0px !important;
    }
    .guideline-card {
        background: #dcecff;
        border: 1px solid #c3dcf6;
        border-left: 4px solid #6ba7df;
        border-radius: 10px;
        color: #17324d;
        margin: 0.35rem 0 1.25rem;
        padding: 1rem 1.15rem;
    }
    .guideline-meta {
        align-items: center;
        color: #587086;
        display: flex;
        flex-wrap: wrap;
        font-size: 0.78rem;
        gap: 0.45rem 0.8rem;
        margin-bottom: 0.8rem;
    }
    .guideline-source { color: #315d85; font-weight: 600; }
    .guideline-section + .guideline-section {
        border-top: 1px solid #bdd7ef;
        margin-top: 1rem;
        padding-top: 0.9rem;
    }
    .guideline-section h4 {
        color: #164f83;
        font-size: 1rem;
        font-weight: 650;
        line-height: 1.35;
        margin: 0 0 0.55rem;
    }
    .guideline-paragraph { line-height: 1.6; margin: 0.25rem 0 0.7rem; }
    .guideline-list { list-style: none; margin: 0.45rem 0 0; padding: 0; }
    .guideline-list li {
        border-left: 2px solid #8dbbe5;
        margin: 0.5rem 0;
        padding: 0.12rem 0 0.12rem 0.85rem;
    }
    .guideline-list.numbered { counter-reset: guideline-item; }
    .guideline-list.numbered li { counter-increment: guideline-item; }
    .guideline-list.numbered li::before {
        color: #477aa7;
        content: counter(guideline-item) ".";
        font-weight: 650;
        margin-right: 0.45rem;
    }
    .guideline-label { color: #174f80; font-weight: 650; }
    .guideline-label::after { content: ": "; }
    .guideline-description { line-height: 1.55; }
    .history-detail { color: #657786; font-size: 0.82rem; }
</style>
""", unsafe_allow_html=True)
st.title("Assistente de Factualidade")
st.caption("Avaliação assistida de afirmações")


def fixture_data() -> dict[str, dict]:
    path = Path(__file__).parent / "data" / "factuality_test_tasks.json"
    if not path.exists():
        return {}
    return {item["id"]: item for item in json.loads(path.read_text(encoding="utf-8"))}


def load_fixture() -> None:
    selected = st.session_state.get("fixture_selector")
    item = fixture_data().get(selected)
    if not item:
        return
    for key, value in {
        "f_query": item.get("user_query", ""),
        "f_response": item.get("response", ""),
        "f_target": item.get("target_sentence", ""),
        "f_location": item.get("user_location", ""),
        "f_locale": item.get("user_locale", "Portuguese (BR)"),
        "f_date": item.get("response_date", ""),
    }.items():
        st.session_state[key] = value


def global_history() -> None:
    if not history_enabled():
        st.caption("Privacidade: esta demonstração pública não armazena o conteúdo das tarefas.")
        return
    sessions = list_sessions()
    with st.expander(f"Histórico de tarefas ({len(sessions)})", expanded=False):
        import_result = st.session_state.pop("history_import_result", None)
        if import_result:
            st.success(
                f"Importação concluída: {import_result['imported']} tarefa(s) adicionada(s)"
                f" e {import_result['skipped']} já existente(s) ignorada(s)."
            )
        if not sessions:
            st.caption("Nenhuma tarefa analisada nesta instalação.")
        else:
            accepted = sum(item.get("draft", {}).get("task_summary", {}).get("gemini_review_status") == "accepted" for item in sessions)
            rejected = sum(item.get("draft", {}).get("task_summary", {}).get("gemini_review_status") in {"rejected", "corrected"} for item in sessions)
            pending = sum(item.get("draft", {}).get("task_summary", {}).get("gemini_review_status") == "pending" for item in sessions)
            c1, c2, c3 = st.columns(3)
            c1.metric("Aceitas", accepted)
            c2.metric("Rejeitadas ou corrigidas", rejected)
            c3.metric("Aguardando revisão", pending)
            st.divider()
            if st.session_state.pop("history_loaded", False):
                st.success("Tarefa restaurada. Os campos e o resultado estão disponíveis abaixo.")

            status_labels = {
                "accepted": "Confirmada", "corrected": "Corrigida",
                "rejected": "Descartada", "pending": "A revisar",
            }
            for index, item in enumerate(sessions[:10]):
                task_data = item.get("task", {})
                summary_data = item.get("draft", {}).get("task_summary", {})
                query_text = task_data.get("query") or summary_data.get("user_query") or "Sem consulta"
                status_text = summary_data.get("gemini_review_status") or item.get("status", "draft")
                rating_text = summary_data.get("gemini_final_rating") or summary_data.get("factuality_rating_suggestion") or "-"
                saved_at = item.get("saved_at", "")[:16].replace("T", " ")
                row_text, row_action = st.columns([8, 1])
                row_text.markdown(
                    f"**{query_text}**  \n<span class='history-detail'>{saved_at} · {rating_text} · "
                    f"{status_labels.get(status_text, 'Rascunho')}</span>", unsafe_allow_html=True,
                )
                if row_action.button("Abrir", key=f"open_history_{item.get('session_id', index)}", use_container_width=True):
                    st.session_state.update(form_state_from_session(item))
                    st.session_state["history_loaded"] = True
                    st.rerun()

        st.divider()
        with st.expander("Exportar ou importar histórico", expanded=False):
            st.caption("O arquivo inclui tarefas, resultados e fontes. Chaves de API e configurações não são exportadas.")
            filename, export_data = create_history_export(sessions)
            export_col, import_col = st.columns(2)
            export_col.download_button(
                "Exportar histórico", data=export_data, file_name=filename,
                mime="application/json", disabled=not sessions, use_container_width=True,
            )
            uploaded_history = import_col.file_uploader(
                "Importar arquivo JSON", type=["json"], key="history_import_file",
                label_visibility="collapsed",
            )
            if import_col.button(
                "Importar histórico", disabled=uploaded_history is None,
                use_container_width=True, key="history_import_button",
            ):
                try:
                    result = import_history_export(uploaded_history.getvalue())
                except HistoryImportError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["history_import_result"] = result
                    st.rerun()


global_history()

fixtures = fixture_data()
options = ["manual", *fixtures.keys()]
fixture_labels = {
    fixture_id: f"Exemplo {index}: {item['user_query']}"
    for index, (fixture_id, item) in enumerate(fixtures.items(), start=1)
}
st.selectbox(
    "Tarefa de exemplo",
    options,
    key="fixture_selector",
    format_func=lambda value: fixture_labels.get(value, "Preencher nova tarefa"),
    on_change=load_fixture,
)

c1, c2, c3 = st.columns([2, 1, 1])
query = c1.text_input("Consulta do usuário", key="f_query", placeholder="Ex.: Quem ganhou o título de 2023?")
location = c2.text_input("Localização do usuário", key="f_location", placeholder="Ex.: Cidade e região")
locale = c3.text_input("Idioma da tarefa", key="f_locale", value="Portuguese (BR)")
date = st.text_input("Data da resposta", key="f_date", placeholder="Ex.: 18/02/2026")

left, right = st.columns(2, gap="medium")
response_text = left.text_area("Resposta completa", key="f_response", height=240)
target_text = right.text_area("Trecho destacado para verificar", key="f_target", height=240)

if response_text or target_text:
    with st.expander("Prévia da tarefa", expanded=False):
        esc_resp = html.escape(response_text)
        fragments = highlighted_fragments(response_text, target_text)
        preview = esc_resp
        matched_fragment = False
        for fragment in fragments:
            escaped_fragment = html.escape(fragment)
            if escaped_fragment in preview:
                preview = preview.replace(
                    escaped_fragment,
                    f"<mark style='background:#ffeb3b;padding:2px 4px;border-radius:3px;'>{escaped_fragment}</mark>",
                )
                matched_fragment = True
        if target_text and not matched_fragment:
            esc_target = html.escape(target_text)
            preview += f"<hr><mark style='background:#ffeb3b;padding:2px 4px;'>{esc_target}</mark>"
        html_table = f"""
        <div style="font-family: Arial, sans-serif; color: #333; margin-top: 10px;">
            <p style="font-size: 18px; margin-bottom: 12px; color: #555;">Avalie o <mark style="background-color: #ffeb3b; padding: 2px 4px; font-weight: bold;">trecho destacado</mark> dentro do contexto:</p>
            <table style="width: 100%; border-collapse: collapse; border: 1px solid #bbb; background-color: #fff; font-size: 13px;">
                <thead>
                    <tr style="background-color: #e8eaed; border-bottom: 1px solid #bbb;">
                        <th style="padding: 10px; text-align: center; border-right: 1px solid #bbb; width: 50%; font-weight: bold; color: #222;">Trecho em análise</th>
                        <th style="padding: 10px; text-align: center; font-weight: bold; color: #222;">Pergunta</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td style="padding: 16px; border-right: 1px solid #bbb; vertical-align: top; white-space: pre-wrap; color: #1558d6; line-height: 1.5;">{preview}</td>
                        <td style="padding: 16px; vertical-align: top; line-height: 1.4; color: #222;">
                            <b>Até que ponto o trecho em análise está correto de acordo com a pesquisa?</b><br>
                            <span style="font-size: 12px; color: #444;">Considere as evidências encontradas e faça pesquisas adicionais quando necessário.</span>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
        """
        st.markdown(html_table, unsafe_allow_html=True)

claims = [ClaimInput(text=target_text)] if target_text.strip() else []
factuality_input = FactualityInput(
    user_query=query,
    response=response_text,
    target_sentence=target_text,
    highlighted_fragments=highlighted_fragments(response_text, target_text),
    response_date=date,
    user_location=location,
    user_locale=locale,
    claims=claims,
)
task = Task(task_type="factuality", query=query, user_location=location, locale=locale, factuality=factuality_input)

# Actions
st.write("")
if gemini_configured():
    st.caption("Gemini pronto para pesquisar e analisar.")
    if st.button("Pesquisar e analisar", type="primary", use_container_width=True):
        try:
            with st.status("Preparando a análise...", expanded=True) as progress:
                st.write("Consultando as diretrizes da tarefa...")
                st.write("Pesquisando fontes confiáveis e verificando as afirmações...")
                review = review_with_gemini(task)
                st.write("Organizando o resultado para revisão...")
                enriched = merge_review(create_draft(task), review)
                progress.update(label="Análise concluída", state="complete", expanded=False)
            st.session_state["draft"] = enriched.model_dump()
            st.session_state["task"] = task.model_dump()
            st.session_state["session_id"] = save_session(st.session_state["task"], st.session_state["draft"], "draft").stem
        except GeminiUnavailable as exc:
            st.error(str(exc))
        except Exception as exc:
            log_gemini_error(exc)
            st.error(friendly_gemini_error(exc))
else:
    st.warning("O Gemini não está configurado nesta instalação.")
    if st.button("Preparar rascunho local", use_container_width=True):
        st.session_state["draft"] = create_draft(task).model_dump()
        st.session_state["task"] = task.model_dump()
        st.session_state["session_id"] = save_session(st.session_state["task"], st.session_state["draft"], "draft").stem

# Render Output Draft & Human Review Loop
if "draft" in st.session_state:
    draft = st.session_state["draft"]
    summary = draft["task_summary"]
    st.divider()
    st.subheader("Resultado da análise")

    if task.task_type == "factuality":
        final_rating = (
            summary.get("human_corrected_rating")
            or summary.get("gemini_final_rating")
            or summary.get("factuality_rating_suggestion")
            or "Aguardando"
        )
        review_status = summary.get("gemini_review_status", "pending")
        rating_label = "Classificação final" if review_status in {"accepted", "corrected"} else "Classificação sugerida"
        st.metric(rating_label, final_rating)
        latency = summary.get("gemini_latency_ms")
        if latency:
            st.caption(f"Análise concluída em {latency / 1000:.1f}s")


    # Gemini Review & Human Decision Block
    if summary.get("ai_provider") == "Google Gemini":
        with st.container(border=True):
            st.markdown("### Análise")
            st.write(summary.get("gemini_summary", "Sem resumo disponível."))

            searches = summary.get("gemini_search_queries", [])
            citations = summary.get("gemini_web_citations", [])
            if searches or citations:
                with st.expander("Fontes e pesquisa", expanded=False):
                    if searches:
                        st.caption(f"Pesquisas realizadas: {' · '.join(searches)}")
                    if citations:
                        quality_map = {
                            "primary_authoritative": "Fonte oficial ou primária",
                            "reputable_secondary": "Fonte secundária confiável",
                            "general_web": "Fonte da web",
                        }
                        for src in citations:
                            q_label = quality_map.get(src.get("source_quality"), "Fonte da web")
                            st.markdown(f"- [{src.get('title', src.get('url'))}]({src.get('url')}) — *{q_label}*")
                    else:
                        st.caption("Nenhuma fonte histórica adequada foi encontrada.")

            if review_status == "accepted":
                st.success(f"Resultado confirmado: {final_rating}")
            elif review_status == "corrected":
                st.success(f"Resultado alterado e confirmado: {final_rating}")
                if summary.get("gemini_correction"):
                    st.caption(f"Observação: {summary['gemini_correction']}")
            elif review_status == "rejected":
                st.warning("Resultado descartado. Execute uma nova análise quando quiser tentar novamente.")
            else:
                st.markdown("#### Sua decisão")
                b1, b2 = st.columns([3, 1])
                if b1.button("Confirmar resultado", key="btn_accept", type="primary", use_container_width=True):
                    summary["gemini_review_status"] = "accepted"
                    st.session_state["draft"] = draft
                    save_session(st.session_state["task"], draft, "approved", st.session_state.get("session_id"))
                    st.rerun()
                if b2.button("Descartar", key="btn_reject", use_container_width=True):
                    summary["gemini_review_status"] = "rejected"
                    st.session_state["draft"] = draft
                    save_session(st.session_state["task"], draft, "discarded", st.session_state.get("session_id"))
                    st.rerun()

                with st.expander("Escolher outra classificação", expanded=False):
                    st.caption("Use esta opção somente quando você discordar da classificação sugerida.")
                    corr_rating = st.selectbox(
                        "Classificação correta",
                        ["Inaccurate", "Unsupported", "Disputed", "Accurate", "Can't confidently assess", "No claims present"],
                        index=None,
                        placeholder="Selecione uma classificação",
                        key="corr_rating",
                    )
                    corr_text = st.text_input(
                        "Observação opcional",
                        key="corr_notes",
                        placeholder="Ex.: A fonte oficial confirma outra data.",
                    )
                    if st.button("Confirmar alteração", key="btn_save_corr", disabled=corr_rating is None):
                        summary["gemini_review_status"] = "corrected"
                        summary["gemini_correction"] = corr_text.strip()
                        summary["human_corrected_rating"] = corr_rating
                        for evaluation in draft.get("result_evaluations", []):
                            evaluation["factuality_rating"] = corr_rating
                        st.session_state["draft"] = draft
                        save_session(st.session_state["task"], draft, "approved", st.session_state.get("session_id"))
                        st.rerun()

    # Detailed Claims Breakdown
    if draft.get("result_evaluations"):
        with st.expander("Como o agente chegou a essa conclusão", expanded=False):
            evaluations = draft["result_evaluations"]
            for index, eval_item in enumerate(evaluations, start=1):
                if len(evaluations) > 1:
                    st.markdown(f"**Afirmação {index}**")
                st.caption(f"Classificação: {eval_item.get('factuality_rating') or final_rating}")
                st.write(eval_item.get("reasoning", ""))
                if eval_item.get("evidence_required"):
                    st.caption(f"Limitação: {', '.join(eval_item['evidence_required'])}")

    # Guideline Citations
    if draft.get("source_citations"):
        with st.expander("Diretrizes consultadas", expanded=False):
            for cite in draft["source_citations"]:
                st.markdown(format_guideline_citation(cite), unsafe_allow_html=True)
