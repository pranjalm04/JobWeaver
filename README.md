# physicianx

Worker-first job discovery + extraction pipeline.

## LLM Setup (LiteLLM-first)

The pipeline now uses LiteLLM as the single LLM integration path.

- Choose provider by model string in `.env`:
  - OpenAI: `openai/gpt-4o-mini`
  - OpenRouter: `openrouter/openai/gpt-4o-mini`
  - Gemini: `gemini/gemini-2.0-flash`
- Set `LLM_API_KEY` (or legacy `API_KEY_GEMINI` fallback).
- Optional advanced settings:
  - `LLM_API_BASE`
  - `LLM_EXTRA_HEADERS_JSON` (JSON object string)

## Quickstart (local worker)

1) Install deps:

```bash
poetry install
```

2) Copy env:

```bash
cp .env.example .env
```

3) Start a broker (Redis) and worker:

```bash
poetry run celery -A physicianx.worker.celery_app worker -l info
```

4) Enqueue a seed:

```bash
poetry run physicianx enqueue-seed --seed-url "https://example.com/careers"
```

## Run in-process (no Redis)

Set `LLM_API_KEY`, `LLM_MODEL_LISTING`, `LLM_MODEL_JOB_DETAIL`, and `SEED_URLS` in `.env`, ensure `PYTHONPATH` includes `src` (or `pip install -e .`), then:

```bash
python examples/pipeline_example.py
```

## Outputs

Outputs default to `outputs/` unless `OUTPUT_DIR` is set.

