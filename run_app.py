"""
Script para iniciar o aplicativo Streamlit contornando problemas de event loop e dependências.
"""
import os
import sys
import subprocess


def run_streamlit():
    """Executa o aplicativo Streamlit usando um subprocess com configurações otimizadas"""
    # Obter o caminho do interpretador Python atual
    python_exec = sys.executable

    # Preparar o comando para iniciar o Streamlit
    command = [
        python_exec,
        "-m", "streamlit",
        "run",
        "youtube_downloader.py",
        "--browser.serverAddress=localhost",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
    ]

    # Configurar variáveis de ambiente para o processo
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_DISABLE_WATCHER_WARNINGS"] = "true"

    print("Iniciando o aplicativo RASPA TUDO - CID...")
    print("Acesse http://localhost:8501 no seu navegador")

    # Executar o processo do Streamlit
    process = subprocess.run(command, env=env)
    return process.returncode


if __name__ == "__main__":
    # Garantir que estamos no diretório correto
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Executar o aplicativo
    sys.exit(run_streamlit())
