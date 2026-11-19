# Website Link Analysis API

Submit a publicly reachable HTML page to generate a brand and competitor comparison, five search queries, SEO improvements, up to five important offerings, and audience segments.

## Run locally

Use Python 3.11 or newer. Create a virtual environment and install the dependencies.

```sh
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `GEMINI_API_KEY` to a [Google AI Studio API key](https://aistudio.google.com/apikey). Start Uvicorn.

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Open [Swagger UI](http://localhost:4000/docs) or POST a JSON body with the page URL.

```sh
curl -X POST http://localhost:4000/link-analysis \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.python.org/"}'
```

[Sample JSON response](docs/sample-response.json) uses a fictional repair shop fixture. [Verification logs](docs/verification.txt) show the offline endpoint tests.

| Status | Typical cause |
| --- | --- |
| 422 | Invalid URL, nonpublic destination, or insufficient readable text |
| 413 | HTML exceeded the size limit |
| 415 | Response was non-HTML or used an unsupported content encoding |
| 502 | Website or provider returned an unusable response |
| 503 | Model is unconfigured or the provider is unavailable |
| 504 | Website or model request timed out |

Errors from the application use `{"success":false,"error":"..."}`.

## Architecture

1. FastAPI validates the request format. The fetcher resolves the host to public addresses, connects to a checked IP while preserving the HTTP Host and TLS server name, and repeats the checks at every redirect.
2. The HTML parser extracts title, metadata, headings and main-page text. It ranks deduplicated excerpts by heading importance, business terms and readable length before selecting context. The fetch stage has a 12-second budget, a 4 MB response cap, and a 14,000-character body context cap. Video pages and pages with little readable text can use descriptive metadata as evidence.
3. Gemini gets numbered evidence excerpts and a JSON schema for all five sections. Pydantic checks the result and platform coverage. The API resolves observed-offering references back to their source text and omits individual claims that cite missing evidence.
4. The response exposes the analyzed page and limits of its evidence. Competitor comparisons are hypotheses labeled `ai_suggestion`. Audience segments are analysis or recommendations. Search queries are candidate phrases. Single-page HTML extraction works best on public server-rendered pages and may have limited evidence on client-rendered or access-restricted pages.

## Model selection & Requirement based Model Routing for cost optimization

On-demand standard API prices in USD per million tokens, as listed by the providers on 19 November 2026. The example calculation uses 6,000 input tokens and 2,000 billable output tokens for each model, excluding additional provider features. Actual tokens vary by page, model and tokenizer.

| Model | Input / output | Context | Structured output | Estimated cost | Expected quality and speed |
| --- | ---: | ---: | --- | ---: | --- |
| Gemini 3.1 Flash-Lite | $0.25 / $1.50 | 1,048,576 input tokens | JSON Schema | $0.0045 | Fast-tier starting point. Check evidence accuracy, SEO specificity and competitor relevance on business pages. [Model](https://aistudio.google.com/docs/models/gemini-3.1-flash-lite) · [Pricing](https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite) |
| GPT-5.4 mini | $0.75 / $4.50 | 400,000 tokens | Structured Outputs | $0.0135 | Mini model suited to high-volume tasks. Test whether better synthesis of ambiguous pages justifies the higher per-call cost. [Model and pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini) |
| Claude Haiku 5.5 | $0.10 / $0.50 up to 100K prompt tokens | 1 million tokens | JSON Schema | $0.0016 | Anthropic's speed-focused tier and the lowest calculated cost in this comparison. Test on the same evidence and schema before changing adapters. [Model and pricing](https://platform.claude.com/docs/en/models/haiku-5-5/overview) · [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) |

Gemini 3.1 Flash-Lite is the launch choice for native schema support, low estimated cost and simple REST integration. Budget roughly 10–25 seconds for a successful uncached request on a responsive website as a planning estimate. The fetch and provider hard time budgets are 12 and 38 seconds respectively. Comparative latency and accuracy need a live benchmark.

The default alternate model is Gemini 3.5 Flash-Lite via `GEMINI_FALLBACK_MODEL`. The standard model handles sparse and metadata-only pages first. Product or business metadata, or a long page with many headings, selects the alternate first. A recoverable provider or output failure tries the other model once within the same provider time budget. Authentication and quota failures stop immediately. The alternate costs an estimated $0.0068 at this example token mix, and two attempts can incur two charges. Set the alternate variable to an empty value to disable it. [Fallback model](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite) · [Pricing](https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite)

The extraction cap and deduplication reduce token input. Successful first attempts use one structured call. If repeat requests justify caching, cache by evidence hash, model and prompt version with a short TTL. For model evaluation, freeze a representative corpus across local services, SaaS, ecommerce and sparse pages. Score schema validity, citation accuracy, competitor fit and SEO actionability, and record billed tokens plus p50/p95 latency for each model.

## Verification and deployment

```sh
python -m unittest discover -s tests -v
```

The offline suite runs FastAPI against deterministic website and provider data. For Render, create a Blueprint from this repository, set `GEMINI_API_KEY` as a secret, and deploy. The public demo serves [Swagger](https://dxora-assignment-71t4.onrender.com/docs) and [the analysis endpoint](https://dxora-assignment-71t4.onrender.com/link-analysis). Verify with the sample POST against the assigned HTTPS origin. Configure a provider spending limit and apply an upstream request limit before exposing the demo widely. [Render Blueprints](https://render.com/docs/infrastructure-as-code)
