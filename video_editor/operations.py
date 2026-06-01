"""핵심 영상 연산 — extract / merge / split / frames / timeline."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from . import core
from .core import (
    format_time,
    has_audio,
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


# --------------------------------------------------------------------------- #
# 1) extract — 시간 구간 추출
# --------------------------------------------------------------------------- #
def extract(
    src: str,
    *,
    start: str | float | None = None,
    end: str | float | None = None,
    duration: str | float | None = None,
    out: str | None = None,
    accurate: bool = False,
    keep_audio: bool = False,
    overwrite: bool = False,
) -> Path:
    """[start, end] 또는 [start, start+duration] 구간을 잘라낸다.

    기본은 스트림 복사(-c copy)라 매우 빠르고 무손실이지만, 컷 지점이 가장
    가까운 키프레임에 맞춰질 수 있다. 프레임 정확도가 필요하면 accurate=True
    (재인코딩, 느리지만 정확).
    """
    in_path = resolve_input(src)
    t_start = parse_time(start) or 0.0
    t_end = parse_time(end)
    t_dur = parse_time(duration)

    if t_end is None and t_dur is None:
        core.fail("끝 시점을 지정하세요: --end 또는 --duration 중 하나가 필요합니다.")
    if t_end is not None and t_dur is not None:
        warn("--end 와 --duration 이 함께 지정됨 → --end 를 사용합니다.")
        t_dur = None
    if t_end is not None and t_end <= t_start:
        core.fail(f"--end({format_time(t_end)})가 --start({format_time(t_start)})보다 작거나 같습니다.")

    dest = resolve_output(out, suffix_name(in_path, "_cut"), overwrite=overwrite)

    args: list[str] = []
    if accurate:
        # 정확한 컷: -ss/-t 를 -i 뒤에 두고 재인코딩
        args += ["-i", str(in_path), "-ss", f"{t_start}"]
        if t_end is not None:
            args += ["-to", f"{t_end}"]
        else:
            args += ["-t", f"{t_dur}"]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
        args += ["-c:a", "aac"] if keep_audio else ["-an"]
    else:
        # 빠른 컷: -ss 를 -i 앞에 두고 스트림 복사
        args += ["-ss", f"{t_start}", "-i", str(in_path)]
        if t_end is not None:
            args += ["-to", f"{t_end - t_start}"]  # 입력 앞 -ss 기준이라 상대시간
        else:
            args += ["-t", f"{t_dur}"]
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
        if not keep_audio:
            args += ["-an"]

    args += ["-y", str(dest)]

    span = format_time(t_end - t_start) if t_end is not None else format_time(t_dur)
    info(f"입력 : {in_path.name}")
    info(f"구간 : {format_time(t_start)} 부터 {span} 길이  ({'정확/재인코딩' if accurate else '빠름/무손실복사'})")
    run_ffmpeg(args)
    ok(f"추출 완료 → {dest}")
    return dest


# --------------------------------------------------------------------------- #
# 2) merge — 여러 영상 병합
# --------------------------------------------------------------------------- #
def merge(
    sources: list[str],
    *,
    out: str | None = None,
    reencode: bool = False,
    keep_audio: bool = False,
    overwrite: bool = False,
) -> Path:
    """여러 영상을 순서대로 이어붙인다.

    기본은 concat demuxer + 스트림 복사(무손실, 빠름)이지만 모든 입력의
    코덱/해상도/fps가 동일해야 한다. 입력 사양이 제각각이면 reencode=True 로
    동일 규격으로 재인코딩하여 병합한다.
    """
    if len(sources) < 2:
        core.fail("병합하려면 최소 2개의 입력이 필요합니다.")
    in_paths = [resolve_input(s) for s in sources]

    first = probe(in_paths[0])
    dest = resolve_output(out, f"{in_paths[0].stem}_merged{in_paths[0].suffix}", overwrite=overwrite)

    info("병합 순서:")
    for i, p in enumerate(in_paths, 1):
        info(f"   {i}. {p.name}")

    if reencode:
        # concat 필터로 재인코딩 (규격 달라도 OK). 첫 영상 해상도/fps로 통일.
        inputs: list[str] = []
        for p in in_paths:
            inputs += ["-i", str(p)]
        n = len(in_paths)
        scale = f"scale={first.width}:{first.height}:force_original_aspect_ratio=decrease,pad={first.width}:{first.height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        chains = "".join(f"[{i}:v]{scale}[v{i}];" for i in range(n))
        if keep_audio:
            vlabels = "".join(f"[v{i}][{i}:a]" for i in range(n))
            filtic = f"{chains}{vlabels}concat=n={n}:v=1:a=1[outv][outa]"
            tail = ["-map", "[outv]", "-map", "[outa]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac"]
        else:
            vlabels = "".join(f"[v{i}]" for i in range(n))
            filtic = f"{chains}{vlabels}concat=n={n}:v=1:a=0[outv]"
            tail = ["-map", "[outv]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an"]
        args = inputs + ["-filter_complex", filtic, *tail, "-y", str(dest)]
        info("방식 : 재인코딩 병합 (규격 자동 통일)")
        run_ffmpeg(args)
    else:
        # concat demuxer + 스트림 복사. 임시 리스트 파일 필요.
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            list_path = Path(f.name)
            for p in in_paths:
                # ffmpeg concat 리스트는 작은따옴표 이스케이프 필요
                safe = str(p.resolve()).replace("'", "'\\''")
                f.write(f"file '{safe}'\n")
        try:
            args = ["-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy"]
            if not keep_audio:
                args += ["-an"]
            args += ["-y", str(dest)]
            info("방식 : 무손실 복사 병합 (입력 규격 동일 가정)")
            run_ffmpeg(args)
        finally:
            list_path.unlink(missing_ok=True)

    ok(f"병합 완료 → {dest}")
    return dest


# --------------------------------------------------------------------------- #
# 3) split — 일정 길이 단위 분할
# --------------------------------------------------------------------------- #
def split(
    src: str,
    *,
    chunk: str | float = 60,
    out_dir: str | None = None,
    keep_audio: bool = False,
    overwrite: bool = False,
) -> Path:
    """영상을 chunk초 단위 세그먼트로 나눈다 (무손실 복사)."""
    in_path = resolve_input(src)
    seconds = parse_time(chunk)
    if not seconds or seconds <= 0:
        core.fail("--chunk 는 0보다 큰 값이어야 합니다.")

    out_root = Path(out_dir) if out_dir else core.OUTPUT_DIR / f"{in_path.stem}_chunks"
    out_root.mkdir(parents=True, exist_ok=True)
    pattern = out_root / f"{in_path.stem}_%03d{in_path.suffix}"

    if any(out_root.iterdir()) and not overwrite:
        core.fail(f"출력 폴더가 비어있지 않습니다: {out_root}\n    -y / --overwrite 로 덮어쓰기 허용.")

    args = [
        "-i", str(in_path),
        "-c", "copy", "-map", "0",
    ]
    if not keep_audio:
        args += ["-an"]
    args += [
        "-f", "segment", "-segment_time", f"{seconds}",
        "-reset_timestamps", "1",
        "-y", str(pattern),
    ]
    info(f"입력 : {in_path.name}")
    info(f"분할 : {seconds:g}초 단위 → {out_root}")
    run_ffmpeg(args)
    made = sorted(out_root.glob(f"{in_path.stem}_*{in_path.suffix}"))
    ok(f"분할 완료: {len(made)}개 세그먼트 → {out_root}")
    return out_root


# --------------------------------------------------------------------------- #
# 4) frames — 프레임(이미지) 추출 (데이터셋용)
# --------------------------------------------------------------------------- #
def frames(
    src: str,
    *,
    every: int | None = None,
    fps: float | None = None,
    start: str | float | None = None,
    end: str | float | None = None,
    out_dir: str | None = None,
    img_format: str = "jpg",
    quality: int = 95,
    max_frames: int | None = None,
) -> Path:
    """영상에서 프레임을 이미지로 저장한다. (OpenCV 사용)

    샘플링:
        every=N  → N번째 프레임마다 저장
        fps=F    → 초당 F장 저장
        (둘 다 미지정이면 모든 프레임 저장)
    """
    import cv2

    in_path = resolve_input(src)
    meta = probe(in_path)
    src_fps = meta.fps if meta.fps > 0 else 30.0

    if every is not None and fps is not None:
        warn("--every 와 --fps 동시 지정 → --fps 우선 사용.")
        every = None
    if fps is not None:
        step = max(1, round(src_fps / fps))
    elif every is not None:
        step = max(1, every)
    else:
        step = 1

    t_start = parse_time(start) or 0.0
    t_end = parse_time(end)
    start_frame = int(t_start * src_fps)
    end_frame = int(t_end * src_fps) if t_end is not None else meta.frame_count

    out_root = Path(out_dir) if out_dir else core.OUTPUT_DIR / f"{in_path.stem}_frames"
    out_root.mkdir(parents=True, exist_ok=True)

    info(f"입력 : {in_path.name}  ({src_fps:.2f} fps)")
    info(f"샘플 : {step}프레임마다 1장" + (f"  (≈{src_fps/step:.2f} fps)" if step > 1 else ""))
    info(f"구간 : 프레임 {start_frame} ~ {end_frame}")
    _grab_sequence(
        in_path, src_fps, step, start_frame, end_frame,
        out_root, img_format, quality, max_frames,
    )
    return out_root


def image_sequence(
    src: str,
    *,
    slice_sec: str | float = 1,
    start: str | float | None = None,
    end: str | float | None = None,
    out_dir: str | None = None,
    img_format: str = "jpg",
    quality: int = 95,
    max_frames: int | None = None,
) -> Path:
    """영상을 일정 시간 간격(time slice)으로 샘플링해 이미지 시퀀스로 저장한다.

    slice_sec 초마다 1장씩 저장한다 (기본 1초). 결과는 output/<이름>_images/ 에 모인다.
    데이터셋용으로 흔히 쓰는 "초당 N장" 추출에 맞춰진 단순 인터페이스.
    """
    in_path = resolve_input(src)
    meta = probe(in_path)
    src_fps = meta.fps if meta.fps > 0 else 30.0

    interval = parse_time(slice_sec)
    if not interval or interval <= 0:
        core.fail("--slice 는 0보다 큰 값이어야 합니다 (예: 1, 0.5, 2).")
    step = max(1, round(src_fps * interval))

    t_start = parse_time(start) or 0.0
    t_end = parse_time(end)
    start_frame = int(t_start * src_fps)
    end_frame = int(t_end * src_fps) if t_end is not None else meta.frame_count

    out_root = Path(out_dir) if out_dir else core.OUTPUT_DIR / f"{in_path.stem}_images"
    out_root.mkdir(parents=True, exist_ok=True)

    info(f"입력 : {in_path.name}  ({src_fps:.2f} fps)")
    info(f"슬라이스 : {interval:g}초마다 1장  (≈{src_fps/step:.3f} fps, {step}프레임 간격)")
    info(f"구간 : 프레임 {start_frame} ~ {end_frame}")
    _grab_sequence(
        in_path, src_fps, step, start_frame, end_frame,
        out_root, img_format, quality, max_frames,
    )
    return out_root


def _grab_sequence(
    in_path: Path,
    src_fps: float,
    step: int,
    start_frame: int,
    end_frame: int,
    out_root: Path,
    img_format: str,
    quality: int,
    max_frames: int | None,
) -> Path:
    """프레임을 step 간격으로 읽어 이미지 파일로 저장하는 공용 루프 (OpenCV)."""
    import cv2

    img_format = img_format.lower().lstrip(".")
    if img_format in ("jpg", "jpeg"):
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, int(quality)]
    elif img_format == "png":
        # png 압축 레벨(0~9): quality 높을수록 덜 압축
        encode_params = [cv2.IMWRITE_PNG_COMPRESSION, max(0, min(9, 9 - quality // 11))]
    else:
        encode_params = []

    cap = cv2.VideoCapture(str(in_path))
    if not cap.isOpened():
        core.fail(f"영상을 열 수 없습니다: {in_path}")
    if start_frame > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    saved = 0
    idx = start_frame
    while idx < end_frame:
        ret, frame = cap.read()
        if not ret:
            break
        if (idx - start_frame) % step == 0:
            # 0부터 시작하는 연속 순번으로 저장 (0000, 0001, ...)
            name = out_root / f"{in_path.stem}_{saved:06d}.{img_format}"
            cv2.imwrite(str(name), frame, encode_params)
            saved += 1
            if saved % 200 == 0:
                print(f"    ... {saved}장 저장", end="\r")
            if max_frames is not None and saved >= max_frames:
                info(f"--max {max_frames} 도달 → 중단")
                break
        idx += 1
    cap.release()

    ok(f"이미지 시퀀스 저장 완료: {saved}장 → {out_root}")
    return out_root


# --------------------------------------------------------------------------- #
# 5) timeline — 타임스탬프 목록의 여러 구간을 잘라 하나로 병합 (슈퍼컷)
# --------------------------------------------------------------------------- #
# 시간 토큰: 90 / 90.5 / 1:30 / 01:02:03 / 1:02:03.250
_TIME = r"\d+(?::\d+){0,2}(?:\.\d+)?"
# 범위 구분자: ~ , -> , – , — , to , -
_RANGE_RE = re.compile(rf"({_TIME})\s*(?:~|->|–|—|to|-)\s*({_TIME})")


def parse_ranges_file(path: str | Path) -> list[tuple[float, float]]:
    """타임스탬프 파일을 읽어 (start, end) 초 리스트로 반환.

    지원 형식 예 (한 줄에 한 구간):
        1\t21:10~21:34          # 앞의 인덱스/라벨은 자동 무시
        21:51 ~ 22:02
        00:24:54 - 00:25:00
        90-120                  # 초 단위
    빈 줄과 '#' 주석은 건너뛴다.
    """
    p = Path(path)
    if not p.exists():
        core.fail(f"타임스탬프 파일이 없습니다: {p}")

    ranges: list[tuple[float, float]] = []
    for lineno, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _RANGE_RE.search(line)
        if not m:
            warn(f"  {p.name}:{lineno} 구간을 해석하지 못해 건너뜀: {raw!r}")
            continue
        start = parse_time(m.group(1))
        end = parse_time(m.group(2))
        if start is None or end is None or end <= start:
            warn(f"  {p.name}:{lineno} 잘못된 구간(끝<=시작) 건너뜀: {raw!r}")
            continue
        ranges.append((start, end))
    return ranges


def _parse_inline_ranges(items: list[str]) -> list[tuple[float, float]]:
    """CLI로 직접 준 '1:30~2:45' 형태의 구간 문자열들을 파싱."""
    out: list[tuple[float, float]] = []
    for item in items:
        m = _RANGE_RE.search(item)
        if not m:
            core.fail(f"구간 형식 오류: {item!r} (예: 1:30~2:45, 90-120)")
        start, end = parse_time(m.group(1)), parse_time(m.group(2))
        if start is None or end is None or end <= start:
            core.fail(f"잘못된 구간(끝<=시작): {item!r}")
        out.append((start, end))
    return out


def timeline(
    src: str,
    *,
    from_file: str | None = None,
    ranges: list[str] | None = None,
    out: str | None = None,
    copy: bool = False,
    keep_audio: bool = False,
    overwrite: bool = False,
) -> Path:
    """타임스탬프 목록의 여러 구간을 추출해 순서대로 하나의 영상으로 병합한다.

    구간 소스: from_file(타임스탬프 파일) 또는 ranges(인라인 문자열) 중 하나 이상.
    기본은 프레임 정확 병합(filter_complex, 1회 재인코딩). copy=True 면 각 구간을
    무손실 복사로 잘라 concat(빠르지만 컷 지점이 키프레임에 정렬됨).
    """
    in_path = resolve_input(src)

    segs: list[tuple[float, float]] = []
    if from_file:
        segs += parse_ranges_file(from_file)
    if ranges:
        segs += _parse_inline_ranges(ranges)
    if not segs:
        core.fail("추출할 구간이 없습니다. --from-file 또는 --range 로 구간을 지정하세요.")

    dest = resolve_output(out, suffix_name(in_path, "_timeline"), overwrite=overwrite)

    total = sum(e - s for s, e in segs)
    info(f"입력 : {in_path.name}")
    info(f"구간 : {len(segs)}개  (합계 {format_time(total)})")
    for i, (s, e) in enumerate(segs, 1):
        info(f"   {i:>2}. {format_time(s)} ~ {format_time(e)}  ({e - s:.2f}s)")

    if copy:
        _timeline_copy(in_path, segs, dest, keep_audio)
    else:
        _timeline_reencode(in_path, segs, dest, keep_audio)

    ok(f"타임라인 병합 완료: {len(segs)}개 구간 → {dest}")
    return dest


def _timeline_reencode(
    in_path: Path, segs: list[tuple[float, float]], dest: Path, keep_audio: bool
) -> None:
    """filter_complex의 trim+concat 으로 프레임 정확 병합 (1회 재인코딩)."""
    audio = keep_audio and has_audio(in_path)
    parts: list[str] = []
    for i, (s, e) in enumerate(segs):
        parts.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
        if audio:
            parts.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]")
    n = len(segs)
    if audio:
        concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
        parts.append(f"{concat_in}concat=n={n}:v=1:a=1[outv][outa]")
        maps = ["-map", "[outv]", "-map", "[outa]"]
    else:
        concat_in = "".join(f"[v{i}]" for i in range(n))
        parts.append(f"{concat_in}concat=n={n}:v=1:a=0[outv]")
        maps = ["-map", "[outv]"]

    args = [
        "-i", str(in_path),
        "-filter_complex", ";".join(parts),
        *maps,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
    ]
    if audio:
        args += ["-c:a", "aac"]
    args += ["-y", str(dest)]
    info("방식 : 프레임 정확 병합 (재인코딩)" + ("" if audio else "  [오디오 없음]"))
    run_ffmpeg(args)


def _timeline_copy(
    in_path: Path, segs: list[tuple[float, float]], dest: Path, keep_audio: bool
) -> None:
    """각 구간을 무손실 복사로 잘라 임시 파일로 만든 뒤 concat demuxer 로 병합."""
    info("방식 : 무손실 복사 병합 (컷 지점이 키프레임에 정렬될 수 있음)"
         + ("" if keep_audio else "  [오디오 없음]"))
    tmp_dir = Path(tempfile.mkdtemp(prefix="timeline_"))
    try:
        clips: list[Path] = []
        for i, (s, e) in enumerate(segs):
            clip = tmp_dir / f"seg_{i:04d}{in_path.suffix}"
            seg_args = [
                "-ss", f"{s}", "-i", str(in_path),
                "-t", f"{e - s}",
                "-c", "copy", "-avoid_negative_ts", "make_zero",
            ]
            if not keep_audio:
                seg_args += ["-an"]
            seg_args += ["-y", str(clip)]
            run_ffmpeg(seg_args, quiet=True)
            clips.append(clip)

        list_path = tmp_dir / "concat.txt"
        with list_path.open("w", encoding="utf-8") as f:
            for clip in clips:
                safe = str(clip.resolve()).replace("'", "'\\''")
                f.write(f"file '{safe}'\n")
        run_ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", "-y", str(dest)]
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
