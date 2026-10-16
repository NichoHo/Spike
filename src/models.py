"""
Spike: Pydantic schemas for LLM outputs and candidates.
Blueprint §6.3 & §6.4.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator

from src.config import HUMOR_STYLES


class LLMJudgeResponse(BaseModel):
    """Schema for candidate moment evaluation. Field order is the order the model writes them:
    it explains why the moment is funny before it commits to a score (§6.7)."""
    keep: bool = Field(description="False unless a stranger with no context would laugh")
    why_funny: str = Field(default="", description="What happens, what the viewer feels, and why it works")
    humor_type: str = Field(default="other", description="One of the HUMOR_STYLES, or other")
    needs_context: bool = Field(default=False, description="True if a cold viewer would be confused")
    contrast: bool = Field(default=False, description="Hubris before the reaction, or an outcome unusual for this creator")
    score: int = Field(ge=0, le=100, description="30 fans smile, 50 stranger chuckles, 70 stranger shares, 90 viral")
    topic_start_line: int = Field(default=1, description="First line of the current topic; the clip never starts before it")
    setup_start_line: int = Field(default=1, description="First line a viewer needs to understand the payoff")
    payoff_line: int = Field(default=1, description="The punchline or key moment")
    reaction_end_line: int = Field(default=1, description="Last line of the reaction to the payoff")
    cut_lines: List[int] = Field(default_factory=list, description="Lines inside the clip that are fluff and can be cut out")
    punchline: str = Field(description="Exact quote of the punchline or key moment")
    title: str = Field(description="Short engaging title for the clip")
    hook_text: str = Field(description="3 to 8 word funny summary of what happens in the clip, not a quote")
    post_caption: str = Field(description="Social media caption")
    hashtags: List[str] = Field(default_factory=list, description="Relevant hashtags without hash symbol")
    reason: str = Field(default="", description="Brief rationale for the score")
    mood: str = Field(
        default="laugh", description="Emotional tone of the clip"
    )
    pace: str = Field(
        default="natural",
        description="'tight' to jump-cut every pause, 'natural' to cut only long dead air",
    )
    music: bool = Field(default=True, description="True if a quiet background music bed helps the clip")
    music_track: str = Field(default="", description="Track id from the music catalogue that best fits, or empty")

    @field_validator("humor_type", mode="before")
    @classmethod
    def _humor_type(cls, v):
        v = str(v or "").strip().lower()
        return v if v in HUMOR_STYLES else "other"


class TranscriptProposal(BaseModel):
    """Schema for moments proposed by reading transcript chunks."""
    start_line: int
    end_line: int
    punchline: str
    estimated_score: int = Field(ge=0, le=100)
    topic: str


class TranscriptChunkProposals(BaseModel):
    """Up to 3 moments proposed per 8-minute transcript chunk."""
    proposals: List[TranscriptProposal] = Field(default_factory=list, max_length=3)


class PairwiseCompareResponse(BaseModel):
    """Response for pairwise clip re-ranking comparison."""
    winner: Literal["A", "B", "TIE"] = Field(description="Which clip would more viewers find entertaining?")
    reason: str = Field(description="Brief 1-sentence explanation")


class Candidate(BaseModel):
    """Internal candidate representation."""
    id: Optional[int] = None
    video_id: int
    peak_t: Optional[float] = None
    start_s: float
    end_s: float
    origin: Literal["signal", "llm_chunk", "both"] = "signal"
    chat_mood: Optional[str] = None
    signal_score: Optional[int] = None
    llm_score: Optional[int] = None
    final_score: Optional[int] = None
    av_score: Optional[int] = None
    punchline: Optional[str] = None
    features: Dict[str, Any] = Field(default_factory=dict)
    title: Optional[str] = None
    hook_text: Optional[str] = None
    post_caption: Optional[str] = None
    hashtags: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    mood: Optional[str] = None
    needs_context: bool = False
    status: Literal["proposed", "selected", "low_score", "rejected", "hubris", "dropped"] = "proposed"
