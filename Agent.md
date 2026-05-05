# Codex Agent Notes

이 문서는 다른 Codex 세션이 이 프로젝트에 바로 합류할 수 있도록 남기는 작업 메모입니다. 코드보다 운영 안전성과 확장 방향을 먼저 이해하는 것이 중요합니다.

## 프로젝트 개요

이 프로젝트는 운영/요청 로그를 읽고, 문제 원인 후보를 추론한 뒤, 사람이 검토할 수 있는 수정 방향과 예시 코드를 제안하는 Python + FastAPI 기반 MVP입니다.

핵심 원칙:

- 운영 코드 자동 수정 금지
- git push, merge, deploy 자동 수행 금지
- 운영 환경 쓰기 작업 금지
- 결과는 항상 "수정 제안"으로 취급
- 불확실한 경우 단정하지 말고 원인 후보와 confidence로 표현
- 재현 방법, 영향 범위, 수정 방향, 검증 방법을 함께 제안

## 현재 주요 기능

- `POST /analyze/text`: raw text 로그 분석
- `POST /analyze/file`: 로그 파일 업로드 분석
- `GET /health`: health check
- CLI: `python -m app.cli --file samples/error.log`
- Markdown report 생성
- FastAPI admin page: `/admin`
- Integration management page: `/admin/integrations`
- MongoDB 기반 탐지/설정 저장
- 프로젝트별 Observability Integration 등록
- 현재 실제 수집 fetcher는 Kibana
- Sentry는 integration type과 입력 shape은 열려 있지만 fetcher는 아직 미구현
- Integration type 선택에 따라 endpoint/resource field label, placeholder, help text가 변경됨
- Kibana integration은 `focus_fields`를 저장하며, fetcher가 `_source`에서 해당 필드만 `selected_fields` JSON으로 정리해 analyzer/LLM 입력에 사용
- LLM provider는 integration별로 설정 가능
- `custom` provider 선택 시에만 custom provider input 활성화

## 현재 도메인 모델 방향

초기에는 Kibana source 중심이었지만, 지금은 프로젝트별 integration 구조로 변경되었습니다.

개념:

- `Project`: 예시 `GOA`, `DOBO`
- `ProjectIntegration`: 프로젝트에 연결된 관측 도구 설정
- `IntegrationType`: `kibana`, `sentry`; 실제 fetcher는 현재 `kibana`만 구현
- `DetectionRecord`: LLM/rule 기반 분석 결과로 이상 징후라고 판단된 항목

중요 필드:

- `project_name`: 프로젝트명, 입력값은 uppercase normalize
- `integration_type`: `kibana` 등 관측 도구 종류
- `endpoint_url`: Kibana/Sentry/custom endpoint URL
- `resource_name`: Kibana data view 또는 추후 Sentry project slug 같은 리소스명
- `focus_fields`: Kibana `_source`에서 LLM 분석에 우선 사용할 dotted field path 목록
- `llm_provider`: `mock`, `openai`, `anthropic`, `gemini`, `azure-openai`, `bedrock`, `vertex-ai`, `openrouter`, `ollama`, `custom`
- `llm_model`: optional

## 핵심 파일

- `app/main.py`: FastAPI app 생성, repository/service/poller wiring
- `app/api/routes.py`: 로그 분석 API
- `app/api/admin.py`: admin UI/API 라우트
- `app/schemas/analysis.py`: 분석 결과 Pydantic schema
- `app/schemas/admin.py`: project/integration/detection schema
- `app/services/analysis_service.py`: analyzer 선택과 fallback orchestration
- `app/services/detection_service.py`: integration polling 결과 분석 및 detection 저장
- `app/repositories/admin_repository.py`: MongoDB/InMemory repository
- `app/integrations/base.py`: fetcher protocol과 fetch result 공통 타입
- `app/integrations/kibana.py`: Kibana log fetcher
- `app/integrations/registry.py`: integration type별 fetcher registry
- `app/workers/integration_poller.py`: background polling worker
- `app/templates/admin/index.html`: project 요약 및 최신 detection 화면
- `app/templates/admin/integrations.html`: project integration 등록/목록/토글 화면
- `app/templates/admin/detections.html`: 프로젝트별 detection 목록
- `app/static/admin.css`: admin style
- `tests/test_admin.py`: admin/project/integration 관련 핵심 테스트

## Disable 동작

`Disable`을 누르면 integration은 즉시 다음 상태가 되어야 합니다.

- `enabled = false`
- `last_status = "disabled"`
- `last_error = None`
- 이후 `poll-now` 및 background poll 대상에서 제외

`DetectionService.poll_integration`은 fetch/analysis/write 사이에 repository에서 최신 enabled 상태를 다시 확인합니다. 이렇게 해야 사용자가 disable한 직후 늦게 도착한 polling 결과가 `disabled` 상태를 다시 `ok`로 덮어쓰지 않습니다.

