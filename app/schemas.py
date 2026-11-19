"""The public response contract and the model's structured output."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

Platform = Literal["Google", "Facebook", "Instagram", "LinkedIn", "X"]


class Request(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class Brand(BaseModel):
    name: str
    category: str
    summary: str


class Competitor(BaseModel):
    name: str
    comparison_basis: str
    possible_strengths: list[str]
    possible_gaps: list[str]
    status: Literal["ai_suggestion"]


class Competition(BaseModel):
    brand_overview: str
    main_offerings: list[str]
    competitors: list[Competitor] = Field(max_length=5)
    strengths: list[str]
    opportunities: list[str]


class Query(BaseModel):
    query: str
    platforms: list[Platform] = Field(min_length=1)
    intent: str
    business_relevance: str
    target_audience: str


class SEO(BaseModel):
    primary_keyword: str
    secondary_keywords: list[str]
    long_tail_keywords: list[str]
    business_keywords: list[str]
    recommended_title: str
    title_structure: str
    meta_description: str
    meta_keywords: list[str]
    supporting_content: list[str]


class Service(BaseModel):
    name: str
    description: str
    target_industry: str
    target_customer: str
    main_benefit: str
    status: Literal["observed", "inferred_recommendation"]
    evidence: str


class Audience(BaseModel):
    primary_audience: list[str]
    secondary_audience: list[str]
    industries: list[str]
    business_types: list[str]
    customer_profiles: list[str]
    geography: list[str]
    customer_needs: list[str]
    customer_interests: list[str]
    marketing_segments: list[str]


class Analysis(BaseModel):
    competitor_analysis: Competition
    target_search_queries: list[Query] = Field(min_length=5, max_length=5)
    seo_improvements: SEO
    top_services: list[Service] = Field(max_length=5)
    target_audience: Audience

    @model_validator(mode="after")
    def validate_queries(self):
        if len({item.query.strip().casefold() for item in self.target_search_queries}) != 5:
            raise ValueError("Five distinct queries are required.")
        platforms = {platform for item in self.target_search_queries for platform in item.platforms}
        if platforms != {"Google", "Facebook", "Instagram", "LinkedIn", "X"}:
            raise ValueError("Queries must cover all five platforms.")
        return self


class ModelResult(BaseModel):
    brand: Brand
    analysis: Analysis
    evidence_limitations: list[str]


class Response(ModelResult):
    success: Literal[True] = True
    website: str
    analyzed_page: str
