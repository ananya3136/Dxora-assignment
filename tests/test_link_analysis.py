"""Offline tests for the normal endpoint and controlled error paths."""

import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app import llm, website
from app.main import app
from app.schemas import ModelResult

SAMPLE = json.loads((Path(__file__).parents[1] / "docs/sample-response.json").read_text())
HTML = """
<html><head><title>Harbor Bike Repair</title></head>
<body><nav>Menu</nav><main><h1>Harbor Bike Repair</h1>
<p>We offer brake adjustments for daily riders.</p></main></body></html>
"""


class LinkAnalysisTests(unittest.TestCase):
    def test_ranking_keeps_late_business_content_within_budget(self):
        opening = "".join(f"<p>Editorial note {i}: {'background ' * 50}</p>" for i in range(40))
        evidence = website.extract_evidence(
            f"<main>{opening}<p>We provide payroll services for small businesses.</p></main>"
        )
        self.assertTrue(evidence["body"].startswith("We provide payroll services"))
        self.assertLessEqual(len(evidence["body"]), website.MAX_EVIDENCE_CHARS)

    def test_ranking_includes_text_outside_semantic_elements(self):
        evidence = website.extract_evidence(
            "<main><h1>Acme</h1><div>We provide payroll services for small businesses.</div></main>"
        )
        self.assertIn("payroll services", evidence["body"])

    def test_video_evidence_uses_metadata_instead_of_host_boilerplate(self):
        evidence = website.extract_evidence("""
            <meta property="og:type" content="video.other">
            <meta property="og:title" content="Brake repair walkthrough">
            <meta property="og:description" content="A mechanic demonstrates how to adjust bicycle brakes for daily riding.">
            <body>About Press Copyright Contact Creators Privacy Policy</body>
        """)
        self.assertEqual(evidence["evidence_scope"], "page_metadata")
        self.assertIn("adjust bicycle brakes", evidence["body"])
        self.assertNotIn("Copyright", evidence["body"])

    def test_full_endpoint(self):
        with (
            patch("app.website.fetch_html", AsyncMock(return_value=(SAMPLE["analyzed_page"], HTML))),
            patch("app.llm.analyze", AsyncMock(return_value=ModelResult.model_validate(SAMPLE))) as analyze,
            TestClient(app) as client,
        ):
            result = client.post("/link-analysis", json={"url": SAMPLE["website"]})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), SAMPLE)
        self.assertIn("brake adjustments", analyze.call_args.args[0]["body"])
        self.assertNotIn("Menu", analyze.call_args.args[0]["body"])

    def test_invalid_url_and_missing_body(self):
        with TestClient(app) as client:
            for body in ({}, {"url": "file:///tmp/index.html"}, {"url": "http://127.0.0.1/"}):
                with self.subTest(body=body):
                    result = client.post("/link-analysis", json=body)
                    self.assertEqual(result.status_code, 422)
                    self.assertFalse(result.json()["success"])

    def test_website_and_provider_errors(self):
        with TestClient(app) as client:
            with patch("app.website.fetch_html", AsyncMock(side_effect=website.WebsiteError(502, "unreachable"))):
                self.assertEqual(client.post("/link-analysis", json={"url": SAMPLE["website"]}).status_code, 502)
            with (
                patch("app.website.fetch_html", AsyncMock(return_value=(SAMPLE["analyzed_page"], HTML))),
                patch("app.llm.analyze", AsyncMock(side_effect=llm.ModelError(504, "timed out"))),
            ):
                result = client.post("/link-analysis", json={"url": SAMPLE["website"]})
                self.assertEqual(result.status_code, 504)
                self.assertEqual(result.json(), {"success": False, "error": "timed out"})

    def test_openapi(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/docs").status_code, 200)
            self.assertIn("/link-analysis", client.get("/openapi.json").json()["paths"])


class GeminiContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_payload_and_evidence_checks(self):
        evidence = website.extract_evidence(HTML)
        for excerpt in ("E2", "E999"):
            with self.subTest(excerpt=excerpt):
                provider_result = ModelResult.model_validate(SAMPLE)
                provider_result.analysis.top_services[0].evidence = excerpt

                def generate(request):
                    payload = json.loads(request.content)
                    schema = payload["generationConfig"]["responseJsonSchema"]
                    self.assertEqual(schema["$defs"]["Competitor"]["properties"]["status"]["enum"],
                                     ["ai_suggestion"])
                    context = json.loads(payload["contents"][0]["parts"][0]["text"])
                    self.assertEqual(context["excerpts"]["E2"],
                                     "We offer brake adjustments for daily riders.")
                    return httpx.Response(200, json={"candidates": [{
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": provider_result.model_dump_json()}]},
                    }]})

                client = httpx.AsyncClient(transport=httpx.MockTransport(generate))
                with patch.dict("os.environ", {"GEMINI_API_KEY": "test-fixture-key"}), patch(
                    "app.llm.httpx.AsyncClient", return_value=client
                ):
                    result = await llm.analyze(evidence)
                    self.assertEqual(result.brand.name, "Harbor Bike Repair")
                    if excerpt == "E999":
                        self.assertEqual(result.analysis.top_services, [])
                        self.assertIn("Omitted 1", result.evidence_limitations[-1])
                    else:
                        self.assertEqual(result.analysis.top_services[0].evidence,
                                         "We offer brake adjustments for daily riders.")

    async def test_model_routes_and_falls_back_after_malformed_output(self):
        evidence = website.extract_evidence(HTML)
        models = []
        expected = ModelResult.model_validate(SAMPLE)

        async def generate(_client, _key, model, _payload):
            models.append(model)
            if len(models) == 1:
                raise ValueError("Incomplete generation")
            return expected

        with (
            patch.dict("os.environ", {
                "GEMINI_API_KEY": "test-fixture-key",
                "GEMINI_MODEL": "standard",
                "GEMINI_FALLBACK_MODEL": "enhanced",
            }),
            patch("app.llm.generate", AsyncMock(side_effect=generate)),
        ):
            self.assertEqual(llm.model_order(evidence), ("standard", "enhanced"))
            evidence["metadata"]["og:type"] = "product"
            self.assertEqual(llm.model_order(evidence), ("enhanced", "standard"))
            self.assertEqual((await llm.analyze(evidence)).brand.name, "Harbor Bike Repair")
        self.assertEqual(models, ["enhanced", "standard"])
