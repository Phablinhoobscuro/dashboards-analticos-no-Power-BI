"""
Coletor parametrizado - Projeto de Desenvolvimento de Dashboard Analítico

Empresas configuradas:
- Smart Fit (SMFT3)
- TOTVS (TOTS3)
- Porto Seguro (PSSA3)
- MRV (MRVE3)
- Localiza (RENT3)

Fontes:
1) CVM Dados Abertos
   - ITR: balanço de 30/06 e DRE acumulada do 1º semestre
   - DFP: balanço de 31/12 e DRE anual
2) Yahoo Finance via yfinance
   - preços diários
   - histórico de quantidade de ações, quando disponível
   - informações atuais de mercado
3) Relações com Investidores (RI) oficiais
   - dividendos/JCP por ação, quando há histórico detalhado suficiente

Metodologia:
- 1S: ITR de 30/06
- 2S: balanço da DFP em 31/12 e resultado semestral derivado por:
      DRE anual - DRE acumulada até 30/06
- Indicadores de resultado usam TTM (últimos 12 meses) quando aplicável.
- Crescimento de Receita é YoY:
      1S vs 1S do ano anterior e 2S vs 2S do ano anterior.
- Demonstrações consolidadas são priorizadas.
- A maior VERSAO apresentada à CVM é mantida.

IMPORTANTE:
- O coletor foi parametrizado, mas cada empresa deve ser VALIDADA depois da
  primeira execução. Empresas de setores distintos podem exigir tratamento
  específico de contas ou de proventos.
- Porto Seguro possui, nesta versão, apenas referência anual oficial de
  proventos no RI; por isso o Dividend Yield semestral fica como NaN até que
  o histórico detalhado oficial seja incorporado.
"""


from __future__ import annotations

import argparse
import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf


# ============================================================
# CONFIGURAÇÃO
# ============================================================

SCRIPT_DIR = Path(__file__).resolve().parent
ARQUIVO_CONFIG = SCRIPT_DIR / "empresas_dashboard.json"
ARQUIVO_PROVENTOS = SCRIPT_DIR / "proventos_oficiais.csv"
ARQUIVO_AJUSTES_HISTORICOS = SCRIPT_DIR / "ajustes_historicos.csv"

# Três anos completos do projeto
ANOS_ALVO = [2023, 2024, 2025]

# Coleta 1 ano anterior para permitir TTM/12M no início da série
ANO_BOOTSTRAP = min(ANOS_ALVO) - 1
ANOS_COLETA = list(range(ANO_BOOTSTRAP, max(ANOS_ALVO) + 1))

PASTA_BASE_SAIDA = Path("saida_empresas")
PASTA_CACHE_CVM = PASTA_BASE_SAIDA / "_cache_cvm"
PASTA_CONSOLIDADO = PASTA_BASE_SAIDA / "consolidado"

CVM_BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (projeto acadêmico UniSales; coleta de dados públicos)"
})

# Variáveis preenchidas por configurar_empresa()
EMPRESA = {}
EMPRESA_CHAVE = ""
PREFIXO_ARQUIVO = ""
PASTA_SAIDA = PASTA_BASE_SAIDA
PASTA_CVM_RAW = PASTA_SAIDA / "cvm_filtrado"
RI_DIVIDENDOS_URL = ""
DIVIDENDOS_OFICIAIS_COMPLETOS = False
PROVENTOS_ESPERA_EVENTOS = False


def carregar_empresas_config() -> dict:
    if not ARQUIVO_CONFIG.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {ARQUIVO_CONFIG}"
        )
    with ARQUIVO_CONFIG.open("r", encoding="utf-8") as f:
        return json.load(f)


def configurar_empresa(chave: str) -> dict:
    global EMPRESA, EMPRESA_CHAVE, PREFIXO_ARQUIVO
    global PASTA_SAIDA, PASTA_CVM_RAW
    global RI_DIVIDENDOS_URL
    global DIVIDENDOS_OFICIAIS_COMPLETOS, PROVENTOS_ESPERA_EVENTOS

    empresas = carregar_empresas_config()

    if chave not in empresas:
        disponiveis = ", ".join(empresas.keys())
        raise KeyError(
            f"Empresa '{chave}' não configurada. Disponíveis: {disponiveis}"
        )

    EMPRESA_CHAVE = chave
    EMPRESA = empresas[chave]
    PREFIXO_ARQUIVO = EMPRESA.get("prefixo_arquivo", chave)

    PASTA_SAIDA = PASTA_BASE_SAIDA / PREFIXO_ARQUIVO
    PASTA_CVM_RAW = PASTA_SAIDA / "cvm_filtrado"

    RI_DIVIDENDOS_URL = EMPRESA.get("ri_dividendos_url", "")
    DIVIDENDOS_OFICIAIS_COMPLETOS = (
        EMPRESA.get("proventos_status") == "completo"
    )
    PROVENTOS_ESPERA_EVENTOS = bool(
        EMPRESA.get("proventos_espera_eventos", False)
    )

    return EMPRESA


def conta_config(nome: str, padrao: str) -> str:
    return EMPRESA.get("contas", {}).get(nome, padrao)


def usar_comparativos_reapresentados() -> bool:
    """
    Se True, o coletor tenta usar o comparativo PENULTIMO divulgado
    no ano seguinte para a série histórica.

    Exemplo:
      - 1S/2024 -> ITR 2025, PENULTIMO;
      - 2024 anual -> DFP 2025, PENULTIMO.

    Se o documento do ano seguinte ainda não existir, usa o valor
    original do próprio exercício.
    """
    return bool(EMPRESA.get("usar_comparativos_reapresentados", False))

# ============================================================
# UTILITÁRIOS
# ============================================================

def somente_digitos(valor: str) -> str:
    return re.sub(r"\D", "", str(valor))


def sem_acento(valor: object) -> str:
    texto = "" if pd.isna(valor) else str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.strip().upper()


def garantir_pastas() -> None:
    PASTA_BASE_SAIDA.mkdir(parents=True, exist_ok=True)
    PASTA_CACHE_CVM.mkdir(parents=True, exist_ok=True)
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    PASTA_CVM_RAW.mkdir(parents=True, exist_ok=True)


def baixar_zip(url: str, timeout: int = 120) -> zipfile.ZipFile:
    """
    Usa cache local compartilhado entre as empresas.

    Os ZIPs anuais da CVM são os mesmos para todas as companhias.
    Assim, ao processar a segunda empresa em diante, o arquivo não
    precisa ser baixado novamente.
    """
    PASTA_CACHE_CVM.mkdir(parents=True, exist_ok=True)
    nome = Path(url.split("?")[0]).name
    caminho = PASTA_CACHE_CVM / nome

    if caminho.exists() and caminho.stat().st_size > 0:
        print(f"Cache CVM: {nome}")
        return zipfile.ZipFile(caminho)

    print(f"Baixando CVM: {url}")
    resposta = SESSION.get(url, timeout=timeout)
    resposta.raise_for_status()

    caminho.write_bytes(resposta.content)
    return zipfile.ZipFile(caminho)


