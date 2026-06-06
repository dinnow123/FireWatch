# FireWatch Prototype — 작업 상태 보고

> 분석 단계 UI prototype 산출물. PyQt6 데스크톱 앱. 실 시뮬레이션 엔진은 구현하지 않음 — mock data 기반 시연용.

---

## 1. 목적과 범위

`FireWatch_Prototype_Spec.md` 명세에 따라 만든 **분석 단계 채점용 시연 데모**. UC1~UC11에 해당하는 7개 핵심 화면을 동작하는 데스크톱 앱으로 구현했다. 이후 Implementation 단계에서 진짜 CA 엔진과 데이터베이스 연동이 필요하다.

**구현 안 한 것:**
- 진짜 확률적 셀룰러 오토마타 엔진 (Conceptualization 단계 문서에서 약속한 것)
- 실제 앙상블 (20~50회) — UI에서 카운터로만 흉내냄
- 데이터베이스 연동 — 건물 데이터는 Python 상수로 하드코딩
- IoT 센서 연동, 데이터 어시밀레이션 — 명세상 추후 단계

---

## 2. 실행

```bash
cd "/Users/iseungmin/Documents/오픈소스SW설계"
python3 -m firewatch_prototype.main
```

의존성: Python 3.10+, PyQt6, numpy. 폰트: IBM Plex Sans KR + IBM Plex Mono (`brew install --cask font-ibm-plex-sans-kr font-ibm-plex-mono`).

---

## 3. 디렉토리 구조

```
firewatch_prototype/
├── main.py                 QApplication 진입점, 폰트 설정, theme.qss 로드
├── theme.qss               다크 테마 스타일시트 (전부)
├── mock/
│   ├── buildings.py        건물 4개 + 검색 함수
│   ├── floorplan_gen.py    셀타입 맵 생성 (OUTSIDE/ROOM/WALL/WALL_WEAK)
│   └── simulator.py        Mock 앙상블 생성기 (CA 아님 — 4절 참조)
├── views/                  화면별 위젯 (각 UC 매핑)
│   ├── main_window.py      메인 윈도우 + 사이드바 + 모드 토글 + 상태 보관
│   ├── report_input.py     UC1 신고 입력 + UC2 건물 로드
│   ├── parameters.py       UC3 파라미터 설정
│   ├── simulation.py       UC4 시뮬레이션 실행 (mock progress)
│   ├── heatmap.py          UC5 히트맵 + UC6 층 전환 + UC7 시간 조작
│   ├── section.py          UC8 단면도
│   ├── summary.py          UC9 결과 요약
│   └── comparison.py       UC10 시나리오 비교
└── widgets/                재사용 가능한 그래픽 위젯
    ├── floorplan.py        평면도 그리드 (입력용, ignition 클릭)
    ├── heatmap_grid.py     히트맵 그리드 (heat_color 함수 포함)
    ├── colorbar.py         가로 컬러바 범례
    ├── section_diagram.py  단면도 (층별 직사각형 스택)
    ├── charts.py           LineChart + FloorBars (custom QPainter)
    └── delta_grid.py       Δ 그리드 (diverging color, 비교 화면용)
```

UC11 (Reset Simulation)은 별도 화면이 아니라 [main_window.py](views/main_window.py)의 `_handle_reset_request()` 에서 `QMessageBox` 다이얼로그로 처리.

---

## 4. Mock simulator 정확히 무엇인가

**[mock/simulator.py](mock/simulator.py) 의 `generate_ensemble()` 은 CA 가 아님.** 다음을 한 번 수행한다:

1. Dijkstra 그리드 거리 — 발화 셀에서 ROOM=비용 1, WALL=비용 4, WALL_WEAK=비용 2, OUTSIDE=차단
2. 가우시안 `exp(-d² / (2·radius_t²))`, radius 가 시간에 따라 선형 증가 (`1.0 + t·0.7`)
3. 층간 falloff `exp(-|f - 발화층| / 1.6)`
4. 파라미터 스칼라 곱 (`_suppression_factor`)
5. 재질 캡 (`PROB_CAP` from floorplan_gen.py): WALL 0.40, WALL_WEAK 0.95, ROOM 1.00, OUTSIDE 0.00
6. 작은 가우시안 노이즈

따라서 출력은 **결정론적 closed-form 공식**의 결과이며, "셀 상태 전이 규칙" 이나 "앙상블 평균" 같은 CA 의 핵심 요소는 없다. UI 의 `회차 N/30` 카운터는 progress bar 일 뿐 — 함수는 한 번만 호출된다.

