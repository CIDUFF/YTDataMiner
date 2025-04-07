"""
Script alternativo para transcrição sem usar Streamlit diretamente.
Evita problemas de conflito com PyTorch e bibliotecas de ML.
"""
import os
import sys
import argparse
import yaml
from datetime import datetime



def download_audio(url, output_dir):
    """Baixa o áudio de um vídeo do YouTube"""
    import yt_dlp

    os.makedirs(output_dir, exist_ok=True)

    # Primeiro obter metadados
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        title = info.get('title', 'video')
        # Sanitizar título
        safe_title = "".join(c for c in title if c.isalnum()
                             or c in " ._-").strip()
        if not safe_title:
            safe_title = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Baixar áudio
    output_template = os.path.join(output_dir, safe_title)

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio',
        'outtmpl': output_template + '.%(ext)s',
        'quiet': True,
        'no_warnings': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # Encontrar arquivo baixado
    for ext in ['.m4a', '.mp3', '.ogg', '.wav', '.webm']:
        if os.path.exists(output_template + ext):
            return output_template + ext, info

    return None, info


def transcribe(audio_file, language="pt", model="small"):
    """Transcreve um arquivo de áudio usando faster-whisper"""
    from faster_whisper import WhisperModel

    # Verificar disponibilidade de GPU
    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        print(
            f"Usando dispositivo: {device} com tipo de computação: {compute_type}")
    except:
        device = "cpu"
        compute_type = "int8"
        print("PyTorch não disponível, usando CPU com int8")

    # Carregar modelo
    model = WhisperModel(model, device=device, compute_type=compute_type)

    # Transcrever
    print(f"Transcrevendo {audio_file} usando modelo {model} em {language}")
    segments, info = model.transcribe(
        audio_file,
        language=language if language != "auto" else None,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True
    )

    # Formatar resultado
    result = {
        "segments": []
    }

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

    return result


def format_markdown(transcription, metadata):
    """Formata a transcrição e metadados em markdown"""
    # Extrair segmentos
    segments = transcription.get('segments', [])

    # Preparar cabeçalho YAML
    yaml_header = {
        'title': metadata.get('title', 'Sem título'),
        'author': metadata.get('uploader', 'Desconhecido'),
        'date': metadata.get('upload_date', ''),
        'url': metadata.get('webpage_url', ''),
        'video_id': metadata.get('id', ''),
        'duration': metadata.get('duration', 0),
        'tags': metadata.get('tags', []),
        'categories': metadata.get('categories', []),
        'statistics': {
            'views': metadata.get('view_count', 0),
            'likes': metadata.get('like_count', 0),
            'comments': metadata.get('comment_count', 0)
        }
    }

    # Converter para YAML
    yaml_string = yaml.dump(yaml_header, allow_unicode=True, sort_keys=False)

    # Montar markdown
    markdown_content = f"""---
{yaml_string}---

# {metadata.get('title', 'Sem título')}

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

    # Adicionar descrição original
    if metadata.get('description'):
        markdown_content += f"\n## Descrição Original\n\n{metadata['description']}\n"

    return markdown_content


def save_transcription(markdown_content, title):
    """Salva a transcrição em um arquivo markdown"""
    # Criar diretório para transcrições
    transcriptions_dir = os.path.join(os.getcwd(), "transcriptions")
    os.makedirs(transcriptions_dir, exist_ok=True)

    # Criar nome de arquivo seguro
    safe_title = "".join(c for c in title if c.isalnum()
                         or c in " ._-").strip()
    if not safe_title or len(safe_title) < 3:
        safe_title = f"transcription_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Adicionar timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = os.path.join(
        transcriptions_dir, f"{safe_title}_{timestamp}.md")

    # Salvar arquivo
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(markdown_content)

    return file_path


def main():
    parser = argparse.ArgumentParser(
        description="Transcreve vídeos do YouTube")
    parser.add_argument("url", help="URL do vídeo do YouTube")
    parser.add_argument("--language", "-l", default="pt",
                        help="Código do idioma (pt, en, es, etc)")
    parser.add_argument("--model", "-m", default="small", choices=["tiny", "base", "small", "medium", "large"],
                        help="Tamanho do modelo de transcrição")

    args = parser.parse_args()


    # Baixar áudio
    print(f"Baixando áudio de {args.url}...")
    audio_file, video_info = download_audio(args.url, "temp_audio")

    if not audio_file:
        print("Erro ao baixar áudio.")
        return 1

    print(f"Áudio baixado: {audio_file}")

    # Transcrever
    print("Iniciando transcrição...")
    transcription = transcribe(audio_file, args.language, args.model)

    if not transcription:
        print("Erro na transcrição.")
        return 1

    # Formatar markdown
    print("Formatando transcrição...")
    markdown_content = format_markdown(transcription, video_info)

    # Salvar
    output_file = save_transcription(
        markdown_content, video_info.get('title', 'video'))
    print(f"Transcrição salva em: {output_file}")

    # Limpar arquivo temporário
    try:
        os.remove(audio_file)
        print("Arquivo de áudio temporário removido.")
    except:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
