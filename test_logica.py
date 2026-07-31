"""
Testes automatizados da lógica pura do sistema.
Rode com: pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from logica import (
    calcular_km_rodado,
    status_troca_oleo,
    formatar_numero_fiscalizacao,
    extrair_trecho,
    melhor_correspondencia_nome,
    extrair_viatura,
    interpretar_guarnicao_por_voz,
)

NOMES_EFETIVO = [
    "1º Tenente PM Gesner Batista Ramos",
    "3º Sargento PM Madson Acosta Flores",
    "Cabo PM Thiago David Mareco de Souza",
]


# ---------------------------------------------------------------------------
# KM rodado
# ---------------------------------------------------------------------------

def test_km_rodado_calculo_normal():
    assert calcular_km_rodado(150000, 150230) == 230

def test_km_rodado_final_igual_inicial():
    assert calcular_km_rodado(150000, 150000) == 0

def test_km_rodado_nao_fica_negativo_com_dado_invalido():
    # km_final menor que km_inicial não pode gerar km rodado negativo
    assert calcular_km_rodado(150000, 100) == 0

def test_km_rodado_com_valores_none():
    assert calcular_km_rodado(None, 150000) == 0
    assert calcular_km_rodado(150000, None) == 0


# ---------------------------------------------------------------------------
# Troca de óleo
# ---------------------------------------------------------------------------

def test_troca_oleo_situacao_ok():
    situacao, msg = status_troca_oleo(km_inicial=155000, ultima_troca_km=150000)
    assert situacao == "ok"

def test_troca_oleo_situacao_alerta():
    # faltam 400km pros 10.000 -> deve alertar
    situacao, msg = status_troca_oleo(km_inicial=159600, ultima_troca_km=150000)
    assert situacao == "alerta"
    assert "400" in msg

def test_troca_oleo_situacao_atrasado():
    situacao, msg = status_troca_oleo(km_inicial=161000, ultima_troca_km=150000)
    assert situacao == "atrasado"

def test_troca_oleo_limite_exato_9500():
    situacao, _ = status_troca_oleo(km_inicial=159500, ultima_troca_km=150000)
    assert situacao == "alerta"

def test_troca_oleo_limite_exato_10000():
    situacao, _ = status_troca_oleo(km_inicial=160000, ultima_troca_km=150000)
    assert situacao == "atrasado"


# ---------------------------------------------------------------------------
# Numeração do Relatório de Fiscalização
# ---------------------------------------------------------------------------

def test_formatar_numero_fiscalizacao():
    numero = formatar_numero_fiscalizacao(2, "2ºPEL/2ªCIA/1ºBPMA/CPAMB", 2026)
    assert numero == "02/2ºPEL/2ªCIA/1ºBPMA/CPAMB/2026"

def test_formatar_numero_fiscalizacao_sequencial_dois_digitos():
    numero = formatar_numero_fiscalizacao(15, "2ºPEL/2ªCIA/1ºBPMA/CPAMB", 2027)
    assert numero.startswith("15/")


# ---------------------------------------------------------------------------
# Interpretação de comandos de voz
# ---------------------------------------------------------------------------

def test_extrair_trecho_basico():
    texto = "comandante Madson motorista Mareco"
    resultado = extrair_trecho("comandante", ["comandante", "motorista"], texto.lower(), texto)
    assert resultado.strip() == "Madson"

def test_extrair_trecho_chave_ausente():
    texto = "motorista Mareco"
    resultado = extrair_trecho("comandante", ["comandante", "motorista"], texto.lower(), texto)
    assert resultado is None

def test_melhor_correspondencia_nome_encontra_por_sobrenome():
    resultado = melhor_correspondencia_nome("sargento madson", NOMES_EFETIVO)
    assert resultado == "3º Sargento PM Madson Acosta Flores"

def test_melhor_correspondencia_nome_nao_encontra():
    resultado = melhor_correspondencia_nome("nome que nao existe na lista", NOMES_EFETIVO)
    assert resultado is None

def test_melhor_correspondencia_nome_trecho_vazio():
    assert melhor_correspondencia_nome("", NOMES_EFETIVO) is None
    assert melhor_correspondencia_nome(None, NOMES_EFETIVO) is None

def test_extrair_viatura_encontra_placa():
    resultado = extrair_viatura("a viatura empregada é RWE6B39 hoje")
    assert resultado == "RWE6B39"

def test_extrair_viatura_sem_padrao_de_placa():
    # nenhuma palavra tem letra+número misturados -> usa a última palavra como palpite
    resultado = extrair_viatura("nenhuma placa aqui")
    assert resultado == "AQUI"

def test_interpretar_guarnicao_por_voz_frase_completa():
    frase = "Comandante Sargento Madson, motorista Mareco, viatura RWE6B39, km inicial 12000"
    resultado = interpretar_guarnicao_por_voz(frase, NOMES_EFETIVO)
    assert resultado["comandante"] == "3º Sargento PM Madson Acosta Flores"
    assert resultado["motorista"] == "Cabo PM Thiago David Mareco de Souza"
    assert resultado["viatura"] == "RWE6B39"
    assert resultado["km_inicial"] == 12000

def test_interpretar_guarnicao_por_voz_km_com_pontuacao():
    frase = "km inicial 12.500"
    resultado = interpretar_guarnicao_por_voz(frase, NOMES_EFETIVO)
    assert resultado["km_inicial"] == 12500

def test_interpretar_guarnicao_por_voz_campos_ausentes_ficam_none():
    frase = "sem nenhuma informação reconhecível aqui"
    resultado = interpretar_guarnicao_por_voz(frase, NOMES_EFETIVO)
    assert resultado["comandante"] is None
    assert resultado["km_inicial"] is None
