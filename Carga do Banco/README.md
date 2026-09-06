# Carga e Persistência — DashboardIbovespa

Este diretório documenta e automatiza a etapa de **persistência dos dados consolidados no SQL Server** do projeto acadêmico **Dashboard Analítico de Análise Fundamentalista**.

A base utilizada é produzida pelo **Coletor Parametrizado V7 — Database Ready**, que consolida dados de cinco empresas do Ibovespa para os exercícios de 2023 a 2025, utilizando 2022 como período auxiliar (*bootstrap*) para cálculos TTM e YoY.

## Objetivo

A etapa de carga transforma os arquivos CSV consolidados em um modelo relacional/analítico no SQL Server, pronto para consumo pelo Power BI.

Fluxo da solução:

```text
CVM + RI + Yahoo Finance
          ↓
Coletor Parametrizado V7
          ↓
CSVs consolidados
          ↓
Carga Python + pyodbc
          ↓
SQL Server — DashboardIbovespa
          ↓
Power BI
```

## Estrutura do banco

O banco `DashboardIbovespa` é composto por:

| Tabela | Finalidade | Granularidade |
|---|---|---|
| `DimEmpresa` | Cadastro das cinco empresas | 1 linha por empresa |
| `DimData` | Calendário para análise temporal e drill-down | 1 linha por dia |
| `DimPeriodoSemestral` | Períodos analíticos do trabalho | 1 linha por semestre |
| `FatoFinanceiroSemestral` | Dados contábeis e de mercado por semestre | empresa + semestre |
| `FatoIndicadorSemestral` | Indicadores fundamentalistas | empresa + semestre |
| `FatoPrecoDiario` | Histórico diário de preços | empresa + pregão |
| `FatoProvento` | Dividendos e JCP | empresa + evento |
| `HistoricoAcoes` | Quantidade histórica de ações em circulação | empresa + data |

A `DimData` contém **1.461 datas**, de `2022-01-01` a `2025-12-31`, permitindo montar no Power BI a hierarquia:

```text
Ano → Trimestre → Mês → Dia
```

## Arquivos desta etapa

```text
01_criar_banco_dashboard_ibovespa_v2.sql
02_corrigir_popular_dimdata.sql
03_popular_dimempresa.sql
04_carga_banco_dashboard_v2.py
05_validar_carga_banco.sql
requirements_carga_banco.txt
README.md
```

### `01_criar_banco_dashboard_ibovespa_v2.sql`

Cria o banco, as dimensões, as tabelas fato, chaves primárias, chaves estrangeiras, restrições de unicidade e índices. Também cria a estrutura da `DimData` e da `DimPeriodoSemestral`.

### `02_corrigir_popular_dimdata.sql`

Popula a `DimData` com o intervalo de 2022 a 2025. Este script também registra a correção aplicada à primeira versão do `INSERT`, na qual `DataCompleta` não estava presente na lista do `SELECT`.

### `03_popular_dimempresa.sql`

Insere as cinco empresas validadas na dimensão de empresas:

- Smart Fit — `SMFT3`
- TOTVS — `TOTS3`
- Porto Seguro — `PSSA3`
- MRV — `MRVE3`
- Localiza — `RENT3`

### `04_carga_banco_dashboard_v2.py`

Automatiza a carga dos seis CSVs consolidados. O script:

1. valida a presença dos arquivos;
2. confere as contagens esperadas e possíveis duplicidades;
3. conecta ao SQL Server via `pyodbc`;
4. sincroniza a `DimEmpresa`;
5. confirma `DimData`, `DimPeriodoSemestral` e `DimEmpresa`;
6. limpa as tabelas fato para permitir uma recarga idempotente;
7. converte `empresa_chave` em `EmpresaID`;
8. converte datas em `DataID` no formato `YYYYMMDD`;
9. carrega as cinco tabelas fato;
10. valida as contagens finais;
11. executa `COMMIT` somente se toda a carga terminar corretamente.

Em caso de erro, é executado `ROLLBACK`, evitando carga parcial.

### `05_validar_carga_banco.sql`

Executa as validações finais de integridade, incluindo:

- contagens gerais;
- unicidade de empresa + semestre;
- quantidade de pregões por empresa;
- intervalo do histórico de ações;
- quantidade de eventos de proventos;
- amostra dos sete indicadores;
- P/L não interpretável da MRV;
- não comparabilidade da Localiza em 1S/2023.

## Pré-requisitos

- SQL Server 2022/2025 ou versão compatível;
- SQL Server Management Studio (SSMS);
- Python 3.10+;
- ODBC Driver 18 for SQL Server (ou compatível);
- autenticação Windows disponível para a instância;
- CSVs consolidados gerados pelo Coletor Parametrizado V7.

