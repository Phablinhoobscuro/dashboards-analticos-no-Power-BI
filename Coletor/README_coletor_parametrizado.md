# Coletor Parametrizado V5 — MRV corrigida

Mantém todas as correções anteriores de Smart Fit, TOTVS e Localiza.

## 1. Bootstrap de dividendos MRV 2022

Foi incluído o evento de 21/09/2022:

- Tipo: Dividendo
- Valor: R$ 0,1978084 por ação
- Pagamento: 04/10/2022
- Fonte: RI oficial da MRV

Esse valor é usado apenas porque entra na janela TTM do Dividend Yield
em 30/06/2023.

## 2. Interpretabilidade do P/L

O arquivo de indicadores agora recebe duas colunas:

- `pl_interpretabilidade`
- `motivo_pl_interpretabilidade`

Regra:

- lucro TTM > 0  -> `INTERPRETAVEL`
- lucro TTM <= 0 -> `NAO_INTERPRETAVEL`
- lucro ausente  -> `INDETERMINADO`

O valor numérico do P/L continua salvo para auditoria.

## Valores esperados para a MRV

Depois da execução:

- DY 1S23 deve ficar próximo de 1,71%
- DY dos demais períodos deve permanecer 0%
- P/L continua numericamente negativo quando houver prejuízo TTM
- `pl_interpretabilidade` deve ficar `NAO_INTERPRETAVEL` nos períodos
  em que o lucro TTM for não positivo

## Execução

Os arquivos do ZIP já estão com os nomes esperados pelo script.

```bash
python coletor_parametrizado.py --empresa mrv
```

Depois valide principalmente:
- `dividendos_por_acao_12m_brl` em 30/06/2023
- `dividend_yield_12m_pct`
- `pl_interpretabilidade`
