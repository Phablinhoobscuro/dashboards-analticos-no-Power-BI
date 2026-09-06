
USE DashboardIbovespa;
GO

/* ============================================================
   ETAPA 5 — VALIDAÇÃO DA CARGA
   Base esperada: Coletor Parametrizado V7
   ============================================================ */

-- 1. Contagens principais
SELECT 'DimEmpresa' AS Tabela, COUNT(*) AS Registros FROM dbo.DimEmpresa
UNION ALL
SELECT 'DimData', COUNT(*) FROM dbo.DimData
UNION ALL
SELECT 'DimPeriodoSemestral', COUNT(*) FROM dbo.DimPeriodoSemestral
UNION ALL
SELECT 'FatoFinanceiroSemestral', COUNT(*) FROM dbo.FatoFinanceiroSemestral
UNION ALL
SELECT 'FatoIndicadorSemestral', COUNT(*) FROM dbo.FatoIndicadorSemestral
UNION ALL
SELECT 'FatoPrecoDiario', COUNT(*) FROM dbo.FatoPrecoDiario
UNION ALL
SELECT 'FatoProvento', COUNT(*) FROM dbo.FatoProvento
UNION ALL
SELECT 'HistoricoAcoes', COUNT(*) FROM dbo.HistoricoAcoes;
GO

-- Valores esperados:
-- DimEmpresa                 5
-- DimData                    1461
-- DimPeriodoSemestral        6
-- FatoFinanceiroSemestral    30
-- FatoIndicadorSemestral     30
-- FatoPrecoDiario            3745
-- FatoProvento               49
-- HistoricoAcoes             1840

/* 2. Financeiro: deve existir exatamente 1 registro
      por empresa + período, totalizando 30 */
SELECT
    e.Ticker,
    p.Ano,
    p.Semestre,
    COUNT(*) AS Quantidade
FROM dbo.FatoFinanceiroSemestral f
JOIN dbo.DimEmpresa e
    ON e.EmpresaID = f.EmpresaID
JOIN dbo.DimPeriodoSemestral p
    ON p.PeriodoID = f.PeriodoID
GROUP BY
    e.Ticker,
    p.Ano,
    p.Semestre
HAVING COUNT(*) <> 1;
GO

/* 3. Indicadores: mesma regra */
SELECT
    e.Ticker,
    p.Ano,
    p.Semestre,
    COUNT(*) AS Quantidade
FROM dbo.FatoIndicadorSemestral f
JOIN dbo.DimEmpresa e
    ON e.EmpresaID = f.EmpresaID
JOIN dbo.DimPeriodoSemestral p
    ON p.PeriodoID = f.PeriodoID
GROUP BY
    e.Ticker,
    p.Ano,
    p.Semestre
HAVING COUNT(*) <> 1;
GO

/* 4. Preços por empresa:
      esperado = 749 pregões por ticker */
SELECT
    e.Ticker,
    COUNT(*) AS Pregoes,
    MIN(d.DataCompleta) AS PrimeiraData,
    MAX(d.DataCompleta) AS UltimaData
FROM dbo.FatoPrecoDiario f
JOIN dbo.DimEmpresa e
    ON e.EmpresaID = f.EmpresaID
JOIN dbo.DimData d
    ON d.DataID = f.DataID
GROUP BY e.Ticker
ORDER BY e.Ticker;
GO

/* 5. Histórico de ações:
      confirma chave única e intervalo */
SELECT
    e.Ticker,
    COUNT(*) AS Registros,
    MIN(d.DataCompleta) AS PrimeiraData,
    MAX(d.DataCompleta) AS UltimaData
FROM dbo.HistoricoAcoes h
JOIN dbo.DimEmpresa e
    ON e.EmpresaID = h.EmpresaID
JOIN dbo.DimData d
    ON d.DataID = h.DataID
GROUP BY e.Ticker
ORDER BY e.Ticker;
GO

/* 6. Proventos por empresa */
SELECT
    e.Ticker,
    COUNT(*) AS Eventos,
    SUM(CASE WHEN p.EventoBootstrap = 1 THEN 1 ELSE 0 END) AS EventosBootstrap,
    MIN(p.DataDeliberacao) AS PrimeiroEvento,
    MAX(p.DataDeliberacao) AS UltimoEvento
FROM dbo.FatoProvento p
JOIN dbo.DimEmpresa e
    ON e.EmpresaID = p.EmpresaID
GROUP BY e.Ticker
ORDER BY e.Ticker;
GO

/* 7. Amostra dos sete indicadores */
SELECT
    e.Ticker,
    p.Ano,
    p.Semestre,
    i.PLPrecoLucro AS [P/L],
    i.PVPPrecoValorPatrimonial AS [P/VP],
    i.ROEPct AS [ROE %],
    i.ROAPct AS [ROA %],
    i.DividendYield12mPct AS [DY %],
    i.MargemLiquidaPct AS [Margem Líquida %],
    i.CrescimentoReceitaYoYPct AS [Crescimento Receita YoY %],
    i.PLInterpretabilidade,
    i.ComparabilidadeYoY
FROM dbo.FatoIndicadorSemestral i
JOIN dbo.DimEmpresa e
    ON e.EmpresaID = i.EmpresaID
JOIN dbo.DimPeriodoSemestral p
    ON p.PeriodoID = i.PeriodoID
ORDER BY
    e.Ticker,
    p.Ano,
    p.Semestre;
GO

/* 8. Validação específica: MRV deve aparecer com P/L
      não interpretável nos seis períodos */
SELECT
    e.Ticker,
    p.Ano,
    p.Semestre,
    i.PLPrecoLucro,
    i.PLInterpretabilidade
FROM dbo.FatoIndicadorSemestral i
JOIN dbo.DimEmpresa e
    ON e.EmpresaID = i.EmpresaID
JOIN dbo.DimPeriodoSemestral p
    ON p.PeriodoID = i.PeriodoID
WHERE e.Ticker = 'MRVE3'
ORDER BY p.Ano, p.Semestre;
GO

/* 9. Validação específica: Localiza 1S/2023 */
SELECT
    e.Ticker,
    p.Ano,
    p.Semestre,
    i.CrescimentoReceitaYoYPct,
    i.ComparabilidadeYoY,
    i.MotivoComparabilidadeYoY
FROM dbo.FatoIndicadorSemestral i
JOIN dbo.DimEmpresa e
    ON e.EmpresaID = i.EmpresaID
JOIN dbo.DimPeriodoSemestral p
    ON p.PeriodoID = i.PeriodoID
WHERE
    e.Ticker = 'RENT3'
    AND p.Ano = 2023
    AND p.Semestre = '1S';
GO
