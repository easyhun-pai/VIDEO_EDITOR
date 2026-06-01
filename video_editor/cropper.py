"""GUI 기반 영상 크롭 — OpenCV로 프레임 위에 영역을 드래그 선택한 뒤 ffmpeg로 크롭."""

from __future__ import annotations

from pathlib import Path

from . import core
from .core import (
    format_time,
    info,
    ok,
    parse_time,
    probe,
    resolve_input,
    resolve_output,
    run_ffmpeg,
    suffix_name,
    warn,
)

MAX_DISPLAY = 1280  # 미리보기 창 최대 변(픽셀). 4K 등 큰 영상도 화면에 맞춰 축소.


def _grab_frame(path: Path, at_seconds: float):
    """지정 시각의 한 프레임을 읽어온다."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        core.fail(f"영상을 열 수 없습니다: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_idx = max(0, int(at_seconds * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret:
        # 끝부분 요청 시 마지막 유효 프레임으로 폴백
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
    cap.release()
    if not ret:
        core.fail("미리보기 프레임을 읽지 못했습니다.")
    return frame


def select_roi(frame) -> tuple[int, int, int, int] | None:
    """프레임 위에서 사각 영역을 드래그 선택. (x, y, w, h) 원본 좌표 반환.

    조작: 마우스로 드래그 → ENTER/SPACE 확정, C 취소.
    yuv420p 호환을 위해 폭/높이를 짝수로 맞춘다.
    """
    import cv2

    h, w = frame.shape[:2]
    scale = min(1.0, MAX_DISPLAY / max(h, w))
    disp = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1.0 else frame.copy()

    win = "Crop - drag a box | ENTER/SPACE=confirm  C=cancel"
    print("\n  [크롭 GUI] 마우스로 영역을 드래그한 뒤 ENTER 또는 SPACE 로 확정하세요. (취소: C)\n")
    x, y, bw, bh = cv2.selectROI(win, disp, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()
    for _ in range(4):  # destroyAllWindows 후 창이 남는 OS 대응
        cv2.waitKey(1)

    if bw == 0 or bh == 0:
        return None

    inv = 1.0 / scale
    x, y, bw, bh = int(x * inv), int(y * inv), int(bw * inv), int(bh * inv)
    # 경계 클램프
    x = max(0, min(x, w - 2))
    y = max(0, min(y, h - 2))
    bw = min(bw, w - x)
    bh = min(bh, h - y)
    # 짝수 보정
    bw -= bw % 2
    bh -= bh % 2
    if bw < 2 or bh < 2:
        return None
    return x, y, bw, bh


def crop(
    src: str,
    *,
    at: str | float | None = None,
    region: tuple[int, int, int, int] | None = None,
    start: str | float | None = None,
    end: str | float | None = None,
    out: str | None = None,
    keep_audio: bool = False,
    overwrite: bool = False,
) -> Path:
    """GUI(또는 region 직접 지정)로 영역을 정해 영상을 크롭한다.

    region=(x, y, w, h) 를 직접 주면 GUI를 건너뛴다 (배치/자동화용).
    start/end 를 주면 해당 시간 구간만 크롭해서 저장한다.
    """
    in_path = resolve_input(src)
    meta = probe(in_path)

    if region is None:
        # 미리보기 시각: 미지정이면 영상 중간 지점
        at_sec = parse_time(at)
        if at_sec is None:
            at_sec = meta.duration / 2 if meta.duration > 0 else 0.0
        info(f"미리보기 프레임 위치: {format_time(at_sec)}")
        frame = _grab_frame(in_path, at_sec)
        region = select_roi(frame)
        if region is None:
            warn("선택이 취소되었거나 영역이 너무 작습니다. 크롭을 중단합니다.")
            raise SystemExit(0)

    x, y, bw, bh = region
    info(f"크롭 영역: x={x}, y={y}, w={bw}, h={bh}  (원본 {meta.width}x{meta.height})")

    dest = resolve_output(out, suffix_name(in_path, "_crop"), overwrite=overwrite)

    args: list[str] = []
    t_start = parse_time(start)
    t_end = parse_time(end)
    if t_start is not None:
        args += ["-ss", f"{t_start}"]
    args += ["-i", str(in_path)]
    if t_end is not None:
        rel = t_end - (t_start or 0.0)
        if rel <= 0:
            core.fail("--end 가 --start 보다 작거나 같습니다.")
        args += ["-t", f"{rel}"]

    # 비디오만 재인코딩, 오디오는 기본 제거 (keep_audio 시 복사)
    args += [
        "-filter:v", f"crop={bw}:{bh}:{x}:{y}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
    ]
    args += ["-c:a", "copy"] if keep_audio else ["-an"]
    args += ["-y", str(dest)]
    info("크롭 처리 중 (비디오 재인코딩" + (", 오디오 복사" if keep_audio else ", 오디오 제거") + ")...")
    run_ffmpeg(args)
    ok(f"크롭 완료 → {dest}")
    return dest