def localizar_csv_no_zip(zf: zipfile.ZipFile, tipo_doc: str, demonstracao: str,
                         escopo: str, ano: int) -> str:
    """
    Procura, por exemplo:
      itr_cia_aberta_BPA_con_2025.csv
      dfp_cia_aberta_DRE_con_2025.csv
    """
    esperado = f"{tipo_doc.lower()}_cia_aberta_{demonstracao}_{escopo}_{ano}.csv".lower()

    nomes = zf.namelist()

    # 1) tentativa exata
    for nome in nomes:
        if Path(nome).name.lower() == esperado:
            return nome

    # 2) tentativa flexível
    tokens = [
        tipo_doc.lower(),
        demonstracao.lower(),
        escopo.lower(),
        str(ano),
    ]
    candidatos = [
        nome for nome in nomes
        if nome.lower().endswith(".csv")
        and all(token in Path(nome).name.lower() for token in tokens)
    ]

    if not candidatos:
        amostra = "\n".join(nomes[:30])
        raise FileNotFoundError(
            f"Não encontrei CSV para {tipo_doc}/{demonstracao}/{escopo}/{ano}.\n"
            f"Primeiros arquivos do ZIP:\n{amostra}"
        )

    return candidatos[0]


def ler_csv_cvm(tipo_doc: str, demonstracao: str, ano: int,
                escopo: str = "con") -> pd.DataFrame:
    """
    tipo_doc: ITR ou DFP
    demonstracao: BPA, BPP ou DRE
    escopo: con (consolidado)
    """
    tipo_doc = tipo_doc.upper()
    tipo_lower = tipo_doc.lower()

    url = (
        f"{CVM_BASE}/{tipo_doc}/DADOS/"
        f"{tipo_lower}_cia_aberta_{ano}.zip"
    )

    zf = baixar_zip(url)
    membro = localizar_csv_no_zip(
        zf, tipo_lower, demonstracao.upper(), escopo.lower(), ano
    )

    conteudo = zf.read(membro)

    # A CVM historicamente publica esses CSVs com ; e encoding latino.
    # Fazemos tentativa em latin1 e, se necessário, UTF-8.
    ultimo_erro = None
    for encoding in ("latin1", "utf-8-sig", "utf-8"):
        try:
            df = pd.read_csv(
                io.BytesIO(conteudo),
                sep=";",
                encoding=encoding,
                dtype=str,
                low_memory=False,
            )
            df.columns = [c.strip() for c in df.columns]
            return df
        except Exception as exc:
            ultimo_erro = exc

    raise RuntimeError(f"Falha lendo {membro}: {ultimo_erro}")


def filtrar_empresa_ultima_versao(
    df: pd.DataFrame,
    cnpj: str,
    data_referencia: str,
    ordem_exerc: str = "ULTIMO",
    data_fim_exercicio: Optional[str] = None,
) -> pd.DataFrame:
    """
    Filtra CNPJ + DT_REFER, mantém a maior VERSAO e seleciona
    ORDEM_EXERC exatamente igual a ULTIMO ou PENULTIMO.

    Para comparativos reapresentados, DT_REFER pertence ao documento
    do ano seguinte, enquanto DT_FIM_EXERC pertence ao ano histórico.
    """
    copia = df.copy()

    if "CNPJ_CIA" not in copia.columns:
        raise KeyError("CSV da CVM não possui a coluna CNPJ_CIA.")

    alvo = somente_digitos(cnpj)
    copia["_CNPJ_DIGITOS"] = copia["CNPJ_CIA"].map(somente_digitos)
    copia = copia[copia["_CNPJ_DIGITOS"] == alvo].copy()

    if copia.empty:
        raise ValueError(f"Empresa CNPJ {cnpj} não encontrada no arquivo da CVM.")

    if "DT_REFER" in copia.columns:
        copia["_DT_REFER"] = pd.to_datetime(copia["DT_REFER"], errors="coerce")
        alvo_data = pd.Timestamp(data_referencia)
        copia = copia[copia["_DT_REFER"] == alvo_data].copy()

    if copia.empty:
        raise ValueError(
            f"Não há dados para {EMPRESA['nome']} no documento "
            f"DT_REFER={data_referencia}."
        )

    if "VERSAO" in copia.columns:
        copia["_VERSAO_NUM"] = pd.to_numeric(
            copia["VERSAO"].str.replace(",", ".", regex=False),
            errors="coerce",
        )
        if copia["_VERSAO_NUM"].notna().any():
            maior = copia["_VERSAO_NUM"].max()
            copia = copia[copia["_VERSAO_NUM"] == maior].copy()

    if "ORDEM_EXERC" in copia.columns:
        ordem_desejada = sem_acento(ordem_exerc)
        ordem = copia["ORDEM_EXERC"].map(sem_acento)
        filtrado = copia[ordem.eq(ordem_desejada)].copy()

        if filtrado.empty:
            raise ValueError(
                f"ORDEM_EXERC={ordem_exerc} não encontrada para "
                f"{EMPRESA['nome']} em DT_REFER={data_referencia}."
            )

        copia = filtrado

    if "DT_FIM_EXERC" in copia.columns:
        fim_exerc = pd.to_datetime(copia["DT_FIM_EXERC"], errors="coerce")
        alvo_fim = pd.Timestamp(data_fim_exercicio or data_referencia)
        exato = copia[fim_exerc == alvo_fim].copy()

        if not exato.empty:
            copia = exato
        elif data_fim_exercicio is not None:
            raise ValueError(
                f"DT_FIM_EXERC={data_fim_exercicio} não encontrada "
                f"no documento {data_referencia}."
            )

    return copia


def filtrar_dre_acumulada_ano(df: pd.DataFrame, ano: int) -> pd.DataFrame:
    """
    Para ITR de 30/06, privilegia a DRE acumulada desde 01/01 até 30/06.
    Para DFP, privilegia 01/01 até 31/12.
    """
    copia = df.copy()

    if "DT_INI_EXERC" in copia.columns:
        ini = pd.to_datetime(copia["DT_INI_EXERC"], errors="coerce")
        desejado = (ini.dt.year == ano) & (ini.dt.month == 1) & (ini.dt.day == 1)
        filtrado = copia[desejado].copy()
        if not filtrado.empty:
            copia = filtrado

    return copia


def valor_numerico(serie: pd.Series) -> pd.Series:
    texto = serie.astype(str).str.strip()

    # Trata formato brasileiro quando vier como texto.
    # Se houver ponto e vírgula decimal, remove pontos de milhar.
    tem_virgula = texto.str.contains(",", regex=False)
    texto.loc[tem_virgula] = (
        texto.loc[tem_virgula]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )

    return pd.to_numeric(texto, errors="coerce")


def multiplicador_escala(escala: object) -> float:
    e = sem_acento(escala)
    if "BILH" in e:
        return 1_000_000_000.0
    if "MILHAO" in e or "MILHOES" in e:
        return 1_000_000.0
    # "MIL", "MILHAR", "MILHARES"
    if e == "MIL" or "MILHAR" in e:
        return 1_000.0
    return 1.0


def preparar_valores_brl(df: pd.DataFrame) -> pd.DataFrame:
    copia = df.copy()

    if "VL_CONTA" not in copia.columns:
        raise KeyError("CSV não possui VL_CONTA.")

    copia["_VL_NUM"] = valor_numerico(copia["VL_CONTA"])

    if "ESCALA_MOEDA" in copia.columns:
        copia["_MULT_ESCALA"] = copia["ESCALA_MOEDA"].map(multiplicador_escala)
    else:
        copia["_MULT_ESCALA"] = 1.0

    copia["_VL_BRL"] = copia["_VL_NUM"] * copia["_MULT_ESCALA"]
    return copia


def obter_conta(df: pd.DataFrame, codigo: str) -> float:
    """
    Retorna o valor da conta padronizada exata.
    Ex.:
      1       = Ativo Total
      2.03    = Patrimônio Líquido Consolidado
      2.03.09 = Participação dos não controladores
      3.01    = Receita
      3.11    = Lucro/Prejuízo Consolidado do Período
      3.11.01 = Atribuído aos controladores
    """
    if "CD_CONTA" not in df.columns:
        return np.nan

    copia = preparar_valores_brl(df)
    codigo_normalizado = str(codigo).strip()
    achados = copia[copia["CD_CONTA"].astype(str).str.strip() == codigo_normalizado]

    if achados.empty:
        return np.nan

    # Para conta padronizada deveria haver uma linha no exercício atual.
    # Se houver repetição, preferimos a primeira linha não nula.
    valores = achados["_VL_BRL"].dropna()
    if valores.empty:
        return np.nan

    return float(valores.iloc[0])


