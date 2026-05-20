#!/usr/bin/env python3
import html
import os
import json
import re
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path




CHUNK_DURATION_SEC = 300
WINDOW_DURATION_SEC = 10.0
WINDOW_OVERLAP_SEC = 2.0
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

GRPC_SERVER = "grpc.nvcf.nvidia.com:443"
FUNCTION_ID = "b702f636-f60c-4a3d-a6f4-f3568c13bd7d"


@dataclass(frozen=True)
class SubtitleStream:
    subtitle_position: int
    global_index: int
    codec_name: str
    language: str
    title: str


SUBTITLE_LANGUAGE_TAGS = {
    "zh": {"zh", "zho", "chi", "cmn"},
    "en": {"en", "eng"},
    "ja": {"ja", "jpn"},
    "ko": {"ko", "kor"},
    "fr": {"fr", "fra", "fre"},
    "de": {"de", "deu", "ger"},
    "es": {"es", "spa"},
}

SUBTITLE_LANGUAGE_KEYWORDS = {
    "zh": {"中文", "汉语", "普通话", "简体", "繁体", "中文字幕"},
    "en": {"english", "subtitle", "captions", "caption"},
    "ja": {"japanese", "日本語"},
    "ko": {"korean", "한국어"},
    "fr": {"french", "français", "francais"},
    "de": {"german", "deutsch"},
    "es": {"spanish", "español", "espanol"},
}

TEXT_SUBTITLE_CODECS = {
    "subrip",
    "srt",
    "webvtt",
    "ass",
    "ssa",
    "mov_text",
    "text",
    "ttml",
    "dfxp",
}


def _is_text_subtitle_codec(codec_name: str) -> bool:
    return _safe_lower(codec_name) in TEXT_SUBTITLE_CODECS


def _get_base_language(language_code: str) -> str | None:
    code = (language_code or "").strip().lower()
    if not code or code == "multi":
        return None
    return code.split("-", 1)[0]


def _safe_lower(value: str) -> str:
    return (value or "").strip().lower()


def list_subtitle_streams(video_path: Path) -> list[SubtitleStream]:
    """返回字幕流列表。

    - subtitle_position: 字幕流在字幕集合中的顺序（0,1,2...）
    - global_index: ffprobe stream index（用于 ffmpeg -map 0:<index>）
    """

    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-select_streams", "s",
            "-show_entries", "stream=index,codec_name:stream_tags=language,title",
            "-of", "json",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams")
    if not isinstance(streams, list):
        return []

    parsed: list[SubtitleStream] = []
    for subtitle_position, stream in enumerate(streams):
        if not isinstance(stream, dict):
            continue
        if "index" not in stream:
            continue
        tags = stream.get("tags")
        if not isinstance(tags, dict):
            tags = {}

        parsed.append(
            SubtitleStream(
                subtitle_position=subtitle_position,
                global_index=int(stream["index"]),
                codec_name=str(stream.get("codec_name", "")),
                language=str(tags.get("language", "")),
                title=str(tags.get("title", "")),
            )
        )
    return parsed


def choose_subtitle_stream(streams: list[SubtitleStream], language_code: str) -> SubtitleStream | None:
    if not streams:
        return None

    streams = [stream for stream in streams if _is_text_subtitle_codec(stream.codec_name)]
    if not streams:
        return None

    base_language = _get_base_language(language_code)
    if base_language is None:
        return streams[0]

    language_tags = SUBTITLE_LANGUAGE_TAGS.get(base_language, {base_language})
    keyword_set = SUBTITLE_LANGUAGE_KEYWORDS.get(base_language, set())

    def score(stream: SubtitleStream) -> tuple[int, int]:
        points = 0

        lang = _safe_lower(stream.language)
        if lang in language_tags:
            points += 100
        elif lang.startswith(base_language):
            points += 60

        title_lower = _safe_lower(stream.title)
        if title_lower:
            for kw in keyword_set:
                if kw.lower() in title_lower:
                    points += 20
                    break

        if _is_text_subtitle_codec(stream.codec_name):
            points += 5

        # 越靠前越优先
        return points, -stream.subtitle_position

    return max(streams, key=score)


