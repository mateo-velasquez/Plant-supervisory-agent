"""Token usage and exact Decimal cost of a model call (R13)."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

PER_MILLION = Decimal(1_000_000)


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_5m_tokens: int = Field(default=0, ge=0)
    cache_write_1h_tokens: int = Field(default=0, ge=0)

    @property
    def prompt_tokens(self) -> int:
        """Every token sent as prompt: fresh input, cache reads and cache writes."""
        return (
            self.input_tokens
            + self.cache_read_tokens
            + self.cache_write_5m_tokens
            + self.cache_write_1h_tokens
        )


class PriceCard(BaseModel):
    """Prices in USD per million tokens."""

    model_config = ConfigDict(frozen=True)

    input: Decimal
    cache_write_5m: Decimal
    cache_write_1h: Decimal
    cache_read: Decimal
    output: Decimal
    long_context_threshold: int
    long_context_multiplier: Decimal


def cost_usd(usage: Usage, card: PriceCard) -> Decimal:
    """Exact cost; the whole call is multiplied when the prompt exceeds the long-context threshold."""
    total = (
        usage.input_tokens * card.input
        + usage.cache_write_5m_tokens * card.cache_write_5m
        + usage.cache_write_1h_tokens * card.cache_write_1h
        + usage.cache_read_tokens * card.cache_read
        + usage.output_tokens * card.output
    ) / PER_MILLION
    if usage.prompt_tokens > card.long_context_threshold:
        total *= card.long_context_multiplier
    return total
