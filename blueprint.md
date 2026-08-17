# Blueprint - Factuality AI Assessor

Status: Versão final escalonada para entrega do Challenge Alura Agente  
Projeto: Challenge Alura Agente - AI Tech Builder  
Objetivo: Criar um assistente inteligente e auditável para avaliação de factualidade (*Factuality Evaluation*) em respostas de modelos de IA, baseado em leitura de diretrizes normativas (RAG de PDF), pesquisa autônoma de evidências Web e revisão humana obrigatória.

---

## 1. Visão do Produto

O **Factuality AI Assessor** é um agente inteligente que recebe uma tarefa de checagem factual composta por:
1. **User Query** (a pergunta original do usuário);
2. **Contexto Completo da Resposta** (o texto gerado pela IA avaliada);
3. **Highlighted Target Content** (a afirmação/claim específica sob escopo);
4. **Metadados Temporais e Locais** (Data da resposta, Locale e Localização).

O agente processa uma diretriz de avaliação em PDF, recupera as regras aplicáveis, busca evidências em fontes autoritativas na Web, avalia o claim no Gemini 3.6 Flash e entrega um rascunho estruturado e auditável para confirmação humana.

### Fora de Escopo
- Submissão automatizada de ratings sem revisão humana.
- Modos não-factuais legados (Side-by-Side genérico, Page Quality puro e YouTube/Maps descartados no refino do escopo).
- Publicação de dados sensíveis ou diretrizes proprietárias restritas no repositório público.

---

## 2. Fontes de Conhecimento e RAG

O agente ingere documentos normativos via `pypdf`, segmenta por páginas e seções estruturadas e constrói um índice léxico local com metadados de origem.

Precedência de consulta:
1. Caminho definido em `FACTUALITY_GUIDELINES_PATH` (documento privado local, quando presente).
2. `data/sample_factuality_guide.pdf` (guia sintético padronizado para execução pública e reprodutibilidade).

### Escala Oficial de Factualidade
- **Accurate**: Afirmação confirmada por fontes autoritativas e primárias.
- **Inaccurate**: Afirmação refutada diretamente por evidências oficiais.
- **Unsupported**: Afirmação verificável que não possui sustentação em fontes confiáveis.
- **Disputed**: Fontes de alta autoridade discordam formalmente entre si sem consenso.
- **Can't confidently assess**: Evidência inacessível ou insuficiente para emitir julgamento.
- **No claims present**: O texto contém apenas opiniões, saudações ou conselhos não-factuais.

---

## 3. Fluxo Funcional do Agente

```text
Entrada da Tarefa (Query + Resposta + Claim Destacado)
                    │
                    ▼
 RAG Local: Recuperação das Regras e Critérios (PDF)
                    │
                    ▼
 Pesquisa Autônoma de Evidências Web (Google Search + URL Context)
   - Descoberta suplementar via DDGS
   - Filtro de autoridade (.gov, acadêmico, oficial)
   - Extração do trecho relevante da fonte primária
                    │
                    ▼
 Análise Estruturada via Google GenAI SDK (Gemini 3.6 Flash)
   - Validação estrita de schema Pydantic
   - Justificativa, links de evidência e gaps
                    │
                    ▼
 Interface Operacional Streamlit (Histórico + Decisão Humana)
   [ Aceitar Sugestão ]  [ Rejeitar ]  [ Registrar Correção ]
```

---

## 4. Arquitetura Técnica

- **Linguagem**: Python 3.11+
- **Interface Web**: Streamlit (UI reativa, intuitiva e operacional)
- **Leitura de Documentos**: `pypdf` para extração de texto estruturado
- **RAG & Indexação**: `src/retrieval.py` com busca léxica e metadados de seção/página
- **Pesquisa de Evidências**: `ddgs` com ranqueamento determinístico de autoridade e relevância
- **Modelo de IA**: `google-genai` com `gemini-3.6-flash` (Structured JSON Outputs)
- **Validação de Dados**: `pydantic` v2
- **Testes**: `pytest` com toda a suíte automatizada passando
- **Deploy principal**: Python 3.11 + systemd em OCI Compute, otimizado para a shape Always Free de 1 GB
- **Deploy de contingência**: Streamlit Community Cloud, caso seja necessária uma URL pública adicional

---

## 5. Histórico e Auditoria Local

Cada sessão analisada gera um registro em `logs/sessions/` com timestamp, tarefa original, sugestão da IA, fontes recuperadas e a decisão do assessor humano (`accepted`, `rejected`, `corrected`), garantindo auditabilidade completa. O histórico pode ser exportado e importado em JSON pela interface.
