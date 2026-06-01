# 🎬 VIDEO_EDITOR

현장 영상을 **데이터셋으로 전처리**하기 위한 가볍고 범용적인 CLI 툴킷.
시간 구간 추출 · 영상 병합 · 타임라인 슈퍼컷 · GUI 크롭은 물론, 데이터셋 작업에 유용한 **이미지 시퀀스 추출 / 분할 / 메타데이터 확인**까지 한 번에 처리합니다.

```
┌─────────┐  extract · merge   ┌──────────┐
│  data/  │  timeline · crop ─▶│ output/  │
│ *.mp4 … │  images · split …  │ 결과물    │
└─────────┘                    └──────────┘
```

---

## ✨ 기능

| 명령 | 설명 | 핵심 옵션 |
|------|------|-----------|
| `info`    | 해상도·FPS·길이·코덱 등 메타데이터 확인 | — |
| `extract` | 원하는 **시간 구간**만 잘라내기 (기본 무손실·고속) | `-s` `-e` `-d` `--accurate` |
| `merge`   | 여러 영상을 **하나로 병합** | `--reencode` |
| `timeline`| **타임스탬프 목록의 여러 구간**을 잘라 하나로 병합 (슈퍼컷) | `-f` `-r` `--copy` |
| `crop`    | **GUI로 영역을 드래그**해 화면 크롭 | `--at` `--region` `-s` `-e` |
| `images`  | **time slice 단위 이미지 시퀀스** 추출 (기본 1초/장) | `--slice` `-s` `-e` `--format` |
| `frames`  | 프레임을 이미지로 추출 (프레임 단위 제어) | `--fps` `--every` `--format` `--max` |
| `split`   | **일정 길이 단위로 분할** | `--chunk` |

> 입력은 `./data/`, 출력은 `./output/` 기준으로 자동 정리됩니다.
> 파일명만 넘기면 `data/` → `output/` 순으로 찾아줍니다 (전처리 결과물을 바로 다음 작업의 입력으로).
> **모든 영상 출력은 기본적으로 오디오를 제거합니다** (데이터셋 용량 절감). 유지하려면 `--keep-audio`.

---

## 📦 설치

```bash
# 1) 의존성 설치 (Windows에서 pip이 막히면 `python -m pip` 사용)
python -m pip install -r requirements.txt
```

- **ffmpeg는 따로 설치하지 않아도 됩니다.** `imageio-ffmpeg`가 ffmpeg 바이너리를 함께 설치합니다.
- 시스템에 ffmpeg가 이미 있으면 그걸 우선 사용합니다.
- 크롭 GUI는 `opencv-python`의 창 기능을 사용합니다 (로컬 데스크톱 환경 필요).

---

## 🚀 사용법

### 0. 메타데이터 확인
```bash
python edit.py info BCT_hook.mp4
```
```
  BCT_hook.mp4
    해상도   : 3840 x 2160
    FPS      : 29.970
    프레임 수 : 54000
    길이     : 00:30:01.234 (1801.23s)
    코덱     : hevc
    파일크기  : 1804.0 MB
```

### 1. 시간 구간 추출
```bash
# 01:30 ~ 02:45 구간 (무손실·고속, 키프레임 단위 컷)
python edit.py extract BCT_hook.mp4 -s 1:30 -e 2:45

# 시작 시각 + 길이로 지정 (90초부터 30초 분량)
python edit.py extract BCT_hook.mp4 -s 90 -d 30

# 프레임 단위 정확 컷이 필요할 때 (재인코딩, 느림)
python edit.py extract BCT_hook.mp4 -s 1:30 -e 2:45 --accurate -o output/clip.mp4
```
> 시간 형식: `90`, `90.5`, `1:30`, `01:02:03`, `1:02:03.250` 모두 가능.

### 2. 영상 병합
```bash
# 순서대로 이어붙이기 (입력 규격 동일 시 무손실·고속)
python edit.py merge clip1.mp4 clip2.mp4 clip3.mp4 -o output/merged.mp4

# 해상도/코덱/fps가 제각각이면 재인코딩으로 통일해 병합
python edit.py merge phoneA.mp4 camB.mov -o output/merged.mp4 --reencode
```

### 2-1. 타임라인 슈퍼컷 (여러 구간 → 하나로 병합)
타임스탬프 파일에 적어둔 여러 구간을 한 번에 추출해 순서대로 이어붙입니다.

**`timestamp.txt` 형식** (한 줄에 한 구간, 앞의 인덱스/라벨은 자동 무시):
```
1	00:12~00:34
2	12:34~13:34
3	24:54~25:00
```
> 구분자는 `~`, `-`, `->`, `to` 모두 가능. 시간은 `90`/`1:30`/`01:02:03` 형식 지원. `#` 주석·빈 줄 무시.

```bash
# timestamp.txt 자동 사용 (프레임 정확 병합 = 재인코딩)
python edit.py timeline BCT_hook.mp4

# 파일 지정 + 출력 지정
python edit.py timeline BCT_hook.mp4 -f timestamp.txt -o output/supercut.mp4

# 파일 없이 구간 직접 지정 (반복 가능)
python edit.py timeline BCT_hook.mp4 -r 1:30~2:45 -r 5:00~5:30

# 빠른 무손실 모드 (컷 지점이 가까운 키프레임에 정렬될 수 있음)
python edit.py timeline BCT_hook.mp4 -f timestamp.txt --copy
```
> **기본(재인코딩)**: 프레임 정확, 컷 지점이 매끄러움.
> **`--copy`**: 재인코딩 없이 매우 빠르고 무손실이지만, 컷이 키프레임 단위로 맞춰져 길이가 약간 늘 수 있음.

