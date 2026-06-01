"""video_editor — 현장 영상 데이터셋 전처리 툴킷.

핵심 기능
    * extract : 원하는 시간 구간만 잘라내기
    * merge   : 여러 영상을 하나로 병합
    * crop    : GUI로 영역을 선택해 화면 크롭
    * frames  : 데이터셋용 프레임(이미지) 추출
    * split   : 일정 길이 단위로 영상 분할
    * info    : 영상 메타데이터 확인
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "__version__",
]
