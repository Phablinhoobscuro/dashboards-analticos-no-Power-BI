# Coletor Parametrizado V7 — Database Ready

Esta versão mantém todas as regras validadas da V6 e acrescenta uma correção
de qualidade no histórico de ações em circulação retornado pelo `yfinance`.

## Motivo da V7

Na auditoria dos arquivos consolidados, o histórico de ações possuía:

- 2267 linhas;
- 427 chaves duplicadas de `empresa_chave + data`;
- valores distintos em algumas duplicidades.

O problema vinha do próprio histórico retornado pelo provedor, que pode apresentar
mais de uma observação para a mesma data.

## Regra aplicada

O coletor agora:

1. ordena as observações de ações por data usando ordenação estável;
2. para uma mesma data, mantém a última observação retornada;
3. garante uma única linha por `empresa + data`.

Simulação sobre a base consolidada existente:

- antes: 2267 registros;
- depois: 1840 registros;
- removidos: 427 registros duplicados;
- alterações nos 30 valores semestrais já usados nos indicadores: 0.

Portanto, a correção melhora a integridade para carga no banco sem alterar os
indicadores semestrais previamente validados.

## Execução final

```bash
python coletor_parametrizado.py --todas
```

Depois da nova execução, `acoes_em_circulacao_todas_empresas.csv` deve possuir
chave única por `empresa_chave + data`.

A V7 deve ser utilizada como versão final para persistência em banco de dados.