이 사실은 [Prototype Spec §0](../FireWatch_Prototype_Spec.md) 에서 명시 — "실제 시뮬레이션 엔진은 구현하지 않음 (mock data 사용)".

### 4.1 셀 타입 + 재질 정책

[mock/floorplan_gen.py](mock/floorplan_gen.py) 에서:

| 타입 | 의미 | 확산 비용 | 확률 캡 |
|---|---|---|---|
| `OUTSIDE = 0` | 건물 밖 | 차단 | 0.00 |
| `ROOM = 1` | 실내 | 1 | 1.00 |
| `WALL = 2` | 구조벽 (콘크리트/철골) | 4 | **0.40** |
| `WALL_WEAK = 3` | 비구조 칸막이 (석고/유리) | 2 | 0.95 |

원칙: **구조벽은 전소돼도 살아남는다.** 단 재질 따라 예외 허용 (WALL_WEAK). BLDG004 창고의 서편 사무실 칸막이가 WALL_WEAK 로 지정돼 있어서 시연 가능.

### 4.2 파라미터 영향

분석 문서 SimParameters 정의에 맞춰 4개 boolean 만 입력 받는다 (sprinkler / shutter / exit_closed / vent). 외기 온도·풍속은 실내 화재 도메인에 부적합하다고 판단되어 제외 — 환기 시스템이 기능적으로 그 자리를 대체.

`_suppression_factor()`:
- 스프링클러 ×0.55, 방화셔터 ×0.85, 환기 ×1.10, 비상문 닫힘 ×1.03

기준 vs 비교 시 평균 Δ ≈ ±15~20% 정도 차이 만들도록 튜닝.

---

## 5. 화면별 상태

| UC | 화면 | 파일 | 상태 | 비고 |
|---|---|---|---|---|
| UC1+UC2 | 신고 입력 | [report_input.py](views/report_input.py) | 완료 | 주소 검색 → 건물 정보 표시 → 평면도에서 발화점 클릭 |
| UC3 | 파라미터 | [parameters.py](views/parameters.py) | 완료 | 4 boolean 체크박스 (sprinkler/shutter/exit/vent) |
| UC4 | 시뮬레이션 | [simulation.py](views/simulation.py) | mock | 30회차 progress bar (~3.6초). 실제 연산 없음 |
| UC5+6+7 | 히트맵 | [heatmap.py](views/heatmap.py) | 완료 | 층 탭 + 시간 슬라이더, 호버 좌표/확률, 컬러바 범례 |
| UC8 | 단면도 | [section.py](views/section.py) | 완료 | 층별 상위 10% 평균, 그라데이션 색상으로만 위험도 표현 (이산 분류 텍스트 태그 없음) |
| UC9 | 요약 | [summary.py](views/summary.py) | 완료 | 4 stat + 시계열 line chart + 층별 bar chart |
| UC10 | 비교 | [comparison.py](views/comparison.py) | 완료 | 좌우 히트맵 + 하단 Δ 그리드, 진입 시 자동 반대값 세팅 |
| UC11 | 초기화 | main_window 내부 | 완료 | 다이얼로그 → 메모리 상태 초기화 |

---

## 6. 상태 흐름

`MainWindow` 가 4개 보관:
- `_report: dict | None`
- `_parameters: dict | None`
- `_ensemble: np.ndarray | None`        — base 시뮬 결과 (F, T, R, C)
- (`comparison_view._compare_ensemble`)  — 비교 시뮬 결과 (별도)

```
신고 입력 → reportSubmitted ─► _report 저장 → 파라미터 화면
파라미터 → parametersSaved ─► _parameters 저장 → 시뮬레이션 화면
시뮬레이션 → simulationFinished ─► generate_ensemble() 호출, _ensemble 저장
                                  → 모든 결과 화면에 set_context() 푸시
                                  → 히트맵 화면 자동 전환
사이드바 클릭 → _on_screen_selected(key) ─► 해당 화면에 set_context() 다시 푸시
초기화 → _handle_reset_request() ─► 다이얼로그 → 모든 상태 None → 신고 입력 복귀
```

각 결과 화면은 `set_context(report, ensemble)` (또는 `set_context(report, params, ensemble)` for comparison) 한 메서드로 전체 갱신. 데이터가 없을 땐 `시뮬레이션 결과 없음` 안내 표시.

---

## 7. 모드 토글 (Commander / Field Operator)

