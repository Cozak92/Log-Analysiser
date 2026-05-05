# Log Analysis MVP

Python + FastAPI 기반의 안전한 로그 분석 MVP입니다. 이 프로젝트는 운영/요청 로그를 읽고, 가능한 원인 후보를 추론하고, 사람이 검토할 수 있는 수정 방향과 예시 코드를 제안합니다. 이 버전은 절대로 운영 코드를 자동 수정하거나 배포하지 않습니다.

## 프로젝트 목적

- 로그를 입력받는다.
- 문제 원인을 추론한다.
- 수정 방향과 예시 코드를 제안한다.
- 결과를 구조화된 JSON과 Markdown으로 보여준다.

## 범위

- 텍스트 로그 파일 업로드 API
- Raw text 직접 입력 API
- CLI 파일 입력 분석
- Rule-based 분석 + Mock analyzer fallback
- LLM provider 추상화 + OpenAI 스타일 stub adapter
- Markdown 리포트 생성
- 프로젝트별 Observability Integration 등록 및 10초 주기 polling
- Kibana integration 수집, 추후 Sentry 등 추가 가능한 fetcher registry 구조
- 로컬 실행용 Docker / docker-compose

## 비범위

- Git push, merge, PR 생성
- 운영 환경 쓰기 작업
- 자동 코드 수정
- 자동 배포
- Slack 알림
- GitHub Actions 연동
- 프론트엔드 UI

## 안전 원칙

- 결과는 항상 "제안"입니다.
- 자동 파일 overwrite는 하지 않습니다.
- 운영 환경 변경 모듈이나 deploy 모듈은 포함하지 않습니다.
- LLM이 없으면 로컬 heuristic 기반 결과로 안전하게 fallback 합니다.

## 디렉토리 구조

```text
.
├── app
│   ├── analyzers
│   ├── api
│   ├── integrations
│   ├── prompts
│   ├── repositories
│   ├── schemas
│   ├── services
│   ├── static
│   ├── templates
│   ├── utils
│   ├── workers
│   ├── cli.py
│   └── main.py
├── samples
├── tests
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## 실행 방법

### 1. 로컬 개발 환경

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .[dev]
```

### 2. API 서버 실행

```bash
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Admin page:

```bash
http://127.0.0.1:8000/admin
```

Project Integration 관리:

```bash
http://127.0.0.1:8000/admin/integrations
```

로컬에서 실제 Kibana 없이 흐름을 확인하려면 Integrations 메뉴에서 Project name에 `GOA` 또는 `DOBO`, Integration type에 `kibana`, Endpoint URL에 `demo://local`, Resource name에 `payments-*` 또는 `db-*`를 입력한 뒤 `Poll now`를 누르면 샘플 로그 기반 탐지 목록이 프로젝트별로 생성됩니다. Integration type을 `kibana` 또는 `sentry`로 바꾸면 입력해야 하는 endpoint/resource/focus field의 라벨과 도움말이 함께 변경됩니다.

Kibana integration은 `focus_fields`를 설정할 수 있습니다. 예: `@timestamp`, `log.level`, `service.name`, `message`, `error.message`, `error.stack_trace`, `http.response.status_code`. Fetcher는 Kibana `_source`에서 해당 필드만 뽑아 아래 형태의 JSON으로 정리한 뒤 analyzer/LLM 입력으로 보냅니다.

```json
{
  "analysis_input_version": "kibana.focus_fields.v1",
  "project": "GOA",
  "integration": {
    "type": "kibana",
    "resource_name": "db-*"
  },
  "focus_fields": ["@timestamp", "message", "error.stack_trace"],
  "selected_fields": {
    "message": "...",
    "error.stack_trace": "..."
  },
  "missing_fields": []
}
```

### 3. CLI 실행

```bash
.venv\Scripts\python.exe -m app.cli --file samples/null_reference.log --mode mock --report-out analysis_report.md
```

## API 사용 예시

### POST `/analyze/text`

```bash
curl -X POST http://127.0.0.1:8000/analyze/text ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"status=500\nAttributeError: 'NoneType' object has no attribute 'email'\",\"analyzer_mode\":\"mock\",\"include_report\":true}"
```

### POST `/analyze/file`

```bash
curl -X POST http://127.0.0.1:8000/analyze/file ^
  -F "file=@samples/db_timeout.log" ^
  -F "analyzer_mode=rule-based" ^
  -F "include_report=true"
```

### Admin API

```bash
curl http://127.0.0.1:8000/admin/api/summary
```

