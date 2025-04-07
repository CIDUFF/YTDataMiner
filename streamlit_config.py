"""
Arquivo de configuração para resolver problemas de compatibilidade do Streamlit
"""
import sys
import os
import nest_asyncio

# Aplicar nest_asyncio para garantir que temos um loop de eventos sem conflitos
nest_asyncio.apply()


def setup_env():
    """Configurar o ambiente para evitar conflitos de importação durante a execução do Streamlit"""
    # Definir variáveis de ambiente úteis para evitar problemas de dependências
    os.environ["PYTHONUNBUFFERED"] = "1"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"

    # Desabilitar mensagens de aviso do Streamlit sobre importações
    os.environ["STREAMLIT_DISABLE_WATCHER_WARNINGS"] = "true"

    # Aumentar a verbosidade de logs para debug se necessário
    # os.environ["STREAMLIT_LOG_LEVEL"] = "debug"

    # Definir configuração para usar um único processo
    os.environ["STREAMLIT_SERVER_RUN_ON_SAVE"] = "false"


# Aplicar configurações
setup_env()
