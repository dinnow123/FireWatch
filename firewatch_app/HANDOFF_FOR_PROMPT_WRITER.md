# FireWatch — 프롬프트 작성용 Claude 인수인계 문서

> 이 문서를 다음 Claude 세션에 넘기면 됩니다. 사용자가 시키는 다음 작업의 프롬프트를 짜기 전, 이 문서 한 번 읽으면 프로젝트 전체 맥락이 잡힙니다.

---

## 0. 너의 역할 (이 문서를 받는 Claude에게)

너는 사용자(학번 22012106, 이승민)에게 줄 **프롬프트를 작성하는** Claude 다. 실제 코드 작업은 워크트리에서 다른 Claude 세션이 수행한다 (이 문서를 만든 그 세션). 너는:

- 사용자의 자연어 요청을 받아서
- 작업 대상 파일·줄 번호·변경 내용을 명시한 **자족적이고(self-contained), 실행 가능한 프롬프트**로 변환한다
- 작업 후 검증 항목까지 포함시킨다

사용자는 짧고 모호한 한국어로 지시하는 경향이 있다. 너의 역할은 그 의도를 정확히 풀어서 작업자 Claude 에게 명료한 instruction 으로 던지는 것.

---

## 1. 프로젝트 정체

- **이름**: FireWatch
- **무엇인가**: 확률적 셀룰러 오토마타 기반 건물 화재 확산 앙상블 시뮬레이터 (대학 오픈소스SW설계 과제)
- **왜 필요**: 기존 NIST FDS 같은 CFD 도구가 너무 느려서 (수 시간~수 일). 신고 접수 직후 수 초 ~ 수 분 내 확률 분포 형태의 확산 예측을 주는 게 목표
- **현재 단계**: **Analysis** (Conceptualization 다음 / Implementation 전)
- **사용자 정보**:
  - 학번: 22012106, 이름: 이승민
  - GitHub: https://github.com/dinnow123/FireWatch
  - Email: dinola@naver.com (학교 제출용은 fmworks.aicenter@gmail.com 이 활동 메일)

---

## 2. 3-단계 문서 계층 + 현재 상태

| 단계 | 산출물 | 위치 | 상태 |
|---|---|---|---|
| Conceptualization | `Conceptualization_[22012106_이승민].md` | 프로젝트 루트 | 완료 (선행 산출물, 이미 제출됨) |
| **Analysis** | `Analysis_[22012106_이승민].md` | `~/Downloads/` 에 사용자 보관 | **작업 중, 곧 제출 예정** |
| Implementation | (아직 없음) | — | 다음 학기/단계 |

Analysis 문서 구성:
1. Introduction (Executive Summary + Business Goals)
2. Use case modeling (다이어그램 이미지 + 11개 UC description 표)
3. Domain analysis (**15개** 클래스 텍스트 설명, **클래스 다이어그램 이미지 없음**)
4. UI prototype (11개 화면 스크린샷 + 사용 방법)
5. Glossary
6. References (2개만 — 빈약)

### Analysis 문서의 알려진 결함 (방금 평가 완료)

🔴 **반드시 고쳐야 할 것:**
1. §3 클래스 다이어그램 이미지 부재 — draw.io 로 그려서 `images/` 에 추가 필요
2. 클래스 수 15 → 10 통합 필요 ("10개 이내" 규칙 위반)
3. §2.1.2 절 (Actor 권한 매트릭스) 가 §4.10 에서 인용되지만 실제로는 없음 — 깨진 참조

🟡 **점수 깎이는 부분:**
4. 각 클래스의 attribute / operation 명시 부족 (narrative prose 만 있음)
5. §1.2 Business Goals 정량 KPI 없음
6. Glossary 누락 용어 (`Δ`, "상위 10%", "≥70%")
7. References 빈약 (Wolfram CA, Karafyllidis & Thanailakis 같은 화재 CA 표준 인용 추가 권장)
8. §2.1 Use case diagram 본문 설명 한 줄뿐

🟢 **polish:** Revision History 한 줄, UC 표 Author/Date 빈칸 등.

### 권장 10개 클래스 통합안 (이미 사용자에게 제시됨)

1. **User** (role: `COMMANDER` | `FIELD_OPERATOR` enum) ← User/Commander/FieldOperator 3개 통합
2. Building
3. **Floor** (cells 를 2D 행렬 속성으로 흡수) ← Floor + Cell + Material 통합
4. FireSafetyEquipment (type enum: sprinkler/shutter/exit/vent)
5. Report
6. SimParameters (boolean 4개)
7. CAEngine (단일 회차)
8. EnsembleRunner (CAEngine 반복)
9. EnsembleResult
10. DatabaseManager