```bash
curl -X POST http://127.0.0.1:8000/admin/api/integrations ^
  -H "Content-Type: application/json" ^
  -d "{\"project_name\":\"GOA\",\"integration_type\":\"kibana\",\"endpoint_url\":\"demo://local\",\"resource_name\":\"db-*\",\"analyzer_mode\":\"mock\",\"llm_provider\":\"mock\",\"llm_model\":null}"
```

다른 프로젝트도 같은 shape으로 추가할 수 있습니다.

```bash
curl -X POST http://127.0.0.1:8000/admin/api/integrations ^
  -H "Content-Type: application/json" ^
  -d "{\"project_name\":\"DOBO\",\"integration_type\":\"kibana\",\"endpoint_url\":\"demo://local\",\"resource_name\":\"payments-*\",\"analyzer_mode\":\"mock\",\"llm_provider\":\"mock\",\"llm_model\":null}"
```

```bash
curl -X POST http://127.0.0.1:8000/admin/api/poll-now
```

Integration-level LLM provider options are available in the admin page. Built-in choices include `mock`, `openai`, `anthropic`, `gemini`, `azure-openai`, `bedrock`, `vertex-ai`, `openrouter`, and `ollama`. Select `custom` to store a custom provider name such as an internal LLM gateway. The custom provider input is enabled only when `custom` is selected.

## Docker Compose 실행

```bash
docker compose up --build
```

구성에는 FastAPI 앱과 MongoDB가 포함됩니다. 앱은 등록된 project integration을 10초 주기로 polling하고, 분석 결과가 `high` 또는 `critical`이거나 명확한 에러 유형으로 분류되면 MongoDB에 프로젝트별 탐지 항목으로 저장합니다. 현재 실제 수집 fetcher는 Kibana이며, Sentry는 설정 shape과 UI만 먼저 열어두었습니다. Sentry 수집은 `app/integrations` registry에 fetcher를 추가하는 방식으로 확장합니다.

## CLI 사용 예시

Pretty print:

```bash
.venv\Scripts\python.exe -m app.cli --file samples/db_timeout.log --mode auto
```

JSON 출력:

```bash
.venv\Scripts\python.exe -m app.cli --file samples/db_timeout.log --mode rule-based --json
```

## 샘플 입력

- `samples/null_reference.log`
- `samples/db_timeout.log`
- `samples/http_500_stacktrace.log`

## 샘플 출력

- `samples/sample_analysis_result.json`
- `samples/analysis_report.md`

예시 응답 구조:

```json
{
  "analysis": {
    "summary": "Detected a likely db_connection_error incident...",
    "severity": "critical",
    "error_type": "db_connection_error",
    "keywords": ["timeout", "operationalerror"],
    "root_cause_candidates": [
      {
        "title": "Database connectivity or pool availability failed",
        "confidence": 0.9,
        "reason": "..."
      }
    ],
    "impact": "...",
    "reproduction_steps": ["..."],
    "immediate_checks": ["..."],
    "fix_suggestions": [
      {
        "title": "...",
        "description": "...",
        "example_patch": "..."
      }
    ],
    "test_suggestions": ["..."],
    "verification_steps": ["..."],
    "unknowns": ["..."]
  },
  "report_markdown": "# Log Analysis Report ...",
  "meta": {
    "analyzer_used": "mock",
    "fallback_used": true,
    "source_name": "db_timeout.log"
  }
}
```

## 테스트 실행

```bash
.venv\Scripts\python.exe -m pytest
```

## 한계점

- 현재 LLM provider는 safe stub까지만 구현되어 있습니다.
- Rule-based 분석은 로그 컨텍스트가 적으면 generic fallback 비중이 커집니다.
- 현재 실제 수집 fetcher는 Kibana만 구현되어 있습니다. Sentry 등은 같은 `ProjectIntegration` 모델 뒤에 fetcher를 추가해야 합니다.
- Kibana 수집은 `/internal/search/es` API를 사용하므로 Kibana 버전, 권한, 인증 구성에 따라 추가 어댑터가 필요할 수 있습니다.
- 반복 발생 횟수, 배포 이력, 메트릭 상관관계는 아직 수집하지 않습니다.
- 예시 patch는 제안용이며, 실제 저장소 구조에 맞게 사람이 검토해야 합니다.

## 다음 단계 제안

1. OpenAI adapter에 실제 API 호출 구현
2. 로그 chunking / 대용량 파일 스트리밍 지원
3. 서비스/언어별 규칙 세분화
4. Sentry, Slack, custom webhook integration fetcher 추가
5. 반복 발생 집계와 incident correlation 추가
6. 승인 기반 code suggestion export 기능 추가
