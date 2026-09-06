# Coletor Parametrizado — CVM + Mercado + RI

Ferramenta em Python desenvolvida para o projeto acadêmico de **Dashboard Analítico de Análise Fundamentalista**, responsável por coletar, padronizar, enriquecer, validar e consolidar dados financeiros e de mercado de cinco companhias brasileiras.

A versão documentada neste repositório é a **V6**, consolidada após a validação individual das empresas:

| Empresa | Ticker | Setor |
|---|---|---|
| Smart Fit | `SMFT3` | Consumo Cíclico / Academias |
| TOTVS | `TOTS3` | Tecnologia da Informação / Software |
| Porto Seguro | `PSSA3` | Financeiro / Seguros |
| MRV | `MRVE3` | Consumo Cíclico / Construção Civil |
| Localiza | `RENT3` | Consumo Cíclico / Aluguel de carros |

## Objetivo

O coletor foi criado para montar uma base histórica estruturada de **2023 a 2025**, com dados semestrais e preços diários, permitindo posteriormente:

- persistência em banco de dados;
- modelagem no Power BI;
- cálculo e acompanhamento de indicadores fundamentalistas;
- análise temporal;
- rastreabilidade das fontes e dos ajustes aplicados;
- reprodução da coleta para todas as empresas com um único comando.

Para o cálculo de indicadores de 12 meses e do crescimento YoY no início da série, o ano de **2022** é utilizado internamente como *bootstrap*. Os arquivos principais entregues ao projeto permanecem concentrados em 2023–2025.

---

## Fontes de dados

### 1. CVM — Dados Abertos

Fonte principal dos dados contábeis.

Base utilizada:

`https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC`

O coletor trabalha com demonstrações **consolidadas**:

- `ITR` para o primeiro semestre;
- `DFP` para o encerramento anual;
- `BPA` — Balanço Patrimonial Ativo;
- `BPP` — Balanço Patrimonial Passivo;
- `DRE` — Demonstração do Resultado.

Metodologia semestral:

```text
1S = ITR de 30/06
2S = DFP anual - resultado acumulado do ITR de 30/06
```

A maior `VERSAO` disponível na CVM é preservada. Quando configurado para uma companhia, o coletor também tenta utilizar o comparativo `PENULTIMO` divulgado no exercício seguinte, permitindo incorporar reclassificações históricas.

### 2. Yahoo Finance via `yfinance`

Utilizado para:

- preços diários;
- último preço de fechamento disponível até a data-base;
- histórico de ações em circulação, quando disponibilizado;
- snapshot de informações de mercado.

A coleta é executada com `auto_adjust=False`, preservando o fechamento informado na série histórica.

> O Yahoo Finance é uma fonte externa não oficial. Os dados contábeis e os proventos utilizados na metodologia não dependem dele como fonte primária.

### 3. Relações com Investidores — RI

Os dividendos e Juros sobre Capital Próprio (JCP) são mantidos no arquivo curado:

```text
proventos_oficiais.csv
```

Cada evento possui sua fonte oficial de RI. O script **não faz scraping do RI em tempo de execução**; ele consome um snapshot auditável de eventos previamente validados.

---

## Indicadores calculados

O coletor gera sete indicadores principais.

| Indicador | Fórmula usada |
|---|---|
| P/L | Valor de mercado / Lucro atribuível aos controladores TTM |
| P/VP | Valor de mercado / Patrimônio atribuível aos controladores |
| ROE | Lucro atribuível aos controladores TTM / Patrimônio atribuível aos controladores × 100 |
| ROA | Lucro líquido consolidado TTM / Ativo total × 100 |
| Margem Líquida | Lucro líquido consolidado TTM / Receita TTM × 100 |
| Dividend Yield | Proventos por ação dos últimos 12 meses / Preço de referência × 100 |
| Crescimento de Receita | Receita do semestre atual vs. mesmo semestre do ano anterior |

`TTM` (*Trailing Twelve Months*) corresponde à soma dos dois últimos semestres.

O valor de mercado de referência é estimado por:

```text
Valor de mercado = Preço de fechamento de referência × Ações em circulação
```

