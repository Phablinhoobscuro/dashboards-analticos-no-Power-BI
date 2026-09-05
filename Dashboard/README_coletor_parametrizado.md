# Coletor parametrizado — Dashboard Analítico

## Arquivos necessários na mesma pasta

- `coletor_parametrizado.py`
- `empresas_dashboard.json`
- `proventos_oficiais.csv`

## Dependências

```bash
pip install -r requirements_coletor_parametrizado.txt
```

## Listar empresas

```bash
python coletor_parametrizado.py --listar
```

## Executar uma empresa

```bash
python coletor_parametrizado.py --empresa smartfit
python coletor_parametrizado.py --empresa totvs
python coletor_parametrizado.py --empresa porto
python coletor_parametrizado.py --empresa mrv
python coletor_parametrizado.py --empresa localiza
```

## Executar todas

```bash
python coletor_parametrizado.py --todas
```

## Estrutura de saída

```text
saida_empresas/
├── _cache_cvm/
├── smartfit/
├── totvs/
├── porto/
├── mrv/
├── localiza/
└── consolidado/
```

O cache evita baixar os mesmos ZIPs anuais da CVM para cada empresa.

## Metodologia

- ITR 30/06 = primeiro semestre.
- DFP 31/12 = balanço anual.
- Segundo semestre da DRE = DFP anual - ITR acumulada de 30/06.
- P/L, ROE, ROA e Margem usam TTM quando aplicável.
- Crescimento da Receita = YoY por semestre.
- Preços = yfinance.
- Dividendos/JCP = RI oficial quando o histórico é suficientemente detalhado.

## Status inicial dos proventos

- Smart Fit: completo.
- TOTVS: completo.
- Localiza: completo.
- MRV: histórico oficial consultado sem eventos em 2023-2025.
- Porto Seguro: o RI fornece agregado anual; o DY semestral fica NaN nesta versão.

## Ordem recomendada de testes

1. `--empresa smartfit` para conferir que a parametrização reproduz a empresa-piloto.
2. `--empresa totvs` e validar todos os resultados.
3. Localiza.
4. MRV.
5. Porto Seguro por último, pois seguradoras podem exigir tratamento contábil específico.

Não considere uma nova empresa validada apenas porque o script terminou sem erro.
Confira pelo menos Ativo, Patrimônio, Receita, Lucro e os sete indicadores.
