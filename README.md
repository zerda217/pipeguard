# pipeguard

![CI](https://github.com/zerda217/pipeguard/actions/workflows/ci.yml/badge.svg)

**배치 파이프라인용 데이터 품질 게이트.** YAML로 품질 규칙을 선언하면, 위반 시 0이 아닌 종료 코드를 반환해 다음 단계(적재·배포·마트 갱신)를 멈춥니다.

```
pipeguard · examples/orders_bad.csv · 200 rows · 9 checks

  PASS  daily_volume            200 rows, expected [100, 100000]
  PASS  order_id_present        0 nulls (0.00%), allowed 0.00%
  FAIL  order_id_unique         1 duplicate rows on order_id  sample=['O00003']
  PASS  user_id_mostly_present  1 nulls (0.50%), allowed 1.00%
  FAIL  amount_in_range         2 values outside [0, 10000]  sample=[-12.5, 98000.0]
  FAIL  known_country           1 values not in allowed set (1 distinct)  sample=['XX']
  PASS  known_status            0 values not in allowed set (0 distinct)
  PASS  data_is_fresh           latest 2026-10-26T22:54:00+00:00 is 1.1h old, allowed 24h
  WARN  shipped_after_ordered   1 rows violate 'shipped_at.isna() | (shipped_at >= ordered_at)'  sample=['row 0']

Result: FAILED (3 error(s), 1 warning(s)) -> exit 1
```

## 왜 만들었나

데이터 파이프라인 장애의 상당수는 "에러 없이 잘못된 데이터가 끝까지 흘러가는" 형태입니다. 빈 배치, 중복 키, 음수 금액, 하루 늦은 데이터는 쿼리를 실패시키지 않고 대시보드 수치만 조용히 틀어지게 만듭니다.

pipeguard는 이 문제를 **배치 사이의 관문**으로 해결합니다. 규칙은 코드가 아니라 설정(YAML)에 두어 리뷰와 변경 이력 관리가 쉽고, 결과는 종료 코드로 표현해 cron, Airflow, Cloud Run Job, GitHub Actions 어디서든 그대로 쓸 수 있습니다.

## 빠른 시작

```bash
pip install git+https://github.com/zerda217/pipeguard
pipeguard run examples/orders.yaml --as-of 2026-10-26T23:59:00+00:00
```

로컬 개발:

```bash
pip install -e ".[dev]"
pytest
```

Google Colab에서는 셀 하나로 돌려볼 수 있습니다.

```python
!git clone https://github.com/zerda217/pipeguard && pip install -q -e pipeguard
!cd pipeguard && pipeguard run examples/orders.yaml --data examples/orders_bad.csv --as-of 2026-10-26T23:59:00+00:00
```

## 설정

```yaml
version: 1

dataset:
  path: orders.csv                 # 설정 파일 기준 상대 경로. csv / jsonl / parquet
  parse_dates: [ordered_at]        # 날짜로 읽을 컬럼

checks:
  - name: order_id_unique          # 생략 시 "unique:order_id" 형태로 자동 생성
    type: unique
    columns: order_id
    severity: error                # error(기본) | warn
```

### 체크 7종

| type | 파라미터 | 실패 조건 |
|---|---|---|
| `not_null` | `column`, `[max_ratio]` | 결측 비율이 `max_ratio`(기본 0) 초과 |
| `unique` | `columns` (단일 또는 목록) | 키 중복 행 존재 |
| `range` | `column`, `[min]`, `[max]` | 값이 범위 밖이거나 숫자가 아님 |
| `allowed_values` | `column`, `values` | 허용 목록 밖의 값 존재 |
| `freshness` | `column`, `max_age` (`30m`, `24h`, `7d`) | 최신 시각이 `max_age`보다 오래됨 |
| `row_count` | `[min]`, `[max]` | 행 수가 범위 밖 |
| `expression` | `expr` (pandas 불리언 식) | 식을 만족하지 않는 행 존재 |

값 검사(`range`, `allowed_values`)는 결측을 무시합니다. 결측은 `not_null`이 전담해서, 문제 하나가 체크 하나로만 보고되도록 했습니다.

### CLI

```
pipeguard run CONFIG [--data PATH] [--json-out FILE] [--fail-on-warn] [--as-of ISO8601]
pipeguard validate CONFIG      # 데이터를 읽지 않고 설정만 검증
pipeguard list-checks
```

### 종료 코드

| 코드 | 의미 | 스케줄러에서의 처리 |
|---|---|---|
| 0 | 통과 (warn은 있을 수 있음) | 다음 단계 진행 |
| 1 | error 체크 실패 | 다음 단계 중단, 데이터 확인 |
| 2 | 설정 오류 | 규칙 수정 필요. 데이터 문제 아님 |
| 3 | 데이터 로드 실패 | 상류 적재 확인 |

실패 원인을 코드로 구분해 두면, 알림을 받는 순간 "데이터 문제인지, 규칙 문제인지, 상류 장애인지"를 바로 나눌 수 있습니다.

## 설계 결정

**설정 검증은 데이터 로드 전에 끝낸다.** 모르는 체크 타입, 빠진 파라미터, 오타(`colum`), 잘못된 기간 표기는 모두 데이터를 읽기 전에 종료 코드 2로 걸러집니다. 수십 GB를 읽은 뒤에 규칙 오타로 실패하는 일을 막기 위해서입니다.

**실패 시 닫힌다 (fail closed).** 참조한 컬럼이 없거나 체크 함수가 예외를 던지면 해당 체크는 실패로 처리됩니다. 검사가 돌지 못했는데 통과로 보이는 상황이 품질 게이트에서 가장 위험하기 때문입니다.

**체크 하나가 실패해도 나머지는 모두 실행한다.** 첫 실패에서 멈추면 고치고 다시 돌리는 일을 여러 번 반복하게 됩니다. 한 번의 실행으로 문제 전체를 보여줍니다.

**severity로 차단과 경고를 분리한다.** 모든 규칙을 차단 조건으로 걸면 게이트가 너무 자주 멈추고, 결국 아무도 신경 쓰지 않게 됩니다. 새 규칙은 `warn`으로 넣어 관찰한 뒤 `error`로 승격하는 운영을 전제로 했고, 엄격한 환경에서는 `--fail-on-warn`으로 경고도 차단할 수 있습니다.

**기준 시각을 주입할 수 있다.** `freshness`는 "지금"에 의존하는데, `--as-of`로 기준 시각을 넘기면 과거 날짜 재처리(backfill)와 테스트가 재현 가능해집니다.

## 체크 추가하기

체크는 `(df, params, ctx) -> CheckOutcome` 함수 하나입니다. 레지스트리에 파라미터 정의와 함께 등록하면 설정 검증, CLI 목록, 리포트에 자동으로 포함됩니다.

```python
from pipeguard import CheckOutcome, register

@register("positive", required=("column",))
def positive(df, params, ctx):
    """All values must be greater than zero."""
    bad = df[params["column"]] <= 0
    return CheckOutcome(passed=not bad.any(), failed_count=int(bad.sum()),
                        message=f"{int(bad.sum())} non-positive values")
```

## 구조

```
src/pipeguard/
  registry.py   체크 플러그인 레지스트리, 파라미터 명세
  checks.py     내장 체크 7종
  config.py     YAML 로딩과 사전 검증
  loader.py     csv / jsonl / parquet 로딩
  runner.py     체크 실행, fail-closed 처리
  report.py     텍스트·JSON 리포트
  cli.py        run / validate / list-checks
examples/       합성 주문 데이터(정상·오염)와 규칙 예시
tests/          pytest
```

CI는 Python 3.10~3.13에서 테스트를 돌린 뒤, 정상 데이터는 통과하고 오염 데이터는 차단되는지 실제 CLI로 확인합니다.

## 다음 단계

이 게이트의 구조(체크 레지스트리, severity, 종료 코드)를 LLM 출력 평가로 확장하는 **llm-eval-gate**를 준비하고 있습니다.

## License

MIT
