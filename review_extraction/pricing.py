from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_TAX_RATE = 0.14975
PRICING_SOURCE = "OpenAI pricing page, Standard / Short context, checked 2026-07-01"


@dataclass(frozen=True)
class ModelPricing:
    model: str
    input_cost_per_million: float
    cached_input_cost_per_million: float
    output_cost_per_million: float
    tax_rate: float = DEFAULT_TAX_RATE
    source: str = PRICING_SOURCE

    @property
    def input_with_tax(self) -> float:
        return _with_tax(self.input_cost_per_million, self.tax_rate)

    @property
    def cached_input_with_tax(self) -> float:
        return _with_tax(self.cached_input_cost_per_million, self.tax_rate)

    @property
    def output_with_tax(self) -> float:
        return _with_tax(self.output_cost_per_million, self.tax_rate)


BUILTIN_MODEL_PRICING = {
    "gpt-5.5": ModelPricing(
        model="gpt-5.5",
        input_cost_per_million=5.00,
        cached_input_cost_per_million=0.50,
        output_cost_per_million=30.00,
    ),
    "gpt-5.4": ModelPricing(
        model="gpt-5.4",
        input_cost_per_million=2.50,
        cached_input_cost_per_million=0.25,
        output_cost_per_million=15.00,
    ),
    "gpt-5.4-mini": ModelPricing(
        model="gpt-5.4-mini",
        input_cost_per_million=0.75,
        cached_input_cost_per_million=0.075,
        output_cost_per_million=4.50,
    ),
    "gpt-5.4-nano": ModelPricing(
        model="gpt-5.4-nano",
        input_cost_per_million=0.20,
        cached_input_cost_per_million=0.02,
        output_cost_per_million=1.25,
    ),
}


def pricing_for_model(model: str, *, tax_rate: float | None = None) -> ModelPricing | None:
    base = BUILTIN_MODEL_PRICING.get(model)
    if base is None:
        return None
    return ModelPricing(
        model=base.model,
        input_cost_per_million=base.input_cost_per_million,
        cached_input_cost_per_million=base.cached_input_cost_per_million,
        output_cost_per_million=base.output_cost_per_million,
        tax_rate=DEFAULT_TAX_RATE if tax_rate is None else tax_rate,
        source=base.source,
    )


def tax_rate_from_env() -> float:
    raw = os.getenv("OPENAI_TAX_RATE")
    if raw is None or not raw.strip():
        return DEFAULT_TAX_RATE
    return float(raw)


def _with_tax(value: float, tax_rate: float) -> float:
    return round(value * (1 + tax_rate), 9)
