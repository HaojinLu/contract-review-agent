from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ClauseFact(BaseModel):
    dimension: Literal["business_terms", "time_frames", "legal_terms"]
    sub_dimension: str = Field(description="Fine-grained clause class such as price or delivery cycle.")
    normalized_statement: str = Field(description="Short normalized statement extracted from the document.")
    source_quote: str = Field(description="Original quote from the document.")
    key_points: list[str] = Field(default_factory=list)


class ClauseExtractionResult(BaseModel):
    document_role: Literal["procurement", "contract"]
    clauses: list[ClauseFact] = Field(default_factory=list)


class ReviewItem(BaseModel):
    dimension: str
    sub_dimension: str
    procurement_quote: str = ""
    contract_quote: str = ""
    analysis: str = ""
    risk_level: Literal["high", "medium", "low"] | None = None


class ContractReviewReport(BaseModel):
    review_summary: str
    missing_items: list[ReviewItem] = Field(default_factory=list)
    discrepancies: list[ReviewItem] = Field(default_factory=list)
    consistent_items: list[ReviewItem] = Field(default_factory=list)
