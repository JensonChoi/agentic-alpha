"""Separate immutable synthetic fixture; never historical performance evidence."""
import numpy as np
import pandas as pd
from .data import register, sessions


def seed_llm_demo():
    rng=np.random.default_rng(42); rows=[]
    for ticker in ['VOO','QQQ','NVDA','TSLA','AAPL']:
        price=100.
        for day in sessions('2024-01-02','2024-04-12'):
            opening=price; price*=float(np.exp(rng.normal(.002,.005)))
            rows.append(dict(date=day,ticker=ticker,open=opening,close=price,high=max(opening,price)*1.001,low=min(opening,price)*.999,volume=1000000))
    return register('llm-synthetic-v1',pd.DataFrame(rows),'Seed 42 synthetic LLM integration fixture; not historical prices',True)
