import streamlit as st
import os
import re
import time
import subprocess
import sys
import importlib
import tempfile
from datetime import datetime
import platform
import logging
import json
import yaml
from pathlib import Path

# Resolver problema de evento asyncio - deve vir antes de qualquer outra importação que use asyncio

# Resolver problema de conflito com PyTorch - versão melhorada
_orig_import = __import__


def _import_hook(name, globals=None, locals=None, fromlist=(), level=0):
    # Previne o carregamento automático do torch durante o rastreamento de módulos do Streamlit
    if name == 'torch' and any(frame_info[0].f_code.co_filename.find('streamlit/watcher') >= 0
                               for frame_info in sys._current_frames().values()):
        if 'torch' not in sys.modules:
            class DummyTorch:
                _C = type(
                    '_C', (), {'_get_custom_class_python_wrapper': lambda *args: None})

                def __getattr__(self, name):
                    if name == '__path__':
                        return type('__path__', (), {'_path': []})
                    return self

                def __call__(self, *args, **kwargs):
                    return self

            return DummyTorch()
        return sys.modules['torch']
    return _orig_import(name, globals, locals, fromlist, level)


sys.__import__ = _import_hook
sys.modules.pop('torch', None)

# Configurar logging para arquivos em vez de interface
log_dir = os.path.join(os.getcwd(), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(
    log_dir, f"downloader_{datetime.now().strftime('%Y%m%d')}.log")
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Inicializar estado da sessão para armazenar o caminho do arquivo baixado
if 'downloaded_file_path' not in st.session_state:
    st.session_state.downloaded_file_path = None
if 'download_complete' not in st.session_state:
    st.session_state.download_complete = False
if 'file_info' not in st.session_state:
    st.session_state.file_info = {
        'size': 0,
        'name': ''
    }
if 'transcription_path' not in st.session_state:
    st.session_state.transcription_path = None
if 'transcription_complete' not in st.session_state:
    st.session_state.transcription_complete = False

# Configuração da página Streamlit
st.set_page_config(
    page_title="RASPA TUDO - CID",
    page_icon="🎬",
    layout="centered"
)

# Título e descrição
st.title("📥 RASPA TUDO - CID")
st.markdown("Insira o URL de um vídeo do YouTube para baixá-lo ou transcrevê-lo.")

# Função para sanitizar o nome do arquivo


def sanitize_filename(filename):
    # Remove caracteres inválidos para nome de arquivo
    return re.sub(r'[\\/*?:"<>|]', "", filename)

# Função para logs sem exibir na tela


def log_info(message):
    logging.info(message)
    # Não exibe mensagens na interface


def log_error(message):
    logging.error(message)
    # Não mostra detalhes técnicos do erro, apenas mensagem genérica ao usuário

# Verificar/instalar yt-dlp


def ensure_yt_dlp():
    try:
        # Tentar importar yt-dlp para ver se já está instalado
        importlib.import_module('yt_dlp')
        log_info("Biblioteca yt-dlp já está instalada")
        return True
    except ImportError:
        # Instalar yt-dlp se não estiver disponível
        try:
            st.info("Instalando biblioteca necessária...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "yt-dlp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            importlib.import_module('yt_dlp')
            log_info("Biblioteca yt-dlp instalada com sucesso")
            return True
        except Exception as e:
            log_error(f"Erro na instalação da biblioteca yt-dlp: {str(e)}")
            st.error("Não foi possível instalar a biblioteca necessária.")
            return False

# Função para verificar e instalar ffmpeg


def ensure_ffmpeg():
    try:
        # Verificar se ffmpeg está instalado
        if platform.system() == "Windows":
            result = subprocess.run(
                ["where", "ffmpeg"], capture_output=True, text=True)
            ffmpeg_installed = result.returncode == 0
        else:
            result = subprocess.run(
                ["which", "ffmpeg"], capture_output=True, text=True)
            ffmpeg_installed = result.returncode == 0

        if ffmpeg_installed:
            log_info("FFmpeg já está instalado no sistema")
            return True

        # Mensagem para o usuário
        st.info("Verificando ferramentas adicionais para melhor qualidade...")
        log_info("FFmpeg não encontrado. Tentando instalar...")

        # Método alternativo para Windows - baixar executável diretamente
        if platform.system() == "Windows":
            try:
                import urllib.request
                import zipfile
                import shutil

                # URL do FFmpeg estático para Windows (versão mínima)
                ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip"
                temp_dir = tempfile.mkdtemp()
                zip_path = os.path.join(temp_dir, "ffmpeg.zip")

                log_info(f"Baixando FFmpeg de {ffmpeg_url}")
                # Baixar o arquivo
                try:
                    urllib.request.urlretrieve(ffmpeg_url, zip_path)
                except Exception as e:
                    log_error(f"Erro ao baixar FFmpeg: {str(e)}")
                    return False

                log_info("Extraindo FFmpeg...")
                # Extrair o arquivo
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)

                # Encontrar o executável ffmpeg.exe
                ffmpeg_exe = None
                for root, dirs, files in os.walk(temp_dir):
                    if "ffmpeg.exe" in files:
                        ffmpeg_exe = os.path.join(root, "ffmpeg.exe")
                        break

                if ffmpeg_exe:
                    # Copiar para um local no PATH
                    bin_dir = os.path.join(
                        os.path.dirname(sys.executable), "Scripts")
                    os.makedirs(bin_dir, exist_ok=True)
                    dest_path = os.path.join(bin_dir, "ffmpeg.exe")
                    shutil.copy2(ffmpeg_exe, dest_path)

                    log_info(f"FFmpeg instalado em {dest_path}")
                    # Limpar diretório temporário
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return True
                else:
                    log_error("FFmpeg não encontrado no arquivo baixado")
                    return False

            except Exception as e:
                log_error(f"Erro ao instalar FFmpeg manualmente: {str(e)}")
                return False
        else:
            # Para sistemas Linux/Mac - tentar instalar via gerenciador de pacotes
            try:
                log_info("Tentando instalar FFmpeg via sistema")
                # Log silencioso para não mostrar na interface
                return False  # Assumir falha por enquanto
            except Exception as e:
                log_error(f"Erro ao instalar FFmpeg: {str(e)}")
                return False

        return False
    except Exception as e:
        log_error(f"Erro ao verificar/instalar FFmpeg: {str(e)}")
        return False

# Função para obter informações do vídeo antes de baixar


def get_video_info(url):
    try:
        if not ensure_yt_dlp():
            return None

        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True  # Apenas extrai informações, sem baixar
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            log_info(f"Obtendo informações do vídeo: {url}")
            info = ydl.extract_info(url, download=False)

            if not info:
                log_error("Não foi possível obter informações do vídeo")
                st.error("Não foi possível obter informações do vídeo.")
                return None

            video_info = {
                'title': info.get('title', 'Sem título'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Desconhecido'),
                'thumbnail': info.get('thumbnail', ''),
                'description': info.get('description', ''),
                'view_count': info.get('view_count', 0),
                'formats': info.get('formats', [])
            }

            return video_info
    except Exception as e:
        log_error(f"Erro ao obter informações do vídeo: {str(e)}")
        st.error("Não foi possível obter informações do vídeo.")
        return None

# Função para baixar vídeo usando yt-dlp sem necessidade de ffmpeg


def download_without_ffmpeg(url, download_type, output_template):
    try:
        log_info(f"Iniciando download sem FFmpeg: {url}")
        if download_type == "Video (Maior Resolução)":
            # Baixar o melhor formato completo (não requer mesclagem)
            format_option = "best[ext=mp4]/best"
        else:  # Apenas Áudio
            # Baixar apenas o melhor áudio já em formato MP3 se possível
            format_option = "bestaudio[ext=mp3]/bestaudio"

        cmd = [
            "yt-dlp",
            "-f", format_option,
            "-o", output_template + ".%(ext)s",
            "--no-check-certificate",
            url
        ]

        log_info(f"Executando download sem FFmpeg: {' '.join(cmd)}")
        process = subprocess.run(cmd, capture_output=True, text=True)

        if process.returncode == 0:
            log_info("Download concluído com sucesso")
            # Buscar arquivo criado
            for ext in ['.mp4', '.mp3', '.webm', '.m4a', '.ogg']:
                if os.path.exists(output_template + ext):
                    log_info(f"Arquivo encontrado: {output_template + ext}")
                    return output_template + ext

            log_error("Arquivo baixado, mas não encontrado no local esperado")
            return None
        else:
            log_error(f"Erro no download: {process.stderr}")
            return None
    except Exception as e:
        log_error(f"Erro ao baixar sem FFmpeg: {str(e)}")
        return None

# Função principal para baixar vídeo


def download_video_with_yt_dlp(url, download_type, custom_filename=None):
    try:
        if not ensure_yt_dlp():
            log_error("yt-dlp não está disponível")
            return None

        # Obter informações do vídeo para mostrar ao usuário
        video_info = get_video_info(url)

        if not video_info:
            return None

        # Exibir informações do vídeo
        st.info(f"Preparando para baixar: {video_info['title']}")

        # Exibir miniatura se disponível
        if video_info['thumbnail']:
            try:
                st.image(video_info['thumbnail'], width=300)
            except Exception as e:
                log_error(f"Erro ao exibir miniatura: {str(e)}")

        # Informações adicionais
        log_info(
            f"Duração: {video_info['duration']} segundos | Canal: {video_info['uploader']}")

        # Criar diretório para downloads
        download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_dir, exist_ok=True)

        # Definir nome do arquivo
        if custom_filename and custom_filename.strip():
            safe_title = sanitize_filename(custom_filename)
        else:
            safe_title = sanitize_filename(video_info['title'])

        # Se o nome sanitizado ficar vazio, use um nome baseado em timestamp
        if not safe_title or len(safe_title) < 3:
            safe_title = f"youtube_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Verificar se o FFmpeg está instalado
        ffmpeg_available = ensure_ffmpeg()

        if not ffmpeg_available:
            log_info("FFmpeg não disponível, usando método alternativo")
            if download_type == "Video (Maior Resolução)":
                st.info("Baixando na melhor qualidade disponível...")
            else:
                st.info("Baixando áudio no melhor formato disponível...")

        # Caminho para o arquivo de saída
        output_template = os.path.join(download_dir, safe_title)

        # Se FFmpeg não estiver disponível, use o método alternativo
        if not ffmpeg_available:
            return download_without_ffmpeg(url, download_type, output_template)

        # Configurar yt-dlp
        import yt_dlp

        ydl_opts = {
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': False,
            'noprogress': False,
            'noplaylist': True,
        }

        if ffmpeg_available:
            if download_type == "Video (Maior Resolução)":
                ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                expected_extension = '.mp4'
            else:  # Apenas Áudio
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
                expected_extension = '.mp3'

        st.info("Iniciando download...")
        log_info("Iniciando download com yt-dlp...")

        # Barra de progresso
        progress_bar = st.progress(0)
        status_text = st.empty()

        # Função de callback para atualizar o progresso
        def progress_hook(d):
            if d['status'] == 'downloading':
                # Calcular porcentagem
                if d.get('total_bytes'):
                    percentage = d.get('downloaded_bytes', 0) / \
                        d.get('total_bytes', 1) * 100
                    progress_bar.progress(min(int(percentage), 100) / 100)
                    status_text.text(
                        f"Baixando: {percentage:.1f}% de {d.get('total_bytes')/1048576:.1f} MB")
                else:
                    status_text.text(
                        f"Baixando: {d.get('downloaded_bytes', 0)/1048576:.1f} MB")

            if d['status'] == 'finished':
                status_text.text("Processando arquivo...")
                progress_bar.progress(1.0)

        # Adicionar hook de progresso
        ydl_opts['progress_hooks'] = [progress_hook]

        # Executar o download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info_dict)

        log_info(f"Nome do arquivo reportado: {downloaded_file}")

        # Verificar se o arquivo existe
        if os.path.exists(downloaded_file):
            log_info(f"Arquivo encontrado: {downloaded_file}")
            st.session_state.downloaded_file_path = downloaded_file
            file_size = os.path.getsize(
                downloaded_file) / (1024 * 1024)  # Convert to MB
            st.session_state.file_info = {
                'size': file_size,
                'name': os.path.basename(downloaded_file)
            }
            st.session_state.download_complete = True
            return downloaded_file

        # Tentar encontrar o arquivo com extensão diferente
        base_path = os.path.splitext(downloaded_file)[0]
        possible_extensions = ['.mp4', '.webm', '.mkv', '.mp3', '.m4a', '.ogg']

        for ext in possible_extensions:
            possible_file = base_path + ext
            if os.path.exists(possible_file):
                log_info(
                    f"Arquivo encontrado com extensão diferente: {possible_file}")
                st.session_state.downloaded_file_path = possible_file
                file_size = os.path.getsize(
                    possible_file) / (1024 * 1024)  # Convert to MB
                st.session_state.file_info = {
                    'size': file_size,
                    'name': os.path.basename(possible_file)
                }
                st.session_state.download_complete = True
                return possible_file

        # Última tentativa - procurar por arquivos recentes
        files = os.listdir(download_dir)
        now = time.time()
        recent_files = [os.path.join(download_dir, f) for f in files
                        if os.path.isfile(os.path.join(download_dir, f))
                        and os.path.getmtime(os.path.join(download_dir, f)) > now - 60]

        if recent_files:
            recent_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            log_info(f"Encontrado arquivo recente: {recent_files[0]}")
            st.session_state.downloaded_file_path = recent_files[0]
            file_size = os.path.getsize(
                recent_files[0]) / (1024 * 1024)  # Convert to MB
            st.session_state.file_info = {
                'size': file_size,
                'name': os.path.basename(recent_files[0])
            }
            st.session_state.download_complete = True
            return recent_files[0]

        log_error("Não foi possível encontrar o arquivo baixado")
        st.error("Não foi possível encontrar o arquivo baixado.")
        st.session_state.download_complete = False
        st.session_state.downloaded_file_path = None
        return None

    except Exception as e:
        log_error(f"Erro ao baixar o vídeo: {str(e)}")
        st.error("Ocorreu um erro ao baixar o vídeo.")
        st.session_state.download_complete = False
        st.session_state.downloaded_file_path = None

        # Se o erro for relacionado ao ffmpeg, tentar método alternativo
        if "ffmpeg is not installed" in str(e):
            log_info("Erro de FFmpeg, tentando método alternativo")
            return download_without_ffmpeg(url, download_type, os.path.join(os.getcwd(), "downloads",
                                                                            f"youtube_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"))

        return None

# Verificar/instalar bibliotecas necessárias para transcrição


def ensure_transcription_deps():
    try:
        # Tentar usar faster-whisper em vez de whisper regular
        try:
            importlib.import_module('faster_whisper')
            log_info("Biblioteca faster-whisper já está instalada")
            return True
        except ImportError:
            st.info("Instalando biblioteca de transcrição...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "faster-whisper"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            log_info("Biblioteca faster-whisper instalada com sucesso")

        # Verificar/instalar PyYAML
        try:
            importlib.import_module('yaml')
            log_info("Biblioteca yaml já está instalada")
        except ImportError:
            st.info("Instalando biblioteca para processamento de metadados...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "pyyaml"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            log_info("Biblioteca yaml instalada com sucesso")

        return True
    except Exception as e:
        log_error(f"Erro ao instalar bibliotecas para transcrição: {str(e)}")
        st.error(
            "Não foi possível instalar as bibliotecas necessárias para transcrição.")
        return False

# Função para extrair metadados detalhados do vídeo


def get_detailed_video_metadata(url):
    try:
        if not ensure_yt_dlp():
            return None

        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'writeinfojson': True,
            'noplaylist': True
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            ydl_opts['outtmpl'] = os.path.join(temp_dir, 'video_info')

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                log_info(f"Obtendo metadados detalhados do vídeo: {url}")
                info_dict = ydl.extract_info(url, download=False)

                # Extrair tags do vídeo
                tags = info_dict.get('tags', [])
                hashtags = [
                    f"#{tag.replace(' ', '_')}" for tag in tags] if tags else []

                # Extrair estatísticas
                stats = {
                    'view_count': info_dict.get('view_count', 0),
                    'like_count': info_dict.get('like_count', 0),
                    'dislike_count': info_dict.get('dislike_count', 0),
                    'comment_count': info_dict.get('comment_count', 0),
                    'average_rating': info_dict.get('average_rating', None)
                }

                # Criar metadados completos
                metadata = {
                    'title': info_dict.get('title', 'Sem título'),
                    'description': info_dict.get('description', ''),
                    'channel': info_dict.get('uploader', 'Desconhecido'),
                    'channel_id': info_dict.get('uploader_id', ''),
                    'channel_url': info_dict.get('uploader_url', ''),
                    'publish_date': info_dict.get('upload_date', ''),
                    'duration_seconds': info_dict.get('duration', 0),
                    'url': url,
                    'video_id': info_dict.get('id', ''),
                    'categories': info_dict.get('categories', []),
                    'tags': hashtags,
                    'original_tags': tags,
                    'language': info_dict.get('language', 'Desconhecido'),
                    'is_live': info_dict.get('is_live', False),
                    'was_live': info_dict.get('was_live', False),
                    'statistics': stats,
                    'thumbnails': info_dict.get('thumbnails', [])
                }

                # Formatar a data em formato legível se disponível
                if metadata['publish_date'] and len(metadata['publish_date']) == 8:
                    try:
                        year = metadata['publish_date'][:4]
                        month = metadata['publish_date'][4:6]
                        day = metadata['publish_date'][6:8]
                        metadata['publish_date'] = f"{year}-{month}-{day}"
                    except:
                        pass

                return metadata
    except Exception as e:
        log_error(f"Erro ao obter metadados detalhados: {str(e)}")
        return None

# Função para transcrever áudio/vídeo usando faster-whisper


def transcribe_media(file_path, language="pt", model_name="small"):
    try:
        if not ensure_transcription_deps():
            return None

        st.info("Iniciando transcrição do áudio... (isso pode levar alguns minutos)")

        # Importar faster-whisper após garantir que está instalado
        from faster_whisper import WhisperModel

        log_info(f"Carregando modelo de transcrição: {model_name}")
        status_text = st.empty()
        status_text.text("Carregando modelo de transcrição...")

        # Verificar disponibilidade de GPU
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            log_info(
                f"Usando dispositivo: {device} com tipo de computação: {compute_type}")
        except:
            device = "cpu"
            compute_type = "int8"
            log_info("PyTorch não disponível, usando CPU com int8")

        # Carregar modelo
        model = WhisperModel(model_name, device=device,
                             compute_type=compute_type)

        status_text.text(
            "Transcrevendo áudio (isso pode levar vários minutos dependendo do tamanho do vídeo)...")
        log_info(f"Iniciando transcrição: {file_path}")

        # Executar transcrição
        segments, info = model.transcribe(
            file_path,
            language=language if language != "auto" else None,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True
        )

        # Criar resultado formatado semelhante ao resultado do whisper_timestamped
        result = {
            "segments": []
        }

        # Converter formato de saída para o formato esperado pelo resto do código
        for segment in segments:
            segment_dict = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "words": []
            }

            for word in segment.words:
                segment_dict["words"].append({
                    "start": word.start,
                    "end": word.end,
                    "word": word.word
                })

            result["segments"].append(segment_dict)

        status_text.text("Transcrição concluída! Gerando arquivo...")
        log_info("Transcrição concluída com sucesso")

        return result

    except Exception as e:
        log_error(f"Erro na transcrição: {str(e)}")
        st.error(f"Ocorreu um erro durante a transcrição: {str(e)}")
        return None

# Função para formatar a transcrição com metadados em markdown


def format_transcription_markdown(transcription, metadata):
    try:
        # Extrair segmentos de texto
        segments = transcription.get('segments', [])

        # Preparar cabeçalho YAML
        yaml_header = {
            'title': metadata['title'],
            'author': metadata['channel'],
            'date': metadata['publish_date'],
            'url': metadata['url'],
            'video_id': metadata['video_id'],
            'duration': metadata['duration_seconds'],
            'tags': metadata['tags'],
            'categories': metadata['categories'],
            'statistics': {
                'views': metadata['statistics']['view_count'],
                'likes': metadata['statistics']['like_count'],
                'comments': metadata['statistics']['comment_count']
            }
        }

        # Converter para YAML
        yaml_string = yaml.dump(
            yaml_header, allow_unicode=True, sort_keys=False)

        # Montar markdown
        markdown_content = f"""---
{yaml_string}---

# {metadata['title']}

## Transcrição

"""

        # Adicionar segmentos com marcação de tempo
        for segment in segments:
            start_time = segment.get('start', 0)
            text = segment.get('text', '').strip()

            # Formatar tempo em HH:MM:SS
            minutes, seconds = divmod(start_time, 60)
            hours, minutes = divmod(minutes, 60)
            timestamp = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

            markdown_content += f"[{timestamp}] {text}\n\n"

        # Adicionar descrição original do vídeo
        if metadata.get('description'):
            markdown_content += f"\n## Descrição Original\n\n{metadata['description']}\n"

        return markdown_content

    except Exception as e:
        log_error(f"Erro ao formatar transcrição: {str(e)}")
        return None

# Função para salvar transcrição em arquivo markdown


def save_transcription(markdown_content, video_title):
    try:
        # Criar diretório para transcrições
        transcriptions_dir = os.path.join(os.getcwd(), "transcriptions")
        os.makedirs(transcriptions_dir, exist_ok=True)

        # Criar nome de arquivo seguro
        safe_title = sanitize_filename(video_title)
        if not safe_title or len(safe_title) < 3:
            safe_title = f"transcription_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Adicionar timestamp para evitar sobrescrever arquivos
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = os.path.join(
            transcriptions_dir, f"{safe_title}_{timestamp}.md")

        # Salvar arquivo
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(markdown_content)

        return file_path

    except Exception as e:
        log_error(f"Erro ao salvar transcrição: {str(e)}")
        return None

# Função principal para transcrever vídeo


def process_transcription(url=None, file_path=None):
    try:
        if not url and not file_path:
            st.error("É necessário fornecer um URL ou um arquivo para transcrição.")
            return None

        # Se temos apenas URL, precisamos baixar o áudio primeiro
        if url and not file_path:
            st.info("Preparando para baixar o áudio do vídeo...")

            # Obter metadados primeiro
            metadata = get_detailed_video_metadata(url)
            if not metadata:
                st.error("Não foi possível obter informações do vídeo.")
                return None

            # Baixar apenas o áudio para transcrição
            audio_dir = os.path.join(os.getcwd(), "temp_audio")
            os.makedirs(audio_dir, exist_ok=True)

            safe_title = sanitize_filename(metadata['title'])
            output_template = os.path.join(audio_dir, safe_title)

            # Usar yt-dlp para baixar apenas o áudio (formato ogg ou m4a funciona bem)
            if ensure_yt_dlp():
                cmd = [
                    "yt-dlp",
                    "-f", "bestaudio[ext=m4a]/bestaudio",
                    "-o", output_template + ".%(ext)s",
                    "--no-check-certificate",
                    url
                ]

                log_info(f"Baixando áudio para transcrição: {' '.join(cmd)}")
                process = subprocess.run(cmd, capture_output=True, text=True)

                if process.returncode != 0:
                    st.error("Não foi possível baixar o áudio para transcrição.")
                    log_error(f"Erro ao baixar áudio: {process.stderr}")
                    return None

                # Localizar o arquivo baixado
                for ext in ['.m4a', '.ogg', '.mp3', '.wav', '.webm']:
                    if os.path.exists(output_template + ext):
                        file_path = output_template + ext
                        break

                if not file_path or not os.path.exists(file_path):
                    st.error(
                        "Não foi possível encontrar o arquivo de áudio baixado.")
                    return None
            else:
                st.error(
                    "Não foi possível configurar o download de áudio para transcrição.")
                return None
        else:
            # Se temos um arquivo local mas não URL, precisamos obter o URL de alguma forma
            # Por enquanto, vamos criar metadados mínimos
            if not url:
                metadata = {
                    'title': os.path.basename(file_path),
                    'channel': 'Desconhecido',
                    'publish_date': datetime.now().strftime('%Y-%m-%d'),
                    'url': '',
                    'video_id': '',
                    'duration_seconds': 0,
                    'tags': [],
                    'categories': [],
                    'statistics': {'view_count': 0, 'like_count': 0, 'comment_count': 0}
                }
            else:
                metadata = get_detailed_video_metadata(url)

        # Transcrever o áudio
        transcription = transcribe_media(file_path)
        if not transcription:
            st.error("Não foi possível realizar a transcrição.")
            return None

        # Gerar markdown com metadados
        markdown_content = format_transcription_markdown(
            transcription, metadata)
        if not markdown_content:
            st.error("Erro ao formatar a transcrição.")
            return None

        # Salvar em arquivo
        saved_path = save_transcription(markdown_content, metadata['title'])
        if not saved_path:
            st.error("Erro ao salvar a transcrição.")
            return None

        # Limpar arquivos temporários se necessário
        if url and file_path and file_path.startswith(os.path.join(os.getcwd(), "temp_audio")):
            try:
                os.remove(file_path)
            except:
                pass

        # Atualizar estado de sessão
        st.session_state.transcription_path = saved_path
        st.session_state.transcription_complete = True

        return saved_path

    except Exception as e:
        log_error(f"Erro no processo de transcrição: {str(e)}")
        st.error("Ocorreu um erro durante o processo de transcrição.")
        return None


# Interface do usuário - separada em duas partes: formulário e área de download
with st.form("download_form"):
    video_url = st.text_input("URL do Vídeo do YouTube:")

    # Adicionar opção para transcrição
    operation_type = st.radio(
        "O que você deseja fazer?",
        ["Baixar Vídeo/Áudio", "Transcrever Vídeo"]
    )

    if operation_type == "Baixar Vídeo/Áudio":
        download_type = st.selectbox(
            "Selecione o formato:",
            ["Video (Maior Resolução)", "Apenas Áudio (MP3)"]
        )
    else:
        # Opções para transcrição
        transcription_language = st.selectbox(
            "Idioma da transcrição:",
            ["pt", "en", "es", "fr", "de", "auto"]
        )

        transcription_model = st.selectbox(
            "Modelo de transcrição:",
            ["tiny", "base", "small", "medium"],
            index=2,  # "small" como padrão
            help="Modelos maiores são mais precisos mas consomem mais recursos e tempo"
        )

    custom_filename = st.text_input(
        "Nome personalizado para o arquivo (opcional):", "")

    submitted = st.form_submit_button("Processar")

# Processamento (fora do formulário)
if submitted and video_url:
    # Verificar se o URL é válido
    if not re.match(r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.*', video_url):
        st.error("URL inválido. Por favor, use um link do YouTube válido.")
    else:
        if operation_type == "Baixar Vídeo/Áudio":
            # Lógica existente para download
            with st.spinner("Baixando..."):
                file_path = download_video_with_yt_dlp(
                    video_url, download_type, custom_filename if custom_filename else None)

                if file_path and os.path.exists(file_path) and st.session_state.file_info:
                    # Verificar se file_info existe e tem a chave 'size'
                    file_size = st.session_state.file_info.get('size', 0)
                    st.success(
                        f"Download concluído! Tamanho do arquivo: {file_size:.2f} MB")
                elif file_path and os.path.exists(file_path):
                    # Se file_info não estiver configurado corretamente
                    file_size = os.path.getsize(file_path) / (1024 * 1024)
                    st.session_state.file_info = {
                        'size': file_size,
                        'name': os.path.basename(file_path)
                    }
                    st.session_state.downloaded_file_path = file_path
                    st.session_state.download_complete = True
                    st.success(
                        f"Download concluído! Tamanho do arquivo: {file_size:.2f} MB")
                else:
                    st.error("Não foi possível completar o download.")
        else:
            # Nova lógica para transcrição
            with st.spinner("Transcrevendo vídeo... (isso pode levar vários minutos)"):
                transcription_path = process_transcription(url=video_url)

                if transcription_path and os.path.exists(transcription_path):
                    st.success("Transcrição concluída com sucesso!")
                else:
                    st.error("Não foi possível completar a transcrição.")
elif submitted:
    st.warning("Por favor, insira um URL válido do YouTube.")

# Área de download para vídeo/áudio
if st.session_state.download_complete and st.session_state.downloaded_file_path and os.path.exists(st.session_state.downloaded_file_path):
    # Exibir informações do arquivo
    file_name = st.session_state.file_info.get(
        'name', os.path.basename(st.session_state.downloaded_file_path))
    st.info(f"Arquivo pronto para download: {file_name}")

    # Botão de download fora do formulário
    try:
        with open(st.session_state.downloaded_file_path, "rb") as file:
            st.download_button(
                label="Clique para baixar o arquivo",
                data=file,
                file_name=file_name,
                mime="application/octet-stream",
                key="download_button"  # Chave única para o botão
            )
    except Exception as e:
        log_error(f"Erro ao criar botão de download: {str(e)}")
        st.error("Erro ao preparar o arquivo para download.")
        st.session_state.download_complete = False

# Área de download para transcrição
if st.session_state.transcription_complete and st.session_state.transcription_path and os.path.exists(st.session_state.transcription_path):
    # Exibir prévia da transcrição
    st.subheader("Prévia da Transcrição")

    # Ler primeiras linhas do arquivo
    with open(st.session_state.transcription_path, 'r', encoding='utf-8') as file:
        preview_lines = []
        yaml_section = False
        yaml_ended = False
        content_lines = 0

        for line in file:
            if line.strip() == '---' and not yaml_section:
                yaml_section = True
                preview_lines.append(line)
                continue
            elif line.strip() == '---' and yaml_section:
                yaml_ended = True
                preview_lines.append(line)
                continue

            if yaml_section and not yaml_ended:
                preview_lines.append(line)
            elif yaml_ended:
                if content_lines < 10:  # Mostrar apenas primeiras 10 linhas do conteúdo
                    preview_lines.append(line)
                    content_lines += 1

    # Mostrar prévia
    st.code("".join(preview_lines) + "\n...", language="markdown")

    # Botão para download da transcrição
    with open(st.session_state.transcription_path, 'rb') as file:
        st.download_button(
            label="Baixar Transcrição (Markdown)",
            data=file,
            file_name=os.path.basename(st.session_state.transcription_path),
            mime="text/markdown",
            key="download_transcription"
        )

# Rodapé com informações
st.markdown("---")
st.markdown("### Como usar:")
st.markdown("""
1. Cole o URL de um vídeo do YouTube
2. Selecione o formato desejado
3. Opcionalmente, defina um nome personalizado para o arquivo
4. Clique em "Baixar"
5. Após o processamento, clique no botão para baixar o arquivo
""")

# Informações adicionais
st.markdown("---")
st.markdown("### Sobre este aplicativo:")
st.markdown("""
Este aplicativo usa a biblioteca yt-dlp para baixar vídeos do YouTube.
O uso desta ferramenta é de sua responsabilidade e deve respeitar os termos de serviço do YouTube.
""")