(Scenario 클래스는 `(SimParameters, EnsembleResult)` 페어로 표현 가능해서 제거)

---

## 3. Prototype 코드 상태 (이미 구현 완료)

### 위치
- 작업본 (worktree): `/Users/iseungmin/Documents/오픈소스SW설계/.claude/worktrees/nervous-davinci-c11535/firewatch_prototype/`
- 본 프로젝트 사본 (rsync 됨): `/Users/iseungmin/Documents/오픈소스SW설계/firewatch_prototype/`
- 둘은 동기화 상태. 작업 후 본 폴더에도 sync 해야 함.

### 실행

```bash
cd "/Users/iseungmin/Documents/오픈소스SW설계"
python3 -m firewatch_prototype.main
```

의존성: Python 3.10+, PyQt6, numpy.
폰트: `brew install --cask font-ibm-plex-sans-kr font-ibm-plex-mono` (사용자 이미 설치 완료)

### 파일 구조

```
firewatch_prototype/
├── main.py                 QApplication 진입점, theme.qss 로드, IBM Plex 폰트 우선
├── theme.qss               다크 테마 (배경 #0d1117, 강조 #10b981)
├── PROTOTYPE_STATUS.md     팀장 Claude 가 코드 리뷰할 때 읽는 문서
├── HANDOFF_FOR_PROMPT_WRITER.md   ← 이 파일
├── mock/
│   ├── buildings.py        건물 4개 (BLDG001~004) + Equipment dataclass + find_building()
│   ├── floorplan_gen.py    셀맵 생성기 (OUTSIDE/ROOM/WALL/WALL_WEAK), SPREAD_COST, PROB_CAP
│   └── simulator.py        generate_ensemble() — CA가 아닌 closed-form mock
├── views/                  화면별 위젯 (UC 매핑)
│   ├── main_window.py      MainWindow + TopBar + Sidebar + ScreenSpec
│   ├── report_input.py     UC1+UC2
│   ├── parameters.py       UC3 (체크박스 4개만, 슬라이더 제거됨)
│   ├── simulation.py       UC4 (mock progress 3.6초)
│   ├── heatmap.py          UC5+UC6+UC7
│   ├── section.py          UC8
│   ├── summary.py          UC9
│   └── comparison.py       UC10
└── widgets/                재사용 그래픽 위젯
    ├── floorplan.py        FloorplanGrid (입력용, ignition 클릭)
    ├── heatmap_grid.py     HeatmapGrid + heat_color() 함수
    ├── colorbar.py         HeatmapColorbar (가로 그라데이션 범례)
    ├── section_diagram.py  SectionDiagram (층별 스택)
    ├── charts.py           LineChart + FloorBars
    └── delta_grid.py       DeltaGrid (diverging color, 비교 화면용)
```

UC11 (Reset Simulation) 은 `MainWindow._handle_reset_request()` 에서 `QMessageBox` 로 처리. 별도 화면 아님.

### 화면별 상태

| UC | 화면 | 파일 | 상태 |
|---|---|---|---|
| UC1+UC2 | 신고 입력 | `views/report_input.py` | 완료 |
| UC3 | 파라미터 | `views/parameters.py` | 완료 (4 boolean만) |
| UC4 | 시뮬레이션 | `views/simulation.py` | mock — 30회차 progress bar |
| UC5+6+7 | 히트맵 | `views/heatmap.py` | 완료 |
| UC8 | 단면도 | `views/section.py` | 완료 (위험 텍스트 태그 없음, 그라데이션만) |
| UC9 | 요약 | `views/summary.py` | 완료 |
| UC10 | 비교 | `views/comparison.py` | 완료 |
| UC11 | 초기화 | main_window 내부 | 완료 |

---

## 4. Mock simulator 의 진실 (반드시 알아둘 것)

`mock/simulator.py` 의 `generate_ensemble()` 은 **CA 가 아니다.** 다음 closed-form 공식이다:

1. Dijkstra 그리드 거리 (발화 셀 → 모든 셀, 비용: ROOM=1, WALL_WEAK=2, WALL=4, OUTSIDE=차단)
2. 가우시안 `exp(-d² / (2·radius_t²))` — radius 가 시간에 따라 선형 증가 `1.0 + t·0.7`
3. 층간 falloff `exp(-|f - 발화층| / 1.6)`
4. 파라미터 스칼라 곱 `_suppression_factor()`:
   - 스프링클러 ×0.55
   - 방화셔터 ×0.85
   - 환기 ×1.10
   - 비상문 닫힘 ×1.03
5. 재질 캡 (`PROB_CAP`): WALL 0.40, WALL_WEAK 0.95, ROOM 1.00, OUTSIDE 0.00
6. 작은 가우시안 노이즈