O preço utilizado é o último fechamento disponível **até** a data contábil do semestre.

---

## Regras de qualidade e interpretação

### P/L negativo

O valor numérico do P/L é preservado para auditoria, mas recebe uma classificação adicional:

```text
lucro TTM > 0   -> INTERPRETAVEL
lucro TTM <= 0  -> NAO_INTERPRETAVEL
```

Isso evita interpretar P/L negativo como sinal de ação “barata”.

### Crescimento YoY não comparável

O coletor permite marcar períodos em que o crescimento é matematicamente calculável, porém não diretamente comparável economicamente.

Exemplo: `RENT3` em `1S/2023`, devido à combinação de negócios Localiza/Locamerica efetiva em 2022.

### Ajustes históricos documentados

Casos especiais são registrados em:

```text
ajustes_historicos.csv
```

O ajuste é aplicado apenas ao campo explicitamente informado, mantendo:

- fonte;
- motivo;
- data de referência;
- campo alterado;
- valor adotado.

Quando um campo de fluxo do primeiro semestre é ajustado, o segundo semestre é recalculado de forma a preservar o total anual validado.

---

## Tratamentos específicos validados

A ferramenta é parametrizada, mas a validação foi realizada empresa a empresa.

- **Smart Fit** — empresa-piloto usada para validar o fluxo completo.
- **TOTVS** — utilização de comparativos reapresentados e ajuste documentado da DRE de 1S/2024.
- **Localiza** — correção documentada do lucro atribuível aos controladores em 1S/2024 e marcação de não comparabilidade de 1S/2023.
- **MRV** — inclusão de provento de 2022 necessário ao DY TTM de 1S/2023 e classificação do P/L negativo.
- **Porto Seguro** — histórico detalhado de JCP/dividendos de 2022–2025 baseado em avisos oficiais aos acionistas.

---

## Estrutura do projeto

```text
.
├── coletor_parametrizado.py
├── empresas_dashboard.json
├── proventos_oficiais.csv
├── ajustes_historicos.csv
├── requirements_coletor_parametrizado.txt
└── saida_empresas/
    ├── _cache_cvm/
    ├── smartfit/
    ├── totvs/
    ├── porto/
    ├── mrv/
    ├── localiza/
    └── consolidado/
```

Arquivos de configuração:

### `empresas_dashboard.json`

Define, por empresa:

- razão social;
- CNPJ;
- ticker B3;
- ticker Yahoo;
- setor;
- contas CVM utilizadas;
- endereço do RI;
- regras de proventos;
- uso de comparativos reapresentados;
- observações e exceções de comparabilidade.

### `proventos_oficiais.csv`

Snapshot dos eventos de dividendos e JCP validados em fontes oficiais.

### `ajustes_historicos.csv`

Correções/reclassificações pontuais que não podem ser recuperadas automaticamente com segurança apenas pela estrutura padronizada da CVM.

---

## Requisitos

Recomendado:

- Python 3.10 ou superior;
- conexão com a internet;
- Windows, Linux ou macOS.

Dependências:

```text
pandas
numpy
requests
yfinance
scipy
```

Instalação:

```bash
pip install -r requirements_coletor_parametrizado.txt
```

> `scipy` é necessário para o modo de reparo utilizado pelo `yfinance`.

---

## Como executar

### Listar empresas configuradas

```bash
python coletor_parametrizado.py --listar
```

### Executar uma empresa

```bash
python coletor_parametrizado.py --empresa smartfit
python coletor_parametrizado.py --empresa totvs
python coletor_parametrizado.py --empresa porto
python coletor_parametrizado.py --empresa mrv
python coletor_parametrizado.py --empresa localiza
```

### Executar todas e consolidar

```bash
python coletor_parametrizado.py --todas
```

### Limpar cache da CVM

```bash
python coletor_parametrizado.py --todas --limpar-cache
```

Os arquivos ZIP anuais da CVM são armazenados em cache compartilhado para evitar downloads repetidos durante a execução das cinco empresas.

---

## Saídas por empresa

Cada execução individual produz:

```text
<empresa>_financeiro_semestral.csv
<empresa>_precos_diarios.csv
<empresa>_dividendos.csv
<empresa>_acoes_em_circulacao.csv
<empresa>_indicadores.csv
<empresa>_info_mercado_atual.json
<empresa>_metadata.json
```

Também é criada a pasta `cvm_filtrado`, útil para auditoria das demonstrações selecionadas.

### Granularidade

| Arquivo | Granularidade |
|---|---|
| `financeiro_semestral` | 1 linha por empresa e semestre |
| `indicadores` | 1 linha por empresa e semestre |
| `precos_diarios` | 1 linha por pregão |
| `dividendos` | 1 linha por evento |
| `acoes_em_circulacao` | 1 linha por observação/data disponível |
| `metadata` | 1 snapshot por execução/empresa |

---

## Consolidação

Ao executar `--todas`, a pasta abaixo é criada:

```text
saida_empresas/consolidado/
```

Arquivos:

```text
empresas.csv
financeiro_semestral_todas_empresas.csv
precos_diarios_todas_empresas.csv
dividendos_todas_empresas.csv
acoes_em_circulacao_todas_empresas.csv
indicadores_todas_empresas.csv
```

Na versão validada do projeto, `indicadores_todas_empresas.csv` contém **30 registros semestrais**:

```text
5 empresas × 6 semestres = 30 registros
```

Esses arquivos são a camada de integração prevista para carga em banco de dados e posterior consumo pelo Power BI.

---

## Fluxo do processamento

```text
CVM (ITR/DFP) ─────────────┐
                           │
Yahoo Finance / yfinance ──┼─> Coletor parametrizado
                           │        │
RI oficial / snapshots ────┘        │
                                    v
                           Padronização e validação
                                    │
                           Ajustes históricos auditáveis
                                    │
                                    v
                            Indicadores fundamentalistas
                                    │
                                    v
                            CSVs por empresa
                                    │
                                    v
                             Base consolidada
                                    │
                                    v
                            Banco de dados / Power BI
```

---

## Cache e rastreabilidade

Os ZIPs da CVM são armazenados em:

```text
saida_empresas/_cache_cvm/
```

Isso melhora o tempo de execução porque os mesmos arquivos anuais são compartilhados entre as empresas.

A rastreabilidade é mantida por colunas como:

- `origem_balanco`;
- `origem_resultado`;
- `comparativo_reapresentado`;
- `ano_documento_fonte`;
- `ordem_exerc_fonte`;
- `ajuste_historico_aplicado`;
- `campos_ajustados`;
- `fonte_ajuste_historico`;
- `motivo_ajuste_historico`.

---

## Cuidados metodológicos

1. Empresas de setores diferentes não devem ser comparadas apenas por um único indicador.
2. Indicadores de seguradoras, como ROA e Margem Líquida, devem ser interpretados considerando particularidades do setor financeiro.
3. P/L negativo é mantido para auditoria, mas classificado como não interpretável.
4. Reclassificações publicadas posteriormente podem alterar comparativos históricos.
5. Preços e quantidade de ações são obtidos de fonte de mercado externa e podem ser reparados/atualizados pelo provedor.
6. Proventos são considerados pela data de **declaração/aprovação**, conforme a metodologia adotada no projeto.
7. O coletor não substitui a validação contábil das demonstrações originais.

---

## Fontes institucionais utilizadas

- CVM Dados Abertos: `https://dados.cvm.gov.br/`
- Smart Fit RI: `https://investor.smartfit.com.br/dividendos-jcp/`
- TOTVS RI: `https://ri.totvs.com/informacoes-financeiras/dividendos-e-jcp/`
- Porto Seguro RI: `https://ri.portoseguro.com.br/governanca-corporativa/dividendos-e-jcp/`
- MRV RI: `https://ri.mrv.com.br/mercados-de-capitais/dividendos-e-jcp/`
- Localiza RI: `https://ri.localiza.com/mercado-de-capitais/dividendos-e-jcp/`

---

## Uso acadêmico

O projeto foi desenvolvido com finalidade acadêmica e analítica. Os dados coletados devem ser conferidos nas fontes originais antes de qualquer uso financeiro, contábil ou de investimento.

O coletor **não constitui recomendação de investimento**.
