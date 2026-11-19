# Website Link Analysis API

Submit a publicly reachable HTML page to generate a brand and competitor comparison, five search queries, SEO improvements, up to five important offerings, and audience segments.

## Submission

| Deliverable | Location |
| --- | --- |
| Public repository and Python source | [GitHub repository](https://github.com/ananya3136/Dxora-assignment) and [application source](app/) |
| Setup and execution | [Run locally](#run-locally) |
| Sample requests and responses | [API examples](#api-examples) and [complete sample JSON](docs/sample-response.json) |
| Implementation evidence | [Verification and deployment](#verification-and-deployment) and [execution logs](docs/verification.txt) |
| LLM comparison and recommendation | [Model comparison](#model-comparison) and [implemented model selection](#implemented-model-selection) |
| Credential configuration | [Local setup](#run-locally), [environment template](.env.example), and [Render blueprint](render.yaml) |

## Assignment requirements

The API implements the five analysis sections and the technical requirements in the [practical test brief](https://github.com/chivoxai/practical-test/blob/main/link-analysis.md).

| Requirement | Implementation |
| --- | --- |
| Brand and competitor analysis | Summarizes the business and its offerings. Competitor comparisons include reasons for the match, potential strengths and gaps, and the `ai_suggestion` label. |
| Five search queries | Validates that five distinct queries cover Google, Facebook, Instagram, LinkedIn, and X. Each includes intent, relevance, and audience. Search volume and rankings are outside the response contract. |
| SEO recommendations | Provides primary, secondary, and long-tail keywords, plus a recommended title, meta description, and supporting content. |
| Top offerings and audiences | Returns up to five offerings with evidence references or an inference label, plus audience segments, customer needs, and geography when supported. |
| Structured API and safe fetching | FastAPI and Swagger expose the contract. Pydantic validates Gemini output, and the fetcher checks public addresses on every redirect. |

## Run locally

Use Python 3.11 or newer. Create a virtual environment and install the dependencies.

```sh
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `GEMINI_API_KEY` to a [Google AI Studio API key](https://aistudio.google.com/apikey). Git ignores `.env` and the tracked template leaves the key blank. Use the hosting provider's secret settings for deployments.

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port 4000
```

## API examples

Open [Swagger UI](http://localhost:4000/docs) or POST a JSON body with the page URL.

```sh
curl -X POST http://localhost:4000/link-analysis \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.python.org/"}'
```

In PowerShell, pipe the JSON to `curl.exe`.

```powershell
'{"url":"https://www.python.org/"}' | curl.exe -i --json '@-' http://localhost:4000/link-analysis
```

A successful request returns HTTP 200. This excerpt shows the envelope for the fictional repair shop fixture. The [complete success response](docs/sample-response.json) includes all five analysis sections, and the [execution logs](docs/verification.txt) record live runs on real sites.

```json
{
  "success": true,
  "website": "https://example.com",
  "analyzed_page": "https://example.com/",
  "brand": {
    "name": "Harbor Bike Repair",
    "category": "Bicycle repair",
    "summary": "A fictional workshop offering bicycle maintenance."
  }
}
```

For example, posting `{"url":"ftp://example.com/"}` returns HTTP 422.

```json
{"success":false,"error":"Provide a public HTTP or HTTPS URL using its default port."}
```

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

## Model comparison

On-demand standard API prices in USD per million tokens, as listed by the providers on 19 November 2026. The example calculation uses 6,000 input tokens and 2,000 billable output tokens for each model, excluding additional provider features. Actual tokens vary by page, model and tokenizer.

| Model | Input / output | Context | Structured output | Estimated cost | Expected quality and speed |
| --- | ---: | ---: | --- | ---: | --- |
| Gemini 3.1 Flash-Lite | $0.25 / $1.50 | 1,048,576 input tokens | JSON Schema | $0.0045 | Fast-tier starting point. Check evidence accuracy, SEO specificity and competitor relevance on business pages. [Model](https://aistudio.google.com/docs/models/gemini-3.1-flash-lite) · [Pricing](https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite) |
| Gemini 3.5 Flash-Lite | $0.30 / $2.50 | 1,048,576 input tokens | JSON Schema | $0.0068 | Low-latency alternate in the implemented adapter. Its relative quality on this workload needs a controlled comparison. [Model](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite) · [Pricing](https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite) |
| GPT-5.4 mini | $0.75 / $4.50 | 400,000 tokens | Structured Outputs | $0.0135 | Mini model suited to high-volume tasks. Test whether better synthesis of ambiguous pages justifies the higher per-call cost. [Model and pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini) |
| Claude Haiku 5.5 | $0.10 / $0.50 up to 100K prompt tokens | 1 million tokens | JSON Schema | $0.0016 | Anthropic's speed-focused tier and the lowest calculated cost in this comparison. Test on the same evidence and schema before changing adapters. [Model and pricing](https://platform.claude.com/docs/en/models/haiku-5-5/overview) · [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) |

## Implemented model selection

**Recommendation.** Use Gemini 3.1 Flash-Lite as the default and Gemini 3.5 Flash-Lite as the alternate. The default combines a low estimated per-call cost with native structured output and a working REST integration. The alternate uses the same schema and credentials. Claude Haiku 5.5 has the lowest quoted token cost in the comparison and is a candidate for a future workload benchmark.

| Evidence or outcome | Decision |
| --- | --- |
| Metadata-only or ordinary HTML page | Try `GEMINI_MODEL` first. The default is `gemini-3.1-flash-lite`. |
| HTML with Open Graph type `product`, `product.group`, or `business.business`, or at least 7,000 evidence characters and 10 headings | Try `GEMINI_FALLBACK_MODEL` first. The default is `gemini-3.5-flash-lite`. The thresholds are routing heuristics. |
| Recoverable timeout, model unavailable, upstream server error, or unusable structured output | Try the other model once. Each model attempt is capped at 18 seconds when both are configured, within a shared 38-second provider budget. |
| Authentication or quota failure, or a provider-withheld result | Return a structured error immediately. |
| Valid response with an unsupported observed offering | Omit that offering and include an evidence limitation in the response. |

Set `GEMINI_FALLBACK_MODEL` to an empty value to disable the second model. Both models depend on the same provider account and quota.

Routing by page requirements limits how often ordinary requests use the higher-priced model.

## LLM cost optimization

| Implemented control | Cost impact |
| --- | --- |
| Clean and rank evidence before generation | Removes scripts, navigation, and repeated text. Scoring favors meaningful headings and business terms so the model sees a more useful sample within the 14,000-character evidence body budget. Title, metadata, headings, and the schema add separate input overhead. |
| Number excerpts and validate claims locally | Sends each selected excerpt once. The model cites short IDs, and the application restores the original text and checks references without another LLM call. |
| Generate all five sections together | A successful first attempt uses one structured request. The provider request caps generated output at 4,096 tokens. |
| Route by evidence and bound recovery | Uses the lower-priced model first for ordinary pages. Model switching is limited to one extra attempt. |

The planning estimate uses **6,000 input tokens and 2,000 billable output tokens**. At Gemini 3.1 Flash-Lite rates, `(6,000 × $0.25 + 2,000 × $1.50) / 1,000,000 = $0.0045`. Gemini 3.5 Flash-Lite costs **$0.0068** at the same token mix. If both attempts are billed for that token mix, the illustrative total is **$0.0113**. Actual billing depends on token usage and provider billing rules. Gemini output rates include billable thinking tokens. [Gemini pricing](https://aistudio.google.com/docs/pricing)

For repeat traffic, a future short-lived cache keyed by evidence hash, model, and prompt version could avoid repeated generation. Measure the repeat-request rate before adding it.

## Measured results and benchmarking

Live local checks of version 1.1.0 returned HTTP 200 with all five sections for Example.com (**7.0 s**), Shopify (**9.9 s**), and Metacritic (**14.6 s**). These are single end-to-end observations that include website fetching. The planning range is 10–25 seconds for a successful uncached request on a responsive site. The fetch and shared provider time budgets are 12 and 38 seconds respectively. [Execution logs](docs/verification.txt)

Comparative accuracy, provider latency, and billed token counts have yet to be benchmarked on the same corpus. A repeatable comparison would use frozen evidence from local-service, SaaS, ecommerce, and sparse pages, and report schema pass rate, claim grounding, competitor fit, SEO usefulness, billed tokens, and p50/p95 latency.

## Verification and deployment

```sh
python -m unittest discover -s tests -v
```

The offline suite runs FastAPI against deterministic website and provider data. For Render, create a Blueprint from this repository, set `GEMINI_API_KEY` as a secret, and deploy. The public demo serves [Swagger](https://dxora-assignment-71t4.onrender.com/docs) and [the analysis endpoint](https://dxora-assignment-71t4.onrender.com/link-analysis). Verify with the sample POST against the assigned HTTPS origin. Configure a provider spending limit and apply an upstream request limit before exposing the demo widely. [Render Blueprints](https://render.com/docs/infrastructure-as-code)