상단바의 라디오 토글로 전환. Field Operator 모드일 때 `commander_only=True` 인 사이드바 항목(`신고 입력 / 파라미터 / 시뮬레이션 / 비교 / 초기화`)이 회색 비활성화되며, 사이드바 상단에 `읽기 전용 모드` 배너가 뜬다. 이는 UC 권한 매트릭스의 시각적 demo.

`Sidebar.apply_mode()` 가 모든 처리를 한다 — 별도 페이지 생성 없이 같은 인스턴스를 재사용한다.

---

## 8. 디자인 결정 요약

- **다크 테마** `#0d1117` (배경) / `#161b22` (패널) / `#10b981` (강조 단일색)
- **모노 폰트는 데이터에만** — 좌표, 시각, 통계 수치. 메뉴/라벨은 sans
- **그라데이션은 위험도 시각화에만** (회색→주황→빨강 / Δ는 파랑→회색→빨강)
- **벽이 있는 평면도** — 건물이 격자 전체를 채우지 않음. 외부 여백 + 내부 벽으로 실제 평면도처럼 보이게
- **Claude 느낌 제거** (개발 중 사용자 요청 누적):
  - 상태바 통째 제거 (`REPORT/SIM/RUNS/MODE/CLOCK`)
  - 사이드바 navigation 헤더 제거, `01 02 03` 번호 prefix 제거
  - 상단 `CA-ENSEMBLE FIRE PROPAGATION FORECAST · v0.1` subtitle 제거
  - `// SCREEN [X] NOT YET WIRED` 같은 telemetry 텍스트 제거
  - 입력 라벨 모노/letter-spacing → 일반 sans

---

## 9. Implementation 단계로 넘기는 작업 목록

prototype 에서 mock 으로 처리하고 있어서 다음 단계에서 본격 구현이 필요한 항목:

1. **진짜 CA 엔진** — `generate_ensemble()` 자리에 들어가야 함. 시그니처는 유지하면 UI 손댈 필요 없음 (`(building, ignition_floor, ignition_xy, parameters) -> (F, T, R, C) ndarray`)
2. **앙상블 — 진짜로 N회 돌리기** — 현재는 한 번만. 회차마다 다른 시드로 돌려서 평균/분산 도출
3. **데이터베이스** — `mock/buildings.py` 의 4개 상수 → 실제 DB 조회 (UC2 의 정상/비정상 분기 처리)
4. **건물별 평면도 데이터 모델** — 현재 `floorplan_gen.py` 가 procedural generation. 실제로는 DB 에 셀맵 저장해야 함
5. **소방 설비 데이터** — 위치만 정의되어 있고 시뮬레이션에 반영 안 됨. CA 엔진에서 셀 단위로 영향 줘야 함
6. **시뮬레이션 시간 단위** — 현재 1 step = 30 초로 고정. CA 엔진의 dt 와 일치시켜야 함
7. **시나리오 비교 — 두 결과 동시 보관** — 현재는 메모리에 base + compare 따로 들고 있음. 디스크 저장 / 재로드 필요시 직렬화 필요
8. **UC8 단면도 — 상위 10% 평균** 정의는 단순 통계. CA 결과에서도 동일 메트릭이 의미 있는지 검증 필요

---

## 10. 알려진 제약 (prototype 이라 안 한 것)

- 시뮬레이션 도중 사이드바 클릭하면 진행 중인 mock progress 가 강제 정지 (자동 정리 안 함)
- 비교 화면에서 `비교 실행` 후 사이드바로 빠져나가면 비교 결과 휘발 (메모리에서 사라짐)
- 평면도 grid 는 셀당 1m × 1m 라고 가정 — 실제 건물 스케일 반영 안 됨
- 입력 검증 약함: 발화 시각이 미래여도 거부 안 함, 주소 검색은 substring match
- 윈도우 리사이즈 시 평면도 그리드의 cell 크기 동적 계산하지만 폰트 크기는 고정

---

## 11. 파일 위치

작업본은 git worktree:
```
/Users/iseungmin/Documents/오픈소스SW설계/.claude/worktrees/nervous-davinci-c11535/firewatch_prototype/
```

본 프로젝트 폴더 (rsync 로 복사됨):
```
/Users/iseungmin/Documents/오픈소스SW설계/firewatch_prototype/
```

git 브랜치 `claude/nervous-davinci-c11535` 에는 아직 커밋 안 됨. 본 폴더 쪽도 git 미반영 상태. 머지/커밋은 사용자가 직접 결정할 사항으로 남김.
