"""Regional descriptive views: keep surveillance sources and denominators explicit."""
import pandas as pd
import plotly.graph_objects as go

from .extra_sources import SEA_COUNTRIES


def influenza(frame):
    out=frame[frame.country_code.isin(SEA_COUNTRIES)].copy()
    out["country"]=out.country_code.map(SEA_COUNTRIES)
    out["week_start"]=pd.to_datetime(out.week_start)
    out["influenza_positive"]=out.inf_a+out.inf_b
    valid=out.tested.gt(0) & out.influenza_positive.le(out.tested)
    out["positivity_pct"]=(100*out.influenza_positive/out.tested.where(valid)).round(1)
    return out


def coverage(frame, tb):
    sentinel=frame[frame.origin_source.eq("SENTINEL")]
    rows=[]
    for code,name in SEA_COUNTRIES.items():
        all_sources=frame[frame.country_code.eq(code)]
        observations=sentinel[sentinel.country_code.eq(code) & sentinel.tested.notna()]
        last=observations.sort_values("week_start").tail(1)
        annual=tb[tb.country_code.eq(code)].dropna(subset="incidence_per_100000").sort_values("year").tail(1)
        rows.append({"Country":name,"Latest sentinel week":str(last.week_start.iloc[0].date()) if len(last) else "Unavailable",
                     "Tested specimens":last.tested.iloc[0] if len(last) else None,
                     "Influenza positivity (%)":last.positivity_pct.iloc[0] if len(last) else None,
                     "Reporting sources available":", ".join(sorted(all_sources.origin_source.dropna().unique())) or "None returned",
                     "TB estimate year":str(int(annual.year.iloc[0])) if len(annual) else "Unavailable",
                     "TB incidence / 100,000":annual.incidence_per_100000.iloc[0] if len(annual) else None})
    return pd.DataFrame(rows)


def flu_chart(frame):
    data=frame[frame.origin_source.eq("SENTINEL")].copy()
    end=data.week_start.max()
    start=data.week_start.min()
    figure=go.Figure()
    # A common calendar window, explicit missing calendar weeks, and no fallback
    # from sentinel to another source allow interpretable country comparisons.
    calendar=pd.date_range(start,end,freq="W-SUN")
    for code,name in SEA_COUNTRIES.items():
        part=data[data.country_code.eq(code)].set_index("week_start").reindex(calendar)
        figure.add_scatter(x=calendar,y=part.positivity_pct,name=name,connectgaps=False,
                           customdata=part.tested,hovertemplate="%{x|%d %b %Y}<br>%{y:.1f}% positive<br>%{customdata} tested<extra>%{fullData.name}</extra>")
    figure.update_layout(meta=dict(kind="region-flu"),template="plotly_white",height=480,margin=dict(l=60,r=25,t=30,b=60),
                         yaxis_title="Influenza A + B positivity (%)",xaxis_title="Week starting (MMWR)",
                         legend=dict(orientation="h",y=-.2),hovermode="closest",yaxis=dict(rangemode="tozero"))
    return figure


def tb_chart(tb):
    figure=go.Figure()
    for code,name in SEA_COUNTRIES.items():
        part=tb[tb.country_code.eq(code)].dropna(subset="incidence_per_100000").sort_values("year")
        figure.add_scatter(x=part.year,y=part.incidence_per_100000,name=name,connectgaps=False)
    figure.update_layout(meta=dict(kind="region-tb"),template="plotly_white",height=480,margin=dict(l=65,r=25,t=30,b=60),
                         xaxis_title="Year",yaxis_title="Estimated incident TB cases per 100,000 population",
                         legend=dict(orientation="h",y=-.2),hovermode="x unified",yaxis=dict(rangemode="tozero"))
    return figure
