import pandas as pd
from sgsurv.insights import signal_episodes, seasonal_comparison
from sgsurv.revisions import case_changes, record_snapshot
from sgsurv.evaluation import evaluate_events


def sample():
    return pd.DataFrame(dict(disease=["Test"]*5,week_start=pd.date_range("2020-01-05",periods=5,freq="7D"),
        cases=[10,20,30,float("nan"),40],any_alert=[False,True,True,False,True],
        hl_alert=[False,True,True,False,True],c2_alert=[False,True,True,False,True],
        hl_threshold=[15]*5,c2_threshold=[15]*5,year=[2020]*5,week=[1,2,3,4,5]))


def test_episodes_reset_after_missing_week_and_calendar_gap():
    out=signal_episodes(sample())
    assert out.signal_run_weeks.tolist()==[0,1,2,0,1]
    assert out.signal_state.tolist()==["No signal","New signal","Continuing signal","Unavailable","New signal"]
    assert signal_episodes(sample().drop(index=1)).signal_run_weeks.tolist()==[0,1,0,1]


def test_revisions_only_compare_existing_observations():
    old=sample()
    new=old.copy()
    new.loc[0,"cases"]=12
    new.loc[3,"cases"]=0
    changes=case_changes(old,new)
    assert len(changes["changes"])==2
    assert changes["changes"][1]["previous_cases"] is None
    assert changes["changes"][1]["current_cases"]==0
    history=record_snapshot(None,old,new,"new","2026-10-22T00:00:00Z")
    assert len(record_snapshot(history,old,new,"new","later")["updates"])==1
    assert case_changes(old,old.iloc[1:])["removed_rows"]==1


def test_evaluation_distinguishes_missing_coverage_from_no_signal():
    df=sample()
    event=dict(event="Example",disease="Test",anchor_week="2020-01-05",window_weeks=3)
    out=evaluate_events(df,[event])
    assert out.weeks_after_anchor.eq(1).all()
    assert out.evaluable_weeks.eq(3).all()
    assert out.unclassified_signals_outside_window.eq(1).all()
    df["any_alert"]=False
    event["window_weeks"]=5
    assert evaluate_events(df,[event]).iloc[0].status=="Insufficient coverage"


def test_seasonal_uses_epi_year_and_preserves_missing():
    df=sample()
    out=seasonal_comparison(df,"Test")
    assert out.week.tolist()==[1,2,3,4,5]
    assert out.cases.isna().sum()==1
