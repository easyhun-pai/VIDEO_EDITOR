#!/usr/bin/env python3
"""edit.py — 현장 영상 데이터셋 전처리 CLI.

사용 예시
    python edit.py info    data/BCT_hook.mp4
    python edit.py extract BCT_hook.mp4 -s 00:01:30 -e 00:02:45
    python edit.py encode  raw_10GB.mp4 --crf 12
    python edit.py merge   a.mp4 b.mp4 c.mp4 -o output/all.mp4
    python edit.py timeline BCT_hook.mp4 -f timestamp.txt
    python edit.py crop    BCT_hook.mp4
    python edit.py images  BCT8.mp4 --slice 1
    python edit.py frames  BCT_hook.mp4 --fps 2
    python edit.py split   BCT_hook.mp4 --chunk 300

* 모든 영상 출력은 기본적으로 오디오를 제거합니다 (유지하려면 --keep-audio).

자세한 옵션:  python edit.py <명령> -h
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from video_editor import __version__, cropper, operations
from video_editor.core import probe, resolve_input


# --------------------------------------------------------------------------- #
# 서브커맨드 핸들러
# --------------------------------------------------------------------------- #
def cmd_info(a: argparse.Namespace) -> None:
    p = resolve_input(a.input)
    print()
    print("  " + probe(p).summary())
    print()


def cmd_extract(a: argparse.Namespace) -> None:
    operations.extract(
        a.input,
        start=a.start,
        end=a.end,
        duration=a.duration,
        out=a.output,
        accurate=a.accurate,
        keep_audio=a.keep_audio,
        overwrite=a.overwrite,
    )


def cmd_encode(a: argparse.Namespace) -> None:
    operations.encode(
        a.input,
        crf=a.crf,
        codec=a.codec,
        preset=a.preset,
        pix_fmt=a.pix_fmt,
        fps=a.fps,
        keep_audio=a.keep_audio,
        out=a.output,
        overwrite=a.overwrite,
    )


def cmd_merge(a: argparse.Namespace) -> None:
    operations.merge(
        a.inputs,
        out=a.output,
        reencode=a.reencode,
        keep_audio=a.keep_audio,
        overwrite=a.overwrite,
    )


def cmd_timeline(a: argparse.Namespace) -> None:
    from_file = a.from_file
    # 구간 소스 미지정 시 프로젝트 루트의 timestamp.txt 자동 사용
    if not from_file and not a.range:
        default = Path("timestamp.txt")
        if default.exists():
            from_file = str(default)
        else:
            sys.exit("구간을 지정하세요: -f <파일> 또는 -r 1:30~2:45 (또는 ./timestamp.txt 준비)")
    operations.timeline(
        a.input,
        from_file=from_file,
        ranges=a.range,
        out=a.output,
        copy=a.copy,
        keep_audio=a.keep_audio,
        overwrite=a.overwrite,
    )


def cmd_crop(a: argparse.Namespace) -> None:
    region = None
    if a.region:
        try:
            parts = tuple(int(v) for v in a.region.split(","))
            assert len(parts) == 4
            region = parts
        except Exception:
            sys.exit("--region 형식 오류: x,y,w,h 정수 4개로 주세요 (예: 100,50,640,480)")
    cropper.crop(
        a.input,
        at=a.at,
        region=region,
        start=a.start,
        end=a.end,
        out=a.output,
        keep_audio=a.keep_audio,
        overwrite=a.overwrite,
    )


def cmd_frames(a: argparse.Namespace) -> None:
    operations.frames(
        a.input,
        every=a.every,
        fps=a.fps,
        start=a.start,
        end=a.end,
        out_dir=a.output,
        img_format=a.format,
        quality=a.quality,
        max_frames=a.max,
    )


def cmd_images(a: argparse.Namespace) -> None:
    operations.image_sequence(
        a.input,
        slice_sec=a.slice,
        start=a.start,
        end=a.end,
        out_dir=a.output,
        img_format=a.format,
        quality=a.quality,
        max_frames=a.max,
    )


def cmd_split(a: argparse.Namespace) -> None:
    operations.split(
        a.input,
        chunk=a.chunk,
        out_dir=a.output,
        keep_audio=a.keep_audio,
        overwrite=a.overwrite,
    )


# --------------------------------------------------------------------------- #
# 파서 구성
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="edit.py",
        description="현장 영상 데이터셋 전처리 툴킷 (info / extract / encode / merge / timeline / crop / images / frames / split)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--version", action="version", version=f"video_editor {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    # info ------------------------------------------------------------------ #
    s = sub.add_parser("info", help="영상 메타데이터(해상도/fps/길이/코덱) 출력")
    s.add_argument("input", help="입력 영상 (경로 또는 data/ 내 파일명)")
    s.set_defaults(func=cmd_info)

    # extract --------------------------------------------------------------- #
    s = sub.add_parser("extract", help="시간 구간 추출 (잘라내기)")
    s.add_argument("input", help="입력 영상")
    s.add_argument("-s", "--start", help="시작 시각 (예: 90, 1:30, 00:01:30)", default=None)
    s.add_argument("-e", "--end", help="끝 시각", default=None)
    s.add_argument("-d", "--duration", help="시작부터의 길이 (--end 대신)", default=None)
    s.add_argument("-o", "--output", help="출력 경로 (기본: output/<이름>_cut.<확장>)", default=None)
    s.add_argument("--accurate", action="store_true",
                   help="프레임 정확 컷(재인코딩, 느림). 기본은 빠른 무손실 복사")
    s.add_argument("--keep-audio", dest="keep_audio", action="store_true",
                   help="오디오 유지 (기본: 오디오 제거)")
    s.add_argument("-y", "--overwrite", action="store_true", help="기존 출력 덮어쓰기")
    s.set_defaults(func=cmd_extract)

    # encode ---------------------------------------------------------------- #
    s = sub.add_parser(
        "encode",
        help="CRF 기반 재인코딩으로 용량 축소 (웹 친화적: faststart)",
        description="무압축/고비트레이트 원본을 H.264/H.265로 압축합니다. CRF가 낮을수록 고화질·대용량.",
    )
    s.add_argument("input", help="입력 영상")
    s.add_argument("--crf", type=int, default=12,
                   help="화질/용량 트레이드오프 (낮을수록 고화질, 기본 12 ≈ 거의 무손실)")
    s.add_argument("--codec", choices=["h264", "h265"], default="h264",
                   help="코덱 (기본 h264=호환성 최고, h265=용량 더 작음/호환성 낮음)")
    s.add_argument("--preset", default="medium",
                   help="인코딩 프리셋 (느릴수록 용량↓: ultrafast..medium..slow..veryslow, 기본 medium)")
    s.add_argument("--pix-fmt", dest="pix_fmt", default="yuv420p",
                   help="픽셀 포맷 (기본 yuv420p=브라우저 호환). 비트뎁스 보존 필요시 변경")
    s.add_argument("--fps", type=float, default=None, help="출력 fps 강제 변경 (선택)")
    s.add_argument("-o", "--output", help="출력 경로 (기본: output/<이름>_<코덱>crf<값>.mp4)", default=None)
    s.add_argument("--keep-audio", dest="keep_audio", action="store_true",
                   help="오디오 유지 (기본: 오디오 제거)")
    s.add_argument("-y", "--overwrite", action="store_true", help="기존 출력 덮어쓰기")
    s.set_defaults(func=cmd_encode)

    # merge ----------------------------------------------------------------- #
    s = sub.add_parser("merge", help="여러 영상을 하나로 병합")
    s.add_argument("inputs", nargs="+", help="입력 영상 2개 이상 (병합 순서대로)")
    s.add_argument("-o", "--output", help="출력 경로 (기본: output/<첫이름>_merged.<확장>)", default=None)
    s.add_argument("--reencode", action="store_true",
                   help="입력 규격이 서로 다를 때 재인코딩으로 통일하여 병합")
    s.add_argument("--keep-audio", dest="keep_audio", action="store_true",
                   help="오디오 유지 (기본: 오디오 제거)")
    s.add_argument("-y", "--overwrite", action="store_true", help="기존 출력 덮어쓰기")
    s.set_defaults(func=cmd_merge)

    # timeline -------------------------------------------------------------- #
    s = sub.add_parser(
        "timeline",
        help="타임스탬프 목록의 여러 구간을 잘라 하나로 병합 (슈퍼컷)",
        description="타임스탬프 파일(예: '1\\t21:10~21:34')의 구간들을 추출해 순서대로 병합합니다.",
    )
    s.add_argument("input", help="입력 영상")
    s.add_argument("-f", "--from-file", dest="from_file",
                   help="타임스탬프 파일 경로 (미지정 시 ./timestamp.txt 자동 사용)", default=None)
    s.add_argument("-r", "--range", action="append", metavar="A~B",
                   help="구간 직접 지정 (반복 가능, 예: -r 1:30~2:45 -r 5:00~5:30)", default=None)
    s.add_argument("-o", "--output", help="출력 경로 (기본: output/<이름>_timeline.<확장>)", default=None)
    s.add_argument("--copy", action="store_true",
                   help="무손실 복사 병합 (빠름, 컷 지점이 키프레임에 정렬됨). 기본은 프레임 정확 재인코딩")
    s.add_argument("--keep-audio", dest="keep_audio", action="store_true",
                   help="오디오 유지 (기본: 오디오 제거)")
    s.add_argument("-y", "--overwrite", action="store_true", help="기존 출력 덮어쓰기")
    s.set_defaults(func=cmd_timeline)

    # crop ------------------------------------------------------------------ #
    s = sub.add_parser("crop", help="GUI로 영역 선택 후 크롭")
    s.add_argument("input", help="입력 영상")
    s.add_argument("--at", help="미리보기로 띄울 프레임 시각 (기본: 영상 중간)", default=None)
    s.add_argument("--region", help="GUI 없이 영역 직접 지정: x,y,w,h (예: 100,50,640,480)", default=None)
    s.add_argument("-s", "--start", help="크롭할 구간 시작 시각", default=None)
    s.add_argument("-e", "--end", help="크롭할 구간 끝 시각", default=None)
    s.add_argument("-o", "--output", help="출력 경로 (기본: output/<이름>_crop.<확장>)", default=None)
    s.add_argument("--keep-audio", dest="keep_audio", action="store_true",
                   help="오디오 유지 (기본: 오디오 제거)")
    s.add_argument("-y", "--overwrite", action="store_true", help="기존 출력 덮어쓰기")
    s.set_defaults(func=cmd_crop)

    # frames ---------------------------------------------------------------- #
    s = sub.add_parser("frames", help="프레임을 이미지로 추출 (데이터셋용)")
    s.add_argument("input", help="입력 영상")
    s.add_argument("--every", type=int, help="N번째 프레임마다 저장", default=None)
    s.add_argument("--fps", type=float, help="초당 F장 저장 (--every 와 택1)", default=None)
    s.add_argument("-s", "--start", help="시작 시각", default=None)
    s.add_argument("-e", "--end", help="끝 시각", default=None)
    s.add_argument("-o", "--output", help="출력 폴더 (기본: output/<이름>_frames)", default=None)
    s.add_argument("--format", choices=["jpg", "png"], default="jpg", help="이미지 포맷 (기본 jpg)")
    s.add_argument("--quality", type=int, default=95, help="jpg 품질/0~100 (기본 95)")
    s.add_argument("--max", type=int, help="최대 저장 장수 제한", default=None)
    s.set_defaults(func=cmd_frames)

    # images ---------------------------------------------------------------- #
    s = sub.add_parser(
        "images",
        help="time slice 단위로 이미지 시퀀스 추출 (output/<이름>_images/)",
        description="영상을 일정 시간 간격(--slice, 기본 1초)으로 샘플링해 이미지로 저장합니다.",
    )
    s.add_argument("input", help="입력 영상 (output/ 안의 결과물도 파일명만으로 인식)")
    s.add_argument("--slice", default="1",
                   help="추출 간격(초). 기본 1 = 1초당 1장. 예: 0.5, 2, 1:00", metavar="SEC")
    s.add_argument("-s", "--start", help="시작 시각", default=None)
    s.add_argument("-e", "--end", help="끝 시각", default=None)
    s.add_argument("-o", "--output", help="출력 폴더 (기본: output/<이름>_images)", default=None)
    s.add_argument("--format", choices=["jpg", "png"], default="jpg", help="이미지 포맷 (기본 jpg)")
    s.add_argument("--quality", type=int, default=95, help="jpg 품질/0~100 (기본 95)")
    s.add_argument("--max", type=int, help="최대 저장 장수 제한", default=None)
    s.set_defaults(func=cmd_images)

    # split ----------------------------------------------------------------- #
    s = sub.add_parser("split", help="일정 길이 단위로 분할")
    s.add_argument("input", help="입력 영상")
    s.add_argument("--chunk", default="60", help="세그먼트 길이(초 또는 mm:ss, 기본 60)")
    s.add_argument("-o", "--output", help="출력 폴더 (기본: output/<이름>_chunks)", default=None)
    s.add_argument("--keep-audio", dest="keep_audio", action="store_true",
                   help="오디오 유지 (기본: 오디오 제거)")
    s.add_argument("-y", "--overwrite", action="store_true", help="기존 출력 덮어쓰기")
    s.set_defaults(func=cmd_split)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
