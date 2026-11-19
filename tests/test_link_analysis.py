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
        for excerpt, expected_status in (
            ("We offer brake adjustments for daily riders.", None),
            ("We rent electric bikes.", 502),
        ):
            with self.subTest(excerpt=excerpt):
                provider_result = ModelResult.model_validate(SAMPLE)
                provider_result.analysis.top_services[0].evidence = excerpt

                def generate(request):
                    payload = json.loads(request.content)
                    schema = payload["generationConfig"]["responseJsonSchema"]
                    self.assertEqual(schema["$defs"]["Competitor"]["properties"]["status"]["enum"],
                                     ["ai_suggestion"])
                    self.assertIn("brake adjustments", payload["contents"][0]["parts"][0]["text"])
                    return httpx.Response(200, json={"candidates": [{
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": provider_result.model_dump_json()}]},
                    }]})

                client = httpx.AsyncClient(transport=httpx.MockTransport(generate))
                with patch.dict("os.environ", {"GEMINI_API_KEY": "test-fixture-key"}), patch(
                    "app.llm.httpx.AsyncClient", return_value=client
                ):
                    if expected_status:
                        with self.assertRaises(llm.ModelError) as error:
                            await llm.analyze(website.extract_evidence(HTML))
                        self.assertEqual(error.exception.status, expected_status)
                    else:
                        result = await llm.analyze(website.extract_evidence(HTML))
                        self.assertEqual(result.brand.name, "Harbor Bike Repair")
