import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import re
import difflib
import unicodedata
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
import time
import re
import difflib
import unicodedata
import json
from datetime import datetime, timedelta

# --- SISTEMA DE AUTENTICAÇÃO ---
# Dicionário de usuários cadastrados (Altere/adicione os logins e senhas desejados aqui)
USUARIOS_PERMITIDOS = {
    "agente.pelotao": "SenhaPelotao2026",
    "comandante.123": "ComandoSeguro!#",
    "admin": "AdminNeon789"
}

# Inicializa as variáveis de controle de sessão se não existirem
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "usuario_conectado" not in st.session_state:
    st.session_state["usuario_conectado"] = ""
if "unidade_operacional" not in st.session_state:
    st.session_state["unidade_operacional"] = None

# Função que valida as credenciais
def realizar_login(usuario, senha):
    if usuario in USUARIOS_PERMITIDOS and USUARIOS_PERMITIDOS[usuario] == senha:
        st.session_state["autenticado"] = True
        st.session_state["usuario_conectado"] = usuario
        st.rerun()
    else:
        st.error("Usuário ou senha incorretos. Tente novamente.")

# --- PASSO 0: ESCOLHA DA UNIDADE (antes até da senha) ---
# Isola operacionalmente as duas unidades: cada uma só enxerga/mexe nos próprios
# serviços no Formulário de Serviço. O Painel Estratégico (Adm) continua vendo as duas.
if st.session_state["unidade_operacional"] is None:
    st.title("🪖 Sistema de Controle de Produtividade")
    st.subheader("Selecione sua unidade para continuar")
    col_un_a, col_un_b = st.columns(2)
    with col_un_a:
        if st.button("2º Pel Miranda", use_container_width=True, type="primary"):
            st.session_state["unidade_operacional"] = "2º Pel Miranda"
            st.rerun()
    with col_un_b:
        if st.button("GPM Barra", use_container_width=True, type="primary"):
            st.session_state["unidade_operacional"] = "GPM Barra"
            st.rerun()
    st.caption("O Painel Estratégico (Adm) continua com visão das duas unidades, após o login.")
    st.stop()

# Se o usuário NÃO estiver autenticado, exibe a tela de login e para a execução do app aqui
if not st.session_state["autenticado"]:
    st.title("🔒 Sistema de Controle de Produtividade")
    st.caption(f"Unidade selecionada: **{st.session_state['unidade_operacional']}**")
    if st.button("↩️ Trocar unidade"):
        st.session_state["unidade_operacional"] = None
        st.rerun()
    st.subheader("Efetue o login para acessar o formulário")
    
    with st.form("formulario_login"):
        user_input = st.text_input("Usuário / ID Funcional", placeholder="Ex: agente.nome")
        pass_input = st.text_input("Senha", type="password", placeholder="Digite sua senha")
        botao_entrar = st.form_submit_button("Acessar Sistema")
        
        if botao_entrar:
            realizar_login(user_input, pass_input)
            
    # Interrompe o carregamento do restante do código (Bloqueia o acesso)
    st.stop()

# --- FIM DO SISTEMA DE AUTENTICAÇÃO ---
if "patrulhamento_terrestre_list" not in st.session_state:
    st.session_state["patrulhamento_terrestre_list"] = []
if "patrulhamento_fluvial_list" not in st.session_state:
    st.session_state["patrulhamento_fluvial_list"] = []
if "capturas_animais_list" not in st.session_state:
    st.session_state["capturas_animais_list"] = []
if "apreensoes_list" not in st.session_state:
    st.session_state["apreensoes_list"] = []
if "relatorio_id_atual" not in st.session_state:
    st.session_state["relatorio_id_atual"] = None
if "guarnicao_carregada_key" not in st.session_state:
    st.session_state["guarnicao_carregada_key"] = None
if "editando_idx_animal" not in st.session_state:
    st.session_state["editando_idx_animal"] = None
if "editando_idx_terrestre" not in st.session_state:
    st.session_state["editando_idx_terrestre"] = None
if "editando_idx_fluvial" not in st.session_state:
    st.session_state["editando_idx_fluvial"] = None
if "editando_idx_apreensao" not in st.session_state:
    st.session_state["editando_idx_apreensao"] = None
if "doc_geracao" not in st.session_state:
    st.session_state["doc_geracao"] = 0

# Configuração da página (Modo Largo para Computadores do Quartel)
st.set_page_config(page_title="Sistema de Produtividade - Pelotão", page_icon="icone_pelotao_512.png", layout="wide")

# CSS de impressão: some com cabeçalho, barra de abas e botões apenas na hora
# de imprimir/salvar em PDF, deixando o relatório mais limpo no papel.
st.markdown("""
    <style>
    @media print {
        header[data-testid="stHeader"],
        div[data-testid="stToolbar"],
        section[data-testid="stSidebar"],
        div[data-baseweb="tab-list"],
        .stButton, .stDownloadButton, #MainMenu, footer {
            display: none !important;
        }
    }
    </style>
""", unsafe_allow_html=True)
# ==========================================
# CONEXÃO COM O BANCO DE DADOS (NEON PG)
# ==========================================
load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

def init_connection():
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        return None

def buscar_relatorio_em_andamento(unidade, comandante):
    """Procura, para a guarnição informada, um relatório com status 'Em Andamento'.
    Usado para retomar automaticamente o serviço do dia anterior."""
    conn = init_connection()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM relatorios_servico WHERE unidade = %s AND comandante = %s AND status = %s ORDER BY id DESC LIMIT 1;",
            (unidade, comandante, "Em Andamento")
        )
        registro = cur.fetchone()
        cur.close()
        conn.close()
        return registro
    except Exception:
        return None

def listar_relatorios_em_andamento(unidade):
    """Lista todos os relatórios 'Em Andamento' de uma unidade — usado no painel
    'GU Serviço' no topo do formulário, já isolado por unidade operacional."""
    conn = init_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM relatorios_servico WHERE unidade = %s AND status = %s ORDER BY id DESC;",
            (unidade, "Em Andamento")
        )
        registros = cur.fetchall()
        cur.close()
        conn.close()
        return registros
    except Exception:
        return []
def buscar_relatorios(unidade, termo):
    """Busca relatórios (qualquer status) por Nº do relatório ou nome do
    comandante, restrito à unidade operacional atual. Usado para localizar
    relatórios já concluídos e conferir/editar."""
    conn = init_connection()
    if not conn:
        return []
    try:
        cur = conn.cursor()
        termo_like = f"%{termo}%"
        cur.execute(
            "SELECT * FROM relatorios_servico WHERE unidade = %s AND (CAST(id AS TEXT) ILIKE %s OR comandante ILIKE %s) ORDER BY id DESC LIMIT 20;",
            (unidade, termo_like, termo_like)
        )
        registros = cur.fetchall()
        cur.close()
        conn.close()
        return registros
    except Exception:
        return []


def salvar_relatorio(colunas_valores: dict, id_existente=None):
    """Grava o relatório no banco: insere um novo registro (dia 1) ou atualiza
    um registro 'Em Andamento' já existente (dias 2 a 5). Retorna (id, erro)."""
    conn = init_connection()
    if not conn:
        return None, "Sem conexão com o banco de dados."
    try:
        cur = conn.cursor()
        if id_existente:
            # Campos "fundadores" do serviço: só são gravados na criação (Dia 1).
            # Nenhum salvamento posterior (autosave, edição de itens, progresso
            # do dia) pode alterá-los — evita que a contagem de dias/identidade
            # da guarnição seja corrompida por uma retomada ou salvamento parcial.
            campos_imutaveis_apos_criacao = {"data_inicial", "km_inicial", "unidade", "comandante"}
            colunas_valores = {k: v for k, v in colunas_valores.items() if k not in campos_imutaveis_apos_criacao}
            sets = ", ".join(f"{col} = %s" for col in colunas_valores.keys())
            valores = list(colunas_valores.values()) + [id_existente]
            cur.execute(f"UPDATE relatorios_servico SET {sets} WHERE id = %s;", valores)
            novo_id = id_existente
        else:
            colunas = ", ".join(colunas_valores.keys())
            placeholders = ", ".join(["%s"] * len(colunas_valores))
            valores = list(colunas_valores.values())
            cur.execute(f"INSERT INTO relatorios_servico ({colunas}) VALUES ({placeholders}) RETURNING id;", valores)
            novo_id = cur.fetchone()["id"]
        conn.commit()
        cur.close()
        conn.close()
        return novo_id, None
    except Exception as e:
        conn.close()
        return None, str(e)

def carregar_registro_na_sessao(registro_aberto):
    """Carrega todos os dados de um relatório 'Em Andamento' na sessão atual,
    reutilizada tanto pelo painel 'GU Serviço' quanto pela retomada manual."""
    st.session_state["relatorio_id_atual"] = registro_aberto["id"]
    st.session_state["patrulhamento_terrestre_list"] = json.loads(registro_aberto.get("patrulhamento_terrestre") or "[]")
    st.session_state["patrulhamento_fluvial_list"] = json.loads(registro_aberto.get("patrulhamento_fluvial") or "[]")
    st.session_state["viatura_prefixo"] = registro_aberto.get("viatura_prefixo") or ""
    st.session_state["km_inicial_input"] = registro_aberto.get("km_inicial") or 0
    if registro_aberto.get("data_inicial"):
        st.session_state["data_ini_sel"] = registro_aberto.get("data_inicial")
    if registro_aberto.get("data_final"):
        st.session_state["data_fim_sel"] = registro_aberto.get("data_final")
    st.session_state["comandante_sel"] = registro_aberto.get("comandante") or ""
    st.session_state["motorista_sel"] = registro_aberto.get("motorista") or ""
    try:
        st.session_state["capturas_animais_list"] = json.loads(registro_aberto.get("capturas_animais") or "[]")
    except Exception:
        st.session_state["capturas_animais_list"] = []
    try:
        st.session_state["apreensoes_list"] = json.loads(registro_aberto.get("apreensoes") or "[]")
    except Exception:
        st.session_state["apreensoes_list"] = []
    try:
        st.session_state["armamento_carregado"] = json.loads(registro_aberto.get("armamento_municao") or "[]") or None
    except Exception:
        st.session_state["armamento_carregado"] = None
    st.session_state["alteracoes_servico_input"] = registro_aberto.get("alteracoes_servico") or ""
    st.session_state["guarnicao_carregada_key"] = f"{registro_aberto.get('unidade')}|{registro_aberto.get('comandante')}"

def montar_dados_parciais(unidade, equipe, finalidade, comandante, motorista, data_ini, data_fim,
                           viatura_p, km_ini):
    """Monta um dicionário parcial (dados dos Blocos 01-02 + listas já registradas)
    para o salvamento automático a cada abordagem/captura. Como é um UPDATE parcial,
    os demais campos (apreensões, armamento, alterações etc.) não são sobrescritos."""
    return {
        "status": "Em Andamento",
        "unidade": unidade,
        "equipe": equipe,
        "finalidade": finalidade,
        "comandante": comandante,
        "motorista": motorista,
        "data_inicial": data_ini,
        "data_final": data_fim,
        "viatura_prefixo": viatura_p,
        "km_inicial": km_ini,
        "patrulhamento_terrestre": json.dumps(st.session_state.get("patrulhamento_terrestre_list", []), ensure_ascii=False),
        "patrulhamento_fluvial": json.dumps(st.session_state.get("patrulhamento_fluvial_list", []), ensure_ascii=False),
        "capturas_animais": json.dumps(st.session_state.get("capturas_animais_list", []), ensure_ascii=False),
        "apreensoes": json.dumps(st.session_state.get("apreensoes_list", []), ensure_ascii=False),
    }

