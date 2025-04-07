"""
Script independente para transcrever vídeos do YouTube sem usar Streamlit
"""
import os
import sys
import subprocess
import argparse
from datetime import datetime
import re


def sanitize_filename(filename):
    """Remove caracteres inválidos para nome de arquivo"""
    return re.sub(r'[\\/*?:"<>|]', "", filename)


def download_audio(url, output_dir="temp_audio"):
    """Baixa o áudio de um vídeo do YouTube usando yt-dlp diretamente via subprocess"""
    os.makedirs(output_dir, exist_ok=True)

    # Primeiro obter título para nomear arquivo
    print("Obtendo informações do vídeo...")
    info_cmd = ["yt-dlp", "--skip-download",
                "--print", "title", "--print", "tags", url]
    try:
        result = subprocess.check_output(
            info_cmd, text=True).strip().split('\n')
        title = result[0]

        # Capturar tags se disponíveis
        tags = []
        if len(result) > 1:
            tags_str = ' '.join(result[1:])
            if tags_str.strip():
                tags = [tag.strip() for tag in tags_str.split(',')]

        safe_title = sanitize_filename(title)
        if not safe_title:
            safe_title = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    except:
        safe_title = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        tags = []

    output_template = os.path.join(output_dir, safe_title)

    # Baixar apenas o áudio
    print(f"Baixando áudio de: {url}")
    download_cmd = [
        "yt-dlp",
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "-o", output_template + ".%(ext)s",
        "--no-check-certificate",
        url
    ]

    try:
        subprocess.run(download_cmd, check=True)

        # Encontrar arquivo baixado
        for ext in ['.m4a', '.mp3', '.ogg', '.wav', '.webm']:
            if os.path.exists(output_template + ext):
                print(f"Áudio baixado: {output_template + ext}")
                return output_template + ext, safe_title, tags

        print("Erro: Arquivo baixado não encontrado")
        return None, safe_title, tags
    except Exception as e:
        print(f"Erro ao baixar áudio: {str(e)}")
        return None, safe_title, tags


def get_video_metadata(url):
    """Obtém metadados completos do vídeo"""
    print("Obtendo metadados do vídeo...")
    try:
        # Usar yt-dlp para obter informações completas do vídeo em formato JSON
        cmd = ["yt-dlp", "-J", url]
        result = subprocess.check_output(cmd, text=True)

        import json
        info = json.loads(result)

        # Extrair tags no formato desejado
        tags = []
        if 'tags' in info:
            tags = info['tags']

        # Obter categorias
        categories = []
        if 'categories' in info:
            categories = info['categories']

        # Adicionar categorias às tags
        for category in categories:
            if category and category not in tags:
                tags.append(category)

        # Formatar tags no formato #tag1, #tag2, #tag3
        formatted_tags = []
        for tag in tags:
            if tag:
                # Substituir espaços por underscore
                tag_clean = tag.strip().replace(' ', '_')
                # Remover caracteres problemáticos
                tag_clean = re.sub(r'[^\w_]', '', tag_clean)
                if tag_clean:
                    formatted_tag = f"#{tag_clean}"
                    if formatted_tag not in formatted_tags:
                        formatted_tags.append(formatted_tag)

        # Juntar as tags no formato pedido
        tags_string = ", ".join(formatted_tags)

        return {
            'title': info.get('title', 'Sem título'),
            'uploader': info.get('uploader', 'Desconhecido'),
            'upload_date': info.get('upload_date', ''),
            'description': info.get('description', ''),
            'tags': formatted_tags,
            'tags_string': tags_string,
            'duration': info.get('duration', 0),
            'view_count': info.get('view_count', 0),
            'like_count': info.get('like_count', 0)
        }
    except Exception as e:
        print(f"Erro ao obter metadados: {str(e)}")
        return {
            'title': 'Desconhecido',
            'tags': [],
            'tags_string': ''
        }