관련 테스트:

- `tests/test_admin.py::test_disable_integration_immediately_marks_status_disabled`

## 실행 방법

로컬 개발 환경:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

API 서버:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Admin:

```text
http://127.0.0.1:8000/admin
```

Integrations:

```text
http://127.0.0.1:8000/admin/integrations
```

Docker Compose:

```powershell
docker compose up --build
```

주의: 이전 세션에서 Docker Desktop Linux engine이 실행 중이지 않아 build 실행은 실패한 적이 있습니다. `docker compose config`는 정상 통과했습니다.

## 테스트와 검증

기본 검증:

```powershell
.\.venv\Scripts\python.exe -m compileall app
.\.venv\Scripts\python.exe -m pytest
docker compose config
```

현재 마지막 확인 결과:

- `pytest`: `13 passed`
- `compileall app`: 통과
- `docker compose config`: 통과

## 샘플 사용

실제 Kibana 없이 admin 흐름을 확인하려면:

- Project name: `GOA` 또는 `DOBO`
- Integration type: `kibana`
- Endpoint URL: `demo://local`
- Resource name: `db-*` 또는 `payments-*`
- Analyzer mode: `mock`
- LLM provider: `mock`

그 뒤 `Poll now`를 누르면 샘플 로그 기반 detection이 프로젝트별로 표시됩니다.

Integration type을 `sentry`로 선택하면 UI의 endpoint/resource 필드가 Sentry URL과 project slug 기준으로 바뀝니다. 다만 Sentry fetcher는 아직 없으므로 polling 시 fetcher 미구현 에러가 정상입니다.

Kibana focus fields 예시:

- `@timestamp`
- `log.level`
- `service.name`
- `message`
- `error.message`
- `error.stack_trace`
- `http.response.status_code`

Kibana fetcher는 위 field path들을 `_source`에서 추출해 `analysis_input_version: kibana.focus_fields.v1`, `focus_fields`, `selected_fields`, `missing_fields`를 포함한 JSON 문자열로 만든 뒤 `AnalysisService.analyze_text(...)`에 넘깁니다.

## LLM Provider 구조

현재 실제 LLM 호출은 stub/fallback 중심입니다.

- API 키가 없어도 `mock`/rule-based로 동작해야 합니다.
- 실제 OpenAI 등 provider 연결은 `app/analyzers/llm.py` 쪽 adapter를 확장합니다.
- source-level이 아니라 integration-level 설정을 사용합니다.
- `custom` 선택 시 custom provider명을 저장합니다.

## MongoDB 저장 구조

현재 collection:

- `project_integrations`
- `detections`

기존 `kibana_sources` 기반 코드는 새 구조로 이동했습니다. repository mapping에는 일부 legacy field fallback이 남아 있습니다.

## 브랜치/PR 메모

2026-05-05 기준 stacked PR 흐름:

- `codex/add-python-admin-mvp`: Python/FastAPI/Mongo/admin MVP 초기 구현
- `codex/project-integrations-admin`: Kibana source 중심 구조를 project integration 구조로 변경
- `codex/disable-integration-status`: disable 즉시 `disabled` 상태 전환 및 poll write guard 추가

PR base를 잡을 때는 아래처럼 쌓는 것이 자연스럽습니다.

- `codex/project-integrations-admin` base: `codex/add-python-admin-mvp`
- `codex/disable-integration-status` base: `codex/project-integrations-admin`

## 개발 시 주의점

- 이 프로젝트는 "제안 시스템"이며 운영 변경 시스템이 아닙니다.
- deploy, GitHub Actions, Slack 알림, 자동 PR 생성, 자동 코드 수정 기능은 아직 구현하지 않습니다.
- admin 이름은 Kibana 종속적으로 되돌리지 말고 `Observability`, `Integration`, `Project` 같은 범용 용어를 유지합니다.
- 새로운 관측 도구를 추가할 때는 `ProjectIntegration` 모델을 재사용하고 `IntegrationFetcherRegistry`에 fetcher를 추가합니다.
- integration 등록 UI는 `/admin/integrations`에 두고, `/admin` 홈은 프로젝트 요약/최신 탐지 중심으로 유지합니다.
- 테스트에서는 MongoDB 대신 `Settings(mongo_uri="memory://")`를 사용합니다.
- Windows 환경에서 `rg` 실행이 `Access is denied`로 실패한 적이 있으므로, 검색이 막히면 `Get-ChildItem | Select-String`을 사용합니다.
- `gh` CLI는 설치되어 있지 않았습니다. PR 생성은 GitHub compare URL을 사용했습니다.

## 추천 다음 작업

- Sentry fetcher adapter 추가
- Kibana 인증/header 설정 모델링
- 프로젝트별 detection filter API 추가
- detection severity/status filter 추가
- 실제 OpenAI provider adapter 구현
- 반복 발생 detection correlation 개선
