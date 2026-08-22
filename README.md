# Assistente de Factualidade

Agente desenvolvido para o Challenge Alura Agente do programa AI Tech Builder. A aplicação ajuda um Internet Assessor a verificar rapidamente afirmações factuais, localizar evidências confiáveis e preparar uma classificação para revisão humana.

## Aplicação publicada

- Aplicação: [http://144.22.136.1:8501](http://144.22.136.1:8501) — IP público reservado na OCI
- Infraestrutura: Oracle Cloud Infrastructure, Oracle Linux 9 e serviço `systemd`
- Evidência visual: [captura neutra da aplicação publicada na OCI](docs/deploy-oci.png)

## Como funciona

1. O avaliador informa a consulta, a resposta completa e o trecho destacado.
2. O mecanismo de recuperação consulta localmente as diretrizes extraídas dos PDFs.
3. O agente pesquisa a web e prioriza fontes oficiais, primárias e especializadas.
4. O Gemini compara a afirmação com as evidências e produz uma classificação justificada.
5. O avaliador humano aceita, rejeita ou corrige o resultado.

O agente nunca envia uma avaliação automaticamente.

## Arquitetura

```text
Interface Streamlit
        |
        v
Entrada estruturada da tarefa
        |
        +--> Recuperação das diretrizes em PDF
        |
        +--> Pesquisa de evidências na web
        |
        v
Análise estruturada com Google Gemini
        |
        v
Resultado, fontes e revisão humana
        |
        v
Histórico local em JSON
```

Principais componentes:

- `app.py`: interface e fluxo de revisão humana.
- `src/retrieval.py`: recuperação local das diretrizes.
- `src/research.py`: pesquisa e seleção de fontes.
- `src/gemini.py`: integração e resposta estruturada do Gemini.
- `src/evaluator.py`: montagem do resultado da avaliação.
- `src/storage.py`: histórico local das tarefas.
- `deploy/oci/setup_vm.sh`: instalação e configuração da aplicação na OCI.

## Tecnologias

| Tecnologia | Finalidade |
| --- | --- |
| Python 3.11 | Aplicação e processamento |
| Streamlit | Interface web |
| Google Gemini e `google-genai` | Análise factual estruturada com Google Search e URL Context |
| DDGS | Descoberta local suplementar de evidências na web |
| PyPDF | Extração das diretrizes em PDF |
| Pydantic | Validação das entradas e respostas |
| Pytest | Testes automatizados |
| OCI Compute e systemd | Hospedagem em nuvem |

## Classificações utilizadas

- `Accurate`: a afirmação é sustentada por evidências confiáveis.
- `Inaccurate`: pelo menos uma afirmação é contradita por evidência confiável.
- `Unsupported`: não há evidência confiável suficiente para avaliar a afirmação.
- `Disputed`: fontes confiáveis apresentam evidências conflitantes.
- `Can't confidently assess`: não é possível avaliar adequadamente.
- `No claims present`: não existe afirmação factual verificável.

Os nomes permanecem em inglês porque correspondem às opções oficiais da tarefa.

## Fluxo de uso

O avaliador informa a consulta, a resposta completa, o trecho destacado, a data e a localização quando forem relevantes. O agente pesquisa evidências, consulta as diretrizes recuperadas e apresenta uma classificação sugerida, uma justificativa curta e as fontes utilizadas. A decisão final permanece com o avaliador humano.

A interface pública não inclui respostas pré-carregadas. Isso evita confundir dados artificiais com demonstrações de capacidade e impede que tarefas privadas sejam distribuídas junto ao projeto.

## Executar localmente no Windows

Clone o repositório e entre na pasta:

```powershell
git clone https://github.com/lsotavio/challenge-alura-agente-factuality-ai-assessor.git
```

```powershell
cd challenge-alura-agente-factuality-ai-assessor
```

Crie e ative o ambiente:

```powershell
py -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

Instale as dependências:

```powershell
pip install -r requirements.txt
```

Configure a chave somente na sessão atual:

```powershell
$env:GEMINI_API_KEY="SUA_CHAVE_GEMINI"
```

Inicie a aplicação:

```powershell
streamlit run app.py
```

Acesse `http://localhost:8501`.

## Testes

```powershell
pytest
```

Os testes cobrem schemas, recuperação de diretrizes, pesquisa e integração do Gemini com respostas simuladas. Esses testes validam o comportamento do software sem consumir cota da API e não são apresentados como avaliações factuais reais.

## Deploy na OCI

O deploy leve não utiliza Docker, devido aos limites da instância Always Free. O instalador prepara swap, Python 3.11, ambiente virtual, segredo protegido e serviço persistente.

```powershell
.\deploy_to_oci.ps1
```

Na primeira execução, informe o caminho completo da chave SSH da instância. Também é possível passar os dados explicitamente:

```powershell
.\deploy_to_oci.ps1 -Ip "144.22.136.1" -SshKey "C:\caminho\para\sua-chave.key"
```

A porta TCP `8501` deve estar liberada na VCN da OCI. A chave Gemini é solicitada de forma oculta pelo PowerShell e armazenada no servidor com acesso restrito.

## Contexto educacional da infraestrutura

O desafio não forneceu créditos ou acesso pago a uma API de LLM; a integração utiliza o free tier do Google AI Studio e está sujeita aos respectivos limites de uso. A instância OCI Always Free de 1 GB também exigiu um deploy leve com swap e `systemd`, sem Docker em produção. Essas condições podem limitar testes contínuos, mas não alteram a arquitetura demonstrada.
