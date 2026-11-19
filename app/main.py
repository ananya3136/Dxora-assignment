"""FastAPI entry point."""

import asyncio

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import llm, website
from app.schemas import Request, Response

load_dotenv()
app = FastAPI(title="Website Link Analysis", version="1.1.0")


def error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": False, "error": message})


@app.exception_handler(RequestValidationError)
async def invalid_request(_request, _exc):
    return error(422, "Send a JSON object with a url string of 1 to 2048 characters.")


@app.get("/", include_in_schema=False)
async def home():
    return {"name": app.title, "documentation": "/docs"}


@app.post("/link-analysis", response_model=Response)
async def link_analysis(request: Request):
    try:
        final_url, html = await website.fetch_html(request.url)
        evidence = await asyncio.to_thread(website.extract_evidence, html)
        result = await llm.analyze({"page_url": final_url.split("?")[0], **evidence})
    except (website.WebsiteError, llm.ModelError) as exc:
        return error(exc.status, str(exc))
    return Response(website=request.url, analyzed_page=final_url, **result.model_dump())
