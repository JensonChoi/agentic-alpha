from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator, ConfigDict

STRATEGIES = ['buy_and_hold', 'momentum', 'congressional', 'single_agent', 'multi_agent']
class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    action: Literal['BUY', 'SELL', 'HOLD']
    target_weight: float = Field(default=0, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    rationale: str = Field(max_length=2000)
    strategy_id: str = ''
class Proposals(BaseModel):
    signals: list[Signal] = Field(max_length=20)
    summary: str = Field(default='', max_length=3000)
class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default='Research experiment', max_length=100)
    strategy: Literal['buy_and_hold','momentum','congressional','single_agent','multi_agent'] = 'momentum'
    mode: Literal['historical','forward'] = 'historical'
    dataset: str = 'demo'
    start: date = date(2024, 4, 1)
    end: date = date(2024, 12, 31)
    initial_capital: float = Field(default=100000, gt=0, le=1e12)
    universe: list[str] = Field(default=['VOO','AAPL','MSFT','NVDA'], min_length=1, max_length=100)
    max_position_weight: float = Field(default=.1, gt=0, le=1)
    max_exposure: float = Field(default=1, gt=0, le=1)
    max_positions: int = Field(default=5, ge=1, le=100)
    short_window: int = Field(default=20, ge=2)
    long_window: int = Field(default=50, ge=3, le=500)
    rebalance: Literal['daily','weekly','monthly'] = 'weekly'
    fee: float = Field(default=0, ge=0)
    slippage_bps: float = Field(default=5, ge=0, le=1000)
    reinvest_dividends: bool = False
    copy_method: Literal['equal','fixed','proportional'] = 'equal'
    fixed_allocation: float = Field(default=.05, gt=0, le=1)
    provider: Literal['ollama','compatible','openai'] = 'ollama'
    model: str = ''
    decision_model: str = ''
    seed: int = 42
    max_model_calls: int = Field(default=4, ge=1, le=8)
    local_cost_per_hour: float = Field(default=0, ge=0)
    @model_validator(mode='after')
    def validate_config(self):
        if self.end < self.start: raise ValueError('end precedes start')
        if self.short_window >= self.long_window: raise ValueError('short_window must be below long_window')
        if len(set(self.universe)) != len(self.universe): raise ValueError('Duplicate symbols')
        if self.strategy == 'buy_and_hold' and 'VOO' not in self.universe: raise ValueError('VOO baseline requires VOO')
        if self.strategy in ('single_agent','multi_agent') and not self.model: raise ValueError('Select a model')
        if self.strategy == 'multi_agent' and self.max_model_calls < 4: raise ValueError('Multi-agent requires four model calls')
        return self
