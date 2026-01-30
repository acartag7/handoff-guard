"""Schemas for each agent handoff."""

from pydantic import BaseModel, Field


class PlannerOutput(BaseModel):
    """What the planner hands off to researcher."""
    topic: str = Field(description="The main topic to research")
    questions: list[str] = Field(description="3-5 specific questions to answer")
    tone: str = Field(description="Desired tone: formal, casual, technical")


class ResearcherOutput(BaseModel):
    """What the researcher hands off to writer."""
    topic: str
    facts: list[str] = Field(description="5-10 key facts discovered")
    sources: list[str] = Field(description="Source attributions")
    questions_answered: int = Field(ge=1, le=10)


class WriterOutput(BaseModel):
    """Final output from writer."""
    draft: str = Field(min_length=100, description="The written content")
    word_count: int = Field(ge=50)
    tone: str
    title: str
