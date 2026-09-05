# Coletor Parametrizado V6 — Porto Seguro / versão final das 5 empresas

Mantém todas as correções anteriores de Smart Fit, TOTVS, Localiza e MRV
e completa o histórico de proventos da Porto Seguro (PSSA3).

## Metodologia do Dividend Yield

O projeto usa:

`DY TTM = soma dos proventos brutos por ação declarados nos 12 meses anteriores / preço de referência`

A data técnica do evento é a data de declaração/aprovação, e não a data de pagamento.

Isso é importante na Porto porque vários JCP são declarados durante o exercício
e pagos apenas depois da Assembleia do ano seguinte.

Dividendos adicionais entram somente quando são aprovados formalmente.

## Eventos adicionados

### Bootstrap 2022
- 24/08/2022 — JCP — R$ 0,62330389068/ação
- 26/10/2022 — JCP — R$ 0,08777106007/ação

### 2023
- 26/06/2023 — JCP — R$ 0,58940881104/ação
- 25/09/2023 — JCP — R$ 0,29169001539/ação
- 21/12/2023 — JCP — R$ 0,53022069535/ação
- 28/03/2024 — dividendo adicional referente a 2023 — R$ 0,09380122264/ação

### 2024
- 25/03/2024 — JCP — R$ 0,29935563114/ação
- 25/06/2024 — JCP — R$ 0,31918046848/ação
- 24/09/2024 — JCP — R$ 0,40982315690/ação
- 24/12/2024 — JCP — R$ 0,42105133122/ação
- 28/03/2025 — dividendo adicional 1ª parte — R$ 0,12691131299/ação
- 28/03/2025 — dividendo adicional 2ª parte — R$ 0,47889395150/ação

### 2025
- 25/03/2025 — JCP — R$ 0,43273681330/ação
- 23/06/2025 — JCP — R$ 0,48320810620/ação
- 22/09/2025 — JCP — R$ 0,53380435871/ação
- 19/12/2025 — JCP — R$ 0,53760384028/ação

O dividendo adicional referente a 2025 foi aprovado apenas em 31/03/2026;
portanto NÃO entra no DY em 31/12/2025.

## TTM esperado da Porto

- 30/06/2023: R$ 1,30048376179/ação
- 31/12/2023: R$ 1,41131952178/ação
- 30/06/2024: R$ 1,53424803300/ação
- 31/12/2024: R$ 1,54321181038/ação
- 30/06/2025: R$ 2,35262467211/ação
- 31/12/2025: R$ 2,59315838298/ação

Com os preços obtidos anteriormente pelo coletor, os DYs devem ficar
aproximadamente em 4,62%, 4,91%, 4,96%, 4,22%, 4,26% e 5,36%.

## Execução

Os arquivos do ZIP já estão com os nomes esperados pelo script.

```bash
python coletor_parametrizado.py --empresa porto
```

Depois valide:
- `porto_dividendos.csv`
- `porto_financeiro_semestral.csv`
- `porto_indicadores.csv`

Se os seis DYs aparecerem corretamente, as cinco empresas estarão fechadas.
