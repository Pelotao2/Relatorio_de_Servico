"""
Funções de lógica "pura" do Sistema de Controle de Produtividade — ou seja,
sem depender do Streamlit, do banco de dados ou de qualquer coisa que precise
de uma sessão do app rodando. Por serem puras (mesma entrada = mesma saída,
sempre), dá pra testar automaticamente com pytest sem precisar abrir o app.

O app.py importa estas funções em vez de redefini-las.
"""
import re
import difflib


# ---------------------------------------------------------------------------
# Interpretação de comandos de voz (usado no preenchimento por voz da guarnição)
# ---------------------------------------------------------------------------

def extrair_trecho(chave, marcadores, texto_lower, texto_original):
    """Pega o texto entre uma palavra-chave e a próxima palavra-chave conhecida."""
    idx = texto_lower.find(chave)
    if idx == -1:
        return None
    inicio = idx + len(chave)
    fim = len(texto_original)
    for outro in marcadores:
        if outro == chave:
            continue
        idx_outro = texto_lower.find(outro, inicio)
        if idx_outro != -1 and idx_outro < fim:
            fim = idx_outro
    return texto_original[inicio:fim].strip(" :,-")


def melhor_correspondencia_nome(trecho, nomes_validos):
    """Casa um trecho de fala (ex.: 'sargento madson') com o nome completo mais
    parecido da lista do efetivo (ex.: '3º Sargento PM Madson Acosta Flores')."""
    if not trecho:
        return None
    candidatos = difflib.get_close_matches(trecho, nomes_validos, n=1, cutoff=0.45)
    if candidatos:
        return candidatos[0]
    palavras_trecho = [p for p in re.split(r'\s+', trecho.lower()) if len(p) > 2]
    melhor, melhor_pontos = None, 0
    for nome in nomes_validos:
        nome_lower = nome.lower()
        pontos = sum(1 for p in palavras_trecho if p in nome_lower)
        if pontos > melhor_pontos:
            melhor, melhor_pontos = nome, pontos
    return melhor if melhor_pontos > 0 else None


def extrair_viatura(trecho):
    """Procura, dentro do trecho falado, uma palavra com letras E números
    misturados (formato típico de prefixo/placa, ex.: RWE6B39)."""
    if not trecho:
        return None
    palavras = re.findall(r'[A-Za-z0-9\-]+', trecho)
    candidatos = [p for p in palavras if re.search(r'[A-Za-z]', p) and re.search(r'\d', p)]
    if candidatos:
        return candidatos[0].upper()
    return palavras[-1].upper() if palavras else None


def interpretar_guarnicao_por_voz(texto, nomes_validos):
    """Extrai comandante, motorista, viatura e KM inicial de uma frase falada
    de uma só vez, casando nomes com a lista de nomes válidos da unidade.
    Retorna um dicionário; campos não identificados vêm como None."""
    texto_lower = texto.lower()
    marcadores = ["comandante", "motorista", "viatura", "prefixo", "km inicial", "quilometragem inicial"]

    trecho_cmt = extrair_trecho("comandante", marcadores, texto_lower, texto)
    trecho_mot = extrair_trecho("motorista", marcadores, texto_lower, texto)
    trecho_viat = extrair_trecho("viatura", marcadores, texto_lower, texto) or \
                  extrair_trecho("prefixo", marcadores, texto_lower, texto)

    km_inicial = None
    m_km = re.search(r'km\s*inicial\D{0,6}(\d[\d\.]*)', texto_lower) or \
           re.search(r'quilometragem\s*inicial\D{0,6}(\d[\d\.]*)', texto_lower)
    if m_km:
        km_inicial = int(m_km.group(1).replace(".", ""))

    return {
        "comandante": melhor_correspondencia_nome(trecho_cmt, nomes_validos),
        "motorista": melhor_correspondencia_nome(trecho_mot, nomes_validos),
        "viatura": extrair_viatura(trecho_viat),
        "km_inicial": km_inicial
    }


# ---------------------------------------------------------------------------
# Quilometragem e troca de óleo
# ---------------------------------------------------------------------------

def calcular_km_rodado(km_inicial, km_final):
    """KM rodado no serviço. Nunca retorna negativo (protege contra dado
    inconsistente de km_final menor que km_inicial)."""
    if km_final is None or km_inicial is None or km_final < km_inicial:
        return 0
    return km_final - km_inicial


def status_troca_oleo(km_inicial, ultima_troca_km):
    """Verifica a situação da troca de óleo da viatura.
    Retorna uma tupla (situacao, mensagem) onde situacao é
    'ok', 'alerta' (faltam <500km) ou 'atrasado' (já passou dos 10.000km)."""
    km_desde_troca = km_inicial - ultima_troca_km
    if km_desde_troca >= 10000:
        return ("atrasado", f"Troca de óleo atrasada! Já rodou {km_desde_troca:.0f} km desde a última troca.")
    if km_desde_troca >= 9500:
        return ("alerta", f"Faltam {10000 - km_desde_troca:.0f} km para a próxima troca de óleo desta viatura!")
    return ("ok", "")


# ---------------------------------------------------------------------------
# Numeração de documentos
# ---------------------------------------------------------------------------

def formatar_numero_fiscalizacao(sequencial, designacao, ano):
    """Monta o número oficial do Relatório de Fiscalização, ex.: '02/2ºPEL/2ªCIA/1ºBPMA/CPAMB/2026'."""
    return f"{sequencial:02d}/{designacao}/{ano}"