# Busca automática do próximo número sequencial para controle e busca
proximo_numero = 1
conn_controle = init_connection()
if conn_controle:
    try:
        cur_c = conn_controle.cursor()
        cur_c.execute("SELECT COALESCE(MAX(id), 0) + 1 as proximo FROM relatorios_servico;")
        proximo_numero = cur_c.fetchone()['proximo']
        cur_c.close()
        conn_controle.close()
    except:
        proximo_numero = 1

# Inicialização de travas de segurança
if "relatorio_enviado" not in st.session_state:
    st.session_state["relatorio_enviado"] = False

# Dados do Efetivo Real por Extenso
EFETIVO = {
    "2º Pel Miranda": [
        "1º Tenente PM Gesner Batista Ramos",
        "Subtenente PM Luiz Carlos Cavalieri Silva",
        "1º Sargento PM João Vaz",
        "1º Sargento PM Ronaldo da Silva",
        "2º Sargento PM Rafael Bucinsky Fontes",
        "3º Sargento PM Augusto Graça",
        "3º Sargento PM Macsuel Vilalba Santana",
        "3º Sargento PM Madson Acosta Flores",
        "Cabo PM Edmar Falcão Santana"
    ],
    "GPM Barra": [
        "3º Sargento PM Luiz Alberto Antonieto",
        "3º Sargento PM Diego Aguilera Romeiro",
        "Cabo PM Luiz Henrique da Silva Ferreira",
        "Cabo PM Thiago David Mareco de Souza"
    ]
}

# Matrícula de cada policial, usada para preencher automaticamente o campo
# ao selecionar o Comandante da Guarnição. Preencha os que estiverem em branco.
MATRICULAS = {
    "1º Tenente PM Gesner Batista Ramos": "",
    "Subtenente PM Luiz Carlos Cavalieri Silva": "",
    "1º Sargento PM João Vaz": "",
    "1º Sargento PM Ronaldo da Silva": "",
    "2º Sargento PM Rafael Bucinsky Fontes": "",
    "3º Sargento PM Augusto Graça": "",
    "3º Sargento PM Macsuel Vilalba Santana": "",
    "3º Sargento PM Madson Acosta Flores": "25849021",
    "Cabo PM Edmar Falcão Santana": "",
    "3º Sargento PM Luiz Alberto Antonieto": "",
    "3º Sargento PM Diego Aguilera Romeiro": "",
    "Cabo PM Luiz Henrique da Silva Ferreira": "",
    "Cabo PM Thiago David Mareco de Souza": ""
}
# ==========================================
# FUNÇÕES AUXILIARES: DITADO POR VOZ (TRANSCRIÇÃO LOCAL, SEM API PAGA)
# ==========================================
import tempfile
try:
    from faster_whisper import WhisperModel
    VOZ_DISPONIVEL = True
except ImportError:
    VOZ_DISPONIVEL = False

@st.cache_resource
def carregar_modelo_voz():
    """Carrega o modelo de transcrição de voz (Whisper local). Roda 100% offline
    depois do primeiro uso (que baixa o modelo, ~250MB, uma única vez)."""
    return WhisperModel("small", device="cpu", compute_type="int8")

def transcrever_audio(audio_bytes):
    """Transcreve um áudio (bytes) para texto em português."""
    modelo = carregar_modelo_voz()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        caminho_tmp = tmp.name
    segments, _ = modelo.transcribe(caminho_tmp, language="pt")
    return " ".join(seg.text.strip() for seg in segments).strip()
def _normalizar_texto(txt):
    """Remove acentos e deixa em minúsculas para comparação mais tolerante."""
    if not txt:
        return ""
    nfkd = unicodedata.normalize("NFKD", txt)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower().strip()

def identificar_policial(trecho_falado, unidade):
    """Casa um trecho de fala (ex: 'sargento madson') com um nome do efetivo
    cadastrado para a unidade. Retorna o nome completo ou None."""
    if not trecho_falado:
        return None
    lista = EFETIVO.get(unidade, [])
    alvo = _normalizar_texto(trecho_falado)
    melhor_nome, melhor_pontuacao = None, 0.0
    for nome in lista:
        nome_norm = _normalizar_texto(nome)
        pontuacao = difflib.SequenceMatcher(None, alvo, nome_norm).ratio()
        for palavra in alvo.split():
            if len(palavra) > 3 and palavra in nome_norm:
                pontuacao += 0.15
        if pontuacao > melhor_pontuacao:
            melhor_pontuacao, melhor_nome = pontuacao, nome
    return melhor_nome if melhor_pontuacao >= 0.35 else None

def extrair_dados_montagem_equipe(texto, unidade):
    """Extrai comandante, motorista, viatura e km inicial de uma fala do tipo:
    'Iniciando o serviço, comandante da equipe Sargento Madson, motorista CB
    Mareco, a viatura empregada é RWE6B39, km inicial 12000'."""
    texto_norm = _normalizar_texto(texto)

    def _trecho_entre(inicio_regex, fins_regex):
        m_ini = re.search(inicio_regex, texto_norm)
        if not m_ini:
            return ""
        pos_ini = m_ini.end()
        pos_fim = len(texto_norm)
        for f in fins_regex:
            m_fim = re.search(f, texto_norm[pos_ini:])
            if m_fim:
                pos_fim = min(pos_fim, pos_ini + m_fim.start())
        return texto_norm[pos_ini:pos_fim].strip(" ,.")

    fins_comuns = [r"\bmotorista\w*\b", r"\bviatura\w*\b", r"\bveiculo\w*\b", r"\bembarcaca\w*\b", r"\bkm\b", r"\bquilometragem\w*\b"]

    trecho_comandante = _trecho_entre(r"\bcomandante\w*\b", fins_comuns)
    trecho_motorista = _trecho_entre(r"\bmotorista\w*\b", [r"\bviatura\w*\b", r"\bveiculo\w*\b", r"\bembarcaca\w*\b", r"\bkm\b", r"\bquilometragem\w*\b"])
    trecho_viatura = _trecho_entre(r"\b(viatura|veiculo|embarcaca\w*)\b", [r"\bkm\b", r"\bquilometragem\w*\b"])

    m_km = re.search(r"(?:km|quilometragem)\w*\s*(?:inicial)?\s*(?:e|de|é)?\s*(\d+)", texto_norm)
    km_inicial = int(m_km.group(1)) if m_km else None

    prefixo_viatura = None
    if trecho_viatura:
        m_prefixo = re.search(r"[a-z0-9]{4,8}", trecho_viatura.replace(" ", ""))
        if m_prefixo:
            prefixo_viatura = m_prefixo.group(0).upper()

    return {
        "comandante": identificar_policial(trecho_comandante, unidade),
        "motorista": identificar_policial(trecho_motorista, unidade),
        "viatura": prefixo_viatura,
        "km_inicial": km_inicial,
        "texto_bruto": texto,
    }

def montagem_equipe_por_voz(unidade):
    """Botão de microfone para montar a guarnição por comando de voz. Depois
    de transcrever, mostra um resumo (texto + áudio) para conferência antes
    de preencher e salvar a guarnição."""
    if not VOZ_DISPONIVEL:
        return
    with st.expander("🎙️ Montar guarnição por voz", expanded=False):
        st.caption("Fale, por exemplo: 'Comandante Sargento Madson, motorista CB Mareco, viatura RWE6B39, km inicial 12000'.")
        geracao = st.session_state.get("audio_geracao_equipe", 0)
        audio = st.audio_input("Gravar comando de voz", key=f"audio_equipe_{geracao}", label_visibility="collapsed")

        if audio is not None:
            with st.spinner("Transcrevendo e identificando os dados..."):
                texto = transcrever_audio(audio.getvalue())
                dados = extrair_dados_montagem_equipe(texto, unidade) if texto else None
            st.session_state["audio_geracao_equipe"] = geracao + 1
            if dados:
                st.session_state["equipe_voz_pendente"] = dados
            else:
                st.warning("Não consegui entender o áudio. Tente novamente falando pausadamente.")
            st.rerun()

        pendente = st.session_state.get("equipe_voz_pendente")
        if pendente:
            st.markdown("**Confira o que foi entendido:**")
            st.write(f"🗣️ *\"{pendente['texto_bruto']}\"*")

            comandante_confirmado = st.selectbox(
                "Comandante identificado", EFETIVO[unidade],
                index=EFETIVO[unidade].index(pendente["comandante"]) if pendente["comandante"] in EFETIVO[unidade] else 0,
                key="voz_comandante_confirm"
            )
            motorista_confirmado = st.selectbox(
                "Motorista identificado", EFETIVO[unidade],
                index=EFETIVO[unidade].index(pendente["motorista"]) if pendente["motorista"] in EFETIVO[unidade] else 0,
                key="voz_motorista_confirm"
            )
            viatura_confirmada = st.text_input("Viatura identificada", value=pendente["viatura"] or "", key="voz_viatura_confirm")
            km_confirmado = st.number_input("KM Inicial identificado", min_value=0, step=1, value=pendente["km_inicial"] or 0, key="voz_km_confirm")

            resumo_falado = (
                f"Confirmando. Comandante {comandante_confirmado}. "
                f"Motorista {motorista_confirmado}. Viatura {viatura_confirmada}. "
                f"Quilometragem inicial {km_confirmado}."
            )
            components.html(f"""
                <script>
                    const msg = new SpeechSynthesisUtterance({json.dumps(resumo_falado)});
                    msg.lang = "pt-BR";
                    window.speechSynthesis.cancel();
                    window.speechSynthesis.speak(msg);
                </script>
            """, height=0)

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("✅ Confirmar e Salvar Guarnição", use_container_width=True, key="confirmar_equipe_voz"):
                    st.session_state["comandante_sel"] = comandante_confirmado
                    st.session_state["motorista_sel"] = motorista_confirmado
                    st.session_state["viatura_prefixo"] = viatura_confirmada
                    st.session_state["km_inicial_input"] = int(km_confirmado)
                    st.session_state["equipe_voz_pendente"] = None
                    st.session_state["salvar_guarnicao_via_voz"] = True
                    st.rerun()
            with col_c2:
                if st.button("✖️ Descartar", use_container_width=True, key="descartar_equipe_voz"):
                    st.session_state["equipe_voz_pendente"] = None
                    st.rerun()

def campo_texto_com_voz(label, key, altura=100, placeholder=None):
    """Campo de texto com botão de ditado por voz ao lado (🎙️). Use no lugar de
    st.text_area(label, key=key) em qualquer campo de relato/observação."""
    col_txt, col_mic = st.columns([9, 1])
    if VOZ_DISPONIVEL:
        with col_mic:
            with st.expander("🎙️", expanded=False):
                st.caption("Grave sua fala — o texto é transcrito automaticamente.")
                geracao = st.session_state.get(f"audio_geracao_{key}", 0)
                audio = st.audio_input("Gravar", key=f"audio_{key}_{geracao}", label_visibility="collapsed")
                if audio is not None:
                    with st.spinner("Transcrevendo..."):
                        texto_transcrito = transcrever_audio(audio.getvalue())
                    if texto_transcrito:
                        texto_atual = st.session_state.get(key, "")
                        st.session_state[key] = (texto_atual + " " + texto_transcrito).strip()
                    st.session_state[f"audio_geracao_{key}"] = geracao + 1
                    if texto_transcrito:
                        st.success("Transcrito! Confira o texto ao lado.")
                    else:
                        st.warning("Não consegui identificar fala no áudio. Tente novamente.")
                    st.rerun()
    with col_txt:
        valor = st.text_area(label, key=key, height=altura, placeholder=placeholder)
    return valor


