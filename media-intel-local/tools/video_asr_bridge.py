"""
Download short videos and transcribe speech with faster-whisper.

This file is executed by an external Python environment. The parent pipeline
stays Python 3.8 compatible and receives JSON only.
"""
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List

import requests
from faster_whisper import WhisperModel


def _read_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("ASR bridge payload must be a JSON object")
    return payload


def _path(value: Any) -> Path:
    return Path(str(value)).expanduser().resolve()


def _safe_name(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text) or "video"


def _download_video(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Referer": "https://www.douyin.com/",
    }
    session = requests.Session()
    session.trust_env = False
    with session.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True) as response:
        response.raise_for_status()
        with path.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    file_obj.write(chunk)


def _load_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _transcribe(model: WhisperModel, video_path: Path, language: str) -> Dict[str, Any]:
    segments_iter, info = model.transcribe(
        str(video_path),
        language=language or None,
        vad_filter=True,
        beam_size=5,
    )
    segments = []
    texts = []
    for segment in segments_iter:
        text = str(segment.text or "").strip()
        if text:
            texts.append(text)
        segments.append(
            {
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "text": text,
            }
        )
    return {
        "asr_text": " ".join(texts).strip(),
        "asr_segments": segments,
        "asr_language": getattr(info, "language", language or ""),
        "asr_language_probability": float(getattr(info, "language_probability", 0.0) or 0.0),
    }


def _run(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    runtime_dir = _path(payload.get("runtime_dir") or ".runtime/douyin/asr")
    videos_dir = runtime_dir / "videos"
    cache_dir = runtime_dir / "cache"
    model_dir = runtime_dir / "models"
    model_name = str(payload.get("model") or "small").strip()
    language = str(payload.get("language") or "zh").strip()
    device = str(payload.get("device") or "cpu").strip()
    compute_type = str(payload.get("compute_type") or "int8").strip()
    items = payload.get("items") or []
    if not isinstance(items, list):
        raise ValueError("ASR bridge items must be a list")

    model = WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
        download_root=str(model_dir),
    )

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        aweme_id = _safe_name(item.get("aweme_id"))
        video_url = str(item.get("video_url") or "").strip()
        cache_path = cache_dir / "{}.json".format(aweme_id)
        cached = _load_cache(cache_path)
        if cached.get("asr_text"):
            results.append(cached)
            continue

        result = {
            "aweme_id": aweme_id,
            "asr_text": "",
            "asr_segments": [],
            "asr_language": "",
            "asr_error": "",
        }
        try:
            if not video_url:
                raise ValueError("missing video_url")
            video_path = videos_dir / "{}.mp4".format(aweme_id)
            _download_video(video_url, video_path)
            result.update(_transcribe(model, video_path, language))
        except Exception as exc:
            result["asr_error"] = str(exc)
        if result.get("asr_text"):
            _write_cache(cache_path, result)
        results.append(result)
    return results


def main() -> None:
    original_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        output = _run(_read_payload())
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        output = {"error": str(exc)}
    finally:
        sys.stdout = original_stdout
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
