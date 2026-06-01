"""공통 유틸 — ffmpeg 탐지, 시간 파싱, 영상 메타데이터(probe), 경로 헬퍼."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# 프로젝트 기본 디렉터리 (repo 루트 기준)
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"

# 흔히 쓰는 영상 확장자
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".flv", ".wmv", ".mpg", ".mpeg", ".ts"}


# --------------------------------------------------------------------------- #
# 콘솔 출력 헬퍼
# --------------------------------------------------------------------------- #
def info(msg: str) -> None:
    print(f"  {msg}")


def ok(msg: str) -> None:
    print(f"\033[92m[OK]\033[0m {msg}")


def warn(msg: str) -> None:
    print(f"\033[93m[!]\033[0m {msg}")


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"\033[91m[X]\033[0m {msg}", file=sys.stderr)
    raise SystemExit(1)


# --------------------------------------------------------------------------- #
# ffmpeg 탐지
# --------------------------------------------------------------------------- #
_FFMPEG_CACHE: str | None = None


def find_ffmpeg() -> str:
    """ffmpeg 실행 파일 경로를 반환.

    우선순위: 시스템 PATH의 ffmpeg → imageio-ffmpeg가 번들한 바이너리.
    둘 다 없으면 안내 메시지와 함께 종료.
    """
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE:
        return _FFMPEG_CACHE

    exe = shutil.which("ffmpeg")
    if exe:
        _FFMPEG_CACHE = exe
        return exe

    try:
        import imageio_ffmpeg  # type: ignore

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        _FFMPEG_CACHE = exe
        return exe
    except Exception:
        fail(
            "ffmpeg를 찾을 수 없습니다.\n"
            "    해결: 시스템에 ffmpeg를 설치하거나, `pip install imageio-ffmpeg` 를 실행하세요.\n"
            "    (requirements.txt에 포함되어 있습니다: pip install -r requirements.txt)"
        )


def run_ffmpeg(args: list[str], *, quiet: bool = False) -> None:
    """ffmpeg 명령 실행. 실패 시 종료."""
    cmd = [find_ffmpeg(), "-hide_banner"]
    cmd += ["-loglevel", "error", "-stats"] if not quiet else ["-loglevel", "error"]
    cmd += args
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        fail(f"ffmpeg 처리 실패 (exit {exc.returncode}). 위 로그를 확인하세요.")


def has_audio(path: str | os.PathLike) -> bool:
    """입력에 오디오 스트림이 있는지 ffmpeg로 확인한다.

    (imageio-ffmpeg는 ffprobe를 번들하지 않으므로 ffmpeg -i 의 stderr를 파싱)
    """
    proc = subprocess.run(
        [find_ffmpeg(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        errors="replace",
    )
    return "Audio:" in proc.stderr


# --------------------------------------------------------------------------- #
# 시간 파싱 / 포맷
# --------------------------------------------------------------------------- #
def parse_time(value: str | float | int | None) -> float | None:
    """시간 문자열을 초(float)로 변환.

    허용 형식: "90", "90.5", "1:30", "01:02:03", "1:02:03.250"
    None이면 None 반환.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if ":" in text:
            parts = [float(p) for p in text.split(":")]
            if len(parts) == 2:
                m, s = parts
                return m * 60 + s
            if len(parts) == 3:
                h, m, s = parts
                return h * 3600 + m * 60 + s
            raise ValueError
        return float(text)
    except ValueError:
        fail(f"시간 형식을 해석할 수 없습니다: {value!r} (예: 90, 1:30, 01:02:03)")
        return None  # unreachable


def format_time(seconds: float) -> str:
    """초 → HH:MM:SS.mmm 문자열."""
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


# --------------------------------------------------------------------------- #
# 영상 메타데이터 (OpenCV 사용 — ffprobe 불필요)
# --------------------------------------------------------------------------- #
@dataclass
class VideoInfo:
    path: Path
    width: int
    height: int
    fps: float
    frame_count: int
    duration: float  # 초
    codec: str
    size_bytes: int

    def summary(self) -> str:
        mb = self.size_bytes / (1024 * 1024)
        return (
            f"{self.path.name}\n"
            f"    해상도   : {self.width} x {self.height}\n"
            f"    FPS      : {self.fps:.3f}\n"
            f"    프레임 수 : {self.frame_count}\n"
            f"    길이     : {format_time(self.duration)} ({self.duration:.2f}s)\n"
            f"    코덱     : {self.codec}\n"
            f"    파일크기  : {mb:.1f} MB"
        )


def probe(path: str | os.PathLike) -> VideoInfo:
    """OpenCV로 영상 기본 정보를 읽는다."""
    import cv2  # 지연 임포트 (cv2 미설치 환경에서도 import 모듈은 동작)

    p = Path(path)
    if not p.exists():
        fail(f"파일이 없습니다: {p}")

    cap = cv2.VideoCapture(str(p))
    if not cap.isOpened():
        fail(f"영상을 열 수 없습니다 (코덱/손상 확인): {p}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
    codec = (
        "".join(chr((fourcc_int >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00 ")
        or "unknown"
    )
    cap.release()

    duration = (frame_count / fps) if fps > 0 else 0.0
    return VideoInfo(
        path=p,
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        duration=duration,
        codec=codec,
        size_bytes=p.stat().st_size,
    )


# --------------------------------------------------------------------------- #
# 경로 / 입력 헬퍼
# --------------------------------------------------------------------------- #
def resolve_input(path: str | os.PathLike) -> Path:
    """입력 경로 해석. 상대경로면 data/ → output/ 순으로도 찾아본다.

    (전처리 결과물이 output/ 에 쌓이므로, 그 파일명만 줘도 바로 후속 작업 가능.)
    """
    p = Path(path)
    if p.exists():
        return p
    for base in (DATA_DIR, OUTPUT_DIR):
        candidate = base / p
        if candidate.exists():
            return candidate
    fail(f"입력 파일을 찾을 수 없습니다: {path} (data/, output/ 안에도 없음)")
    return p  # unreachable


def ensure_output_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def resolve_output(
    out: str | os.PathLike | None,
    default_name: str,
    *,
    overwrite: bool,
) -> Path:
    """출력 경로 결정. 미지정 시 output/ 아래 default_name 사용."""
    if out is None:
        dest = OUTPUT_DIR / default_name
    else:
        dest = Path(out)
        # 디렉터리만 줬으면 default_name 붙이기
        if dest.is_dir() or str(out).endswith(("/", "\\")):
            dest = dest / default_name
    ensure_output_dir(dest)

    if dest.exists() and not overwrite:
        fail(f"출력 파일이 이미 존재합니다: {dest}\n    덮어쓰려면 -y / --overwrite 옵션을 쓰세요.")
    return dest


def suffix_name(src: Path, suffix: str, ext: str | None = None) -> str:
    """원본 이름에 접미사를 붙인 파일명 생성. 예: clip → clip_cut.mp4"""
    new_ext = ext if ext is not None else src.suffix
    return f"{src.stem}{suffix}{new_ext}"