# ==========================================
# FUNÇÃO AUXILIAR: CAMPO COM MÚLTIPLOS REGISTROS (BOTÃO "+")
# ==========================================
def campo_multiplo(label, session_key, placeholder_prefix=None):
    """Renderiza um campo de texto que pode ser repetido com um botão '+'.
    Retorna a lista de valores preenchidos (não vazios)."""
    if session_key not in st.session_state:
        st.session_state[session_key] = [""]

    if placeholder_prefix is None:
        placeholder_prefix = label

    st.markdown(f"**{label}**")
    remover_idx = None
    geracao = st.session_state.get("doc_geracao", 0)
    for i in range(len(st.session_state[session_key])):
        c1, c2, c3 = st.columns([7, 1, 1])
        with c1:
            st.session_state[session_key][i] = st.text_input(
                label,
                value=st.session_state[session_key][i],
                key=f"{session_key}_{geracao}_{i}",
                label_visibility="collapsed",
                placeholder=f"{placeholder_prefix} nº {i + 1}"
            )
        with c2:
            if i == len(st.session_state[session_key]) - 1:
                if st.button("➕", key=f"add_{session_key}_{geracao}_{i}", help="Adicionar outro registro"):
                    st.session_state[session_key].append("")
                    st.rerun()
        with c3:
            if len(st.session_state[session_key]) > 1:
                if st.button("➖", key=f"rem_{session_key}_{geracao}_{i}", help="Remover este registro"):
                    remover_idx = i

    if remover_idx is not None:
        st.session_state[session_key].pop(remover_idx)
        st.rerun()

    return [v.strip() for v in st.session_state[session_key] if v.strip() != ""]

# Criando as abas principais na interface do usuário
aba_policial, aba_adm = st.tabs(["Formulário de Serviço", "Painel Estratégico (Adm)"])

