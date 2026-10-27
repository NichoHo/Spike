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
        description="'natural' to cut long dead air, 'off' to keep every pause",
    )
    music: bool = Field(default=True, description="True if a quiet background music bed helps the clip")
    music_track: str = Field(default="", description="Track id from the music catalogue that best fits, or empty")

    @field_validator("humor_type", mode="before")
    @classmethod
    def _humor_type(cls, v):
        v = str(v or "").strip().lower()
        return v if v in HUMOR_STYLES else "other"


class VideoVerdict(BaseModel):
    """Gemini's verdict after watching a shortlisted clip. Observations come before the score."""
    what_happens: str = Field(default="", description="What is seen and heard, in order")
    visible: bool = Field(description="The funny or key thing is seen or heard in the clip itself")
    standalone: bool = Field(description="A stranger understands it without chat, earlier context or inside jokes")
    reaction: str = Field(default="none", description="peak, routine, reading_chat or none")
    ends_on_reaction: bool = Field(default=True, description="The clip ends on the reaction, not before it")
    why: str = Field(default="", description="Why it works or does not, for a stranger")
    score: int = Field(ge=0, le=100, description="30 fans smile, 50 stranger chuckles, 70 stranger shares, 90 viral")

    @field_validator("reaction", mode="before")
    @classmethod
    def _reaction(cls, v):
        v = str(v or "").strip().lower()
        return v if v in ("peak", "routine", "reading_chat", "none") else "none"


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


ANIME_ARCHETYPES = ("comedy_beat", "iconic_line", "fight_sakuga", "transformation", "emotional",
                    "twist_reveal", "romance_wholesome", "cringe_reaction")


class AnimeScores(BaseModel):
    self_contained: int = Field(ge=0, le=10)
    payoff: int = Field(ge=0, le=10)
    setup_present: int = Field(ge=0, le=10)
    delivery: int = Field(ge=0, le=10)
    quotability: int = Field(ge=0, le=10)


class AnimeCandidate(BaseModel):
    """One anime moment from the whole-episode text judge. `why` comes before `scores` so the model explains first."""
    start: str = Field(default="", description="MM:SS, informational; the line numbers decide the edges")
    end: str = Field(default="", description="MM:SS, informational")
    setup_line_idx: List[int] = Field(default_factory=list, description="Lines a stranger needs before the punchline")
    punchline_line_idx: int = Field(description="The punchline or peak line")
    archetype: str = Field(description="One of ANIME_ARCHETYPES")
    why: str = Field(default="", description="One sentence: why a stranger laughs or cares")
    scores: AnimeScores
    needs_prior_context: bool = False
    spoiler: bool = False
    hook_line_idx: Optional[int] = None
    hook_text: str = Field(default="", description="3 to 8 word question or observation for a stranger, not a quote")
    title: str = Field(default="", description="5 to 12 words: name the main character and say what happens")
    hashtags: List[str] = Field(default_factory=list, description="Genre and show tags without #")
    seed_ids: List[str] = Field(default_factory=list)

    @field_validator("archetype", mode="before")
    @classmethod
    def _archetype(cls, v):
        v = str(v or "").strip().lower()
        return v if v in ANIME_ARCHETYPES else "comedy_beat"


class AnimeJudgeResponse(BaseModel):
    candidates: List[AnimeCandidate] = Field(default_factory=list)
