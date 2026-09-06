#!/usr/bin/env python3
# -*- coding: utf-8 -*-

r"""
Carga reproduzível dos consolidados do Coletor Parametrizado V7
para o banco SQL Server DashboardIbovespa.

Uso recomendado no Windows:

    python carga_banco_dashboard.py ^
      --servidor localhost ^
      --banco DashboardIbovespa ^
      --pasta "C:\Users\Phablo\Downloads\Nova pasta\saida_empresas\consolidado"

Autenticação padrão: Windows (Trusted Connection).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import pyodbc


ARQUIVOS = {
    "empresas": "empresas.csv",
    "financeiro": "financeiro_semestral_todas_empresas.csv",
    "indicadores": "indicadores_todas_empresas.csv",
    "precos": "precos_diarios_todas_empresas.csv",
    "dividendos": "dividendos_todas_empresas.csv",
    "acoes": "acoes_em_circulacao_todas_empresas.csv",
}

CONTAGENS_ESPERADAS = {
    "empresas": 5,
    "financeiro": 30,
    "indicadores": 30,
    "precos": 3745,
    "dividendos": 49,
    "acoes": 1840,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Carrega os CSVs consolidados V7 no SQL Server."
    )
    parser.add_argument(
        "--servidor",
        default="localhost",
        help="Instância SQL Server. Padrão: localhost",
    )
    parser.add_argument(
        "--banco",
        default="DashboardIbovespa",
        help="Banco de destino. Padrão: DashboardIbovespa",
    )
    parser.add_argument(
        "--pasta",
        required=True,
        help="Pasta que contém os seis CSVs consolidados.",
    )
    parser.add_argument(
        "--sem-limpar",
        action="store_true",
        help="Não apaga as tabelas fato antes da carga. Use apenas se souber o que está fazendo.",
    )
    return parser.parse_args()


def escolher_driver() -> str:
    drivers = pyodbc.drivers()

    preferencia = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server",
    ]

    for driver in preferencia:
        if driver in drivers:
            return driver

    encontrados = ", ".join(drivers) if drivers else "(nenhum)"
    raise RuntimeError(
        "Nenhum driver ODBC compatível com SQL Server foi encontrado. "
        f"Drivers detectados: {encontrados}"
    )


def conectar(servidor: str, banco: str) -> pyodbc.Connection:
    driver = escolher_driver()

    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={servidor};"
        f"DATABASE={banco};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )

    print(f"[SQL] Driver: {driver}")
    print(f"[SQL] Servidor: {servidor}")
    print(f"[SQL] Banco: {banco}")

    return pyodbc.connect(conn_str, autocommit=False)


def validar_arquivos(pasta: Path) -> dict[str, Path]:
    caminhos: dict[str, Path] = {}

    for chave, nome in ARQUIVOS.items():
        caminho = pasta / nome
        if not caminho.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
        caminhos[chave] = caminho

    return caminhos


def carregar_csvs(caminhos: dict[str, Path]) -> dict[str, pd.DataFrame]:
    dfs: dict[str, pd.DataFrame] = {}

    for chave, caminho in caminhos.items():
        df = pd.read_csv(caminho, encoding="utf-8-sig")
        dfs[chave] = df
        print(f"[CSV] {caminho.name}: {len(df)} registros")

    return dfs


def validar_base(dfs: dict[str, pd.DataFrame]) -> None:
    erros: list[str] = []

    for chave, esperado in CONTAGENS_ESPERADAS.items():
        atual = len(dfs[chave])
        if atual != esperado:
            erros.append(
                f"{ARQUIVOS[chave]}: esperado {esperado}, encontrado {atual}"
            )

    if dfs["empresas"]["empresa_chave"].duplicated().any():
        erros.append("empresas.csv contém empresa_chave duplicada.")

    if dfs["financeiro"].duplicated(["empresa_chave", "data_referencia"]).any():
        erros.append("financeiro semestral contém empresa + data duplicada.")

    if dfs["indicadores"].duplicated(["empresa_chave", "data_referencia"]).any():
        erros.append("indicadores contém empresa + data duplicada.")

    if dfs["precos"].duplicated(["empresa_chave", "data"]).any():
        erros.append("preços diários contém empresa + data duplicada.")

    if dfs["acoes"].duplicated(["empresa_chave", "data"]).any():
        erros.append("ações em circulação contém empresa + data duplicada.")

    if erros:
        raise ValueError(
            "A validação pré-carga encontrou problemas:\n- "
            + "\n- ".join(erros)
        )

    print("[OK] Validação pré-carga concluída.")


def nulo(v: Any) -> Any:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except TypeError:
        pass
    return v


def texto(v: Any) -> str | None:
    v = nulo(v)
    return None if v is None else str(v)


def inteiro(v: Any) -> int | None:
    v = nulo(v)
    return None if v is None else int(v)


def booleano(v: Any) -> int:
    v = nulo(v)
    if v is None:
        return 0
    if isinstance(v, str):
        return 1 if v.strip().lower() in {"true", "1", "sim", "yes"} else 0
    return 1 if bool(v) else 0


def decimal_sql(v: Any) -> float | None:
    """
    Converte valores numéricos para float antes do envio ao pyodbc.

    Motivo:
    em algumas versões do pyodbc/ODBC Driver 18, o envio de objetos
    Decimal em executemany/fast_executemany pode gerar o erro
    "Converting decimal loses precision", mesmo quando o valor cabe
    corretamente no DECIMAL definido no SQL Server.

    O SQL Server continuará armazenando os dados nas colunas DECIMAL
    configuradas no schema; a conversão final é feita pelo próprio banco.
    """
    v = nulo(v)
    if v is None:
        return None
    return float(v)


def data_py(v: Any):
    v = nulo(v)
    if v is None:
        return None
    return pd.to_datetime(v).date()


def data_id(v: Any) -> int:
    d = pd.to_datetime(v)
    return int(d.strftime("%Y%m%d"))


def sincronizar_dim_empresa(
    cursor: pyodbc.Cursor,
    empresas: pd.DataFrame,
) -> None:
    sql_update = """
        UPDATE dbo.DimEmpresa
        SET
            Empresa = ?,
            CNPJ = ?,
            Ticker = ?,
            TickerYahoo = ?,
            Setor = ?,
            ProventosStatus = ?,
            RIDividendosURL = ?
        WHERE EmpresaChave = ?;
    """

    sql_insert = """
        INSERT INTO dbo.DimEmpresa (
            EmpresaChave, Empresa, CNPJ, Ticker,
            TickerYahoo, Setor, ProventosStatus, RIDividendosURL
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """

    for _, r in empresas.iterrows():
        chave = texto(r["empresa_chave"])

        cursor.execute(
            sql_update,
            texto(r["empresa"]),
            texto(r["cnpj"]),
            texto(r["ticker"]),
            texto(r["ticker_yahoo"]),
            texto(r["setor"]),
            texto(r["proventos_status"]),
            texto(r["ri_dividendos_url"]),
            chave,
        )

        if cursor.rowcount == 0:
            cursor.execute(
                sql_insert,
                chave,
                texto(r["empresa"]),
                texto(r["cnpj"]),
                texto(r["ticker"]),
                texto(r["ticker_yahoo"]),
                texto(r["setor"]),
                texto(r["proventos_status"]),
                texto(r["ri_dividendos_url"]),
            )

    print("[OK] DimEmpresa sincronizada.")


def obter_mapas(cursor: pyodbc.Cursor):
    empresa_map = {
        str(chave): int(empresa_id)
        for empresa_id, chave in cursor.execute(
            "SELECT EmpresaID, EmpresaChave FROM dbo.DimEmpresa"
        ).fetchall()
    }

    periodo_map = {
        (int(ano), str(semestre)): int(periodo_id)
        for periodo_id, ano, semestre in cursor.execute(
            """
            SELECT PeriodoID, Ano, Semestre
            FROM dbo.DimPeriodoSemestral
            """
        ).fetchall()
    }

    return empresa_map, periodo_map


def validar_dimensoes(
    cursor: pyodbc.Cursor,
    empresa_map: dict[str, int],
    periodo_map: dict[tuple[int, str], int],
) -> None:
    total_datas = cursor.execute(
        "SELECT COUNT(*) FROM dbo.DimData"
    ).fetchval()

    if len(empresa_map) != 5:
        raise RuntimeError(
            f"DimEmpresa deveria possuir 5 empresas; encontrou {len(empresa_map)}."
        )

    if len(periodo_map) != 6:
        raise RuntimeError(
            f"DimPeriodoSemestral deveria possuir 6 períodos; encontrou {len(periodo_map)}."
        )

    if total_datas != 1461:
        raise RuntimeError(
            f"DimData deveria possuir 1461 datas; encontrou {total_datas}."
        )

    print("[OK] Dimensões validadas: 5 empresas, 6 períodos e 1461 datas.")


def limpar_fatos(cursor: pyodbc.Cursor) -> None:
    # Ordem sem risco de conflitos futuros caso novas FKs sejam adicionadas.
    tabelas = [
        "dbo.HistoricoAcoes",
        "dbo.FatoProvento",
        "dbo.FatoPrecoDiario",
        "dbo.FatoIndicadorSemestral",
        "dbo.FatoFinanceiroSemestral",
    ]

    for tabela in tabelas:
        cursor.execute(f"DELETE FROM {tabela}")

    print("[OK] Tabelas fato limpas para recarga idempotente.")


def carregar_financeiro(
    cursor: pyodbc.Cursor,
    df: pd.DataFrame,
    empresa_map: dict[str, int],
    periodo_map: dict[tuple[int, str], int],
) -> None:
    sql = """
        INSERT INTO dbo.FatoFinanceiroSemestral (
            EmpresaID,
            PeriodoID,
            AtivoTotalBRL,
            PatrimonioLiquidoConsolidadoBRL,
            ParticipacaoNaoControladoresBRL,
            PatrimonioAtribuivelControladoresBRL,
            ReceitaSemestreBRL,
            LucroLiquidoConsolidadoSemestreBRL,
            LucroAtribuivelControladoresSemestreBRL,
            ComparativoReapresentado,
            AnoDocumentoFonte,
            OrdemExercFonte,
            OrigemBalanco,
            OrigemResultado,
            AjusteHistoricoAplicado,
            CamposAjustados,
            FonteAjusteHistorico,
            MotivoAjusteHistorico,
            PrecoFechamentoDataRefBRL,
            AcoesEmCirculacaoDataRef,
            ValorMercadoEstimadoDataRefBRL,
            DividendosPorAcaoSemestreBRL,
            DividendosPorAcao12mBRL
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        );
    """

    registros = []

    for _, r in df.iterrows():
        empresa_id = empresa_map[str(r["empresa_chave"])]
        periodo_id = periodo_map[(int(r["ano"]), str(r["semestre"]))]

        registros.append(
            (
                empresa_id,
                periodo_id,
                decimal_sql(r["ativo_total_brl"]),
                decimal_sql(r["patrimonio_liquido_consolidado_brl"]),
                decimal_sql(r["participacao_nao_controladores_brl"]),
                decimal_sql(r["patrimonio_atribuivel_controladores_brl"]),
                decimal_sql(r["receita_semestre_brl"]),
                decimal_sql(r["lucro_liquido_consolidado_semestre_brl"]),
                decimal_sql(r["lucro_atribuivel_controladores_semestre_brl"]),
                booleano(r["comparativo_reapresentado"]),
                inteiro(r["ano_documento_fonte"]),
                texto(r["ordem_exerc_fonte"]),
                texto(r["origem_balanco"]),
                texto(r["origem_resultado"]),
                booleano(r["ajuste_historico_aplicado"]),
                texto(r["campos_ajustados"]),
                texto(r["fonte_ajuste_historico"]),
                texto(r["motivo_ajuste_historico"]),
                decimal_sql(r["preco_fechamento_data_ref_brl"]),
                inteiro(r["acoes_em_circulacao_data_ref"]),
                decimal_sql(r["valor_mercado_estimado_data_ref_brl"]),
                decimal_sql(r["dividendos_por_acao_semestre_brl"]),
                decimal_sql(r["dividendos_por_acao_12m_brl"]),
            )
        )

    cursor.fast_executemany = False
    cursor.executemany(sql, registros)
    print(f"[OK] FatoFinanceiroSemestral: {len(registros)} registros.")


def carregar_indicadores(
    cursor: pyodbc.Cursor,
    df: pd.DataFrame,
    empresa_map: dict[str, int],
    periodo_map: dict[tuple[int, str], int],
) -> None:
    sql = """
        INSERT INTO dbo.FatoIndicadorSemestral (
            EmpresaID,
            PeriodoID,
            ReceitaTTMBRL,
            LucroConsolidadoTTMBRL,
            LucroControladoresTTMBRL,
            PLPrecoLucro,
            PVPPrecoValorPatrimonial,
            ROEPct,
            ROAPct,
            MargemLiquidaPct,
            DividendYield12mPct,
            ReceitaMesmoSemestreAnoAnteriorBRL,
            CrescimentoReceitaYoYPct,
            PLInterpretabilidade,
            MotivoPLInterpretabilidade,
            ComparabilidadeYoY,
            MotivoComparabilidadeYoY
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    registros = []

    for _, r in df.iterrows():
        empresa_id = empresa_map[str(r["empresa_chave"])]
        periodo_id = periodo_map[(int(r["ano"]), str(r["semestre"]))]

        registros.append(
            (
                empresa_id,
                periodo_id,
                decimal_sql(r["receita_ttm_brl"]),
                decimal_sql(r["lucro_consolidado_ttm_brl"]),
                decimal_sql(r["lucro_controladores_ttm_brl"]),
                decimal_sql(r["pl_preco_lucro"]),
                decimal_sql(r["pvp_preco_valor_patrimonial"]),
                decimal_sql(r["roe_pct"]),
                decimal_sql(r["roa_pct"]),
                decimal_sql(r["margem_liquida_pct"]),
                decimal_sql(r["dividend_yield_12m_pct"]),
                decimal_sql(r["receita_mesmo_semestre_ano_anterior_brl"]),
                decimal_sql(r["crescimento_receita_yoy_pct"]),
                texto(r["pl_interpretabilidade"]),
                texto(r["motivo_pl_interpretabilidade"]),
                texto(r["comparabilidade_yoy"]),
                texto(r["motivo_comparabilidade_yoy"]),
            )
        )

    cursor.fast_executemany = False
    cursor.executemany(sql, registros)
    print(f"[OK] FatoIndicadorSemestral: {len(registros)} registros.")


def carregar_precos(
    cursor: pyodbc.Cursor,
    df: pd.DataFrame,
    empresa_map: dict[str, int],
) -> None:
    sql = """
        INSERT INTO dbo.FatoPrecoDiario (
            EmpresaID,
            DataID,
            PrecoAbertura,
            PrecoMaximo,
            PrecoMinimo,
            PrecoFechamento,
            PrecoAjustado,
            Volume,
            DividendosYahoo,
            StockSplits,
            Reparado
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    registros = []

    for _, r in df.iterrows():
        registros.append(
            (
                empresa_map[str(r["empresa_chave"])],
                data_id(r["data"]),
                decimal_sql(r["Open"]),
                decimal_sql(r["High"]),
                decimal_sql(r["Low"]),
                decimal_sql(r["Close"]),
                decimal_sql(r["Adj Close"]),
                inteiro(r["Volume"]),
                decimal_sql(r["Dividends"]),
                decimal_sql(r["Stock Splits"]),
                booleano(r["Repaired?"]),
            )
        )

    cursor.fast_executemany = False
    cursor.executemany(sql, registros)
    print(f"[OK] FatoPrecoDiario: {len(registros)} registros.")


def carregar_proventos(
    cursor: pyodbc.Cursor,
    df: pd.DataFrame,
    empresa_map: dict[str, int],
) -> None:
    sql = """
        INSERT INTO dbo.FatoProvento (
            EmpresaID,
            TipoProvento,
            PeriodoDeliberacao,
            DataDeliberacao,
            DataPagamento,
            BaseDistribuicao,
            VolumeTotalBRL,
            DividendoPorAcaoBRL,
            Fonte,
            EventoBootstrap
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """

    registros = []

    for _, r in df.iterrows():
        registros.append(
            (
                empresa_map[str(r["empresa_chave"])],
                texto(r["tipo_provento"]),
                texto(r["periodo_deliberacao"]),
                data_py(r["data"]),
                data_py(r["data_pagamento"]),
                inteiro(r["base_distribuicao"]),
                decimal_sql(r["volume_total_brl"]),
                decimal_sql(r["dividendo_por_acao_brl"]),
                texto(r["fonte"]),
                booleano(r["evento_bootstrap"]),
            )
        )

    cursor.fast_executemany = False
    cursor.executemany(sql, registros)
    print(f"[OK] FatoProvento: {len(registros)} registros.")


def carregar_acoes(
    cursor: pyodbc.Cursor,
    df: pd.DataFrame,
    empresa_map: dict[str, int],
) -> None:
    sql = """
        INSERT INTO dbo.HistoricoAcoes (
            EmpresaID,
            DataID,
            AcoesEmCirculacao
        )
        VALUES (?, ?, ?);
    """

    registros = [
        (
            empresa_map[str(r["empresa_chave"])],
            data_id(r["data"]),
            inteiro(r["acoes_em_circulacao"]),
        )
        for _, r in df.iterrows()
    ]

    cursor.fast_executemany = False
    cursor.executemany(sql, registros)
    print(f"[OK] HistoricoAcoes: {len(registros)} registros.")


def validar_contagens_finais(cursor: pyodbc.Cursor) -> None:
    esperadas = {
        "DimEmpresa": 5,
        "DimData": 1461,
        "DimPeriodoSemestral": 6,
        "FatoFinanceiroSemestral": 30,
        "FatoIndicadorSemestral": 30,
        "FatoPrecoDiario": 3745,
        "FatoProvento": 49,
        "HistoricoAcoes": 1840,
    }

    print("\n=== VALIDAÇÃO FINAL ===")

    erros = []

    for tabela, esperado in esperadas.items():
        atual = int(
            cursor.execute(
                f"SELECT COUNT(*) FROM dbo.{tabela}"
            ).fetchval()
        )
        status = "OK" if atual == esperado else "ERRO"
        print(f"{tabela:28} {atual:5}  [{status}]")

        if atual != esperado:
            erros.append(f"{tabela}: esperado {esperado}, encontrado {atual}")

    if erros:
        raise RuntimeError(
            "Carga concluída com contagens divergentes:\n- "
            + "\n- ".join(erros)
        )


def main() -> None:
    args = parse_args()
    pasta = Path(args.pasta).expanduser().resolve()

    print("=" * 72)
    print("CARGA DO BANCO DashboardIbovespa — BASE V7")
    print("=" * 72)
    print(f"Pasta dos consolidados: {pasta}")

    caminhos = validar_arquivos(pasta)
    dfs = carregar_csvs(caminhos)
    validar_base(dfs)

    conn = conectar(args.servidor, args.banco)
    cursor = conn.cursor()

    try:
        sincronizar_dim_empresa(cursor, dfs["empresas"])

        empresa_map, periodo_map = obter_mapas(cursor)
        validar_dimensoes(cursor, empresa_map, periodo_map)

        if not args.sem_limpar:
            limpar_fatos(cursor)

        carregar_financeiro(
            cursor, dfs["financeiro"], empresa_map, periodo_map
        )
        carregar_indicadores(
            cursor, dfs["indicadores"], empresa_map, periodo_map
        )
        carregar_precos(cursor, dfs["precos"], empresa_map)
        carregar_proventos(cursor, dfs["dividendos"], empresa_map)
        carregar_acoes(cursor, dfs["acoes"], empresa_map)

        validar_contagens_finais(cursor)

        conn.commit()

        print("\n[SUCESSO] Transação confirmada.")
        print("Banco pronto para validação no SSMS e conexão com o Power BI.")

    except Exception:
        conn.rollback()
        print("\n[ROLLBACK] Nenhuma carga parcial foi mantida.")
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