def salvar_filtrado(df: pd.DataFrame, nome: str) -> None:
    caminho = PASTA_CVM_RAW / nome
    df.to_csv(caminho, index=False, encoding="utf-8-sig")


# ============================================================
# CVM - EXTRAÇÃO SEMESTRAL
# ============================================================

def extrair_primeiro_semestre(
    ano: int,
    usar_comparativo_ano_seguinte: bool = False,
) -> dict:
    data_alvo = f"{ano}-06-30"

    if usar_comparativo_ano_seguinte:
        ano_arquivo = ano + 1
        data_doc = f"{ano_arquivo}-06-30"
        ordem = "PENULTIMO"
        sufixo = f"REAPRESENTADO_EM_{ano_arquivo}"
    else:
        ano_arquivo = ano
        data_doc = data_alvo
        ordem = "ULTIMO"
        sufixo = "ORIGINAL"

    bpa = filtrar_empresa_ultima_versao(
        ler_csv_cvm("ITR", "BPA", ano_arquivo),
        EMPRESA["cnpj"],
        data_doc,
        ordem_exerc=ordem,
        data_fim_exercicio=data_alvo,
    )
    bpp = filtrar_empresa_ultima_versao(
        ler_csv_cvm("ITR", "BPP", ano_arquivo),
        EMPRESA["cnpj"],
        data_doc,
        ordem_exerc=ordem,
        data_fim_exercicio=data_alvo,
    )
    dre = filtrar_empresa_ultima_versao(
        ler_csv_cvm("ITR", "DRE", ano_arquivo),
        EMPRESA["cnpj"],
        data_doc,
        ordem_exerc=ordem,
        data_fim_exercicio=data_alvo,
    )
    dre = filtrar_dre_acumulada_ano(dre, ano)

    salvar_filtrado(bpa, f"{ano}_1S_ITR_BPA_con_{sufixo}.csv")
    salvar_filtrado(bpp, f"{ano}_1S_ITR_BPP_con_{sufixo}.csv")
    salvar_filtrado(dre, f"{ano}_1S_ITR_DRE_con_{sufixo}.csv")

    ativo_total = obter_conta(bpa, conta_config("ativo_total", "1"))
    pl_consolidado = obter_conta(
        bpp, conta_config("pl_consolidado", "2.03")
    )
    nci = obter_conta(
        bpp, conta_config("nao_controladores", "2.03.09")
    )

    pl_controladores = (
        pl_consolidado - nci
        if pd.notna(pl_consolidado) and pd.notna(nci)
        else pl_consolidado
    )

    reapresentado = bool(usar_comparativo_ano_seguinte)

    return {
        "empresa": EMPRESA["nome"],
        "ticker": EMPRESA["ticker_b3"],
        "ano": ano,
        "semestre": "1S",
        "data_referencia": data_alvo,
        "ativo_total_brl": ativo_total,
        "patrimonio_liquido_consolidado_brl": pl_consolidado,
        "participacao_nao_controladores_brl": nci,
        "patrimonio_atribuivel_controladores_brl": pl_controladores,
        "receita_semestre_brl": obter_conta(
            dre, conta_config("receita", "3.01")
        ),
        "lucro_liquido_consolidado_semestre_brl": obter_conta(
            dre, conta_config("lucro_consolidado", "3.11")
        ),
        "lucro_atribuivel_controladores_semestre_brl": obter_conta(
            dre, conta_config("lucro_controladores", "3.11.01")
        ),
        "comparativo_reapresentado": reapresentado,
        "ano_documento_fonte": ano_arquivo,
        "ordem_exerc_fonte": ordem,
        "origem_balanco": (
            f"CVM ITR {ano_arquivo} - PENULTIMO de 30/06/{ano}"
            if reapresentado
            else f"CVM ITR {ano} 30/06 - ULTIMO"
        ),
        "origem_resultado": (
            f"CVM ITR {ano_arquivo} DRE - PENULTIMO 01/01/{ano}-30/06/{ano}"
            if reapresentado
            else f"CVM ITR {ano} DRE acumulada 01/01-30/06 - ULTIMO"
        ),
    }


def extrair_anual_dfp(
    ano: int,
    usar_comparativo_ano_seguinte: bool = False,
) -> dict:
    data_alvo = f"{ano}-12-31"

    if usar_comparativo_ano_seguinte:
        ano_arquivo = ano + 1
        data_doc = f"{ano_arquivo}-12-31"
        ordem = "PENULTIMO"
        sufixo = f"REAPRESENTADO_EM_{ano_arquivo}"
    else:
        ano_arquivo = ano
        data_doc = data_alvo
        ordem = "ULTIMO"
        sufixo = "ORIGINAL"

    bpa = filtrar_empresa_ultima_versao(
        ler_csv_cvm("DFP", "BPA", ano_arquivo),
        EMPRESA["cnpj"],
        data_doc,
        ordem_exerc=ordem,
        data_fim_exercicio=data_alvo,
    )
    bpp = filtrar_empresa_ultima_versao(
        ler_csv_cvm("DFP", "BPP", ano_arquivo),
        EMPRESA["cnpj"],
        data_doc,
        ordem_exerc=ordem,
        data_fim_exercicio=data_alvo,
    )
    dre = filtrar_empresa_ultima_versao(
        ler_csv_cvm("DFP", "DRE", ano_arquivo),
        EMPRESA["cnpj"],
        data_doc,
        ordem_exerc=ordem,
        data_fim_exercicio=data_alvo,
    )
    dre = filtrar_dre_acumulada_ano(dre, ano)

    salvar_filtrado(bpa, f"{ano}_ANUAL_DFP_BPA_con_{sufixo}.csv")
    salvar_filtrado(bpp, f"{ano}_ANUAL_DFP_BPP_con_{sufixo}.csv")
    salvar_filtrado(dre, f"{ano}_ANUAL_DFP_DRE_con_{sufixo}.csv")

    ativo_total = obter_conta(bpa, conta_config("ativo_total", "1"))
    pl_consolidado = obter_conta(
        bpp, conta_config("pl_consolidado", "2.03")
    )
    nci = obter_conta(
        bpp, conta_config("nao_controladores", "2.03.09")
    )

    pl_controladores = (
        pl_consolidado - nci
        if pd.notna(pl_consolidado) and pd.notna(nci)
        else pl_consolidado
    )

    reapresentado = bool(usar_comparativo_ano_seguinte)

    return {
        "data_referencia": data_alvo,
        "ativo_total_brl": ativo_total,
        "patrimonio_liquido_consolidado_brl": pl_consolidado,
        "participacao_nao_controladores_brl": nci,
        "patrimonio_atribuivel_controladores_brl": pl_controladores,
        "receita_ano_brl": obter_conta(
            dre, conta_config("receita", "3.01")
        ),
        "lucro_liquido_consolidado_ano_brl": obter_conta(
            dre, conta_config("lucro_consolidado", "3.11")
        ),
        "lucro_atribuivel_controladores_ano_brl": obter_conta(
            dre, conta_config("lucro_controladores", "3.11.01")
        ),
        "comparativo_reapresentado": reapresentado,
        "ano_documento_fonte": ano_arquivo,
        "ordem_exerc_fonte": ordem,
        "origem_balanco": (
            f"CVM DFP {ano_arquivo} - PENULTIMO de 31/12/{ano}"
            if reapresentado
            else f"CVM DFP {ano} 31/12 - ULTIMO"
        ),
        "origem_resultado": (
            f"CVM DFP {ano_arquivo} DRE - PENULTIMO 01/01/{ano}-31/12/{ano}"
            if reapresentado
            else f"CVM DFP {ano} DRE anual - ULTIMO"
        ),
    }


