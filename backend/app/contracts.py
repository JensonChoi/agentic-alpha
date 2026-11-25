from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, Field, model_validator, ConfigDict

STRATEGIES = ['buy_and_hold', 'momentum', 'congressional', 'single_agent', 'multi_agent']
class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    ticker: str = Field(min_length=1, max_length=20)
    action: Literal['BUY', 'SELL', 'HOLD']
    target_weight: float = Field(default=0, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    rationale: str = Field(max_length=2000)
    strategy_id: str = ''
TradeSignal = Signal

class Proposals(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    signals: list[Signal] = Field(max_length=20)
    summary: str = Field(default='', max_length=3000)
class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(default='Research experiment', max_length=100)
    strategy: Literal['buy_and_hold','momentum','congressional','single_agent','multi_agent'] = 'momentum'
    mode: Literal['historical','forward'] = 'historical'
    dataset: str = 'demo'
    start: date = date(2024, 4, 1)
    end: date = date(2024, 12, 31)
    initial_capital: float = Field(default=100000, gt=0, le=1e12)
    universe: list[str] = Field(default=['VOO','AAPL','MSFT','NVDA'], min_length=1, max_length=100)
    max_position_weight: float = Field(default=.1, gt=0, le=1)
    position_weight_overrides: dict[str, Annotated[float, Field(gt=0, le=1)]] = Field(default_factory=dict)
    max_exposure: float = Field(default=1, gt=0, le=1)
    max_positions: int = Field(default=5, ge=1, le=100)
    short_window: int = Field(default=20, ge=2)
    long_window: int = Field(default=50, ge=3, le=500)
    rebalance: Literal['daily','weekly','monthly'] = 'weekly'
    cash_interest_rate: float = Field(default=0, ge=0, le=1)
    fee: float = Field(default=0, ge=0)
    slippage_bps: float = Field(default=5, ge=0, le=1000)
    reinvest_dividends: bool = False
    disclosure_snapshot: str | None = None
    starting_holdings_snapshot: str | None = None
    starting_holdings_since: date | None = None
    availability_policy: Literal['verified', 'filing_date'] = 'verified'
    disclosure_coverage_policy: Literal['fail', 'skip_quarantined'] = 'fail'
    member_id: str = 'P000197'
    owners: list[Literal['self','spouse','dependent','joint','unknown']] = ['self','spouse','dependent','joint','unknown']
    missing_price_policy: Literal['fail','skip'] = 'fail'
    copy_method: Literal['equal','fixed','proportional'] = 'equal'
    fixed_allocation: float = Field(default=.05, gt=0, le=1)
    provider: Literal['ollama','compatible','openai'] = 'ollama'
    model: str = ''
    decision_model: str = ''
    seed: int = 42
    max_model_calls: int = Field(default=12, ge=1, le=64)
    local_cost_per_hour: float = Field(default=0, ge=0)
    decision_provider: Literal['ollama','compatible','openai'] | None = None
    temperature: float = Field(default=0, ge=0, le=2)
    output_tokens: int = Field(default=2048, ge=128, le=8192)
    context_tokens: int = Field(default=8192, ge=2048, le=32768)
    call_timeout: float = Field(default=90, gt=0, le=600)
    decision_timeout: float = Field(default=600, gt=0, le=3600)
    analyst_concurrency: int = Field(default=1, ge=1, le=3)
    tool_rounds: int = Field(default=2, ge=0, le=4)
    tool_calls: int = Field(default=8, ge=0, le=32)
    retries: int = Field(default=1, ge=0, le=2)
    price_only: bool = False
    max_candidates: int = Field(default=10, ge=1, le=20)
    news_max_age_days: int = Field(default=7, ge=1, le=365)
    fundamentals_max_age_days: int = Field(default=180, ge=1, le=730)
    input_price_per_million: float | None = Field(default=None, ge=0)
    output_price_per_million: float | None = Field(default=None, ge=0)
    api_budget_usd: float | None = Field(default=None, gt=0)
    thinking: bool | None = None
    @model_validator(mode='before')
    @classmethod
    def llm_universe(cls, values):
        if isinstance(values, dict) and values.get('strategy') in ('single_agent', 'multi_agent') and 'universe' not in values:
            values = {**values, 'universe': ['VOO', 'QQQ', 'NVDA', 'TSLA', 'AAPL']}
        return values
    @model_validator(mode='after')
    def validate_config(self):
        if self.starting_holdings_snapshot:
            if self.strategy != 'congressional' or not self.disclosure_snapshot: raise ValueError('Starting holdings require normalized congressional strategy')
            if not self.starting_holdings_since or self.starting_holdings_since >= self.start: raise ValueError('Starting holdings require lookback before start')
            if self.copy_method != 'equal': raise ValueError('Inferred starting holdings require equal sizing')
        elif self.starting_holdings_since: raise ValueError('Starting holdings require a snapshot')
        if self.end < self.start: raise ValueError('end precedes start')
        if self.short_window >= self.long_window: raise ValueError('short_window must be below long_window')
        if len(set(self.universe)) != len(self.universe): raise ValueError('Duplicate symbols')
        if self.position_weight_overrides:
            if self.strategy not in ('momentum', 'single_agent', 'multi_agent'):
                raise ValueError('Position weight overrides require momentum or an agent strategy')
            if self.position_weight_overrides.keys() - set(self.universe):
                raise ValueError('Position weight overrides require symbols in the universe')
        if self.strategy == 'buy_and_hold' and 'VOO' not in self.universe: raise ValueError('VOO baseline requires VOO')
        if self.strategy in ('single_agent','multi_agent') and not self.model: raise ValueError('Select a model')
        if self.strategy == 'multi_agent' and self.max_model_calls < 4: raise ValueError('Multi-agent requires four model calls')
        return self

    def position_weight_limit(self, ticker: str) -> float:
        return self.position_weight_overrides.get(ticker, self.max_position_weight)