**중요**: UI 에 보이는 "회차 N/30" 카운터는 진짜 앙상블이 아니라 progress bar 일 뿐. `generate_ensemble()` 은 한 번만 호출된다.

이 사실은 `Prototype Spec` 에 명시되어 있다 — "실제 시뮬레이션 엔진은 구현하지 않음 (mock data 사용)". Implementation 단계에서 진짜 CA + 진짜 앙상블로 교체될 예정.

---

## 5. 셀 타입 시스템 (재질 정책)

`mock/floorplan_gen.py` 에 정의:

| 상수 | 값 | 의미 | 확산 비용 | 확률 캡 |
|---|---|---|---|---|
| `OUTSIDE` | 0 | 건물 밖 (외부 공간) | 차단 | 0.00 |
| `ROOM` | 1 | 실내 (가연성) | 1 | 1.00 |
| `WALL` | 2 | 구조벽 (콘크리트/철골) | 4 | **0.40** |
| `WALL_WEAK` | 3 | 비구조 칸막이 (석고/유리) | 2 | 0.95 |

**원칙**: 구조벽은 전소돼도 살아남는다 (PROB_CAP=0.40 으로 캡). 단 WALL_WEAK 는 예외로 무너질 수 있다 (PROB_CAP=0.95). 사용자가 명시적으로 요청한 요구사항.

BLDG004 (창고) 의 서편 사무실 칸막이가 WALL_WEAK 로 지정돼 있어 시연 가능.

---

## 6. 디자인 제약 (절대 위반하지 말 것)

사용자는 **"Claude스러운 디자인"** 에 매우 민감하다. 다음을 지켜야 함:

### 절대 금지
- 이모지 (UI 텍스트, 코드 주석, 마크다운 문서 어디에도)
- 보라/파스텔 그라데이션
- 둥근 카드 / 부드러운 그림자 / glassmorphism
- "Welcome to FireWatch!" 같은 친근한 환영 메시지
- 라이브 시계, 중복 모드 표시 같은 장식성 chrome (사용자 명시 요청으로 상태바 통째 제거됨)
- `// COMMENT-STYLE` 같은 telemetry 텍스트
- `01 02 03` 같은 zero-padded 번호 prefix
- ALL CAPS + letter-spacing 으로 sci-fi 흉내
- 데코러티브 부제목 (`CA-ENSEMBLE FIRE PROPAGATION FORECAST · v0.1` 같은 거)

### 따라야 할 톤
- 다크 테마: 배경 `#0d1117`, 패널 `#161b22`
- 강조색은 시안그린 `#10b981` **한 가지만**
- 위험도 그라데이션은 **히트맵·단면도에만**: 회색 `#4a4a4a` → 주황 `#f59e0b` → 빨강 `#dc2626`
- Δ (delta) 색상: 파랑 `#2563eb` ← 회색 → 빨강 (diverging)
- 폰트:
  - 시스템(UI 라벨): `IBM Plex Sans KR`
  - 모노스페이스(좌표/시각/수치): `IBM Plex Mono`
  - **모노는 데이터에만** — 메뉴/라벨에 모노 쓰지 말 것
- 1px 보더 `#30363d`, border-radius 작게 (Qt 기본은 그대로 둠 — 사용자가 둥근 거 OK 라고 했음)
- 정보 밀도 높게 (NASA mission control 톤)

### 분석 단계에서 결정된 제약
- **SimParameters 는 4 boolean 만**: `sprinkler`, `shutter`, `exit_closed`, `vent`
- 외기 온도·풍속 제거됨 (실내 화재 도메인에 부적합 — 환기 시스템이 그 자리 대체)
- 단면도/히트맵은 **이산 분류 텍스트 태그 없이 그라데이션만**으로 위험도 표현 ("위험" 라벨 같은 거 X)
- 로그에서 "CA Engine" 같은 구체 클래스명 외부 노출 자제 (예: "시뮬레이션 엔진 초기화")

---

## 7. 사용자 커뮤니케이션 패턴

### 사용자가 자주 쓰는 표현
- "ㅇㅇ" / "진행" = "다음 단계 진행해" (앞 작업 OK 의미)
- "이거 ___ 야?" = 질문 — 답하면서 명확히 짚어줄 것
- "근데" / "단" = 조건 / 제약 / 반대 의견 추가
- "강구" = "방안을 마련해/제안해"
- 짧고 모호한 한국어로 지시 → 너의 역할은 정확히 풀어내는 것

### 사용자가 좋아하는 것
- 단계적·점진적 변경 (한 번에 다 하지 말 것)
- 변경 후 `git diff` 형식 요약
- 변경 후 검증 결과 (numpy 출력, 컴파일 체크 등)
- 파일 경로 + 줄 번호 명시
- 영어/한국어 혼용 OK (코드는 영어, 설명은 한국어)

