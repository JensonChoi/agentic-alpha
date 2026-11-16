from copy import deepcopy
from decimal import Decimal
from test_engine import fixture,config
from app.engine import simulate

async def test_cash_interest_calendar_days_and_restart():
    f,m=fixture()
    c=config(strategy='congressional',cash_interest_rate=.035)
    saved=[]
    def checkpoint(progress,state): saved.append(deepcopy(state)); return True
    result=await simulate(c,f,m,checkpoint)
    expected=Decimal('100000'); previous=c.start
    for point in result['equity']:
        from datetime import date
        day=date.fromisoformat(point['date'])
        expected+=expected*Decimal('.035')*Decimal((day-previous).days)/Decimal(365)
        previous=day
    assert result['cash']==float(expected)
    resumed=await simulate(c,f,m,resume=saved[4])
    assert resumed['metrics']==result['metrics']
    assert resumed['equity']==result['equity']
