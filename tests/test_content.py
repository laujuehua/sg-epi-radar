import pytest
import pandas as pd
from sgsurv.content import normalise,tags
from sgsurv.clean import psi_from_daily_peaks


def test_mers_is_not_labelled_as_covid():
    assert "MERS" in tags("Middle East respiratory syndrome coronavirus - Saudi Arabia")
    assert "COVID-19" not in tags("Middle East respiratory syndrome coronavirus - Saudi Arabia")


def test_feed_links_reject_untrusted_urls_and_strip_title_markup():
    with pytest.raises(ValueError):
        normalise("Influenza outbreak","javascript:alert(1)","2026-10-23","Source","Global","Media headline")
    item=normalise("<b>Influenza</b> &amp; surveillance","https://www.who.int/example","2026-10-23","WHO","Global","Official outbreak notice")
    assert item["title"]=="Influenza & surveillance"


def test_non_health_media_is_not_included_as_an_outbreak():
    assert normalise("New train timetable","https://www.channelnewsasia.com/example","2026-10-23","CNA","Singapore","Media headline") is None


def test_refreshed_psi_uses_daily_peaks_not_regional_means_and_flags_partial_weeks():
    daily=pd.DataFrame({"date":["2026-10-18","2026-10-19","2026-10-25"],"psi_daily_max":[90,110,30],"psi_daily_mean":[10,20,15]})
    out=psi_from_daily_peaks(daily)
    assert out.psi_mean.tolist()==[100,30]
    assert out.days_with_data.tolist()==[2,1]
    assert out.days_unhealthy.tolist()==[1,0]
    assert out.haze_week.tolist()==[True,False]