def transcribe_with_whisper(audio_file, output_dir="transcriptions", language="pt", model_size="small", metadata=None):
    """Transcreve áudio usando whisper-cli diretamente via subprocess e adiciona metadados"""
    os.makedirs(output_dir, exist_ok=True)

    # Nome base do arquivo sem extensão
    base_name = os.path.splitext(os.path.basename(audio_file))[0]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_base = os.path.join(output_dir, f"{base_name}_{timestamp}")

    # Arquivo de saída final (vamos usar .md para incluir metadados)
    final_output = f"{output_base}.md"

    print(f"Transcrevendo áudio usando modelo whisper {model_size}...")
    print(f"Isso pode levar vários minutos dependendo do tamanho do arquivo.")

    # Comando para usar whisper-cli (pacote openai-whisper)
    whisper_cmd = [
        "whisper",
        audio_file,
        "--model", model_size,
        "--language", language,
        "--output_dir", output_dir,
        "--output_format", "txt"
    ]

    try:
        # Executar whisper como subprocess
        subprocess.run(whisper_cmd, check=True)

        # Whisper gera arquivos com nomes diferentes, procurar o arquivo .txt gerado mais recente
        txt_files = [f for f in os.listdir(output_dir) if f.endswith('.txt') and
                     os.path.getmtime(os.path.join(output_dir, f)) >
                     os.path.getmtime(audio_file)]

        if txt_files:
            # Ordenar por data de modificação, mais recente primeiro
            txt_files.sort(key=lambda x: os.path.getmtime(
                os.path.join(output_dir, x)), reverse=True)

            # Ler a transcrição
            with open(os.path.join(output_dir, txt_files[0]), 'r', encoding='utf-8') as f:
                transcription_text = f.read()

            # Criar arquivo markdown com metadados
            with open(final_output, 'w', encoding='utf-8') as f:
                # Adicionar cabeçalho com metadados
                f.write("---\n")
                f.write(f"title: {metadata.get('title', 'Sem título')}\n")
                f.write(
                    f"date: {metadata.get('upload_date', datetime.now().strftime('%Y-%m-%d'))}\n")

                # Adicionar tags no formato desejado
                f.write(f"tags: {metadata.get('tags_string', '')}\n")

                f.write(f"views: {metadata.get('view_count', 0)}\n")
                f.write(f"likes: {metadata.get('like_count', 0)}\n")
                f.write("---\n\n")

                # Adicionar título
                f.write(f"# {metadata.get('title', 'Sem título')}\n\n")

                # Adicionar transcrição
                f.write("## Transcrição\n\n")
                f.write(transcription_text)

                # Adicionar tags de novo como hashtags
                f.write("\n\n## Tags\n\n")
                f.write(metadata.get('tags_string', ''))

                # Adicionar descrição se disponível
                if metadata.get('description'):
                    f.write("\n\n## Descrição Original\n\n")
                    f.write(metadata.get('description', ''))

            # Remover o arquivo txt original se desejar
            try:
                os.remove(os.path.join(output_dir, txt_files[0]))
            except:
                pass

            print(f"Transcrição concluída e salva em: {final_output}")
            return final_output
        else:
            print("Erro: Arquivo de transcrição não encontrado")
            return None
    except Exception as e:
        print(f"Erro na transcrição: {str(e)}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Baixa e transcreve vídeos do YouTube sem usar Streamlit")
    parser.add_argument("url", help="URL do vídeo do YouTube")
    parser.add_argument("--language", "-l", default="pt",
                        help="Código do idioma (pt, en, es, etc)")
    parser.add_argument("--model", "-m", default="small",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Tamanho do modelo de transcrição")

    args = parser.parse_args()

    # Obter metadados completos do vídeo
    metadata = get_video_metadata(args.url)
    print(f"Título: {metadata['title']}")
    print(f"Tags: {metadata['tags_string']}")

    # Baixar áudio
    audio_file, title, _ = download_audio(args.url)
    if not audio_file:
        return 1

    # Transcrever
    transcription_file = transcribe_with_whisper(
        audio_file,
        language=args.language,
        model_size=args.model,
        metadata=metadata
    )

    if not transcription_file:
        return 1

    # Limpar arquivo temporário de áudio
    print("Removendo arquivo de áudio temporário...")
    try:
        os.remove(audio_file)
    except:
        print("Aviso: Não foi possível remover o arquivo de áudio temporário.")

    print("\nProcesso concluído com sucesso!")
    print(f"Transcrição disponível em: {transcription_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