# ------------------------------------------
# VISÃO 1: FORMULÁRIO DE SERVIÇO (POLICIAL)
# ------------------------------------------
with aba_policial:
    # Cabeçalho com numeração dinâmica integrada conforme o desenho "Nº"
    col_tit1, col_tit2 = st.columns([4, 1])
    with col_tit1:
        col_logo, col_texto_tit = st.columns([1, 6])
        with col_logo:
            st.image("icone_pelotao_512.png", width=70)
        with col_texto_tit:
            st.markdown("# RELATÓRIO DE SERVIÇO DIÁRIO OFICIAL")
            st.caption(f"Unidade: **{st.session_state['unidade_operacional']}** — Preencha os campos operacionais da guarnição abaixo.")
    with col_tit2:
        if st.session_state["relatorio_id_atual"]:
            st.metric("Nº DO RELATÓRIO", f"{st.session_state['relatorio_id_atual']:04d}")
        else:
            st.metric("PRÓXIMO Nº (se novo)", f"{proximo_numero:04d}")

        with st.popover("🔍 Buscar Relatório", use_container_width=True):
            st.caption("Busque por Nº do relatório ou nome do comandante — inclui relatórios já concluídos.")
            termo_busca = st.text_input("Buscar", placeholder="Ex: 0005 ou Madson", key="termo_busca_relatorio", label_visibility="collapsed")
            if termo_busca:
                resultados_busca = buscar_relatorios(st.session_state["unidade_operacional"], termo_busca)
                if resultados_busca:
                    for reg in resultados_busca:
                        st.markdown(f"**Nº {reg['id']:04d}** — {reg.get('comandante','')} — *{reg.get('status','')}*")
                        if st.button("👁️ Visualizar / Editar", key=f"busca_ver_{reg['id']}", use_container_width=True):
                            carregar_registro_na_sessao(reg)
                            st.rerun()
                        st.divider()
                else:
                    st.info("Nenhum relatório encontrado.")

    # --- PAINEL "GU SERVIÇO" — guarnições com serviço em andamento nesta unidade ---
    # Fica visível assim que a página abre, sem precisar escolher comandante antes.
    # Isolado por unidade_operacional: uma unidade não vê os serviços da outra.
    if st.session_state["relatorio_id_atual"] is None:
        servicos_abertos = listar_relatorios_em_andamento(st.session_state["unidade_operacional"])
        if servicos_abertos:
            st.markdown("##### 🪖 Guarnições com serviço em andamento nesta unidade")
            cols_gu = st.columns(min(len(servicos_abertos), 4))
            for i, reg in enumerate(servicos_abertos):
                try:
                    dias_corridos = (datetime.now().date() - reg["data_inicial"]).days + 1
                except Exception:
                    dias_corridos = 1
                dia_exibido = min(max(dias_corridos, 1), 5)
                nome_curto = (reg.get("comandante") or "").replace("º Sargento PM", "º Sgt").replace("º Tenente PM", "º Ten")
                with cols_gu[i % len(cols_gu)]:
                    if st.button(f"🪖 GU SERVIÇO\nNº {reg['id']:04d} — {nome_curto}\nDia {dia_exibido}/5", key=f"gu_servico_{reg['id']}", use_container_width=True):
                        carregar_registro_na_sessao(reg)
                        st.rerun()
    else:
        st.success(f"🪖 GU em serviço — Nº {st.session_state['relatorio_id_atual']:04d} — Dia em andamento.")

    st.divider()

    st.markdown("### 01 - DADOS DE CONTROLE")
    
    # Define a equipe de forma oculta nos bastidores para não quebrar a tabela do banco de dados
    equipe_sel = "Equipe Única"
    
    # Grid de 3 colunas com a data inicial movida para o centro conforme a indicação
    col_u1, col_u2, col_u3 = st.columns(3)
    with col_u1:
        unidade_sel = st.session_state["unidade_operacional"]
        st.text_input("Unidade / Seção", value=unidade_sel, disabled=True)
        # Campo "Finalidade do Serviço" removido da tela: ficou redundante depois que
        # a finalidade passou a ser registrada por atividade nos itens 04 e 05.
        # Mantido nos bastidores só para não quebrar a coluna "finalidade" do banco.
        finalidade_sel = "Patrulhamento Ambiental"
    with col_u2:
        # A Data Inicial assumiu totalmente o lugar central vago
        data_ini_sel = st.date_input("Data Inicial do Serviço", value=datetime.now(), key="data_ini_sel")
    with col_u3:
        data_fim_sel = st.date_input("Data Final do Serviço (Jornada 5 dias)", value=data_ini_sel + timedelta(days=5), key="data_fim_sel")
    montagem_equipe_por_voz(unidade_sel)
    st.markdown("#### Guarnição de Serviço")
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        comandante_sel = st.selectbox("Comandante da Guarnição", EFETIVO[unidade_sel], key="comandante_sel")
    with col_g2:
        motorista_sel = st.selectbox("Motorista / Tripulante", EFETIVO[unidade_sel], key="motorista_sel")
    with col_g3:
        matricula_comandante = st.text_input(
            "Matrícula do Comandante",
            value=MATRICULAS.get(comandante_sel, ""),
            placeholder="Ex: 123456-7",
            key=f"matricula_{comandante_sel}"
        )

    # --- PROTEÇÃO CONTRA TROCA DE GUARNIÇÃO SEM RESET ---
    # Se o comandante selecionado mudou em relação ao serviço carregado na sessão,
    # zera tudo antes de continuar — impede que um "Salvar" acabe sobrescrevendo
    # (por engano) o relatório de outra equipe/guarnição.
    chave_guarnicao_atual = f"{unidade_sel}|{comandante_sel}"
    if st.session_state.get("guarnicao_carregada_key") != chave_guarnicao_atual:
        st.session_state["relatorio_id_atual"] = None
        st.session_state["patrulhamento_terrestre_list"] = []
        st.session_state["patrulhamento_fluvial_list"] = []
        st.session_state["capturas_animais_list"] = []
        st.session_state["apreensoes_list"] = []
        st.session_state["armamento_carregado"] = None
        st.session_state["cadg_list"] = [""]
        st.session_state["auto_infracao_list"] = [""]
        st.session_state["termo_constatacao_list"] = [""]
        st.session_state["termo_apreensao_list"] = [""]
        st.session_state["relatorio_fiscalizacao_list"] = [""]
        st.session_state["relatorio_vistoria_list"] = [""]
        st.session_state["doc_geracao"] = st.session_state.get("doc_geracao", 0) + 1
        st.session_state["guarnicao_carregada_key"] = chave_guarnicao_atual

    st.divider()

    # OBS: os blocos 02 a 05 abaixo NÃO ficam mais dentro de um st.form.
    # Isso é necessário porque o botão "➕" do item 04 precisa disparar uma
    # atualização imediata da tela (rerun), o que não é possível com widgets
    # dentro de um st.form (lá só o botão de envio final reage).

    # Bloco 02: Controle de Viaturas
    st.markdown("### 02 - CONTROLE DE VIATURAS / EMBARCAÇÕES")
    col3, col4, col5 = st.columns(3)
    with col3:
        viatura = st.text_input("Prefixo da Viatura/Embarcação", placeholder="Ex: VTR-1234", key="viatura_prefixo")
    with col4:
        km_inicial = st.number_input("Quilometragem (KM) Inicial", min_value=0, step=1, key="km_inicial_input")
    with col5:
        encerrar_servico = st.session_state.get("encerrar_servico_check", False)
        km_final = st.number_input(
            "Quilometragem (KM) Final",
            min_value=0, step=1, key="km_final_input",
            disabled=not encerrar_servico,
            help=None if encerrar_servico else "Só é exigido no dia de encerramento do serviço (marque a opção abaixo)."
        )

    encerrar_servico = st.checkbox(
        "🏁 Encerrar o serviço agora (habilita o KM Final e finaliza o relatório de 5 dias)",
        key="encerrar_servico_check"
    )

    km_rodado_calc = km_final - km_inicial if (encerrar_servico and km_final >= km_inicial) else 0
    st.metric("Distância Total Percorrida (KM Rodado)", f"{km_rodado_calc} km" if encerrar_servico else "Disponível no encerramento")

    def autosave_parcial():
        """Salva automaticamente o progresso atual (Em Andamento) no banco.
        Usado ao inserir, editar ou excluir qualquer item das listas 03/04/05."""
        _dados_auto = montar_dados_parciais(
            unidade_sel, equipe_sel, finalidade_sel, comandante_sel, motorista_sel,
            data_ini_sel, data_fim_sel, viatura, km_inicial
        )
        _id_salvo, _erro_auto = salvar_relatorio(_dados_auto, st.session_state["relatorio_id_atual"])
        if not _erro_auto:
            st.session_state["relatorio_id_atual"] = _id_salvo
        return _erro_auto

    if st.button("💾 Salvar Guarnição / Assumir Serviço", use_container_width=True, key="salvar_guarnicao_btn"):
        _dados_guarnicao = montar_dados_parciais(
            unidade_sel, equipe_sel, finalidade_sel, comandante_sel, motorista_sel,
            data_ini_sel, data_fim_sel, viatura, km_inicial
        )
        _id_salvo, _erro_guarnicao = salvar_relatorio(_dados_guarnicao, st.session_state["relatorio_id_atual"])
        if _erro_guarnicao:
            st.error(f"Falha ao salvar a guarnição: {_erro_guarnicao}")
        else:
            st.session_state["relatorio_id_atual"] = _id_salvo
            st.success(f"✅ Guarnição salva! Serviço Nº {_id_salvo:04d} em andamento — já pode fechar o sistema com segurança e retomar depois.")
            st.rerun()

    if st.session_state.get("salvar_guarnicao_via_voz"):
        st.session_state["salvar_guarnicao_via_voz"] = False
        _dados_guarnicao_voz = montar_dados_parciais(
        unidade_sel, equipe_sel, finalidade_sel, comandante_sel, motorista_sel,
        data_ini_sel, data_fim_sel, viatura, km_inicial
        )
        _id_voz, _erro_voz = salvar_relatorio(_dados_guarnicao_voz, st.session_state["relatorio_id_atual"])
        if _erro_voz:
            st.error(f"Falha ao salvar a guarnição por voz: {_erro_voz}")
        else:
            st.session_state["relatorio_id_atual"] = _id_voz
            st.success(f"✅ Guarnição montada por voz e salva! Serviço Nº {_id_voz:04d} em andamento.")
            st.rerun()
    st.divider()

    # Bloco 03: Captura de Animais
    st.markdown("### 03 - CAPTURA DE ANIMAIS (PANTANAL)")
    if st.session_state.get("carregar_edicao_animal") is not None:
        _idx_edit = st.session_state.pop("carregar_edicao_animal")
        _item_edit = st.session_state["capturas_animais_list"][_idx_edit]
        st.session_state["editando_idx_animal"] = _idx_edit
        st.session_state["tipo_animal"] = _item_edit.get("ANIMAL", "Não se aplica")
        st.session_state["qtd_animal"] = _item_edit.get("QUANTIDADE", 0)
        st.session_state["especie_animal"] = _item_edit.get("ESPÉCIE", "Não se aplica")
        st.session_state["cadg_animal_input"] = _item_edit.get("Nº CADG", "")
        st.session_state["avaliacao_animal"] = _item_edit.get("AVALIAÇÃO", "Não se aplica")
        st.session_state["origem_animal"] = _item_edit.get("ORIGEM", "Não se aplica")
        st.session_state["destinacao_animal"] = _item_edit.get("DESTINAÇÃO", "")
        st.session_state["relato_captura"] = _item_edit.get("RELATO", "")
    with st.container(border=True):
        col_anim1, col_anim2, col_anim3 = st.columns(3)
        with col_anim1:
            tipo_animal = st.selectbox("Animal Capturado", ["Não se aplica", "Silvestre", "Doméstico"], key="tipo_animal")
            quantidade_animal = st.number_input("Quantidade de Animais", min_value=0, step=1, key="qtd_animal")
        with col_anim2:
            lista_especies = ["Não se aplica", "Tamanduá", "Quati", "Jacaré", "Onça", "Papagaio","cachorro", "Gato", "Cavalo", "gado", "Cabra", "Carneiro", "Gavião", "Jaguatirica", "Teiú", "Outro"]
            especie_animal = st.selectbox("Espécie do Animal", lista_especies, key="especie_animal")
            cadg_animal = st.text_input("Nº CADG", placeholder="Ex: 12345", key="cadg_animal_input")
        with col_anim3:
            avaliacao_animal = st.selectbox("Avaliação do Estado do Animal", ["Não se aplica", "Ótima", "Boa", "Ruim"], key="avaliacao_animal")
            lista_origens = ["Não se aplica", "Miranda", "Bodoquena", "BR-262", "MS-339", "Residência de Miranda", "Residência de Bodoquena", "Entregue no Pelotão"]
            origem_animal = st.selectbox("Origem / Local da Captura", lista_origens, key="origem_animal")

        col_anim_txt1, col_anim_txt2 = st.columns(2)
        with col_anim_txt1:
           destinacao_animal = campo_texto_com_voz("Destinação do Animal (Breve relato)", "destinacao_animal", altura=70) 
        with col_anim_txt2:
            relato_captura = campo_texto_com_voz("Relato Breve da Captura (Como se deu a ação)", "relato_captura", altura=70)

        editando_animal = st.session_state.get("editando_idx_animal")
        label_animal = "💾 Salvar Edição da Captura" if editando_animal is not None else "➕ Inserir / Salvar Captura de Animal"
        col_btn_a1, col_btn_a2 = st.columns([4, 1])
        with col_btn_a1:
            clicou_salvar_animal = st.button(label_animal, use_container_width=True, key="botao_captura_animal")
        with col_btn_a2:
            if editando_animal is not None and st.button("✖️ Cancelar", use_container_width=True, key="cancelar_edicao_animal"):
                st.session_state["editando_idx_animal"] = None
                st.rerun()

        if clicou_salvar_animal:
            nova_captura = {
                "ANIMAL": tipo_animal, "ESPÉCIE": especie_animal, "QUANTIDADE": quantidade_animal,
                "Nº CADG": cadg_animal, "AVALIAÇÃO": avaliacao_animal, "ORIGEM": origem_animal,
                "DESTINAÇÃO": destinacao_animal, "RELATO": relato_captura
            }
            if editando_animal is not None:
                st.session_state["capturas_animais_list"][editando_animal] = nova_captura
                st.session_state["editando_idx_animal"] = None
            else:
                st.session_state["capturas_animais_list"].append(nova_captura)
            _erro_auto = autosave_parcial()
            if _erro_auto:
                st.warning(f"Captura salva localmente, mas o salvamento automático falhou: {_erro_auto}")
            else:
                st.success("Captura de animal salva automaticamente na nuvem!")
            st.rerun()

    if st.session_state["capturas_animais_list"]:
        st.markdown("###### Capturas registradas")
        for i, item in enumerate(st.session_state["capturas_animais_list"]):
            with st.container(border=True):
                col_row1, col_row2, col_row3 = st.columns([6, 1, 1])
                with col_row1:
                    st.markdown(f"**{item.get('ANIMAL','')} — {item.get('ESPÉCIE','')}** | Qtd: {item.get('QUANTIDADE','')} | Nº CADG: {item.get('Nº CADG','') or '—'} | Avaliação: {item.get('AVALIAÇÃO','')} | Origem: {item.get('ORIGEM','')}")
                    if item.get('DESTINAÇÃO') or item.get('RELATO'):
                        st.caption(f"Destinação: {item.get('DESTINAÇÃO','') or '—'} · Relato: {item.get('RELATO','') or '—'}")
                with col_row2:
                    if st.button("✏️ Editar", key=f"edit_animal_{i}", use_container_width=True):
                        st.session_state["carregar_edicao_animal"] = i
                        st.rerun()
                with col_row3:
                    if st.button("🗑️ Excluir", key=f"del_animal_{i}", use_container_width=True):
                        st.session_state["capturas_animais_list"].pop(i)
                        if st.session_state.get("editando_idx_animal") == i:
                            st.session_state["editando_idx_animal"] = None
                        autosave_parcial()
                        st.rerun()
    st.divider()

        # Bloco 04: Patrulhamento Terrestre
    st.markdown("### 04 - PATRULHAMENTO TERRESTRE / FISCALIZAÇÃO / VISTORIA")
    if st.session_state.get("carregar_edicao_terrestre") is not None:
        _idx_edit = st.session_state.pop("carregar_edicao_terrestre")
        _item_edit = st.session_state["patrulhamento_terrestre_list"][_idx_edit]
        st.session_state["editando_idx_terrestre"] = _idx_edit
        st.session_state["sol_t_input"] = _item_edit.get("SOLICITANTE", "Ministério Público")
        st.session_state["fin_t_input"] = _item_edit.get("FINALIDADE", "NUGEO")
        st.session_state["mun_t_input"] = _item_edit.get("MUNICÍPIO", "Miranda")
        st.session_state["pessoas_t_input"] = _item_edit.get("PESSOAS ABORDADAS", 0)
        st.session_state["dist_t_input"] = _item_edit.get("DISTÂNCIA (KM)", 0.0)
        st.session_state["apreenso_t_input"] = _item_edit.get("APREENSÕES", 0)
        st.session_state["vistorias_t_input"] = _item_edit.get("VISTORIAS", 0)
        st.session_state["fiscalizacoes_t_input"] = _item_edit.get("FISCALIZAÇÕES", 0)
        st.session_state["veiculos_t_input"] = _item_edit.get("VEÍCULOS ABORDADOS", 0)
        st.session_state["cadg_t_input"] = _item_edit.get("Nº CADG", "")
        st.session_state["obs_t_input"] = _item_edit.get("OBSERVAÇÕES", "")
    with st.container(border=True):
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            sol_t = st.selectbox("Solicitante", ["Ministério Público", "1ºBPMA", "Imasul", "Outros"], key="sol_t_input")
            pessoas_t = st.number_input("Qtd Pessoas Abordadas", min_value=0, step=1, key="pessoas_t_input")
            vistorias_t = st.number_input("Qtd Vistorias", min_value=0, step=1, key="vistorias_t_input")
            cadg_t = st.text_input("Nº CADG", placeholder="Ex: 12345", key="cadg_t_input")
        with col_t2:
            fin_t = st.selectbox("Finalidade", ["NUGEO", "Fiscalização", "Vistoria", "Verificação de Denúncia", "Patrulhamento Preventivo", "Prolepse"], key="fin_t_input")
            dist_t = st.number_input("Distância Percorrida (KM)", min_value=0.0, step=0.1, key="dist_t_input")
            fiscalizacoes_t = st.number_input("Qtd Fiscalizações", min_value=0, step=1, key="fiscalizacoes_t_input")
        with col_t3:
            mun_t = st.selectbox("Município", ["Miranda", "Bodoquena", "Anastácio", "Aquidauana", "Corumbá", "Outros"], key="mun_t_input")
            apreenso_t = st.number_input("Qtd Apreensões", min_value=0, step=1, key="apreenso_t_input")
            veiculos_t = st.number_input("Qtd Veículos Abordados", min_value=0, step=1, key="veiculos_t_input")
        
        obs_t = campo_texto_com_voz("Observações sobre o Policiamento Terrestre", "obs_t_input")
        
        editando_terr = st.session_state.get("editando_idx_terrestre")
        label_terr = "💾 Salvar Edição da Atividade" if editando_terr is not None else "➕ Inserir / Salvar Atividade Terrestre"
        col_btn_t1, col_btn_t2 = st.columns([4, 1])
        with col_btn_t1:
            clicou_salvar_terr = st.button(label_terr, use_container_width=True, key="botao_atividade_terrestre")
        with col_btn_t2:
            if editando_terr is not None and st.button("✖️ Cancelar", use_container_width=True, key="cancelar_edicao_terr"):
                st.session_state["editando_idx_terrestre"] = None
                st.rerun()

        if clicou_salvar_terr:
            nova_atv_t = {
                "SOLICITANTE": sol_t, "FINALIDADE": fin_t, "MUNICÍPIO": mun_t,
                "PESSOAS ABORDADAS": pessoas_t, "DISTÂNCIA (KM)": dist_t,
                "APREENSÕES": apreenso_t, "VISTORIAS": vistorias_t, "FISCALIZAÇÕES": fiscalizacoes_t,
                "VEÍCULOS ABORDADOS": veiculos_t, "Nº CADG": cadg_t,
                "OBSERVAÇÕES": obs_t
            }
            if editando_terr is not None:
                st.session_state["patrulhamento_terrestre_list"][editando_terr] = nova_atv_t
                st.session_state["editando_idx_terrestre"] = None
            else:
                st.session_state["patrulhamento_terrestre_list"].append(nova_atv_t)
            _erro_auto = autosave_parcial()
            if _erro_auto:
                st.warning(f"Atividade salva localmente, mas o salvamento automático falhou: {_erro_auto}")
            else:
                st.success("Atividade terrestre salva automaticamente na nuvem!")
            st.rerun()

    if st.session_state["patrulhamento_terrestre_list"]:
        st.markdown("###### Atividades registradas")
        for i, item in enumerate(st.session_state["patrulhamento_terrestre_list"]):
            with st.container(border=True):
                col_row1, col_row2, col_row3 = st.columns([6, 1, 1])
                with col_row1:
                    st.markdown(f"**{item.get('FINALIDADE','')}** — {item.get('SOLICITANTE','')} | {item.get('MUNICÍPIO','')} | Abordados: {item.get('PESSOAS ABORDADAS','')} | Veículos: {item.get('VEÍCULOS ABORDADOS',0)} | Apreensões: {item.get('APREENSÕES','')} | Vistorias: {item.get('VISTORIAS','')} | Fiscalizações: {item.get('FISCALIZAÇÕES','')} | {item.get('DISTÂNCIA (KM)','')} km")
                    if item.get('OBSERVAÇÕES') or item.get('Nº CADG'):
                        st.caption(f"Nº CADG: {item.get('Nº CADG','') or '—'} · Obs: {item.get('OBSERVAÇÕES','') or '—'}")
                with col_row2:
                    if st.button("✏️ Editar", key=f"edit_terr_{i}", use_container_width=True):
                        st.session_state["carregar_edicao_terrestre"] = i
                        st.rerun()
                with col_row3:
                    if st.button("🗑️ Excluir", key=f"del_terr_{i}", use_container_width=True):
                        st.session_state["patrulhamento_terrestre_list"].pop(i)
                        if st.session_state.get("editando_idx_terrestre") == i:
                            st.session_state["editando_idx_terrestre"] = None
                        autosave_parcial()
                        st.rerun()
    st.divider()

    # Bloco 05: Patrulhamento Fluvial
    st.markdown("### 05 - PATRULHAMENTO FLUVIAL")
    if st.session_state.get("carregar_edicao_fluvial") is not None:
        _idx_edit = st.session_state.pop("carregar_edicao_fluvial")
        _item_edit = st.session_state["patrulhamento_fluvial_list"][_idx_edit]
        st.session_state["editando_idx_fluvial"] = _idx_edit
        st.session_state["sol_f_input"] = _item_edit.get("SOLICITANTE", "Ministério Público")
        st.session_state["fin_f_input"] = _item_edit.get("FINALIDADE", "NUGEO")
        st.session_state["mun_f_input"] = _item_edit.get("MUNICÍPIO", "Miranda")
        st.session_state["pescadores_f_input"] = _item_edit.get("PESCADORES ABORDADOS", 0)
        st.session_state["dist_f_input"] = _item_edit.get("DISTÂNCIA", 0.0)
        st.session_state["apreenso_f_input"] = _item_edit.get("APREENSÕES", 0)
        st.session_state["vistorias_f_input"] = _item_edit.get("VISTORIAS", 0)
        st.session_state["embarcacoes_f_input"] = _item_edit.get("EMBARCAÇÕES ABORDADAS", 0)
        st.session_state["cadg_f_input"] = _item_edit.get("Nº CADG", "")
        st.session_state["obs_f_input"] = _item_edit.get("OBSERVAÇÕES", "")
    with st.container(border=True):
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            sol_f = st.selectbox("Solicitante", ["Ministério Público", "1ºBPMA", "Imasul", "Outros"], key="sol_f_input")
            pescadores_f = st.number_input("Qtd Pescadores Abordados", min_value=0, step=1, key="pescadores_f_input")
            vistorias_f = st.number_input("Qtd Vistorias (Fluvial)", min_value=0, step=1, key="vistorias_f_input")
        with col_f2:
            fin_f = st.selectbox("Finalidade", ["NUGEO", "Fiscalização", "Vistoria", "Verificação de Denúncia", "Patrulhamento Preventivo", "Prolepse"], key="fin_f_input")
            dist_f = st.number_input("Distância Percorrida (KM/Milhas)", min_value=0.0, step=0.1, key="dist_f_input")
            apreenso_f = st.number_input("Qtd Apreensões (Fluvial)", min_value=0, step=1, key="apreenso_f_input")
        with col_f3:
            mun_f = st.selectbox("Município", ["Miranda", "Bodoquena", "Anastácio", "Aquidauana", "Corumbá", "Outros"], key="mun_f_input")
            embarcacoes_f = st.number_input("Qtd Embarcações Abordadas", min_value=0, step=1, key="embarcacoes_f_input")
            cadg_f = st.text_input("Nº CADG", placeholder="Ex: 12345", key="cadg_f_input")
            
        obs_f = campo_texto_com_voz("Observações sobre o Policiamento Fluvial", "obs_f_input")
        
        editando_fluv = st.session_state.get("editando_idx_fluvial")
        label_fluv = "💾 Salvar Edição da Atividade" if editando_fluv is not None else "➕ Inserir / Salvar Atividade Fluvial"
        col_btn_f1, col_btn_f2 = st.columns([4, 1])
        with col_btn_f1:
            clicou_salvar_fluv = st.button(label_fluv, use_container_width=True, key="botao_atividade_fluvial")
        with col_btn_f2:
            if editando_fluv is not None and st.button("✖️ Cancelar", use_container_width=True, key="cancelar_edicao_fluv"):
                st.session_state["editando_idx_fluvial"] = None
                st.rerun()

        if clicou_salvar_fluv:
            nova_atv_f = {
                "SOLICITANTE": sol_f, "FINALIDADE": fin_f, "MUNICÍPIO": mun_f,
                "EMBARCAÇÕES ABORDADAS": embarcacoes_f, "PESCADORES ABORDADOS": pescadores_f,
                "DISTÂNCIA": dist_f, "APREENSÕES": apreenso_f, "VISTORIAS": vistorias_f,
                "Nº CADG": cadg_f, "OBSERVAÇÕES": obs_f
            }
            if editando_fluv is not None:
                st.session_state["patrulhamento_fluvial_list"][editando_fluv] = nova_atv_f
                st.session_state["editando_idx_fluvial"] = None
            else:
                st.session_state["patrulhamento_fluvial_list"].append(nova_atv_f)
            _erro_auto = autosave_parcial()
            if _erro_auto:
                st.warning(f"Atividade salva localmente, mas o salvamento automático falhou: {_erro_auto}")
            else:
                st.success("Atividade fluvial salva automaticamente na nuvem!")
            st.rerun()

    if st.session_state["patrulhamento_fluvial_list"]:
        st.markdown("###### Atividades registradas")
        for i, item in enumerate(st.session_state["patrulhamento_fluvial_list"]):
            with st.container(border=True):
                col_row1, col_row2, col_row3 = st.columns([6, 1, 1])
                with col_row1:
                    st.markdown(f"**{item.get('FINALIDADE','')}** — {item.get('SOLICITANTE','')} | {item.get('MUNICÍPIO','')} | Embarcações: {item.get('EMBARCAÇÕES ABORDADAS','')} | Pescadores: {item.get('PESCADORES ABORDADOS','')} | Apreensões: {item.get('APREENSÕES','')} | Vistorias: {item.get('VISTORIAS','')} | {item.get('DISTÂNCIA','')} km")
                    if item.get('OBSERVAÇÕES') or item.get('Nº CADG'):
                        st.caption(f"Nº CADG: {item.get('Nº CADG','') or '—'} · Obs: {item.get('OBSERVAÇÕES','') or '—'}")
                with col_row2:
                    if st.button("✏️ Editar", key=f"edit_fluv_{i}", use_container_width=True):
                        st.session_state["carregar_edicao_fluvial"] = i
                        st.rerun()
                with col_row3:
                    if st.button("🗑️ Excluir", key=f"del_fluv_{i}", use_container_width=True):
                        st.session_state["patrulhamento_fluvial_list"].pop(i)
                        if st.session_state.get("editando_idx_fluvial") == i:
                            st.session_state["editando_idx_fluvial"] = None
                        autosave_parcial()
                        st.rerun()
    st.divider()


    # Bloco 06: Apreensões
    st.markdown("### 06 - APREENSÕES")
    if st.session_state.get("carregar_edicao_apreensao") is not None:
        _idx_edit = st.session_state.pop("carregar_edicao_apreensao")
        _item_edit = st.session_state["apreensoes_list"][_idx_edit]
        st.session_state["editando_idx_apreensao"] = _idx_edit
        st.session_state["infra_crime"] = _item_edit.get("INFRAÇÃO/CRIME", "Não se aplica")
        st.session_state["desc_material"] = _item_edit.get("DESCRIÇÃO", "")
        st.session_state["municipio_apreensao"] = _item_edit.get("MUNICÍPIO", "Não se aplica")
        st.session_state["tipo_material"] = _item_edit.get("TIPO MATERIAL", "Não se aplica")
        st.session_state["quantidade_apreendida"] = _item_edit.get("QUANTIDADE", 0.0)
        st.session_state["unidade_medida"] = _item_edit.get("UNIDADE MEDIDA", "Unidades")
        st.session_state["valor_multa"] = _item_edit.get("VALOR MULTA", 0.0)
        st.session_state["relato_apreensao"] = _item_edit.get("RELATO", "")
        st.session_state["cadg_list"] = _item_edit.get("CADG", "").split("; ") if _item_edit.get("CADG") else [""]
        st.session_state["auto_infracao_list"] = _item_edit.get("AUTO INFRAÇÃO", "").split("; ") if _item_edit.get("AUTO INFRAÇÃO") else [""]
        st.session_state["termo_constatacao_list"] = _item_edit.get("TERMO CONSTATAÇÃO", "").split("; ") if _item_edit.get("TERMO CONSTATAÇÃO") else [""]
        st.session_state["termo_apreensao_list"] = _item_edit.get("TERMO APREENSÃO", "").split("; ") if _item_edit.get("TERMO APREENSÃO") else [""]
        st.session_state["relatorio_fiscalizacao_list"] = _item_edit.get("RELATÓRIO FISCALIZAÇÃO", "").split("; ") if _item_edit.get("RELATÓRIO FISCALIZAÇÃO") else [""]
        st.session_state["relatorio_vistoria_list"] = _item_edit.get("RELATÓRIO VISTORIA", "").split("; ") if _item_edit.get("RELATÓRIO VISTORIA") else [""]
        st.session_state["doc_geracao"] = st.session_state.get("doc_geracao", 0) + 1
    with st.container(border=True):
        col_ap1, col_ap2, col_ap3 = st.columns(3)
        with col_ap1:
            lista_crimes = [
                "Não se aplica", "Pesca Ilegal / Predatória", "Caça Ilegal", 
                "Desmatamento / Exploração Florestal", "Transporte Irregular de Madeira/Carvão",
                "Tráfico de Drogas", "Contrabando", "Descaminho", "Outros Crimes/Infrações"
            ]
            infra_crime = st.selectbox("Infração / Crime Constatado", lista_crimes, key="infra_crime")
            desc_material = st.text_input("Descrição Detalhada do Material", placeholder="Ex: 15kg de Pacu, Rede de pesca, 2m³ de aroeira", key="desc_material")
        with col_ap2:
            municipio_apreensao = st.selectbox("Município da Apreensão", ["Não se aplica", "Miranda", "Bodoquena", "Outros"], key="municipio_apreensao")
            tipo_material = st.selectbox("Tipo de Material Apreendido", ["Não se aplica", "Pescado", "Madeira", "Fauna (outros)", "Flora (outros)", "Outros"], key="tipo_material")
        with col_ap3:
            quantidade_apreendida = st.number_input("Quantidade (Em unidade ou medida)", min_value=0.0, step=1.0, key="quantidade_apreendida")
            unidade_medida = st.selectbox("Unidade da Quantidade Acima", ["Unidades", "Kg", "m³", "Litros", "Outra"], key="unidade_medida")
            valor_multa = st.number_input("Valor da Multa Aplicada (R$)", min_value=0.0, step=50.0, key="valor_multa")

        relato_apreensao = campo_texto_com_voz("Breve Relato da Apreensão / Ocorrência", "relato_apreensao")

        st.divider()
        st.markdown("#### Documentos Vinculados a Esta Apreensão")
        st.caption("Use o botão ➕ para registrar mais de um documento do mesmo tipo nesta mesma apreensão.")
        col_doc1, col_doc2 = st.columns(2)
        with col_doc1:
            cadg_valores = campo_multiplo("Nº CADG", "cadg_list")
            termo_constatacao_valores = campo_multiplo("Nº Termo de Constatação", "termo_constatacao_list")
            relatorio_fiscalizacao_valores = campo_multiplo("Nº Relatório de Fiscalização", "relatorio_fiscalizacao_list")
        with col_doc2:
            auto_infracao_valores = campo_multiplo("Nº Auto de Infração", "auto_infracao_list")
            termo_apreensao_valores = campo_multiplo("Nº Termo de Apreensão", "termo_apreensao_list")
            relatorio_vistoria_valores = campo_multiplo("Nº Relatório de Vistoria", "relatorio_vistoria_list")

        st.divider()
        editando_ap = st.session_state.get("editando_idx_apreensao")
        label_ap = "💾 Salvar Edição da Apreensão" if editando_ap is not None else "➕ Inserir / Salvar Apreensão"
        col_btn_ap1, col_btn_ap2 = st.columns([4, 1])
        with col_btn_ap1:
            clicou_salvar_ap = st.button(label_ap, use_container_width=True, key="botao_apreensao")
        with col_btn_ap2:
            if editando_ap is not None and st.button("✖️ Cancelar", use_container_width=True, key="cancelar_edicao_ap"):
                st.session_state["editando_idx_apreensao"] = None
                st.rerun()

        if clicou_salvar_ap:
            nova_apreensao = {
                "INFRAÇÃO/CRIME": infra_crime, "TIPO MATERIAL": tipo_material, "DESCRIÇÃO": desc_material,
                "QUANTIDADE": quantidade_apreendida, "UNIDADE MEDIDA": unidade_medida, "MUNICÍPIO": municipio_apreensao,
                "VALOR MULTA": valor_multa, "RELATO": relato_apreensao,
                "CADG": "; ".join(cadg_valores),
                "AUTO INFRAÇÃO": "; ".join(auto_infracao_valores),
                "TERMO CONSTATAÇÃO": "; ".join(termo_constatacao_valores),
                "TERMO APREENSÃO": "; ".join(termo_apreensao_valores),
                "RELATÓRIO FISCALIZAÇÃO": "; ".join(relatorio_fiscalizacao_valores),
                "RELATÓRIO VISTORIA": "; ".join(relatorio_vistoria_valores),
            }
            if editando_ap is not None:
                st.session_state["apreensoes_list"][editando_ap] = nova_apreensao
                st.session_state["editando_idx_apreensao"] = None
            else:
                st.session_state["apreensoes_list"].append(nova_apreensao)
            # Limpa os documentos para a próxima apreensão não herdar os desta
            st.session_state["cadg_list"] = [""]
            st.session_state["auto_infracao_list"] = [""]
            st.session_state["termo_constatacao_list"] = [""]
            st.session_state["termo_apreensao_list"] = [""]
            st.session_state["relatorio_fiscalizacao_list"] = [""]
            st.session_state["relatorio_vistoria_list"] = [""]
            st.session_state["doc_geracao"] = st.session_state.get("doc_geracao", 0) + 1
            _erro_auto = autosave_parcial()
            if _erro_auto:
                st.warning(f"Apreensão salva localmente, mas o salvamento automático falhou: {_erro_auto}")
            else:
                st.success("Apreensão e documentos vinculados salvos automaticamente na nuvem!")
            st.rerun()

    if st.session_state["apreensoes_list"]:
        st.markdown("###### Apreensões registradas")
        for i, item in enumerate(st.session_state["apreensoes_list"]):
            with st.container(border=True):
                col_row1, col_row2, col_row3 = st.columns([6, 1, 1])
                with col_row1:
                    st.markdown(f"**{item.get('INFRAÇÃO/CRIME','')}** — {item.get('TIPO MATERIAL','')} | {item.get('MUNICÍPIO','')} | Qtd: {item.get('QUANTIDADE','')} {item.get('UNIDADE MEDIDA','')} | Multa: R$ {item.get('VALOR MULTA',0):,.2f}")
                    if item.get('DESCRIÇÃO') or item.get('RELATO'):
                        st.caption(f"Descrição: {item.get('DESCRIÇÃO','') or '—'} · Relato: {item.get('RELATO','') or '—'}")
                    docs_resumo = " · ".join(f"{rotulo}: {item.get(rotulo)}" for rotulo in ["CADG", "AUTO INFRAÇÃO", "TERMO CONSTATAÇÃO", "TERMO APREENSÃO", "RELATÓRIO FISCALIZAÇÃO", "RELATÓRIO VISTORIA"] if item.get(rotulo))
                    if docs_resumo:
                        st.caption(f"📎 {docs_resumo}")
                with col_row2:
                    if st.button("✏️ Editar", key=f"edit_ap_{i}", use_container_width=True):
                        st.session_state["carregar_edicao_apreensao"] = i
                        st.rerun()
                with col_row3:
                    if st.button("🗑️ Excluir", key=f"del_ap_{i}", use_container_width=True):
                        st.session_state["apreensoes_list"].pop(i)
                        if st.session_state.get("editando_idx_apreensao") == i:
                            st.session_state["editando_idx_apreensao"] = None
                        autosave_parcial()
                        st.rerun()

    st.divider()

        # Bloco 07: Estatística (Automatizado)
    st.markdown("### 07 - ESTATÍSTICA CONSOLIDADA DO SERVIÇO")
    
    # Cálculos automáticos baseados nas tabelas salvas pelo agente
    total_pessoas_t = sum(item["PESSOAS ABORDADAS"] for item in st.session_state["patrulhamento_terrestre_list"])
    total_dist_t = sum(item["DISTÂNCIA (KM)"] for item in st.session_state["patrulhamento_terrestre_list"])
    total_apre_t = sum(item["APREENSÕES"] for item in st.session_state["patrulhamento_terrestre_list"])
    total_vist_t = sum(item["VISTORIAS"] for item in st.session_state["patrulhamento_terrestre_list"])
    total_fisc_t = sum(item["FISCALIZAÇÕES"] for item in st.session_state["patrulhamento_terrestre_list"])
    
    total_emb_f = sum(item["EMBARCAÇÕES ABORDADAS"] for item in st.session_state["patrulhamento_fluvial_list"])
    total_pesc_f = sum(item["PESCADORES ABORDADOS"] for item in st.session_state["patrulhamento_fluvial_list"])
    total_dist_f = sum(item["DISTÂNCIA"] for item in st.session_state["patrulhamento_fluvial_list"])
    total_apre_f = sum(item["APREENSÕES"] for item in st.session_state["patrulhamento_fluvial_list"])
    total_vist_f = sum(item["VISTORIAS"] for item in st.session_state["patrulhamento_fluvial_list"])
    total_prolepse = sum(1 for item in st.session_state["patrulhamento_terrestre_list"] if item["FINALIDADE"] == "Prolepse") + \
                      sum(1 for item in st.session_state["patrulhamento_fluvial_list"] if item["FINALIDADE"] == "Prolepse")
    total_veiculos_t = sum(item.get("VEÍCULOS ABORDADOS", 0) for item in st.session_state["patrulhamento_terrestre_list"])

    total_ai = 0
    total_multas_valor = 0.0
    total_pescado_un = 0.0
    total_pescado_kg = 0.0
    total_madeira_un = 0.0
    total_madeira_m3 = 0.0
    for ap in st.session_state["apreensoes_list"]:
        auto_str = ap.get("AUTO INFRAÇÃO", "") or ""
        total_ai += len([v for v in auto_str.split("; ") if v.strip()])
        total_multas_valor += ap.get("VALOR MULTA", 0) or 0
        qtd_ap = ap.get("QUANTIDADE", 0) or 0
        unidade_ap = ap.get("UNIDADE MEDIDA", "")
        if ap.get("TIPO MATERIAL") == "Pescado":
            if unidade_ap == "Kg":
                total_pescado_kg += qtd_ap
            elif unidade_ap == "Unidades":
                total_pescado_un += qtd_ap
        elif ap.get("TIPO MATERIAL") == "Madeira":
            if unidade_ap == "m³":
                total_madeira_m3 += qtd_ap
            elif unidade_ap == "Unidades":
                total_madeira_un += qtd_ap

    # Exibição visual limpa em formato de cards para conferência rápida
    st.info("📊 Os dados abaixo são calculados em tempo real com base nos patrulhamentos e apreensões inseridos acima.")
    c_est1, c_est2, c_est3 = st.columns(3)
    with c_est1:
        st.metric("Total Pessoas Abordadas (Terr.)", total_pessoas_t)
        st.metric("Total Pescadores Abordados", total_pesc_f)
        st.metric("Total Vistorias (Geral)", total_vist_t + total_vist_f)
        st.metric("Total Veículos Abordados", total_veiculos_t)
    with c_est2:
        st.metric("Total Distância Terrestre", f"{total_dist_t:.1f} KM")
        st.metric("Total Distância Fluvial", f"{total_dist_f:.1f} KM/MN")
        st.metric("Total Fiscalizações", total_fisc_t)
        st.metric("Total Autos de Infração (AI)", total_ai)
    with c_est3:
        st.metric("Total Embarcações Abordadas", total_emb_f)
        st.metric("Total Apreensões (Geral)", total_apre_t + total_apre_f)
        st.metric("Total Prolepse", total_prolepse)
        st.metric("Total em Multas Aplicadas", f"R$ {total_multas_valor:,.2f}")

    st.markdown("###### Apreensões por Tipo de Material")
    c_est4, c_est5 = st.columns(2)
    with c_est4:
        st.metric("Total Pescado Apreendido", f"{total_pescado_un:.0f} un / {total_pescado_kg:.1f} Kg")
    with c_est5:
        st.metric("Total Madeira Apreendida", f"{total_madeira_un:.0f} un / {total_madeira_m3:.1f} m³")

    st.divider()


        # Bloco 08: Controle de Armamento e Munição
    st.markdown("### 08 - CONTROLE DE ARMAMENTO E MUNIÇÃO")
    st.write("Utilize a tabela abaixo para gerenciar os armamentos e munições. Clique em '+' no final da tabela para adicionar novas linhas ou selecione e pressione 'Delete' para excluir.")
    
    # Dados padrão baseados na sua imagem para preenchimento inicial automático
    dados_iniciais = st.session_state.get("armamento_carregado") or [
        {"CODIGO": "31471", "NOMENCLATURA": "CARABINA MARCA IMBEL MODELO IMBEL IA2 CALIBRE 5,56 Nº SERIE JFA07424", "QTDE": 1.00},
        {"CODIGO": "21532", "NOMENCLATURA": "ESPINGARDA MARCA CBC MODELO CBC MILITARY 3.0 RT TACT 12/19\" CALIBRE 12 Nº SERIE KPB4167550", "QTDE": 1.00},
        {"CODIGO": "1626", "NOMENCLATURA": "FUZIL MARCA FABRIQUE MODELO M964 CALIBRE 7,62 Nº SERIE 26625", "QTDE": 1.00},
        {"CODIGO": "17390", "NOMENCLATURA": "MUNICAO MARCA CBC CALIBRE .40", "QTDE": 150.00},
        {"CODIGO": "17392", "NOMENCLATURA": "MUNICAO MARCA CBC CALIBRE 12", "QTDE": 50.00},
        {"CODIGO": "17391", "NOMENCLATURA": "MUNICAO MARCA CBC CALIBRE 38", "QTDE": 25.00},
        {"CODIGO": "17393", "NOMENCLATURA": "MUNICAO MARCA CBC CALIBRE 5,56", "QTDE": 100.00},
        {"CODIGO": "17394", "NOMENCLATURA": "MUNICAO MARCA CBC CALIBRE 7,62", "QTDE": 50.00},
        {"CODIGO": "3736", "NOMENCLATURA": "PISTOLA MARCA IMBEL MODELO MD7 CALIBRE .40 Nº SERIE EQA01986", "QTDE": 1.00}
    ]
    
    # Data editor interativo que permite adicionar, editar e remover linhas.
    # A chave muda por guarnição (não por relatório) para não perder o que já
    # está sendo digitado quando o Nº do relatório é criado no meio da sessão,
    # mas ainda assim recarregar do zero ao trocar de guarnição/retomar outra.
    tabela_armamento = st.data_editor(
        dados_iniciais,
        num_rows="dynamic",
        use_container_width=True,
        key=f"armamento_editor_{st.session_state.get('guarnicao_carregada_key', 'novo')}",
        column_config={
            "CODIGO": st.column_config.TextColumn("CÓDIGO"),
            "NOMENCLATURA": st.column_config.TextColumn("NOMENCLATURA/DESCRIÇÃO", width="large"),
            "QTDE": st.column_config.NumberColumn("QTDE", min_value=0.0, format="%.2f")
        }
    )
    st.divider()

    # Bloco 09: Alterações de Serviço (Antigo Bloco 06)
    st.markdown("### 09 - ALTERAÇÕES DE SERVIÇO")
    alteracoes_servico = campo_texto_com_voz("Descreva detalhadamente as alterações que venham a ocorrer durante o serviço", "alteracoes_servico_input", placeholder="Ex: Sem alterações relevantes...")
    st.divider()


    if encerrar_servico:
        texto_botao = "✅ ENCERRAR SERVIÇO E ENVIAR RELATÓRIO FINAL PARA A NUVEM"
    else:
        texto_botao = "💾 SALVAR PROGRESSO DO DIA (o serviço continua em andamento)"

    enviar = st.button(texto_botao, type="primary", use_container_width=True)

    # Todo este bloco só executa quando o botão é de fato clicado — antes ele
    # rodava a cada interação da tela (bug corrigido), o que tentava gravar
    # um registro novo no banco a cada tecla digitada.
    if enviar and not st.session_state["relatorio_enviado"]:
        if encerrar_servico and km_final < km_inicial:
            st.error("Erro: O KM Final não pode ser menor que o KM Inicial.")
        else:
            st.session_state["relatorio_enviado"] = True

            dados_para_salvar = {
                "status": "Finalizado" if encerrar_servico else "Em Andamento",
                "unidade": unidade_sel,
                "equipe": equipe_sel,
                "finalidade": finalidade_sel,
                "comandante": comandante_sel,
                "motorista": motorista_sel,
                "data_inicial": data_ini_sel,
                "data_final": data_fim_sel,
                "viatura_prefixo": viatura,
                "km_inicial": km_inicial,
                "km_final": km_final if encerrar_servico else None,
                "capturas_animais": json.dumps(st.session_state["capturas_animais_list"], ensure_ascii=False),
                "apreensoes": json.dumps(st.session_state["apreensoes_list"], ensure_ascii=False),
                "pessoas_abordadas": sum(item["PESSOAS ABORDADAS"] for item in st.session_state["patrulhamento_terrestre_list"]),
                "veiculos_abordados": sum(item.get("VEÍCULOS ABORDADOS", 0) for item in st.session_state["patrulhamento_terrestre_list"]),
                "embarcacoes_abordadas": sum(item["EMBARCAÇÕES ABORDADAS"] for item in st.session_state["patrulhamento_fluvial_list"]),
                "bo_lavrados": 0,
                "autos_infracao": sum(len([v for v in ap.get("AUTO INFRAÇÃO", "").split("; ") if v.strip()]) for ap in st.session_state["apreensoes_list"]),
                "prolepse": prolepse if 'prolepse' in locals() else 0,
                "patrulhamento_terrestre": json.dumps(st.session_state["patrulhamento_terrestre_list"], ensure_ascii=False),
                "patrulhamento_fluvial": json.dumps(st.session_state["patrulhamento_fluvial_list"], ensure_ascii=False),
                "armamento_municao": json.dumps(tabela_armamento, ensure_ascii=False) if 'tabela_armamento' in locals() else "[]",
                "alteracoes_servico": alteracoes_servico,
            }

            novo_id, erro = salvar_relatorio(dados_para_salvar, st.session_state["relatorio_id_atual"])

            if erro:
                st.session_state["relatorio_enviado"] = False
                st.error(f"Falha ao salvar no banco Neon: {erro}")
            else:
                st.session_state["relatorio_id_atual"] = novo_id
                if encerrar_servico:
                    st.success(f"✅ Relatório Nº {novo_id:04d} finalizado e gravado com sucesso na nuvem do Pelotão!")
                    # Serviço concluído: limpa tudo para o próximo relatório começar do zero
                    st.session_state["relatorio_id_atual"] = None
                    st.session_state["guarnicao_carregada_key"] = None
                    st.session_state["patrulhamento_terrestre_list"] = []
                    st.session_state["patrulhamento_fluvial_list"] = []
                    st.session_state["capturas_animais_list"] = []
                    st.session_state["apreensoes_list"] = []
                    st.session_state["armamento_carregado"] = None
                else:
                    st.success(f"💾 Progresso do dia salvo na nuvem (Nº {novo_id:04d}). Serviço continua em andamento — pode fechar o sistema com segurança e retomar depois.")
                st.session_state["relatorio_enviado"] = False
                time.sleep(1)
                st.rerun()

    st.divider()
    st.markdown("### Assinatura do Responsável")
    st.markdown(f"""
        <div style="border-top:2px solid #ccc; margin-top:10px; padding-top:20px; text-align:center;">
            <p style="margin-bottom:40px;">____________________________________________</p>
            <p style="margin:0; font-weight:bold; font-size:16px;">{comandante_sel}</p>
            <p style="margin:0;">Matrícula: {matricula_comandante if matricula_comandante else '____________________'}</p>
            <p style="margin:0; color:#888;">Comandante da Guarnição</p>
        </div>
    """, unsafe_allow_html=True)

    st.divider()
    st.markdown("### Exportação do Relatório Corrente")
    # OBS: st.markdown remove atributos como "onclick" por segurança, então o botão
    # antigo nunca executava JavaScript. Usamos components.html, que roda em um
    # iframe com JS habilitado, e chamamos window.parent.print() para imprimir
    # a página inteira do Streamlit (não apenas o conteúdo do iframe).
    components.html(
        """
        <button onclick="window.parent.print()" style="width:100%; padding:10px; background-color:#ff4b4b; color:white; border:none; border-radius:5px; cursor:pointer; font-weight:bold; font-size:15px;">
            IMPRIMIR / SALVAR ABA EM PDF
        </button>
        """,
        height=55,
    )