### 3. GUI 크롭
```bash
# 영상 중간 프레임이 창으로 뜸 → 마우스 드래그로 영역 선택 → ENTER 확정
python edit.py crop BCT_hook.mp4

# 미리보기 프레임 위치 지정 + 특정 구간만 크롭
python edit.py crop BCT_hook.mp4 --at 0:10 -s 0:05 -e 0:20

# GUI 없이 좌표 직접 지정 (자동화/배치용): x,y,w,h
python edit.py crop BCT_hook.mp4 --region 480,270,1280,720
```
> **조작:** 마우스로 박스 드래그 → `ENTER`/`SPACE` 확정, `C` 취소.
> 큰 해상도(4K 등)는 화면에 맞게 축소해 보여주고 좌표는 원본 기준으로 환산합니다.

### 4. 이미지 시퀀스 추출 (time slice)
전처리된 영상을 일정 시간 간격으로 샘플링해 이미지 시퀀스로 만듭니다. (데이터셋 제작용 메인)
```bash
# 1초마다 1장 (기본). output/BCT8.mp4 → output/BCT8_images/
python edit.py images BCT8.mp4

# 0.5초마다 1장 (초당 2장) + 특정 구간만
python edit.py images BCT8.mp4 --slice 0.5 -s 0:10 -e 0:40

# png로 저장
python edit.py images BCT8.mp4 --slice 2 --format png
```
→ `output/BCT8_images/BCT8_000000.jpg`, `BCT8_000001.jpg` … (0부터 연속 순번)
> 출력 폴더는 `output/<파일명>_images/` 로 자동 생성됩니다.
> `output/` 안의 결과물은 **파일명만** 줘도 인식합니다 (`images BCT8.mp4`).

### 4-1. 프레임 추출 (프레임 단위 정밀 제어)
초당 장수(`--fps`)나 N프레임 간격(`--every`)으로 더 세밀하게 뽑고 싶을 때.
```bash
python edit.py frames BCT_hook.mp4 --fps 2
python edit.py frames BCT_hook.mp4 --every 15 -s 1:00 -e 2:00 --format png --max 500
```
→ `output/BCT_hook_frames/BCT_hook_000000.jpg` 형태로 저장 (0부터 연속 순번).

### 5. 영상 분할
```bash
# 5분(300초) 단위로 잘라 여러 파일로 저장 (무손실)
python edit.py split BCT_hook.mp4 --chunk 300
```
→ `output/BCT_hook_chunks/BCT_hook_000.mp4`, `_001.mp4` …

---

## 📂 프로젝트 구조

```
VIDEO_EDITOR/
├── data/                  # 입력 영상 (gitignore)
├── output/                # 결과물 (gitignore)
├── timestamp.txt          # timeline 기본 입력 (선택, 직접 작성)
├── edit.py                # CLI 진입점
├── video_editor/
│   ├── __init__.py
│   ├── core.py            # ffmpeg 탐지·시간 파싱·probe·경로 헬퍼
│   ├── operations.py      # extract / merge / timeline / images / frames / split
│   └── cropper.py         # OpenCV 크롭 GUI + ffmpeg 크롭
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 💡 설계 메모

- **빠름이 기본:** `extract`/`merge`/`split`은 스트림 복사(`-c copy`)라 재인코딩 없이 거의 즉시 끝나고 화질 손실이 없습니다. 정확도가 필요할 때만 재인코딩 옵션(`--accurate`, `--reencode`)을 켜세요.
- **무설치 ffmpeg:** `imageio-ffmpeg` 번들 바이너리를 자동 사용하므로 환경 세팅이 간단합니다.
- **무음이 기본:** 데이터셋에는 소리가 불필요하고 용량만 키우므로, 모든 영상 출력에서 오디오를 제거합니다. 필요하면 `--keep-audio`.
- **짝수 보정:** 크롭은 `yuv420p` 호환을 위해 폭/높이를 자동으로 짝수로 맞춥니다.
- **자동 탐색:** 입력에 파일명만 줘도 `data/` → `output/` 순으로 찾아줍니다. (전처리 결과물을 바로 이어서 처리)

---

## 🔧 더 붙이면 좋은 것 (제안)

데이터셋 전처리 관점에서 다음 기능들이 추가로 유용할 수 있습니다. 필요하면 말씀 주세요:

1. **resize / fps 정규화** — 데이터셋 해상도·프레임레이트 통일 (`--scale 1280x720`, `--fps 15`)
2. **배치 처리** — `data/` 전체를 한 번에 같은 옵션으로 처리 (`--batch`)
3. **장면 전환 감지(scene detect)** — 컷이 바뀌는 지점 자동 분할 (PySceneDetect)
4. **밝기/대비/디인터레이스 등 필터 프리셋** — 현장 영상 품질 보정
5. **YOLO/COCO 라벨링 연계** — 추출 프레임에 바로 어노테이션 파이프라인 연결
6. **메타데이터 CSV 내보내기** — 추출 프레임의 원본 타임코드 매핑 기록 (학습 추적용)
7. **무손실 회전/플립** — 세로/가로 영상 정규화
