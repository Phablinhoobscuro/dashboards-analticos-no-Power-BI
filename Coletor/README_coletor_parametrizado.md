# Coletor Parametrizado V3 — ajuste histórico TOTVS 1S24

Esta versão mantém as correções da V2 e adiciona uma camada genérica de
`ajustes_historicos.csv`.

## Por que ela existe?

A TOTVS reapresentou no ITR de 30/06/2025 o comparativo de 1S24 com valores
reclassificados. O layout padronizado da CVM não oferece, para todas as
demonstrações, o mesmo comparativo de data-base que usamos no modelo.

Por isso, o coletor:
1. coleta normalmente a CVM;
2. aplica somente os campos documentados em `ajustes_historicos.csv`;
3. recalcula o 2S do mesmo ano para manter o total anual;
4. depois calcula TTM, YoY e indicadores.

## Ajustes TOTVS 1S24

- Receita: R$ 2.497.689.000
- Lucro Líquido Consolidado: R$ 250.076.000
- Lucro atribuível aos controladores: R$ 241.521.000

Fonte: ITR TOTVS de 30/06/2025, comparativo acumulado de 01/01/2024 a 30/06/2024.

## O que NÃO é alterado

Ativo e Patrimônio Líquido de 30/06/2024 continuam vindo da demonstração de
posição utilizada originalmente, porque o ajuste documentado é referente à DRE.

## Auditoria

O CSV financeiro inclui:
- `ajuste_historico_aplicado`
- `campos_ajustados`
- `fonte_ajuste_historico`
- `motivo_ajuste_historico`

## Arquivos necessários

O script procura estes nomes:
- `empresas_dashboard.json`
- `proventos_oficiais.csv`
- `ajustes_historicos.csv`

## Execução

```bash
python coletor_parametrizado.py --empresa totvs
```

Depois valide principalmente:
- 1S24 Receita = 2.497.689.000
- 1S24 Lucro Consolidado = 250.076.000
- 1S24 Lucro Controladores = 241.521.000
- 2S24 recalculado automaticamente
- Crescimento YoY 1S25 próximo de 18,11%