def montar_segundo_semestre(ano: int, primeiro: dict, anual: dict) -> dict:
    def diferenca(a, b):
        if pd.isna(a) or pd.isna(b):
            return np.nan
        return float(a) - float(b)

    return {
        "empresa": EMPRESA["nome"],
        "ticker": EMPRESA["ticker_b3"],
        "ano": ano,
        "semestre": "2S",
        "data_referencia": anual["data_referencia"],
        # Balanço é posição em 31/12
        "ativo_total_brl": anual["ativo_total_brl"],
        "patrimonio_liquido_consolidado_brl":
            anual["patrimonio_liquido_consolidado_brl"],
        "participacao_nao_controladores_brl":
            anual["participacao_nao_controladores_brl"],
        "patrimonio_atribuivel_controladores_brl":
            anual["patrimonio_atribuivel_controladores_brl"],

        # Resultado exclusivo jul-dez = anual - 1S
        "receita_semestre_brl": diferenca(
            anual["receita_ano_brl"],
            primeiro["receita_semestre_brl"],
        ),
        "lucro_liquido_consolidado_semestre_brl": diferenca(
            anual["lucro_liquido_consolidado_ano_brl"],
            primeiro["lucro_liquido_consolidado_semestre_brl"],
        ),
        "lucro_atribuivel_controladores_semestre_brl": diferenca(
            anual["lucro_atribuivel_controladores_ano_brl"],
            primeiro["lucro_atribuivel_controladores_semestre_brl"],
        ),
        "comparativo_reapresentado": bool(
            primeiro.get("comparativo_reapresentado", False)
            or anual.get("comparativo_reapresentado", False)
        ),
        "ano_documento_fonte": anual.get("ano_documento_fonte"),
        "ordem_exerc_fonte": anual.get("ordem_exerc_fonte"),
        "origem_balanco": anual.get(
            "origem_balanco",
            "CVM DFP 31/12 - Consolidado",
        ),
        "origem_resultado": (
            "Derivado: "
            + str(anual.get("origem_resultado", "DFP anual"))
            + " MENOS "
            + str(primeiro.get("origem_resultado", "ITR 1S"))
        ),
    }


def coletar_financeiro_cvm() -> pd.DataFrame:
    """
    Para empresas com `usar_comparativos_reapresentados=true`:
    tenta PENULTIMO do ano seguinte e, se não existir, volta para
    ULTIMO do próprio ano.
    """
    linhas = []
    preferir_reapresentado = usar_comparativos_reapresentados()

    for ano in ANOS_COLETA:
        print(f"\n=== CVM período-alvo {ano} ===")

        primeiro = None
        anual = None

        if preferir_reapresentado:
            try:
                print(
                    f"Tentando 1S/{ano} no comparativo ITR {ano + 1}..."
                )
                primeiro = extrair_primeiro_semestre(
                    ano,
                    usar_comparativo_ano_seguinte=True,
                )
                print(f"1S/{ano}: comparativo reapresentado utilizado.")
            except Exception as exc:
                print(
                    f"[INFO] 1S/{ano} sem comparativo reapresentado: {exc}"
                )

        if primeiro is None:
            try:
                primeiro = extrair_primeiro_semestre(
                    ano,
                    usar_comparativo_ano_seguinte=False,
                )
                print(f"1S/{ano}: valor original utilizado.")
            except Exception as exc:
                print(f"[AVISO] Falha no 1S/{ano}: {exc}")

        if preferir_reapresentado:
            try:
                print(
                    f"Tentando anual/{ano} no comparativo DFP {ano + 1}..."
                )
                anual = extrair_anual_dfp(
                    ano,
                    usar_comparativo_ano_seguinte=True,
                )
                print(f"Anual/{ano}: comparativo reapresentado utilizado.")
            except Exception as exc:
                print(
                    f"[INFO] Anual/{ano} sem comparativo reapresentado: {exc}"
                )

        if anual is None:
            try:
                anual = extrair_anual_dfp(
                    ano,
                    usar_comparativo_ano_seguinte=False,
                )
                print(f"Anual/{ano}: valor original utilizado.")
            except Exception as exc:
                print(f"[AVISO] Falha DFP anual/{ano}: {exc}")

        if primeiro is not None:
            linhas.append(primeiro)

        if primeiro is not None and anual is not None:
            linhas.append(
                montar_segundo_semestre(ano, primeiro, anual)
            )

    df = pd.DataFrame(linhas)

    if not df.empty:
        df["data_referencia"] = pd.to_datetime(df["data_referencia"])
        df = df.sort_values("data_referencia").reset_index(drop=True)

    return df


# ============================================================
# RI OFICIAL - DIVIDENDOS / JCP
# ============================================================

def carregar_dividendos_ri_oficial() -> pd.DataFrame:
    """
    Carrega o arquivo único `proventos_oficiais.csv` e retorna apenas
    os eventos da empresa atual.

    Regra:
    - proventos_status == "completo":
        a base oficial foi considerada suficiente para 2023-2025.
    - proventos_status != "completo":
        Dividend Yield semestral não é calculado automaticamente.

    Para empresas oficialmente confirmadas sem eventos no período
    (ex.: MRV em 2023-2025 nesta configuração), o dataframe pode ficar
    vazio e o valor considerado no período será 0.
    """
    colunas = [
        "empresa_chave",
        "tipo_provento",
        "periodo_deliberacao",
        "data",
        "data_pagamento",
        "base_distribuicao",
        "volume_total_brl",
        "dividendo_por_acao_brl",
        "fonte",
    ]

    if not ARQUIVO_PROVENTOS.exists():
        if DIVIDENDOS_OFICIAIS_COMPLETOS:
            raise FileNotFoundError(
                f"Arquivo de proventos não encontrado: {ARQUIVO_PROVENTOS}"
            )
        print(
            f"[AVISO] {EMPRESA_CHAVE}: sem arquivo oficial detalhado "
            "de proventos. DY ficará NaN."
        )
        return pd.DataFrame(columns=colunas)

    df = pd.read_csv(
        ARQUIVO_PROVENTOS,
        encoding="utf-8-sig",
        dtype={"empresa_chave": str},
    )

    faltantes = [c for c in colunas if c not in df.columns]
    if faltantes:
        raise ValueError(
            "proventos_oficiais.csv sem colunas obrigatórias: "
            + ", ".join(faltantes)
        )

    df = df[df["empresa_chave"].str.lower() == EMPRESA_CHAVE.lower()].copy()

    if df.empty:
        if DIVIDENDOS_OFICIAIS_COMPLETOS and PROVENTOS_ESPERA_EVENTOS:
            raise ValueError(
                f"{EMPRESA_CHAVE}: configuração diz que há proventos "
                "oficiais detalhados, mas nenhuma linha foi encontrada."
            )

        if not DIVIDENDOS_OFICIAIS_COMPLETOS:
            print(
                f"[AVISO] {EMPRESA_CHAVE}: RI disponível apenas em formato "
                "insuficiente para DY semestral detalhado. DY ficará NaN."
            )

        return pd.DataFrame(columns=colunas)

    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["data_pagamento"] = pd.to_datetime(
        df["data_pagamento"], errors="coerce"
    )
    df["dividendo_por_acao_brl"] = pd.to_numeric(
        df["dividendo_por_acao_brl"], errors="coerce"
    )
    df["volume_total_brl"] = pd.to_numeric(
        df["volume_total_brl"], errors="coerce"
    )

    if RI_DIVIDENDOS_URL:
        df["fonte"] = df["fonte"].fillna(RI_DIVIDENDOS_URL)

    return df.sort_values("data").reset_index(drop=True)