### 사용자가 싫어하는 것
- 시키지도 않은 추가 기능 만들기
- 시키지도 않은 .md 문서 만들기 (`Write` 도구로 새 마크다운 만들 때 신중할 것)
- 작업 후 장황한 자랑조 설명
- "추가로 X도 했습니다 ✨" 같은 톤

---

## 8. 자주 쓰는 명령어

```bash
# 컴파일 체크 (가장 먼저 할 것)
python3 -m py_compile firewatch_prototype/views/*.py firewatch_prototype/widgets/*.py firewatch_prototype/mock/*.py

# 시뮬레이터 sanity check
python3 -c "
from firewatch_prototype.mock.buildings import BUILDINGS
from firewatch_prototype.mock.simulator import generate_ensemble
from firewatch_prototype.mock.floorplan_gen import get_layout, ROOM
import numpy as np
b = BUILDINGS[0]
m = get_layout(b.id)
ys, xs = np.where(m == ROOM)
e = generate_ensemble(b, '2F', (int(xs[len(xs)//2]), int(ys[len(ys)//2])))
print('shape', e.shape, 'max', float(e.max()))
"

# Worktree → 본 폴더 sync
rsync -a --delete --exclude='__pycache__' \
  "/Users/iseungmin/Documents/오픈소스SW설계/.claude/worktrees/nervous-davinci-c11535/firewatch_prototype/" \
  "/Users/iseungmin/Documents/오픈소스SW설계/firewatch_prototype/"

# 실행 (PyQt GUI)
cd "/Users/iseungmin/Documents/오픈소스SW설계" && python3 -m firewatch_prototype.main
```

---

## 9. 다음 작업 후보 (사용자가 시킬 가능성 높은 것)

### A. Analysis 문서 수정 (제출 임박)
- §3 클래스 다이어그램 그리기 (draw.io, PNG export)
- §3 텍스트 15 → 10 으로 재작성 (위 §2의 통합안 적용)
- §2.1.2 권한 매트릭스 추가 또는 §4.10 인용 삭제
- §5 Glossary 에 Δ, 상위 10%, 70% 임계 추가
- §6 References 확장

### B. Prototype 미세 조정
- 새 화면이나 새 기능 추가 (사용자가 요청 시)
- 디자인 톤 더 조정
- mock 시뮬레이션 동작 변경

### C. Implementation 단계 준비
- 진짜 CA 엔진 설계 (별도 모듈로)
- 진짜 앙상블 실행기 (multiprocessing?)
- DB schema 설계

---

## 10. 프롬프트 작성 시 체크리스트

작업자 Claude 에게 던질 프롬프트를 짤 때 다음 포함 권장:

1. **파일 경로** (절대 경로 또는 worktree 기준 상대 경로)
2. **변경 단위** — 한 번에 하나의 논리적 변경만
3. **변경 전후 상태** (예시 코드 또는 의도)
4. **검증 방법** — 컴파일 체크 / 함수 실행 / 출력 비교
5. **본 폴더 sync** 잊지 말 것 (위 §8 rsync 명령)
6. **기존 디자인 제약 위반 금지 명시** (특히 새 UI 추가 시 — §6 다시 한 번 강조)

작업 결과는:
- diff 형식 요약
- 검증 결과 (출력 또는 OK)
- 본 폴더 sync 완료 확인

이 세 가지를 반드시 사용자에게 보여줘야 함.

---

## 11. 워크플로우 메타

### git 상태
- 브랜치: `claude/nervous-davinci-c11535` (worktree 전용)
- main 에는 아직 머지 안 됨
- 사용자가 커밋·머지 결정함. 작업자 Claude 가 임의로 커밋하지 말 것

### 메모리 (Claude harness)
사용자의 user-memory 에 등록된 것:
- `feedback_ui_chrome.md` — "장식성 UI chrome 피하기, 상태바 기본 추가 X, 라이브 시계 X, 중복 표시 X"

이건 harness 가 자동 주입하므로 작업자 Claude 는 이 메모리를 받게 됨.

---

## 12. TL;DR (한 줄로)

**FireWatch 는 화재 신고 → 확률 분포 형태 확산 예측을 주는 시뮬레이터. PyQt6 데스크톱 프로토타입은 완성 (UC11 까지 + 4건물 평면도 + 재질 캡), 시뮬레이터는 CA가 아닌 closed-form mock. 지금 사용자는 Analysis 문서 (15클래스→10통합, 클래스 다이어그램 추가, 권한 매트릭스 추가)를 마무리하는 중. 디자인은 NASA mission control 톤 + IBM Plex + 다크. 사용자는 "Claude스러운" 장식적 UI 매우 싫어함.**
