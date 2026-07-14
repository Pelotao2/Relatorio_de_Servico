import streamlit as st
from supabase import create_client, Client
import pandas as pd
import time

# Configuração da página para computadores do quartel (Modo Largo)
st.set_page_config(page_title="Sistema de Produtividade - Pelotão", layout="wide")

# ==========================================
# CONEXÃO DIRETA COM O SUPABASE DA NUVEM
# ==========================================
# 🔄 CORREÇÃO DA URL: Apontando exatamente para o servidor do seu Pelotão em São Paulo
SUPABASE_URL = "https://ctnviecmmpqiybyikjjq.supabase.co"
# ⚠️ COLE A SUA CHAVE LONGA EXATAMENTE DENTRO DAS ASPAS ABAIXO:
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN0bnZpZWNtbXBxaXlieWlrampxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODMwNzg1MzQsImV4cCI6MjA5ODY1NDUzNH0.wcBiKBV1M5Ch-hXUOeagaZl4M4YiVP5i-kjB8I_vOfc"

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error("Erro ao conectar ao Banco de Dados. Verifique as credenciais no código.")

# ==========================================
# INTERFACE E NAVEGAÇÃO
# ==========================================

# Limpa os campos do formulário SOMENTE após um envio bem-sucedido
# (evita apagar os dados quando o usuário aperta Enter sem terminar de preencher)
if st.session_state.get("_reset_form"):
    for k in ["input_comandante", "input_motorista", "input_vtr", "input_kmi", "input_kmf",
              "input_pessoas", "input_veic", "input_emb", "input_bos", "input_autos"]:
        st.session_state.pop(k, None)
    st.session_state["_reset_form"] = False

aba_policial, aba_adm = st.tabs(["📝 Formulário de Serviço (Policial)", "📈 Painel Estratégico (Adm)"])

# ------------------------------------------
# VISÃO 1: FORMULÁRIO DO POLICIAL (WORD MIMETIZADO)
# ------------------------------------------
with aba_policial:
    st.markdown("# 📄 RELATÓRIO DE SERVIÇO DIÁRIO")
    st.caption("Preencha os campos abaixo seguindo a ordem tradicional do documento impresso.")
    st.divider()

    # Todos os campos ficam dentro de um st.form: isso evita que o Streamlit
    # reprocesse o envio a cada interação com um campo (causa da duplicação).
    # O código só roda uma vez, quando o botão de submit é clicado.
    with st.form("form_relatorio_servico", clear_on_submit=False):
        # Bloco 01: Dados de Controle
        st.markdown("### 01 - DADOS DE CONTROLE")
        col1, col2 = st.columns(2)
        with col1:
            finalidade = st.selectbox("Finalidade do Serviço", ["Patrulhamento Ambiental", "Operação Integrada", "Fiscalização de Pesca", "Outros"])
            comandante = st.text_input("Comandante da Guarnição (Nome Completo)", key="input_comandante")
        with col2:
            motorista = st.text_input("Motorista/Tripulante (Nome Completo)", key="input_motorista")
        st.divider()

        # Bloco 02: Controle de Viaturas
        st.markdown("### 02 - CONTROLE DE VIATURAS / EMBARCAÇÕES")
        col3, col4, col5 = st.columns(3)
        with col3:
            viatura = st.text_input("Prefixo da Viatura/Embarcação", placeholder="Ex: VTR-1234", key="input_vtr")
        with col4:
            km_inicial = st.number_input("Quilometragem (KM) Inicial", min_value=0, step=1, key="input_kmi")
        with col5:
            km_final = st.number_input("Quilometragem (KM) Final", min_value=0, step=1, key="input_kmf")
        st.divider()

        # Bloco 03: Resumo Estatístico
        st.markdown("### 03 - RESUMO ESTATÍSTICO (PRODUTIVIDADE)")
        col6, col7, col8 = st.columns(3)
        with col6:
            pessoas = st.number_input("Pessoas Abordadas", min_value=0, step=1, key="input_pessoas")
            bo_lavrados = st.number_input("B.O.s Lavrados", min_value=0, step=1, key="input_bos")
        with col7:
            veiculos = st.number_input("Veículos Abordados", min_value=0, step=1, key="input_veic")
            autos = st.number_input("Autos de Infração Aplicados", min_value=0, step=1, key="input_autos")
        with col8:
            embarcacoes = st.number_input("Embarcações Abordadas", min_value=0, step=1, key="input_emb")
        st.divider()

        # Botão de Envio Grande e Destacado (form_submit_button só dispara UMA vez por clique)
        enviar = st.form_submit_button("🚀 FINALIZAR E ENVIAR RELATÓRIO PARA A NUVEM", type="primary", use_container_width=True)

    if enviar:
        if km_final < km_inicial:
            st.error("Erro: O KM Final não pode ser menor que o KM Inicial.")
        elif not comandante or not motorista:
            st.warning("Por favor, preencha os nomes da guarnição antes de finalizar.")
        else:
            dados = {
                "status": "Finalizado", 
                "finalidade": finalidade, 
                "comandante": comandante, 
                "motorista": motorista, 
                "viatura_prefixo": viatura, 
                "km_inicial": km_inicial, 
                "km_final": km_final, 
                "pessoas_abordadas": pessoas, 
                "veiculos_abordados": veiculos,
                "embarcacoes_abordadas": embarcacoes, 
                "bo_lavrados": bo_lavrados, 
                "autos_infracao": autos
            }
            try:
                # Envio direto utilizando a tabela correta
                supabase.table("relatorios_servico").insert(dados).execute()
                st.success("Relatório Oficial enviado com sucesso para a nuvem do Pelotão!")
                st.session_state["_reset_form"] = True
                st.rerun()
            except Exception as e:
                st.error(f"Falha ao salvar na nuvem: {e}")

