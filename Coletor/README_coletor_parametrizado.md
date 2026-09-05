# Coletor Parametrizado V4 — Localiza corrigida

Mantém todas as correções anteriores de Smart Fit e TOTVS e adiciona
três ajustes para a Localiza (RENT3).

## 1. Bootstrap de JCP 2022

Eventos adicionados:

- 23/09/2022 — R$ 0,354889/ação — pagamento 09/11/2022
- 16/12/2022 — R$ 0,366169/ação — pagamento 13/02/2023

Esses eventos entram no Dividend Yield TTM de 30/06/2023.

## 2. Lucro dos controladores — 1S24

Foi criado um ajuste histórico para:

`lucro_atribuivel_controladores_semestre_brl = +164.345.000`

O coletor recalcula automaticamente o 2S24 para preservar o total anual.

## 3. Comparabilidade YoY — 1S23

O crescimento numérico de 1S23 vs 1S22 é mantido, mas recebe:

- `comparabilidade_yoy = NAO_COMPARAVEL`
- `motivo_comparabilidade_yoy = ...`

Isso ocorre porque a combinação de negócios Localiza/Locamerica (Unidas)
tornou-se efetiva em 01/07/2022, alterando estruturalmente a base comparativa.

## Valores esperados após a execução

- DY 1S23: aproximadamente 2,11%
- Lucro controladores 1S24: +R$ 164.345.000
- Lucro controladores 2S24: aproximadamente R$ 1.649.282.000
- P/L e ROE de 1S24/1S25 serão recalculados
- 1S23 ficará marcado como `NAO_COMPARAVEL`

## Execução

Os arquivos do ZIP já estão com os nomes esperados pelo script.

```bash
python coletor_parametrizado.py --empresa localiza
```
