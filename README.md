# Dashboard Analítico — Análise Fundamentalista de Empresas do Ibovespa

Projeto acadêmico desenvolvido para a disciplina de **Projeto de Desenvolvimento de Dashboard Analítico**, com o objetivo de realizar uma análise exploratória de empresas que compõem o **Ibovespa**, utilizando dados financeiros, indicadores fundamentalistas, banco de dados estruturado e visualização no Power BI.

O repositório organiza duas ferramentas principais do projeto:

- **Coletor** — responsável pela coleta, tratamento, padronização e consolidação dos dados.
- **Carga do Banco** — responsável pela criação, carga e validação do banco SQL Server utilizado pelo Power BI.

---

## Objetivo do projeto

A atividade propõe:

- selecionar 5 empresas do Ibovespa;
- analisar os últimos 3 exercícios completos;
- persistir os dados em um banco estruturado;
- calcular indicadores fundamentalistas;
- construir dashboards analíticos no Power BI;
- acompanhar preços históricos com drill-down até o nível diário;
- interpretar os resultados e produzir um artigo acadêmico.

As empresas selecionadas foram:

| Empresa | Ticker |
|---|---|
| Smart Fit | `SMFT3` |
| TOTVS | `TOTS3` |
| Porto Seguro | `PSSA3` |
| MRV | `MRVE3` |
| Localiza | `RENT3` |

O período principal de análise é **2023 a 2025**. Dados de 2022 são utilizados apenas como apoio para cálculos TTM e comparações YoY.

---

## Arquitetura da solução

```text
CVM + Relações com Investidores + Yahoo Finance
                     ↓
              Coletor Python
                     ↓
          Tratamento e validação
                     ↓
            CSVs consolidados
                     ↓
          Carga via Python/pyodbc
                     ↓
        SQL Server — DashboardIbovespa
                     ↓
                 Power BI
```

---

## 1. Coletor

A pasta **`Coletor/`** contém a ferramenta responsável por:

- coletar dados contábeis da CVM;
- coletar preços e dados de mercado via `yfinance`;
- utilizar eventos de dividendos e JCP validados em fontes oficiais de RI;
- construir dados financeiros semestrais;
- calcular indicadores fundamentalistas;
- aplicar ajustes históricos documentados;
- consolidar os dados das cinco empresas.

### Indicadores calculados

O projeto utiliza 7 indicadores:

- P/L
- P/VP
- ROE
- ROA
- Dividend Yield
- Margem Líquida
- Crescimento de Receita

A ferramenta também mantém informações de auditoria e regras de interpretação, como P/L não interpretável em períodos de prejuízo.

> A pasta `Coletor/` possui um README próprio com instruções detalhadas de instalação, execução e metodologia.

---

## 2. Carga do Banco

A pasta **`Carga do Banco/`** contém os scripts responsáveis por:

- criar o banco `DashboardIbovespa`;
- criar dimensões e tabelas fato;
- popular a dimensão de datas;
- carregar os CSVs consolidados no SQL Server;
- relacionar empresas, períodos e datas por chaves;
- validar integridade e quantidade de registros.

### Estrutura principal do banco

```text
DimEmpresa
DimData
DimPeriodoSemestral

FatoFinanceiroSemestral
FatoIndicadorSemestral
FatoPrecoDiario
FatoProvento
HistoricoAcoes
```

A `DimData` foi criada para permitir no Power BI o drill-down:

```text
Ano → Trimestre → Mês → Dia
```

> A pasta `Carga do Banco/` possui um README próprio com instruções de criação, carga e validação do banco.

---

## Situação atual

```text
Coleta             ✅
Tratamento         ✅
Validação          ✅
Consolidação       ✅
Persistência SQL   ✅
Power BI           ⏳
Artigo final       ⏳
```

O banco atualmente contém:

- 5 empresas;
- 6 períodos semestrais;
- 30 registros financeiros;
- 30 registros de indicadores;
- 3.745 registros de preços diários;
- 49 eventos de proventos;
- 1.840 registros de histórico de ações;
- 1.461 registros na dimensão de datas.

---

## Integração com o Power BI

O banco `DashboardIbovespa` será utilizado como fonte de dados do Power BI.

Os dashboards deverão permitir:

- acompanhar a evolução dos indicadores ao longo do tempo;
- comparar as cinco empresas;
- visualizar preços históricos;
- realizar drill-down temporal;
- apresentar KPIs, linhas, barras/colunas e matrizes;
- apoiar a análise interpretativa e o storytelling com dados.

---

## Estrutura do repositório

```text
.
├── Coletor/
│   ├── coletor_parametrizado.py
│   ├── arquivos de configuração
│   └── README.md
│
├── Carga do Banco/
│   ├── scripts SQL
│   ├── script Python de carga
│   ├── requirements
│   └── README.md
│
└── README.md
```

---

## Finalidade acadêmica

Este projeto foi desenvolvido com finalidade **acadêmica e analítica**.

Os dados utilizados foram obtidos de fontes públicas e institucionais, incluindo:

- CVM — Dados Abertos;
- páginas oficiais de Relações com Investidores;
- Yahoo Finance via `yfinance`.

O projeto não constitui recomendação de investimento.

---

## Próximas etapas

- conectar o Power BI ao SQL Server;
- configurar os relacionamentos do modelo;
- criar medidas DAX;
- desenvolver os dashboards;
- realizar a análise dos resultados;
- produzir o artigo acadêmico final conforme o Guia de Normalização da UniSales.