# ------------------------------------------
# VISÃO 2: PAINEL ESTRATÉGICO ADMINISTRATIVO (COMPLETO)
# ------------------------------------------
with aba_adm:
    st.markdown("# PAINEL GERENCIAL DA ADMINISTRAÇÃO")
    senha = st.text_input("Insira a senha administrativa", type="password", key="input_senha")
    
    if senha == "adm123":
        st.success("Acesso liberado!")
        conn = init_connection()
        
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM relatorios_servico ORDER BY id ASC;")
                registros = cur.fetchall()
                cur.close()
                conn.close()
                
                if registros:
                    df = pd.DataFrame(registros)
                    df.columns = [c.lower() for c in df.columns]
                    
                    # Conversões e tratamentos numéricos
                    df['pessoas_abordadas'] = pd.to_numeric(df['pessoas_abordadas'], errors='coerce').fillna(0)
                    df['autos_infracao'] = pd.to_numeric(df['autos_infracao'], errors='coerce').fillna(0)
                    df['km_rodado'] = 0.0
                    if 'status' in df.columns:
                        _mask_final = df['status'] == 'Finalizado'
                        df.loc[_mask_final, 'km_rodado'] = pd.to_numeric(df.loc[_mask_final, 'km_final'], errors='coerce').fillna(0) - pd.to_numeric(df.loc[_mask_final,      'km_inicial'], errors='coerce').fillna(0)
                    df['km_rodado'] = df['km_rodado'].clip(lower=0)
                    
                    if 'quantidade_apreendida' in df.columns:
                        df['quantidade_apreendida'] = pd.to_numeric(df['quantidade_apreendida'], errors='coerce').fillna(0)
                    else:
                        df['quantidade_apreendida'] = 0
                    if 'valor_multa' in df.columns:
                        df['valor_multa'] = pd.to_numeric(df['valor_multa'], errors='coerce').fillna(0)
                    else:
                        df['valor_multa'] = 0

                    for col_json in ['patrulhamento_terrestre', 'patrulhamento_fluvial', 'capturas_animais', 'apreensoes']:
                        if col_json not in df.columns:
                            df[col_json] = "[]"

                    # Novos campos de documentos da apreensão (Nº CADG, Auto de Infração, etc.)
                    for col_doc in ['cadg', 'nr_auto_infracao', 'nr_termo_constatacao', 'nr_termo_apreensao']:
                        if col_doc not in df.columns:
                            df[col_doc] = ""
                        else:
                            df[col_doc] = df[col_doc].fillna("")
                    
                    # Tratamento de datas para o filtro de tempo
                    if 'data_criacao' in df.columns:
                        df['data_filtro'] = pd.to_datetime(df['data_criacao']).dt.date
                    elif 'data_inicial' in df.columns:
                        df['data_filtro'] = pd.to_datetime(df['data_inicial']).dt.date
                    else:
                        df['data_filtro'] = datetime.now().date()
                    
                    # Renomeia o ID para Sequência Numérica Oficial
                    df = df.rename(columns={"id": "Nº Sequencial do Relatório"})
                    
                    # Filtros de tempo (Semana, Mês, Ano)
                    st.markdown("### 📅 Filtro Temporal de Produção")
                    periodo = st.radio("Selecione o período de análise:", ["Total Histórico", "Últimos 7 Dias (Semana)", "Último Mês", "Ano Atual"], horizontal=True)
                    
                    hoje = datetime.now().date()
                    if periodo == "Últimos 7 Dias (Semana)":
                        df = df[df['data_filtro'] >= (hoje - timedelta(days=7))]
                    elif periodo == "Último Mês":
                        df = df[df['data_filtro'] >= (hoje - timedelta(days=30))]
                    elif periodo == "Ano Atual":
                        df = df[pd.to_datetime(df['data_filtro']).dt.year == datetime.now().year]

                    def explodir_lista_json(df_base, coluna_json, mapa_colunas=None):
                        """Transforma a coluna JSON (lista de dicts, uma por atividade/captura)
                        de cada relatório em um DataFrame 'longo', uma linha por item, associado
                        ao Nº do relatório de origem."""
                        linhas = []
                        for _, row in df_base.iterrows():
                            try:
                                itens = json.loads(row.get(coluna_json) or "[]")
                            except Exception:
                                itens = []
                            for item in itens:
                                item_com_ref = dict(item)
                                if mapa_colunas:
                                    for origem, destino in mapa_colunas.items():
                                        if origem in item_com_ref:
                                            item_com_ref[destino] = item_com_ref.pop(origem)
                                item_com_ref["Nº Relatório"] = row.get("Nº Sequencial do Relatório")
                                linhas.append(item_com_ref)
                        return pd.DataFrame(linhas) if linhas else pd.DataFrame()

                    df_graf_terr = explodir_lista_json(df, "patrulhamento_terrestre", {"PESSOAS ABORDADAS": "Pessoas Abordadas", "APREENSÕES": "Apreensões"})
                    df_graf_fluv = explodir_lista_json(df, "patrulhamento_fluvial", {"PESCADORES ABORDADOS": "Pescadores Abordados", "APREENSÕES": "Apreensões", "EMBARCAÇÕES ABORDADAS": "Embarcações Abordadas"})
                    df_graf_animais = explodir_lista_json(df, "capturas_animais")
                    if not df_graf_animais.empty and "QUANTIDADE" in df_graf_animais.columns:
                        total_animais_capturados = int(pd.to_numeric(df_graf_animais["QUANTIDADE"], errors='coerce').fillna(0).sum())
                    else:
                        total_animais_capturados = 0

                    df_graf_apreensoes = explodir_lista_json(df, "apreensoes")
                    if not df_graf_apreensoes.empty:
                        df_graf_apreensoes = df_graf_apreensoes[df_graf_apreensoes["INFRAÇÃO/CRIME"] != "Não se aplica"]
                    total_apreensoes = len(df_graf_apreensoes) if not df_graf_apreensoes.empty else 0
                    total_multas = pd.to_numeric(df_graf_apreensoes["VALOR MULTA"], errors='coerce').fillna(0).sum() if not df_graf_apreensoes.empty and "VALOR MULTA" in df_graf_apreensoes.columns else 0.0

                    # Abas do Dashboard Administrativo
                    tab_geral, tab_unidades, tab_equipes = st.tabs(["📊 Produção Geral", "🏢 Por Unidade", "🪖 Por Equipes (Efetivo)"])
                    
                    with tab_geral:
                        m1, m2, m3, m4, m5 = st.columns(5)
                        m1.metric("Total de Abordagens", int(df['pessoas_abordadas'].sum()))
                        m2.metric("Total de KM Rodado", f"{int(df['km_rodado'].sum())} km")
                        m3.metric("Animais Computados", total_animais_capturados)
                        m4.metric("Apreensões", total_apreensoes)
                        m5.metric("Total em Multas", f"R$ {total_multas:,.2f}")
                        
                        st.divider()
                        st.markdown("### 📋 Sequência Histórica de Relatórios Criados (Numerados)")
                        st.caption("A tabela foi dividida por item para facilitar a leitura.")

                        sub_tab01, sub_tab02, sub_tab03, sub_tab04, sub_tab05 = st.tabs([
                            "01 - Dados de Controle", "02 - Viaturas", "03 - Captura de Animais",
                            "04 - Apreensões", "05 - Estatística"
                        ])

                        with sub_tab01:
                            cols_01 = [c for c in [
                                "Nº Sequencial do Relatório", "status", "data_filtro", "unidade",
                                "finalidade", "comandante", "motorista", "data_inicial", "data_final"
                            ] if c in df.columns]
                            st.dataframe(df[cols_01], use_container_width=True)

                        with sub_tab02:
                            cols_02 = [c for c in [
                                "Nº Sequencial do Relatório", "viatura_prefixo", "km_inicial", "km_final", "km_rodado"
                            ] if c in df.columns]
                            st.dataframe(df[cols_02], use_container_width=True)

                        with sub_tab03:
                            if not df_graf_animais.empty:
                                st.dataframe(df_graf_animais, use_container_width=True)
                            else:
                                st.info("Nenhuma captura de animal registrada no período selecionado.")

                        with sub_tab04:
                            st.markdown("#### Detalhamento de Apreensões (Item 06)")
                            if not df_graf_apreensoes.empty:
                                # Traz contexto do relatório (data e comandante) para cada apreensão
                                cols_contexto = [c for c in ["Nº Sequencial do Relatório", "data_filtro", "comandante"] if c in df.columns]
                                df_contexto = df[cols_contexto].rename(columns={"Nº Sequencial do Relatório": "Nº Relatório"})
                                df_apreensoes_completo = df_graf_apreensoes.merge(df_contexto, on="Nº Relatório", how="left")
                                st.dataframe(df_apreensoes_completo, use_container_width=True)

                                col_ap_g1, col_ap_g2 = st.columns(2)
                                with col_ap_g1:
                                    st.markdown("##### Ocorrências por Tipo de Infração/Crime")
                                    df_graf1 = df_graf_apreensoes.groupby("INFRAÇÃO/CRIME")["Nº Relatório"].count().reset_index()
                                    st.bar_chart(data=df_graf1, x="INFRAÇÃO/CRIME", y="Nº Relatório")
                                with col_ap_g2:
                                    st.markdown("##### Total de Multas por Município")
                                    df_graf2 = df_graf_apreensoes.groupby("MUNICÍPIO")["VALOR MULTA"].sum().reset_index()
                                    st.bar_chart(data=df_graf2, x="MUNICÍPIO", y="VALOR MULTA")
                            else:
                                st.info("Nenhuma apreensão registrada no período selecionado.")

                        with sub_tab05:
                            if not df_graf_apreensoes.empty:
                                df_multas_rel = df_graf_apreensoes.groupby("Nº Relatório")["VALOR MULTA"].sum().reset_index()
                                df_multas_rel = df_multas_rel.rename(columns={"Nº Relatório": "Nº Sequencial do Relatório", "VALOR MULTA": "total_multas"})
                            else:
                                df_multas_rel = pd.DataFrame(columns=["Nº Sequencial do Relatório", "total_multas"])
                            df_05 = df.merge(df_multas_rel, on="Nº Sequencial do Relatório", how="left")
                            df_05["total_multas"] = df_05["total_multas"].fillna(0)
                            cols_05 = [c for c in [
                                "Nº Sequencial do Relatório", "pessoas_abordadas", "veiculos_abordados",
                                "embarcacoes_abordadas", "bo_lavrados", "autos_infracao", "total_multas"
                            ] if c in df_05.columns]
                            st.dataframe(df_05[cols_05], use_container_width=True)
                  
                        with tab_unidades:
                            st.markdown("### ### Comparativo Operacional: 2º Pel Miranda vs GPM Barra")

                            # Unifica os dados para trazer as unidades (Miranda, GPM Barra, etc.)
                            listagem_unidades = []
                            for idx, row in df.iterrows():
                                unid = row.get('unidade', 'Não Informada')
                                multa = pd.to_numeric(row.get('valor_multa', 0), errors='coerce')

                                # Coleta as somas terrestres deste relatório
                                soma_p_terr = 0
                                if not df_graf_terr.empty:
                                    soma_p_terr = df_graf_terr[df_graf_terr["Nº Relatório"] == row.get("Nº Sequencial do Relatório")]["Pessoas Abordadas"].sum()

                                # Coleta as somas fluviais deste relatório
                                soma_p_fluv = 0
                                if not df_graf_fluv.empty:
                                    soma_p_fluv = df_graf_fluv[df_graf_fluv["Nº Relatório"] == row.get("Nº Sequencial do Relatório")]["Pescadores Abordados"].sum()

                                listagem_unidades.append({
                                    "unidade": unid,
                                    "Total Abordados (Geral)": soma_p_terr + soma_p_fluv,
                                    "valor_multa": multa if not pd.isna(multa) else 0
                                })

                            if listagem_unidades:
                                df_unidade_nova = pd.DataFrame(listagem_unidades).groupby('unidade').sum().reset_index()
                                st.dataframe(df_unidade_nova, use_container_width=True)

                                col_un1, col_un2 = st.columns(2)
                                with col_un1:
                                    st.markdown("##### Abordagens por Unidade (Geral)")
                                    st.bar_chart(data=df_unidade_nova, x='unidade', y='Total Abordados (Geral)')
                                with col_un2:
                                    st.markdown("##### Multas Aplicadas por Unidade (R$)")
                                    st.bar_chart(data=df_unidade_nova, x='unidade', y='valor_multa')
                            else:
                                st.info("Dados de unidades não encontrados.")

                        with tab_equipes:
                            st.markdown("### ### Controle de Escala e Produção por Equipes (A, B e C)")

                            listagem_equipes = []
                            for idx, row in df.iterrows():
                                eqp = row.get('equipe', 'Não Informada')

                                soma_p_terr = 0
                                soma_a_terr = 0
                                if not df_graf_terr.empty:
                                    sub_t = df_graf_terr[df_graf_terr["Nº Relatório"] == row.get("Nº Sequencial do Relatório")]
                                    soma_p_terr = sub_t["Pessoas Abordadas"].sum()
                                    soma_a_terr = sub_t["Apreensões"].sum()

                                soma_p_fluv = 0
                                soma_a_fluv = 0
                                if not df_graf_fluv.empty:
                                    sub_f = df_graf_fluv[df_graf_fluv["Nº Relatório"] == row.get("Nº Sequencial do Relatório")]
                                    soma_p_fluv = sub_f["Pescadores Abordados"].sum()
                                    soma_a_fluv = sub_f["Apreensões"].sum()

                                listagem_equipes.append({
                                    "equipe": eqp,
                                    "Abordados": soma_p_terr + soma_p_fluv,
                                    "autos_infracao": soma_a_terr + soma_a_fluv
                                })

                            if listagem_equipes:
                                df_equipe_nova = pd.DataFrame(listagem_equipes).groupby('equipe').sum().reset_index()
                                st.dataframe(df_equipe_nova, use_container_width=True)
                                st.markdown("##### Eficiência de Fiscalização (Autos de Infração por Equipe)")
                                st.bar_chart(data=df_equipe_nova, x='equipe', y='autos_infracao')
                            else:
                                st.info("Dados de equipes não encontrados.")

                            st.divider()
                            st.markdown("### Produção Individual por Comandante de Guarnição")

                            listagem_comandantes = []
                            for idx, row in df.iterrows():
                                cmt = row.get('comandante', 'Não Informado')
                                nr_rel = row.get("Nº Sequencial do Relatório")

                                soma_p_terr = 0
                                if not df_graf_terr.empty:
                                    soma_p_terr = df_graf_terr[df_graf_terr["Nº Relatório"] == nr_rel]["Pessoas Abordadas"].sum()

                                soma_p_fluv = 0
                                if not df_graf_fluv.empty:
                                    soma_p_fluv = df_graf_fluv[df_graf_fluv["Nº Relatório"] == nr_rel]["Pescadores Abordados"].sum()

                                sub_ap = df_graf_apreensoes[df_graf_apreensoes["Nº Relatório"] == nr_rel] if not df_graf_apreensoes.empty else pd.DataFrame()
                                qtd_apreensoes_cmt = len(sub_ap)
                                total_multa_cmt = pd.to_numeric(sub_ap["VALOR MULTA"], errors='coerce').fillna(0).sum() if not sub_ap.empty and "VALOR MULTA" in sub_ap.columns else 0
                                total_ai_cmt = sum(len([v for v in str(x).split("; ") if v.strip()]) for x in sub_ap["AUTO INFRAÇÃO"]) if not sub_ap.empty and "AUTO INFRAÇÃO" in sub_ap.columns else 0

                                listagem_comandantes.append({
                                    "Comandante": cmt,
                                    "Abordagens (Geral)": soma_p_terr + soma_p_fluv,
                                    "Apreensões": qtd_apreensoes_cmt,
                                    "Autos de Infração": total_ai_cmt,
                                    "Total Multas (R$)": total_multa_cmt,
                                    "KM Rodado": row.get('km_rodado', 0)
                                })

                            if listagem_comandantes:
                                df_comandante_nova = pd.DataFrame(listagem_comandantes).groupby('Comandante').sum().reset_index()
                                st.dataframe(df_comandante_nova, use_container_width=True)

                                col_cmt1, col_cmt2 = st.columns(2)
                                with col_cmt1:
                                    st.markdown("##### Abordagens por Comandante")
                                    st.bar_chart(data=df_comandante_nova, x='Comandante', y='Abordagens (Geral)')
                                with col_cmt2:
                                    st.markdown("##### Multas Aplicadas por Comandante (R$)")
                                    st.bar_chart(data=df_comandante_nova, x='Comandante', y='Total Multas (R$)')
                            else:
                                st.info("Dados de comandantes não encontrados.")
            except Exception as e:
                st.error(f"Erro ao carregar o painel administrativo: {e}")