# ============================================================
# AJUSTES HISTÓRICOS / RECLASSIFICAÇÕES
# ============================================================

def aplicar_ajustes_historicos(financeiro: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica correções pontuais documentadas em `ajustes_historicos.csv`.

    O objetivo é tratar situações em que uma companhia reapresenta/reclassifica
    comparativos históricos, mas o layout padronizado da CVM não permite
    recuperar automaticamente todos os campos com a mesma regra.

    Regras:
    1) O ajuste só altera os campos explicitamente informados no CSV.
    2) Antes de aplicar os ajustes de 1S, preserva-se o total anual implícito:
         total anual = 1S original + 2S original
    3) Se um campo de fluxo do 1S for ajustado, o 2S do mesmo ano é recalculado:
         2S corrigido = total anual preservado - 1S corrigido
    4) Campos de posição patrimonial (Ativo/PL) não são recalculados por essa
       rotina; permanecem conforme as demonstrações de posição utilizadas.
    """
    df = financeiro.copy()

    # Colunas de auditoria.
    if "ajuste_historico_aplicado" not in df.columns:
        df["ajuste_historico_aplicado"] = False
    if "campos_ajustados" not in df.columns:
        df["campos_ajustados"] = ""
    if "fonte_ajuste_historico" not in df.columns:
        df["fonte_ajuste_historico"] = ""
    if "motivo_ajuste_historico" not in df.columns:
        df["motivo_ajuste_historico"] = ""

    if not ARQUIVO_AJUSTES_HISTORICOS.exists():
        return df

    ajustes = pd.read_csv(
        ARQUIVO_AJUSTES_HISTORICOS,
        encoding="utf-8-sig",
        dtype={"empresa_chave": str, "semestre": str, "campo": str},
    )

    obrigatorias = {
        "empresa_chave",
        "data_referencia",
        "semestre",
        "campo",
        "valor_brl",
        "fonte",
        "motivo",
    }
    faltantes = obrigatorias.difference(ajustes.columns)
    if faltantes:
        raise ValueError(
            "ajustes_historicos.csv sem colunas obrigatórias: "
            + ", ".join(sorted(faltantes))
        )

    ajustes = ajustes[
        ajustes["empresa_chave"].str.lower() == EMPRESA_CHAVE.lower()
    ].copy()

    if ajustes.empty:
        return df

    df["data_referencia"] = pd.to_datetime(
        df["data_referencia"], errors="coerce"
    )
    ajustes["data_referencia"] = pd.to_datetime(
        ajustes["data_referencia"], errors="coerce"
    )
    ajustes["valor_brl"] = pd.to_numeric(
        ajustes["valor_brl"], errors="coerce"
    )

    # Preserva os totais anuais implícitos ANTES de mexer no 1S.
    campos_fluxo = [
        "receita_semestre_brl",
        "lucro_liquido_consolidado_semestre_brl",
        "lucro_atribuivel_controladores_semestre_brl",
    ]

    totais_anuais = {}

    for ano in sorted(df["ano"].dropna().astype(int).unique()):
        linha_1s = df[
            (df["ano"].astype(int) == ano)
            & (df["semestre"].astype(str) == "1S")
        ]
        linha_2s = df[
            (df["ano"].astype(int) == ano)
            & (df["semestre"].astype(str) == "2S")
        ]

        if linha_1s.empty or linha_2s.empty:
            continue

        totais_anuais[ano] = {}

        for campo in campos_fluxo:
            v1 = pd.to_numeric(
                linha_1s.iloc[0].get(campo), errors="coerce"
            )
            v2 = pd.to_numeric(
                linha_2s.iloc[0].get(campo), errors="coerce"
            )

            if pd.notna(v1) and pd.notna(v2):
                totais_anuais[ano][campo] = float(v1) + float(v2)
            else:
                totais_anuais[ano][campo] = np.nan

    anos_campos_1s_ajustados = {}

    for _, ajuste in ajustes.iterrows():
        data_ref = pd.Timestamp(ajuste["data_referencia"])
        semestre = str(ajuste["semestre"])
        campo = str(ajuste["campo"]).strip()
        valor = ajuste["valor_brl"]

        if campo not in df.columns:
            raise ValueError(
                f"Ajuste histórico solicita campo inexistente: {campo}"
            )

        mask = (
            (df["data_referencia"] == data_ref)
            & (df["semestre"].astype(str) == semestre)
        )

        if mask.sum() != 1:
            raise ValueError(
                f"Esperava 1 linha para ajuste {EMPRESA_CHAVE} "
                f"{data_ref.date()} {semestre}, mas encontrei {mask.sum()}."
            )

        df.loc[mask, campo] = valor
        df.loc[mask, "ajuste_historico_aplicado"] = True

        campos_atuais = str(
            df.loc[mask, "campos_ajustados"].iloc[0] or ""
        ).strip()
        lista_campos = [
            x for x in campos_atuais.split(";") if x
        ]
        if campo not in lista_campos:
            lista_campos.append(campo)
        df.loc[mask, "campos_ajustados"] = ";".join(lista_campos)

        df.loc[mask, "fonte_ajuste_historico"] = str(
            ajuste.get("fonte", "")
        )
        df.loc[mask, "motivo_ajuste_historico"] = str(
            ajuste.get("motivo", "")
        )

        ano = int(data_ref.year)

        if semestre == "1S" and campo in campos_fluxo:
            anos_campos_1s_ajustados.setdefault(ano, set()).add(campo)

    # Recalcula o 2S para manter o total anual reapresentado já preservado.
    for ano, campos in anos_campos_1s_ajustados.items():
        mask_1s = (
            (df["ano"].astype(int) == ano)
            & (df["semestre"].astype(str) == "1S")
        )
        mask_2s = (
            (df["ano"].astype(int) == ano)
            & (df["semestre"].astype(str) == "2S")
        )

        if mask_1s.sum() != 1 or mask_2s.sum() != 1:
            continue

        for campo in campos:
            total_anual = totais_anuais.get(ano, {}).get(campo, np.nan)
            novo_1s = pd.to_numeric(
                df.loc[mask_1s, campo].iloc[0],
                errors="coerce",
            )

            if pd.notna(total_anual) and pd.notna(novo_1s):
                novo_2s = float(total_anual) - float(novo_1s)
                df.loc[mask_2s, campo] = novo_2s

                df.loc[mask_2s, "ajuste_historico_aplicado"] = True

                campos_atuais = str(
                    df.loc[mask_2s, "campos_ajustados"].iloc[0] or ""
                ).strip()
                lista_campos = [
                    x for x in campos_atuais.split(";") if x
                ]
                nome_derivado = campo + "_recalculado_2S"
                if nome_derivado not in lista_campos:
                    lista_campos.append(nome_derivado)

                df.loc[mask_2s, "campos_ajustados"] = ";".join(lista_campos)
                df.loc[
                    mask_2s,
                    "fonte_ajuste_historico",
                ] = "Derivado do ajuste histórico do 1S + total anual preservado"
                df.loc[
                    mask_2s,
                    "motivo_ajuste_historico",
                ] = (
                    "2S recalculado para manter consistência com o "
                    "comparativo/reclassificação do 1S."
                )

    return df


# ============================================================
# YFINANCE - PREÇOS, AÇÕES E INFO DE MERCADO
# ============================================================

def coletar_mercado():
    ticker = yf.Ticker(EMPRESA["ticker_yahoo"])

    inicio_coleta = f"{ANO_BOOTSTRAP}-01-01"
    fim_exclusivo = f"{max(ANOS_ALVO) + 1}-01-02"

    print("\n=== Yahoo Finance / yfinance ===")
    print(f"Ticker: {EMPRESA['ticker_yahoo']}")
    print(f"Período: {inicio_coleta} até {fim_exclusivo} (fim exclusivo)")

    hist = ticker.history(
        start=inicio_coleta,
        end=fim_exclusivo,
        interval="1d",
        auto_adjust=False,
        actions=True,
        repair=True,
    )

    if hist.empty:
        raise RuntimeError("yfinance não retornou histórico de preços.")

    hist = hist.reset_index()

    # Nome da primeira coluna varia (Date/Datetime)
    coluna_data = hist.columns[0]
    hist = hist.rename(columns={coluna_data: "data"})
    hist["data"] = pd.to_datetime(hist["data"], errors="coerce")

    # Remove timezone para facilitar Power BI/CSV.
    try:
        hist["data"] = hist["data"].dt.tz_localize(None)
    except TypeError:
        pass

    # Histórico de ações em circulação.
    try:
        shares = ticker.get_shares_full(
            start=inicio_coleta,
            end=fim_exclusivo,
        )
        if shares is None or len(shares) == 0:
            shares_df = pd.DataFrame(
                columns=["data", "acoes_em_circulacao"]
            )
        else:
            shares_df = shares.rename("acoes_em_circulacao").reset_index()
            shares_df.columns = ["data", "acoes_em_circulacao"]
            shares_df["data"] = pd.to_datetime(
                shares_df["data"], errors="coerce"
            )
            try:
                shares_df["data"] = shares_df["data"].dt.tz_localize(None)
            except TypeError:
                pass
            shares_df = shares_df.sort_values("data")
    except Exception as exc:
        print(f"[AVISO] Não consegui histórico de ações: {exc}")
        shares_df = pd.DataFrame(
            columns=["data", "acoes_em_circulacao"]
        )

    # Snapshot atual de informações de mercado.
    info_interesse = {}
    try:
        info = ticker.get_info()
        chaves = [
            "symbol",
            "longName",
            "currency",
            "exchange",
            "quoteType",
            "sector",
            "industry",
            "marketCap",
            "sharesOutstanding",
            "currentPrice",
            "previousClose",
            "fiftyTwoWeekHigh",
            "fiftyTwoWeekLow",
            "trailingPE",
            "priceToBook",
            "dividendYield",
        ]
        info_interesse = {k: info.get(k) for k in chaves}
    except Exception as exc:
        print(f"[AVISO] Não consegui ticker.get_info(): {exc}")

    return hist, shares_df, info_interesse


# ============================================================
# ENRIQUECIMENTO POR DATA DE REFERÊNCIA
# ============================================================

def ultimo_registro_ate(df: pd.DataFrame, data_ref: pd.Timestamp,
                        col_data: str, col_valor: str):
    if df.empty:
        return np.nan

    temp = df.copy()
    temp[col_data] = pd.to_datetime(temp[col_data], errors="coerce")
    temp = temp[
        (temp[col_data].notna())
        & (temp[col_data] <= data_ref)
        & (temp[col_valor].notna())
    ].sort_values(col_data)

    if temp.empty:
        return np.nan

    return temp.iloc[-1][col_valor]


def soma_dividendos_periodo(
    dividendos: pd.DataFrame,
    inicio: pd.Timestamp,
    fim: pd.Timestamp,
) -> float:
    if dividendos.empty:
        if DIVIDENDOS_OFICIAIS_COMPLETOS:
            return 0.0
        return np.nan

    temp = dividendos.copy()
    temp["data"] = pd.to_datetime(temp["data"], errors="coerce")
    mask = (temp["data"] >= inicio) & (temp["data"] <= fim)

    return float(
        pd.to_numeric(
            temp.loc[mask, "dividendo_por_acao_brl"],
            errors="coerce",
        ).fillna(0).sum()
    )


def enriquecer_semestres_com_mercado(
    financeiro: pd.DataFrame,
    precos: pd.DataFrame,
    dividendos: pd.DataFrame,
    shares: pd.DataFrame,
) -> pd.DataFrame:
    df = financeiro.copy().sort_values("data_referencia").reset_index(drop=True)
    precos = precos.copy()
    precos["data"] = pd.to_datetime(precos["data"], errors="coerce")

    linhas = []

    for _, row in df.iterrows():
        linha = row.to_dict()
        ref = pd.Timestamp(row["data_referencia"])

        # Último pregão até a data-base.
        close = ultimo_registro_ate(precos, ref, "data", "Close")
        acoes = ultimo_registro_ate(
            shares, ref, "data", "acoes_em_circulacao"
        ) if not shares.empty else np.nan

        inicio_semestre = (
            pd.Timestamp(year=ref.year, month=1, day=1)
            if row["semestre"] == "1S"
            else pd.Timestamp(year=ref.year, month=7, day=1)
        )

        div_semestre = soma_dividendos_periodo(
            dividendos, inicio_semestre, ref
        )

        inicio_12m = ref - pd.DateOffset(years=1) + pd.Timedelta(days=1)
        div_12m = soma_dividendos_periodo(
            dividendos, inicio_12m, ref
        )

        linha["preco_fechamento_data_ref_brl"] = close
        linha["acoes_em_circulacao_data_ref"] = acoes
        linha["valor_mercado_estimado_data_ref_brl"] = (
            float(close) * float(acoes)
            if pd.notna(close) and pd.notna(acoes)
            else np.nan
        )
        linha["dividendos_por_acao_semestre_brl"] = div_semestre
        linha["dividendos_por_acao_12m_brl"] = div_12m

        linhas.append(linha)

    return pd.DataFrame(linhas)


# ============================================================
# INDICADORES
# ============================================================

def dividir(a, b, multiplicador=1.0):
    if pd.isna(a) or pd.isna(b) or float(b) == 0:
        return np.nan
    return float(a) / float(b) * multiplicador


def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Metodologia:
    - P/L: valor de mercado / lucro atribuível aos controladores TTM (12M)
    - P/VP: valor de mercado / patrimônio atribuível aos controladores
    - ROE: lucro atribuível aos controladores TTM / patrimônio atribuível
    - ROA: lucro líquido consolidado TTM / ativo total
    - Margem Líquida: lucro líquido consolidado TTM / receita TTM
    - Dividend Yield: dividendos por ação dos últimos 12M / preço
    - Crescimento de Receita YoY: semestre atual vs mesmo semestre do ano anterior

    Além disso, o CSV preserva todos os dados-base usados nos cálculos.
    """
    out = df.copy().sort_values("data_referencia").reset_index(drop=True)

    # TTM = soma dos dois últimos semestres
    out["receita_ttm_brl"] = (
        out["receita_semestre_brl"]
        + out["receita_semestre_brl"].shift(1)
    )

    out["lucro_consolidado_ttm_brl"] = (
        out["lucro_liquido_consolidado_semestre_brl"]
        + out["lucro_liquido_consolidado_semestre_brl"].shift(1)
    )

    out["lucro_controladores_ttm_brl"] = (
        out["lucro_atribuivel_controladores_semestre_brl"]
        + out["lucro_atribuivel_controladores_semestre_brl"].shift(1)
    )

    # Se a conta 3.11.01 não existir, usa o lucro consolidado.
    lucro_ctrl_ttm = out["lucro_controladores_ttm_brl"].where(
        out["lucro_controladores_ttm_brl"].notna(),
        out["lucro_consolidado_ttm_brl"],
    )

    pl_ctrl = out["patrimonio_atribuivel_controladores_brl"].where(
        out["patrimonio_atribuivel_controladores_brl"].notna(),
        out["patrimonio_liquido_consolidado_brl"],
    )

    market_cap = out["valor_mercado_estimado_data_ref_brl"]

    out["pl_preco_lucro"] = [
        dividir(mc, ll)
        for mc, ll in zip(market_cap, lucro_ctrl_ttm)
    ]

    out["pvp_preco_valor_patrimonial"] = [
        dividir(mc, pl)
        for mc, pl in zip(market_cap, pl_ctrl)
    ]

    out["roe_pct"] = [
        dividir(ll, pl, 100)
        for ll, pl in zip(lucro_ctrl_ttm, pl_ctrl)
    ]

    out["roa_pct"] = [
        dividir(ll, ativo, 100)
        for ll, ativo in zip(
            out["lucro_consolidado_ttm_brl"],
            out["ativo_total_brl"],
        )
    ]

    out["margem_liquida_pct"] = [
        dividir(ll, receita, 100)
        for ll, receita in zip(
            out["lucro_consolidado_ttm_brl"],
            out["receita_ttm_brl"],
        )
    ]

    out["dividend_yield_12m_pct"] = [
        dividir(div, preco, 100)
        for div, preco in zip(
            out["dividendos_por_acao_12m_brl"],
            out["preco_fechamento_data_ref_brl"],
        )
    ]

    # Crescimento de Receita YoY (Year over Year):
    # 1S/2025 é comparado com 1S/2024;
    # 2S/2025 é comparado com 2S/2024.
    #
    # O dataframe ainda contém o ano bootstrap (2022) nesta etapa,
    # então o YoY de 2023 também pode ser calculado antes do filtro
    # final que mantém apenas ANOS_ALVO.
    receita_lookup = {
        (int(row["ano"]), str(row["semestre"])): row["receita_semestre_brl"]
        for _, row in out.iterrows()
    }

    receitas_ano_anterior = []
    crescimentos_yoy = []

    for _, row in out.iterrows():
        atual = row["receita_semestre_brl"]
        chave_anterior = (int(row["ano"]) - 1, str(row["semestre"]))
        anterior = receita_lookup.get(chave_anterior, np.nan)

        receitas_ano_anterior.append(anterior)

        if pd.notna(atual) and pd.notna(anterior) and float(anterior) != 0:
            crescimentos_yoy.append(
                dividir(float(atual) - float(anterior), anterior, 100)
            )
        else:
            crescimentos_yoy.append(np.nan)

    out["receita_mesmo_semestre_ano_anterior_brl"] = receitas_ano_anterior
    out["crescimento_receita_yoy_pct"] = crescimentos_yoy

    return out