# ------------------------------------------
# VISÃO 2: PAINEL ESTRATÉGICO ADMINISTRATIVO (DASHBOARD)
# ------------------------------------------
with aba_adm:
    st.markdown("# 📈 PAINEL ESTRATÉGICO ADMINISTRATIVO")
    
    # Proteção por senha
    senha = st.text_input("Insira a senha administrativa para acessar os gráficos", type="password", key="input_senha")
    if senha == "adm123":
        st.success("Acesso liberado!")
        
        try:
            # Busca direta dos dados na tabela
            registros = supabase.table("relatorios_servico").select("*").execute().data
            
            if registros:
                df = pd.DataFrame(registros)
                
                # Tratamento e conversão de dados numéricos
                df['pessoas_abordadas'] = pd.to_numeric(df['pessoas_abordadas'], errors='coerce').fillna(0)
                df['autos_infracao'] = pd.to_numeric(df['autos_infracao'], errors='coerce').fillna(0)
                
                if 'km_rodado' in df.columns:
                    df['km_rodado'] = pd.to_numeric(df['km_rodado'], errors='coerce').fillna(0)
                else:
                    df['km_rodado'] = pd.to_numeric(df['km_final'], errors='coerce').fillna(0) - pd.to_numeric(df['km_inicial'], errors='coerce').fillna(0)
                
                # Exibição das Métricas Rápidas
                total_pessoas = df['pessoas_abordadas'].sum()
                total_km = df['km_rodado'].sum()
                total_autos = df['autos_infracao'].sum()
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Total de Pessoas Abordadas", int(total_pessoas))
                m2.metric("Total de KM Rodado (Frota)", f"{int(total_km)} km")
                m3.metric("Autos de Infração Emitidos", int(total_autos))
                
                st.divider()
                st.markdown("### 📋 Histórico de Produtividade do Pelotão")
                
                colunas_exibir = [c for c in ["id", "data_criacao", "comandante", "viatura_prefixo", "km_rodado", "pessoas_abordadas", "veiculos_abordados", "embarcacoes_abordadas", "bo_lavrados", "autos_infracao"] if c in df.columns]
                st.dataframe(df[colunas_exibir])
                
                # Renderização do gráfico de barras
                st.markdown("### 📊 Comparativo de Abordagens por Comandante")
                if 'comandante' in df.columns and not df['comandante'].dropna().empty:
                    prod_comandante = df.groupby("comandante")["pessoas_abordadas"].sum()
                    st.bar_chart(prod_comandante)
                else:
                    st.info("Insira o nome de um Comandante no formulário para gerar os gráficos comparativos.")
                
            else:
                st.info("Nenhum dado encontrado no banco de dados ainda. Envie um relatório na aba ao lado!")
        except Exception as e:
            st.error(f"Erro ao carregar dados do painel da nuvem: {e}")
    elif senha:
        st.error("Senha incorreta.")