def extract_srt(video_path: Path, output_srt_path: Path, stream: SubtitleStream) -> None:
    output_srt_path.parent.mkdir(exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-i", str(video_path),
            "-map", f"0:{stream.global_index}",
            "-c:s", "srt",
            str(output_srt_path),
            "-y",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _parse_srt_timestamp(value: str) -> float:
    # 00:00:01,234
    hh, mm, rest = value.split(":", 2)
    ss, ms = rest.split(",", 1)
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def parse_srt_to_segments(srt_text: str) -> list[dict]:
    # 极简 SRT 解析：按空行分块
    blocks = re.split(r"\n\s*\n", srt_text.strip())
    segments: list[dict] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue

        # 第1行可能是序号
        time_line_index = 0
        if re.fullmatch(r"\d+", lines[0]):
            time_line_index = 1
        if time_line_index >= len(lines):
            continue

        time_line = lines[time_line_index]
        match = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", time_line)
        if not match:
            continue

        start = _parse_srt_timestamp(match.group(1))
        end = _parse_srt_timestamp(match.group(2))
        text_lines = lines[time_line_index + 1:]
        if not text_lines:
            continue

        text = " ".join(text_lines)
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("\\N", " ").replace("\\n", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue

        segments.append({
            "start": start,
            "end": end,
            "text": text,
        })
    return segments


def _read_key_file(key_path: Path) -> str | None:
    if not key_path.exists():
        return None
    content = key_path.read_text(encoding="utf-8").strip()
    if not content:
        return None
    # 支持文件里写成 "NIM_API_KEY=..." 或直接写 key
    if "=" in content:
        key, value = content.split("=", 1)
        if key.strip() in {"NIM_API_KEY", "NVIDIA_API_KEY"}:
            content = value.strip()
    return content or None


def get_nvidia_api_key() -> str:
    # 优先读取 opencode keys 目录
    key_path = Path.home() / ".config" / "opencode" / "keys" / "nvidia.key"
    file_key = _read_key_file(key_path)
    if file_key:
        return file_key

    # 其次使用环境变量（支持用户手动导出）
    env_key = os.environ.get("NIM_API_KEY") or os.environ.get("NVIDIA_API_KEY")
    if env_key:
        return env_key

    raise RuntimeError(
        "Missing NVIDIA API key. Provide one of:\n"
        "- ~/.config/opencode/keys/nvidia.key (recommended)\n"
        "- NIM_API_KEY / NVIDIA_API_KEY environment variable\n"
        "- ~/.transcribe_video.env containing NIM_API_KEY=...\n"
    )


def get_audio_info(wav_path: Path) -> dict:
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration = frames / float(rate)
    size = wav_path.stat().st_size
    return {"duration": duration, "size": size}


def build_chunk_ranges(duration: float, chunk_duration_sec: int) -> list[tuple[float, float]]:
    chunk_ranges = []
    start = 0.0
    while start < duration:
        end = min(start + chunk_duration_sec, duration)
        chunk_ranges.append((start, end))
        start = end
    return chunk_ranges


def build_request_ranges(duration: float, window_sec: float = WINDOW_DURATION_SEC,
                         overlap_sec: float = WINDOW_OVERLAP_SEC) -> list[tuple[float, float]]:
    request_ranges = []
    if duration <= 0:
        return request_ranges

    step = window_sec - overlap_sec
    if step <= 0:
        raise ValueError("overlap_sec must be smaller than window_sec")

    start = 0.0
    while start < duration:
        end = min(start + window_sec, duration)
        request_ranges.append((start, end))
        if end >= duration:
            break
        start += step
    return request_ranges


def _format_duration(seconds: float) -> str:
    if float(seconds).is_integer():
        return str(int(seconds))
    return str(seconds)


def split_wav(wav_path: Path, tmp_dir: Path) -> list[Path]:
    info = get_audio_info(wav_path)
    chunk_ranges = build_chunk_ranges(info["duration"], CHUNK_DURATION_SEC)
    chunk_paths = []
    for idx, (start, end) in enumerate(chunk_ranges):
        out = tmp_dir / f"chunk_{idx:03d}.wav"
        chunk_duration = _format_duration(end - start)
        result = subprocess.run(
            [
                "ffmpeg", "-i", str(wav_path),
                "-ss", str(start), "-t", chunk_duration,
                "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(out), "-y",
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0 or not out.exists() or out.stat().st_size <= 78:
            raise RuntimeError(f"Failed to create valid chunk: {out}")
        chunk_paths.append(out)
    return chunk_paths


def transcribe_chunk(server: str, metadata: list, chunk_path: Path, language: str) -> dict:
    import grpc
    import riva.client

    auth = riva.client.Auth(
        use_ssl=True,
        uri=server,
        metadata_args=metadata,
    )
    asr_service = riva.client.ASRService(auth)

    config = riva.client.RecognitionConfig(
        language_code=language,
        max_alternatives=1,
        enable_word_time_offsets=True,
        enable_automatic_punctuation=True,
        verbatim_transcripts=True,
    )

    with chunk_path.open("rb") as f:
        audio_bytes = f.read()

    try:
        response = asr_service.offline_recognize(audio_bytes, config)
    except grpc.RpcError as e:
        print(f"gRPC error: {e.details()}", file=sys.stderr)
        return {"results": []}

    if hasattr(response, "result") and not hasattr(response, "results"):
        response = response.result()

    response_results = getattr(response, "results", None)
    if response_results is None:
        return {"results": []}

    return {"results": list(response_results)}


def _normalize_text(text: str) -> str:
    return "".join(text.split())


def _raw_index_after_normalized_chars(text: str, normalized_count: int) -> int:
    if normalized_count <= 0:
        return 0

    seen = 0
    for index, character in enumerate(text):
        if character.isspace():
            continue
        seen += 1
        if seen >= normalized_count:
            return index + 1
    return len(text)


def trim_overlapping_prefix(previous_text: str, current_text: str, max_overlap: int = 80) -> str:
    previous_normalized = _normalize_text(previous_text)
    current_normalized = _normalize_text(current_text)
    if not previous_normalized or not current_normalized:
        return current_text

    limit = min(max_overlap, len(previous_normalized), len(current_normalized))
    for overlap in range(limit, 0, -1):
        if previous_normalized.endswith(current_normalized[:overlap]):
            cut_index = _raw_index_after_normalized_chars(current_text, overlap)
            return current_text[cut_index:].lstrip()
    return current_text


def build_segments_from_results(results: list) -> list[dict]:
    segments = []
    previous_end = 0.0

    for result in results:
        if not result.alternatives:
            continue

        alternative = result.alternatives[0]
        transcript = alternative.transcript.strip()
        if not transcript:
            continue

        end_time = float(getattr(result, "audio_processed", previous_end))
        if end_time < previous_end:
            end_time = previous_end

        segments.append({
            "start": previous_end,
            "end": end_time,
            "text": transcript,
        })
        previous_end = end_time

    return segments


def transcribe_request(server: str, metadata: list, audio_path: Path, language: str,
                       request_start: float, request_end: float) -> dict:
    request_path = audio_path.parent / f".request_{int(request_start * 1000):06d}_{int(request_end * 1000):06d}.wav"
    try:
        subprocess.run(
            [
                "ffmpeg", "-i", str(audio_path),
                "-ss", str(request_start), "-t", _format_duration(request_end - request_start),
                "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(request_path), "-y",
            ],
            check=True, capture_output=True,
        )
        return transcribe_chunk(server, metadata, request_path, language)
    finally:
        if request_path.exists():
            request_path.unlink()


def transcribe_with_nim(
    video_path: Path,
    language: str = "zh-CN",
    progress_callback=None,
    resume_from_sec: float = 0.0,
    initial_segments: list[dict] | None = None,
) -> dict:
    from dotenv import load_dotenv
    import subprocess

    skill_dir = Path(__file__).resolve().parents[1]
    env_path = skill_dir / ".env"
    if not env_path.exists():
        env_path = Path.home() / ".transcribe_video.env"
    load_dotenv(env_path)

    api_key = get_nvidia_api_key()

    metadata = [
        ("function-id", FUNCTION_ID),
        ("authorization", f"Bearer {api_key}"),
    ]

    audio_path = video_path.with_suffix(".wav")
    audio_path_preexisted = audio_path.exists()

    try:
        if not audio_path.exists():
            print(f"Extracting audio from {video_path}...")
            subprocess.run(
                [
                    "ffmpeg", "-i", str(video_path),
                     "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                     str(audio_path), "-y",
                 ],
                 check=True, capture_output=True,
             )

        info = get_audio_info(audio_path)
        print(f"Audio: {info['duration']:.1f}s, {info['size'] / 1024 / 1024:.1f} MB")

        all_segments: list[dict] = []
        if initial_segments:
            all_segments = list(initial_segments)

        request_ranges = build_request_ranges(info["duration"])

        previous_text = ""
        if all_segments:
            # 取末尾多段作为上下文，避免最后一段过短导致接缝不稳
            tail_text = " ".join(str(seg.get("text", "")).strip() for seg in all_segments[-5:])
            previous_text = tail_text.strip()

        if resume_from_sec > 0.0:
            # 对齐到窗口起点网格，避免使用 segment end 推断时产生跳窗/重复。
            step = max(0.1, WINDOW_DURATION_SEC - WINDOW_OVERLAP_SEC)
            epsilon = 1e-3
            aligned = (int((float(resume_from_sec) + epsilon) // step) * step)
            request_ranges = [
                (start, end)
                for (start, end) in request_ranges
                if start + epsilon >= aligned
            ]

        if not request_ranges:
            return {"segments": []}

        total_windows = len(request_ranges)
        print(f"Transcribing {total_windows} fixed windows")
        for i, (request_start, request_end) in enumerate(request_ranges):
            print(f"Transcribing window {i + 1}/{total_windows}: {request_start:.1f}-{request_end:.1f}s")
            result = transcribe_request(
                GRPC_SERVER,
                metadata,
                audio_path,
                language,
                request_start,
                request_end,
            )
            request_segments = build_segments_from_results(result["results"])
            current_text = " ".join(seg["text"] for seg in request_segments).strip()
            if not current_text:
                continue

            current_text = trim_overlapping_prefix(previous_text, current_text)
            if not current_text:
                continue

            all_segments.append({
                "start": request_start,
                "end": request_end,
                "text": current_text,
            })
            previous_text = current_text

            if progress_callback is not None:
                # 兼容旧签名：progress_callback(segments, window_index, total_windows)
                # 新签名：progress_callback(segments, window_index, total_windows, window_start, window_end)
                try:
                    progress_callback(list(all_segments), i + 1, total_windows, request_start, request_end)
                except TypeError:
                    progress_callback(list(all_segments), i + 1, total_windows)

        return {"segments": all_segments}

    finally:
        if not audio_path_preexisted and audio_path.exists():
            audio_path.unlink()



def _build_txt_lines(segments: list[dict]) -> list[str]:
    lines: list[str] = []
    for seg in segments:
        ts = f"{int(seg['start'] // 60):02d}:{int(seg['start'] % 60):02d}"
        lines.append(f"{ts} {str(seg['text']).strip()}")
    return lines


def _atomic_write_text(path: Path, content: str) -> None:
    # 使用“追加 .tmp”的方式，避免多重后缀（如 .json.partial）时 tmp 命名冲突。
    tmp_path = path.with_name(path.name + ".tmp")
    # best-effort 清理旧的 tmp，避免堆积
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except OSError:
        pass

    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def _write_transcript_outputs(
    output_txt_path: Path,
    output_json_path: Path,
    payload: dict,
    segments: list[dict],
) -> int:
    lines = _build_txt_lines(segments)
    _atomic_write_text(output_txt_path, "\n".join(lines))
    _atomic_write_text(output_json_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return len(lines)


def _load_partial_payload(partial_json_path: Path) -> dict | None:
    try:
        data = json.loads(partial_json_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    return data


def _extract_segments_from_partial_payload(data: dict) -> list[dict]:
    raw_segments = data.get("segments")
    if not isinstance(raw_segments, list):
        return []
    segments: list[dict] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        if "text" not in item:
            continue
        segments.append({
            "start": float(item.get("start", 0.0)),
            "end": float(item.get("end", float(item.get("start", 0.0)))),
            "text": str(item.get("text", "")).strip(),
        })
    return [seg for seg in segments if seg["text"]]


def _get_partial_resume_from_payload(data: dict) -> float | None:
    # 精准续跑：如果 partial 里写了 last_window_start，则用它作为“已完成的最后窗口起点”。
    last_window_start = data.get("last_window_start")
    if isinstance(last_window_start, (int, float)):
        step = max(0.1, WINDOW_DURATION_SEC - WINDOW_OVERLAP_SEC)
        return float(last_window_start) + step
    return None


def transcribe_to_files(video_path: Path, language: str = "zh-CN") -> dict:
    print(f"Transcribing: {video_path}")
    print(f"Language: {language}")

    output_dir = video_path.parent / video_path.stem
    output_dir.mkdir(exist_ok=True)

    segments: list[dict]
    used_source = ""

    try:
        subtitle_streams = list_subtitle_streams(video_path)
    except Exception:
        subtitle_streams = []

    if subtitle_streams:
        chosen = choose_subtitle_stream(subtitle_streams, language)
        if chosen is not None:
            srt_path = output_dir / f"{video_path.stem}.srt"
            try:
                extract_srt(video_path, srt_path, chosen)
                srt_text = srt_path.read_text(encoding="utf-8", errors="ignore")
                segments = parse_srt_to_segments(srt_text)
                used_source = f"subtitles:{chosen.codec_name or 'unknown'}"
            except Exception:
                segments = []
                used_source = ""
        else:
            segments = []
    else:
        segments = []

    output_txt_path = output_dir / f"{video_path.stem}.txt"
    output_json_path = output_dir / f"{video_path.stem}.json"
    output_md_path = output_dir / f"{video_path.stem}.md"

    partial_txt_path = output_dir / f"{video_path.stem}.txt.partial"
    partial_json_path = output_dir / f"{video_path.stem}.json.partial"

    def build_payload(current_segments: list[dict], in_progress: bool, window_index: int | None = None,
                      total_windows: int | None = None) -> dict:
        payload = {
            "source": str(video_path),
            "output_dir": str(output_dir),
            "language": language,
            "source_type": used_source,
            "window_duration_sec": WINDOW_DURATION_SEC,
            "window_overlap_sec": WINDOW_OVERLAP_SEC,
            "segments": current_segments,
        }
        if in_progress:
            payload["in_progress"] = True
        if window_index is not None:
            payload["window_index"] = window_index
        if total_windows is not None:
            payload["total_windows"] = total_windows
        return payload

    lines_count = 0

    if not segments:
        used_source = "asr:nim"

        resumed_segments: list[dict] = []
        resume_from_sec = 0.0
        if partial_json_path.exists():
            partial_payload = _load_partial_payload(partial_json_path)
            if partial_payload:
                resumed_segments = _extract_segments_from_partial_payload(partial_payload)
                precise_resume = _get_partial_resume_from_payload(partial_payload)
                if precise_resume is not None:
                    resume_from_sec = precise_resume
                elif resumed_segments:
                    last_end = float(resumed_segments[-1].get("end", 0.0))
                    # 兜底：从上次最后 end 回退 overlap 继续（兼容旧 partial）
                    resume_from_sec = max(0.0, last_end - WINDOW_OVERLAP_SEC)

        # 先写一个空的 partial，保证即使被外部超时杀掉也不会出现“目录空”。
        if not partial_json_path.exists():
            empty_payload = build_payload([], in_progress=True, window_index=0, total_windows=0)
            _write_transcript_outputs(partial_txt_path, partial_json_path, empty_payload, [])

        def progress_callback(current_segments: list[dict], window_index: int, total_windows: int, window_start: float | None = None,
                              window_end: float | None = None) -> None:
            payload = build_payload(current_segments, in_progress=True, window_index=window_index, total_windows=total_windows)
            if window_start is not None:
                payload["last_window_start"] = float(window_start)
            if window_end is not None:
                payload["last_window_end"] = float(window_end)
            _write_transcript_outputs(partial_txt_path, partial_json_path, payload, current_segments)

        result = transcribe_with_nim(
            video_path,
            language,
            progress_callback=progress_callback,
            resume_from_sec=resume_from_sec,
            initial_segments=resumed_segments,
        )
        segments = list(result.get("segments", []))

        final_payload = build_payload(segments, in_progress=False)
        lines_count = _write_transcript_outputs(output_txt_path, output_json_path, final_payload, segments)

        # 清理 partial
        if partial_txt_path.exists():
            partial_txt_path.unlink()
        if partial_json_path.exists():
            partial_json_path.unlink()
    else:
        # 字幕路径：一次性写出最终产物
        final_payload = build_payload(segments, in_progress=False)
        lines_count = _write_transcript_outputs(output_txt_path, output_json_path, final_payload, segments)

    return {
        "txt": output_txt_path,
        "json": output_json_path,
        "md": output_md_path,
        "lines": lines_count,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: transcribe.py <video_path> [language_code]")
        sys.exit(1)

    video_path = Path(sys.argv[1]).resolve()
    language = sys.argv[2] if len(sys.argv) > 2 else "zh-CN"

    try:
        outputs = transcribe_to_files(video_path, language)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Saved to {outputs['txt']} ({outputs['lines']} lines)")
    print(f"Saved json to {outputs['json']}")



if __name__ == "__main__":
    main()