# ============================================================
# SAÍDA
# ============================================================

def salvar_saidas(
    financeiro: pd.DataFrame,
    precos: pd.DataFrame,
    dividendos: pd.DataFrame,
    shares: pd.DataFrame,
    info: dict,
    indicadores: pd.DataFrame,
) -> None:
    # Somente anos do projeto nos arquivos principais.
    financeiro_alvo = financeiro[
        financeiro["ano"].isin(ANOS_ALVO)
    ].copy()

    indicadores_alvo = indicadores[
        indicadores["ano"].isin(ANOS_ALVO)
    ].copy()

    # Identificação explícita para posterior consolidação e banco de dados.
    for tabela in (financeiro_alvo, indicadores_alvo):
        tabela["empresa_chave"] = EMPRESA_CHAVE
        tabela["setor"] = EMPRESA.get("setor", "")

    inicio = pd.Timestamp(f"{min(ANOS_ALVO)}-01-01")
    fim = pd.Timestamp(f"{max(ANOS_ALVO)}-12-31")

    precos_alvo = precos[
        (pd.to_datetime(precos["data"]) >= inicio)
        & (pd.to_datetime(precos["data"]) <= fim)
    ].copy()

    inicio_proventos = pd.Timestamp(f"{ANO_BOOTSTRAP}-01-01")

    dividendos_alvo = dividendos[
        (pd.to_datetime(dividendos["data"]) >= inicio_proventos)
        & (pd.to_datetime(dividendos["data"]) <= fim)
    ].copy() if not dividendos.empty else dividendos.copy()

    if not dividendos_alvo.empty:
        dividendos_alvo["evento_bootstrap"] = (
            pd.to_datetime(dividendos_alvo["data"]).dt.year
            < min(ANOS_ALVO)
        )

    for tabela in (precos_alvo, dividendos_alvo, shares):
        tabela["empresa_chave"] = EMPRESA_CHAVE
        tabela["empresa"] = EMPRESA["nome"]
        tabela["ticker"] = EMPRESA["ticker_b3"]
        tabela["setor"] = EMPRESA.get("setor", "")

    financeiro_alvo.to_csv(
        PASTA_SAIDA / f"{PREFIXO_ARQUIVO}_financeiro_semestral.csv",
        index=False,
        encoding="utf-8-sig",
    )

    precos_alvo.to_csv(
        PASTA_SAIDA / f"{PREFIXO_ARQUIVO}_precos_diarios.csv",
        index=False,
        encoding="utf-8-sig",
    )

    dividendos_alvo.to_csv(
        PASTA_SAIDA / f"{PREFIXO_ARQUIVO}_dividendos.csv",
        index=False,
        encoding="utf-8-sig",
    )

    shares.to_csv(
        PASTA_SAIDA / f"{PREFIXO_ARQUIVO}_acoes_em_circulacao.csv",
        index=False,
        encoding="utf-8-sig",
    )

    indicadores_alvo.to_csv(
        PASTA_SAIDA / f"{PREFIXO_ARQUIVO}_indicadores.csv",
        index=False,
        encoding="utf-8-sig",
    )

    with open(
        PASTA_SAIDA / f"{PREFIXO_ARQUIVO}_info_mercado_atual.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(info, f, ensure_ascii=False, indent=2, default=str)


def adicionar_comparabilidade_yoy(indicadores: pd.DataFrame) -> pd.DataFrame:
    """
    Adiciona sinalização qualitativa para períodos em que o crescimento YoY
    é matematicamente calculável, mas economicamente não é diretamente
    comparável por mudança estrutural relevante na companhia.

    A configuração fica em:
      EMPRESA["periodos_nao_comparaveis_yoy"]

    Formato:
      {
        "YYYY-MM-DD": "motivo"
      }

    O valor numérico do crescimento NÃO é apagado. O dashboard pode mostrar
    o número acompanhado da sinalização de comparabilidade.
    """
    df = indicadores.copy()

    df["comparabilidade_yoy"] = "COMPARAVEL"
    df["motivo_comparabilidade_yoy"] = ""

    mapa = EMPRESA.get("periodos_nao_comparaveis_yoy", {}) or {}

    if not mapa:
        return df

    datas = pd.to_datetime(df["data_referencia"], errors="coerce")

    for data_txt, motivo in mapa.items():
        data_alvo = pd.Timestamp(data_txt)
        mask = datas == data_alvo

        if mask.any():
            df.loc[mask, "comparabilidade_yoy"] = "NAO_COMPARAVEL"
            df.loc[mask, "motivo_comparabilidade_yoy"] = str(motivo)

    return df


def salvar_metadata_execucao() -> None:
    metadata = {
        "empresa_chave": EMPRESA_CHAVE,
        "empresa": EMPRESA["nome"],
        "cnpj": EMPRESA["cnpj"],
        "ticker_b3": EMPRESA["ticker_b3"],
        "ticker_yahoo": EMPRESA["ticker_yahoo"],
        "setor": EMPRESA.get("setor"),
        "anos_alvo": ANOS_ALVO,
        "ano_bootstrap": ANO_BOOTSTRAP,
        "proventos_status": EMPRESA.get("proventos_status"),
        "ri_dividendos_url": EMPRESA.get("ri_dividendos_url"),
        "usar_comparativos_reapresentados":
            EMPRESA.get("usar_comparativos_reapresentados", False),
        "arquivo_ajustes_historicos": str(ARQUIVO_AJUSTES_HISTORICOS),
        "periodos_nao_comparaveis_yoy":
            EMPRESA.get("periodos_nao_comparaveis_yoy", {}),
        "contas_cvm": EMPRESA.get("contas", {}),
        "observacoes": EMPRESA.get("observacoes", []),
    }
    with open(
        PASTA_SAIDA / f"{PREFIXO_ARQUIVO}_metadata.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2, default=str)


def executar_empresa(chave: str) -> None:
    configurar_empresa(chave)
    garantir_pastas()

    print("\n" + "=" * 62)
    print(f"COLETA: {EMPRESA['nome']} ({EMPRESA['ticker_b3']})")
    print("=" * 62)
    print(f"CNPJ: {EMPRESA['cnpj']}")
    print(f"Setor: {EMPRESA.get('setor', '')}")
    print(f"Saída: {PASTA_SAIDA.resolve()}")

    financeiro = coletar_financeiro_cvm()

    if financeiro.empty:
        raise RuntimeError(
            f"Nenhum dado financeiro foi extraído para {EMPRESA_CHAVE}."
        )

    # Aplica reclassificações históricas documentadas antes de calcular
    # TTM, crescimento YoY e demais indicadores.
    financeiro = aplicar_ajustes_historicos(financeiro)

    precos, shares, info = coletar_mercado()
    dividendos = carregar_dividendos_ri_oficial()

    financeiro_mercado = enriquecer_semestres_com_mercado(
        financeiro,
        precos,
        dividendos,
        shares,
    )

    indicadores = calcular_indicadores(financeiro_mercado)
    indicadores = adicionar_comparabilidade_yoy(indicadores)

    salvar_saidas(
        financeiro_mercado,
        precos,
        dividendos,
        shares,
        info,
        indicadores,
    )
    salvar_metadata_execucao()

    print("\n" + "=" * 62)
    print(f"CONCLUÍDO: {EMPRESA_CHAVE}")
    print("=" * 62)
    print(f"Arquivos em: {PASTA_SAIDA.resolve()}")
    print(f"- {PREFIXO_ARQUIVO}_financeiro_semestral.csv")
    print(f"- {PREFIXO_ARQUIVO}_precos_diarios.csv")
    print(f"- {PREFIXO_ARQUIVO}_dividendos.csv")
    print(f"- {PREFIXO_ARQUIVO}_acoes_em_circulacao.csv")
    print(f"- {PREFIXO_ARQUIVO}_indicadores.csv")
    print(f"- {PREFIXO_ARQUIVO}_info_mercado_atual.json")
    print(f"- {PREFIXO_ARQUIVO}_metadata.json")


def consolidar_saidas(chaves: list[str]) -> None:
    PASTA_CONSOLIDADO.mkdir(parents=True, exist_ok=True)

    tipos = {
        "financeiro_semestral": [],
        "precos_diarios": [],
        "dividendos": [],
        "acoes_em_circulacao": [],
        "indicadores": [],
    }

    empresas = carregar_empresas_config()

    for chave in chaves:
        cfg = empresas[chave]
        prefixo = cfg.get("prefixo_arquivo", chave)
        pasta = PASTA_BASE_SAIDA / prefixo

        for tipo in tipos:
            arquivo = pasta / f"{prefixo}_{tipo}.csv"
            if arquivo.exists():
                try:
                    df = pd.read_csv(arquivo, encoding="utf-8-sig")
                    if not df.empty:
                        tipos[tipo].append(df)
                except Exception as exc:
                    print(f"[AVISO] Não foi possível consolidar {arquivo}: {exc}")

    for tipo, partes in tipos.items():
        if partes:
            combinado = pd.concat(partes, ignore_index=True, sort=False)
            destino = PASTA_CONSOLIDADO / f"{tipo}_todas_empresas.csv"
            combinado.to_csv(destino, index=False, encoding="utf-8-sig")
            print(f"Consolidado: {destino}")

    # Cadastro das empresas para futura DimEmpresa/banco.
    cadastro = []
    for chave in chaves:
        cfg = empresas[chave]
        cadastro.append({
            "empresa_chave": chave,
            "empresa": cfg["nome"],
            "cnpj": cfg["cnpj"],
            "ticker": cfg["ticker_b3"],
            "ticker_yahoo": cfg["ticker_yahoo"],
            "setor": cfg.get("setor", ""),
            "proventos_status": cfg.get("proventos_status", ""),
            "ri_dividendos_url": cfg.get("ri_dividendos_url", ""),
        })

    pd.DataFrame(cadastro).to_csv(
        PASTA_CONSOLIDADO / "empresas.csv",
        index=False,
        encoding="utf-8-sig",
    )


def listar_empresas() -> None:
    empresas = carregar_empresas_config()
    print("\nEmpresas configuradas:\n")
    for chave, cfg in empresas.items():
        print(
            f"- {chave:10s} | {cfg['ticker_b3']:5s} | "
            f"{cfg['nome']} | proventos={cfg.get('proventos_status')}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Coletor parametrizado CVM + mercado + RI para o dashboard."
    )

    grupo = parser.add_mutually_exclusive_group(required=False)
    grupo.add_argument(
        "--empresa",
        help="Chave da empresa, ex.: smartfit, totvs, porto, mrv, localiza",
    )
    grupo.add_argument(
        "--todas",
        action="store_true",
        help="Executa todas as empresas configuradas e gera CSVs consolidados.",
    )
    grupo.add_argument(
        "--listar",
        action="store_true",
        help="Lista as empresas configuradas.",
    )

    parser.add_argument(
        "--limpar-cache",
        action="store_true",
        help="Apaga os ZIPs locais da CVM antes da coleta.",
    )

    args = parser.parse_args()

    if args.limpar_cache and PASTA_CACHE_CVM.exists():
        for arquivo in PASTA_CACHE_CVM.glob("*.zip"):
            try:
                arquivo.unlink()
            except OSError:
                pass
        print("Cache CVM limpo.")

    empresas = carregar_empresas_config()

    if args.listar or (not args.empresa and not args.todas):
        listar_empresas()
        print("\nExemplos:")
        print("  python coletor_parametrizado.py --empresa smartfit")
        print("  python coletor_parametrizado.py --empresa totvs")
        print("  python coletor_parametrizado.py --todas")
        return

    if args.todas:
        chaves = list(empresas.keys())
        erros = []

        for chave in chaves:
            try:
                executar_empresa(chave)
            except Exception as exc:
                erros.append((chave, str(exc)))
                print(f"\n[ERRO] {chave}: {exc}")

        consolidar_saidas(chaves)

        if erros:
            print("\nEmpresas com erro:")
            for chave, erro in erros:
                print(f"- {chave}: {erro}")
        return

    if args.empresa not in empresas:
        raise SystemExit(
            f"Empresa '{args.empresa}' não existe. "
            f"Use --listar para ver as opções."
        )

    executar_empresa(args.empresa)


if __name__ == "__main__":
    main()