Dependências Python:

```text
pandas>=2.2
pyodbc>=5.1
```

Instalação:

```bash
pip install -r requirements_carga_banco.txt
```

## CSVs esperados

A pasta informada ao script Python deve conter:

```text
empresas.csv
financeiro_semestral_todas_empresas.csv
indicadores_todas_empresas.csv
precos_diarios_todas_empresas.csv
dividendos_todas_empresas.csv
acoes_em_circulacao_todas_empresas.csv
```

Contagens da base V7 validada:

| Arquivo | Registros |
|---|---:|
| `empresas.csv` | 5 |
| `financeiro_semestral_todas_empresas.csv` | 30 |
| `indicadores_todas_empresas.csv` | 30 |
| `precos_diarios_todas_empresas.csv` | 3.745 |
| `dividendos_todas_empresas.csv` | 49 |
| `acoes_em_circulacao_todas_empresas.csv` | 1.840 |

## Ordem de execução

### 1. Criar o banco e as tabelas

No SSMS, execute:

```text
01_criar_banco_dashboard_ibovespa_v2.sql
```

### 2. Popular a DimData

Execute:

```text
02_corrigir_popular_dimdata.sql
```

Resultado esperado:

```text
TotalDatas: 1461
PrimeiraData: 2022-01-01
UltimaData: 2025-12-31
```

### 3. Popular a DimEmpresa

Execute:

```text
03_popular_dimempresa.sql
```

Resultado esperado: **5 empresas**.

### 4. Instalar dependências

```bash
pip install -r requirements_carga_banco.txt
```

### 5. Executar a carga automatizada

Exemplo no Windows:

```bat
python 04_carga_banco_dashboard_v2.py ^
  --servidor localhost ^
  --banco DashboardIbovespa ^
  --pasta "C:\caminho\para\saida_empresas\consolidado"
```

Autenticação padrão: **Windows / Trusted Connection**.

### 6. Validar no SSMS

Execute:

```text
05_validar_carga_banco.sql
```

## Resultado final validado

A carga final foi concluída com sucesso e resultou em:

| Tabela | Registros |
|---|---:|
| `DimEmpresa` | 5 |
| `DimData` | 1.461 |
| `DimPeriodoSemestral` | 6 |
| `FatoFinanceiroSemestral` | 30 |
| `FatoIndicadorSemestral` | 30 |
| `FatoPrecoDiario` | 3.745 |
| `FatoProvento` | 49 |
| `HistoricoAcoes` | 1.840 |

As verificações adicionais também foram aprovadas:

- 1 registro financeiro por empresa + semestre;
- 1 registro de indicadores por empresa + semestre;
- 749 pregões para cada ticker entre 02/01/2023 e 30/12/2025;
- MRV com `PLInterpretabilidade = NAO_INTERPRETAVEL` nos seis períodos;
- Localiza em 1S/2023 com `ComparabilidadeYoY = NAO_COMPARAVEL`.

## Tratamento de erros e correções aplicadas

Durante a implementação foram identificados e corrigidos três pontos importantes:

### DimData não populada

A primeira versão do `INSERT` possuía uma coluna a mais na lista de destino do que na lista do `SELECT`. A correção adicionou `DataCompleta` explicitamente ao `SELECT`.

### `unicodeescape` no Python

Um caminho Windows presente no *docstring* inicial do script continha `\U`, interpretado pelo Python como início de escape Unicode. O texto foi convertido para *raw string*.

### `Converting decimal loses precision`

O `pyodbc`/ODBC Driver 18 apresentou erro ao enviar objetos `Decimal` em `executemany`. A versão final envia valores numéricos como `float`, mantendo as colunas `DECIMAL` no SQL Server, e desativa `fast_executemany` para maior compatibilidade.

## Reexecução segura

Por padrão, o carregador remove os registros das tabelas fato antes de uma nova carga. Isso permite reconstruir a camada analítica sem duplicar dados.

A opção abaixo existe para casos específicos:

```text
--sem-limpar
```

Ela **não é recomendada** na rotina normal, pois as restrições `UNIQUE` impedem duplicidades e uma carga incremental não foi implementada nesta etapa.

## Integração com Power BI

O banco foi estruturado para ser consumido diretamente pelo Power BI. Recomenda-se importar as oito tabelas e utilizar:

- `DimEmpresa` como dimensão comum;
- `DimPeriodoSemestral` para os indicadores semestrais;
- `DimData` para preços diários e drill-down temporal;
- fatos separados por granularidade para evitar agregações incorretas.

## Uso acadêmico

A camada de persistência foi desenvolvida para demonstrar organização, integridade, reprodutibilidade e rastreabilidade no projeto acadêmico. Ela não constitui sistema de negociação ou recomendação de investimento.
