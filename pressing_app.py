"""
Pressing Analyst – SkillCorner Dynamic Events
==============================================
"Is our pressing a wall that stops progression, or a gamble that leaves us exposed?"
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from pressing_metrics import (
    ball_recoveries,
    bypass_rate,
    chances_after_pressing,
    chances_from_recovery,
    forced_long_ball_ratio,
    pressing_derived_bundle,
    opponent_pass_completion,
    player_pressing_stats,
    ppda,
    pressing_chain_analysis,
    pressing_effectiveness_score,
    progression_filter,
    xthreat_disruption,
)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
DATA_DIR = Path(r"D:\ContextEngineeringProject\dynamic_events_pl_24\dynamic_events_pl_24")
CACHE_FILE = DATA_DIR / "_pressing_cache.parquet"
META_DIR = DATA_DIR / "meta"

st.set_page_config(
    page_title="Pressing Analyst",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    return pd.read_parquet(CACHE_FILE)


@st.cache_data(show_spinner=False)
def load_all_meta() -> dict:
    metas = {}
    for f in META_DIR.glob("*.json"):
        with open(f, "r", encoding="utf-8") as fh:
            metas[int(f.stem)] = json.load(fh)
    return metas


@st.cache_data(show_spinner=False)
def build_match_index(df: pd.DataFrame) -> pd.DataFrame:
    metas = load_all_meta()
    available = set(df["match_id"].unique())
    rows = []
    for mid, m in metas.items():
        if mid not in available:
            continue
        rows.append({
            "match_id": mid,
            "date": m.get("date_time", "")[:10],
            "home_team": m["home_team"]["short_name"],
            "away_team": m["away_team"]["short_name"],
            "home_score": m.get("home_team_score", ""),
            "away_score": m.get("away_team_score", ""),
            "stadium": m.get("stadium", {}).get("name", ""),
        })
    idx = pd.DataFrame(rows)
    idx["label"] = (
        idx["date"] + "  |  " +
        idx["home_team"] + " " + idx["home_score"].astype(str) +
        " - " + idx["away_score"].astype(str) + " " + idx["away_team"]
    )
    return idx.sort_values("date", ascending=False).reset_index(drop=True)


# Bump when league_pressing_table / distributions logic or columns change (invalidates disk + @st.cache_data).
_CACHE_SCHEMA = 4


@st.cache_data(show_spinner=False)
def _pressing_derived(df: pd.DataFrame, *, _schema: int = _CACHE_SCHEMA):
    _ = _schema
    return pressing_derived_bundle(df, DATA_DIR, CACHE_FILE, _schema)


def get_league_table(df: pd.DataFrame, *, _schema: int = _CACHE_SCHEMA) -> pd.DataFrame:
    return _pressing_derived(df, _schema=_schema)[0]


def get_league_distributions(df: pd.DataFrame, *, _schema: int = _CACHE_SCHEMA) -> dict:
    return _pressing_derived(df, _schema=_schema)[1]


def get_match_distributions(df: pd.DataFrame, *, _schema: int = _CACHE_SCHEMA) -> dict:
    return _pressing_derived(df, _schema=_schema)[2]


# ─────────────────────────────────────────────────────────────────────────────
# PITCH HELPER
# ─────────────────────────────────────────────────────────────────────────────
def draw_pitch(fig: go.Figure) -> go.Figure:
    hl, hw = 52.5, 34
    lc = "white"
    shapes = [
        dict(type="rect", x0=-hl, y0=-hw, x1=hl, y1=hw, line=dict(color=lc, width=2)),
        dict(type="line", x0=0, y0=-hw, x1=0, y1=hw, line=dict(color=lc, width=2)),
        dict(type="circle", x0=-9.15, y0=-9.15, x1=9.15, y1=9.15, line=dict(color=lc, width=1.5)),
        dict(type="rect", x0=-hl, y0=-20.15, x1=-hl + 16.5, y1=20.15, line=dict(color=lc, width=1.5)),
        dict(type="rect", x0=hl - 16.5, y0=-20.15, x1=hl, y1=20.15, line=dict(color=lc, width=1.5)),
        dict(type="rect", x0=-hl, y0=-9.16, x1=-hl + 5.5, y1=9.16, line=dict(color=lc, width=1.5)),
        dict(type="rect", x0=hl - 5.5, y0=-9.16, x1=hl, y1=9.16, line=dict(color=lc, width=1.5)),
        dict(type="line", x0=-hl / 3, y0=-hw, x1=-hl / 3, y1=hw,
             line=dict(color=lc, width=0.8, dash="dot")),
        dict(type="line", x0=hl / 3, y0=-hw, x1=hl / 3, y1=hw,
             line=dict(color=lc, width=0.8, dash="dot")),
    ]
    fig.update_layout(
        shapes=shapes, plot_bgcolor="#2d7a3a",
        xaxis=dict(range=[-57, 57], showgrid=False, zeroline=False, showticklabels=False, fixedrange=True),
        yaxis=dict(range=[-38, 38], showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x", fixedrange=True),
        margin=dict(l=10, r=10, t=40, b=10), height=480,
    )
    return fig


OBE_COLORS = {
    "pressing": "#e74c3c",
    "pressure": "#f39c12",
    "counter_press": "#3498db",
    "recovery_press": "#2ecc71",
    "other": "#95a5a6",
}


# ─────────────────────────────────────────────────────────────────────────────
# HELP TEXTS
# ─────────────────────────────────────────────────────────────────────────────
HELP = {
    "effectiveness_score": (
        "A single score (0–100) using percentile normalization. "
        "League view: each component is ranked vs all 20 teams' season totals. "
        "Match view: ranked vs every team-appearance in the dataset (~760 games). "
        "Includes how often the press is **beaten** (bypassed) and how much **danger** "
        "the opponent creates in pressing situations — both scored so higher = better (rarer / safer). "
        "60+ = 'Wall', 40–59 = 'Balanced', below 40 = 'Gamble'."
    ),
    "regains": (
        "How many times the team won the ball back as a direct result of pressing. "
        "Counts moments where a pressing action ended with the team regaining possession."
    ),
    "regains_per_match": (
        "Average ball recoveries from pressing per game. "
        "Higher = pressing frequently wins the ball back."
    ),
    "ppda": (
        "Passes Per Defensive Action — a standard pressing intensity metric. "
        "Counts how many passes the opponent completes for every pressing action we make. "
        "Lower = more aggressive pressing. Example: 8 = very intense, 15+ = passive."
    ),
    "ppda_hb": (
        "Same as PPDA but only during 'high block' — when the team is pressing high up the pitch, "
        "near the opponent's goal. Isolates pressing intensity at its most aggressive."
    ),
    "long_ball_delta": (
        "How much pressing increases the opponent's long-ball frequency. "
        "Compares the % of long passes (>30m) from the opponent's own third during high pressing vs normal play. "
        "Positive = pressing forces more desperate long passes."
    ),
    "block_rate": (
        "How often the opponent gets stuck in their own third. "
        "When they start with the ball deep in their half, this shows what % of the time "
        "they fail to advance past that zone. Higher = pressing traps them effectively."
    ),
    "bypass_rate": (
        "How often the opponent skips the press entirely — going from their own deep zone "
        "all the way to our defensive zone in one move. Lower = our press is hard to beat."
    ),
    "chains": (
        "A 'pressing chain' is when 2+ players press the opponent in rapid succession (within 4 seconds). "
        "More chains = more organized, team-coordinated pressing."
    ),
    "chain_length": (
        "Average number of players involved in each pressing chain. "
        "Longer = more sustained, multi-player pressing sequences."
    ),
    "chain_regain": (
        "How many collective pressing chains ended with the team winning the ball. "
        "Shows whether coordinated pressing actually leads to ball recovery."
    ),
    "force_backward": (
        "How many times a pressing defender forced the opponent to play a backward pass. "
        "The opponent wanted to go forward but the pressure made them retreat."
    ),
    "beaten_rate": (
        "**Press break (beaten):** how often the press is bypassed — the ball carrier dribbles past the presser, "
        "or an opponent’s off-ball run takes the presser out of the play. "
        "This is the frequency of the press being ‘broken’ in a duel. Lower = more solid pressing."
    ),
    "danger_rate": (
        "**Danger during / after press breaks down:** how often, while you are pressing, the opponent’s "
        "attacking threat spikes (EPV above 3%). It captures how exposed you are when the press does not hold. "
        "Lower = less danger conceded from pressing situations."
    ),
    "radar_beaten_component": (
        "Composite sub-score (0–100): how rarely your press is **beaten** vs the reference group "
        "(league teams or all team-games). Higher = fewer bypasses per engagement than peers."
    ),
    "radar_danger_component": (
        "Composite sub-score (0–100): how rarely **danger** (EPV spike) happens during your pressing "
        "vs the reference group. Higher = you limit threat when the press is under strain."
    ),
    "shots_after": (
        "How many times the opponent shot within 10 seconds after a pressing action where we did NOT win the ball. "
        "Regain events are excluded to avoid counting our own shots after recovery."
    ),
    "goals_after": (
        "How many times a goal was conceded within 10 seconds after a pressing action where we did NOT win the ball. "
        "The worst-case outcome of a failed press."
    ),
    "shots_from_regain": (
        "How many times the team created a shot within 10 seconds of winning the ball through pressing. "
        "Shows the attacking reward of successful pressing."
    ),
    "xshot_after_regain": (
        "SkillCorner **xShot** on regain-ending OBE rows (`xshot_player_possession_end`): expected-goals-style "
        "value for the team possession following that ball win. Summed over all regains = total attacking "
        "quality generated after pressing recoveries (not the same as summing only shots)."
    ),
    "xshot_after_regain_pm": (
        "Total xShot after regains in the sample, divided by matches — **xG-style output per game** from "
        "possessions that started with a pressing regain."
    ),
    "xshot_per_regain": (
        "Average xShot per regain event. Higher = each ball win tends to lead into more dangerous possessions."
    ),
    "xshot_on_shot_regains": (
        "Sum of xShot only on regain rows where **lead_to_shot** is true (regains that led to a shot within 10s)."
    ),
    "xt_disruption": (
        "How much pressing reduces the quality of the opponent's passing options, "
        "adjusted for pitch zone to avoid positional bias. "
        "Compares xThreat within the same zone during high pressing vs normal play. "
        "Higher = pressing shuts down dangerous passing lanes."
    ),
    "opp_pass_pct": (
        "The opponent's pass accuracy (% of successful passes) in a specific zone and phase. "
        "When this drops during high pressing, it means our press is making it harder for them to pass accurately."
    ),
    "engagements_per_match": (
        "Average number of pressing actions this player makes per game. "
        "Higher = more active in pressing. Depends on position and role."
    ),
    "regain_rate": (
        "What percentage of this player's pressing actions end with winning the ball. "
        "Higher = more effective individual presser."
    ),
    "in_chain": (
        "How often this player is part of a collective pressing chain — "
        "a coordinated sequence where 2+ teammates press in rapid succession. "
        "Higher = more involved in team pressing patterns."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 1 – LEAGUE PRESSING OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
def page_league_overview():
    st.header("League Pressing Overview")
    st.caption('"Is our pressing a wall that stops progression, or a gamble that leaves us exposed?"')

    df = load_data()

    with st.spinner("Computing league table..."):
        table = get_league_table(df)

    # ── Top KPIs ──
    avg_score = table["effectiveness_score"].mean()
    best = table.iloc[0]
    worst = table.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("League Avg. Score", f"{avg_score:.0f}/100", help=HELP["effectiveness_score"])
    c2.metric("Most Effective", f"{best['team']} ({best['effectiveness_score']:.0f})",
              help="Team with the highest Pressing Effectiveness Score.")
    c3.metric("Least Effective", f"{worst['team']} ({worst['effectiveness_score']:.0f})",
              help="Team with the lowest Pressing Effectiveness Score.")
    c4.metric("Avg. PPDA", f"{table['ppda'].mean():.2f}", help=HELP["ppda"])

    st.divider()

    # ── Effectiveness bar chart ──
    c1, c2 = st.columns([3, 2])
    with c1:
        st.subheader("Pressing Effectiveness Score")
        t_sorted = table.sort_values("effectiveness_score", ascending=True)
        colors = t_sorted["effectiveness_label"].map(
            {"Wall": "#2ecc71", "Balanced": "#f39c12", "Gamble": "#e74c3c"}
        )
        fig = go.Figure(go.Bar(
            x=t_sorted["effectiveness_score"], y=t_sorted["team"],
            orientation="h", marker_color=colors,
            text=t_sorted["effectiveness_label"],
            textposition="inside",
        ))
        fig.update_layout(height=550, margin=dict(t=10, b=10, l=10, r=10),
                          xaxis_title="Score (0-100)", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Wall vs Gamble Radar")
        selected_team = st.selectbox("Select Team", table["team"].tolist(), key="radar_team")
        league_dist = get_league_distributions(df)
        pes = pressing_effectiveness_score(df, selected_team, league_distributions=league_dist)
        comp = pes["components"]

        categories = [
            "Recovery",
            "Progression\nBlock",
            "Forced\nLong Ball",
            "Beaten\n(press bypass)",
            "Danger\n(under press)",
        ]
        values = [comp["recovery"], comp["block"], comp["forced_long_ball"], comp["not_beaten"], comp["not_danger"]]

        fig = go.Figure(go.Scatterpolar(
            r=values + [values[0]],
            theta=categories + [categories[0]],
            fill="toself", name=selected_team,
            fillcolor="rgba(46, 204, 113, 0.3)",
            line_color="#2ecc71",
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            height=400, margin=dict(t=30, b=30),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "**Beaten** = how often the press is bypassed (dribble / run); **Danger** = how often the opponent’s "
            "threat jumps during a press. On this chart, **higher** on those axes = you limit breaks and danger "
            "**more** than the comparison set (percentile-based)."
        )
        st.metric("Composite Score", f"{pes['score']:.0f}/100", delta=pes["label"],
                  help=HELP["effectiveness_score"])

    st.divider()

    # ── League table ──
    st.subheader("Detailed Pressing Table")

    with st.expander("ℹ️ How are table columns calculated?"):
        st.markdown("""
**Score** — *Overall pressing effectiveness (0–100)*

A single number that summarizes how good a team's pressing is. It combines five components with equal weight:
1. **Recovery** — how often pressing wins the ball back
2. **Block** — how often the opponent is trapped in their own third
3. **Forced Long Ball** — how much pressing shifts pass length (long-ball delta from their D3)
4. **Beaten (press bypass)** — how often the press is broken (dribble past or beaten by movement); score reflects how **rare** that is vs peers
5. **Danger (under press)** — how often the opponent’s threat spikes while you press; score reflects how **rare** that danger is vs peers

Each component is scored using **percentile normalization**. In the **league table**, each team's season-long raw value is ranked against the other 19 teams (20 values per metric). On the **match analysis** page, each metric is ranked against all team-games in the season (~760 samples) so a single game is compared to other games, not to full-season aggregates. The final score is the average of all five component percentiles. **60+** = "Wall", **40–59** = "Balanced", **<40** = "Gamble".

> **Data source:** Uses five SkillCorner metrics combined:
> - Recovery score: percentile rank of (regain count / total OBE) among all teams. From **end_type** = "direct_regain" or "indirect_regain" on OBE events.
> - Block score: percentile rank of block rate among all teams. From **third_start** and **third_end** on opponent PP.
> - Forced Long Ball score: percentile rank of long-ball delta among all teams. From **pass_range** = "long" ratio difference between **team_out_of_possession_phase_type** = "high_block" and overall.
> - **Beaten** component: **inverted** percentile of bypass rate — “how often is the press broken?” Lower raw beaten % → higher wedge. From **beaten_by_possession** and **beaten_by_movement** on OBE.
> - **Danger** component: **inverted** percentile of danger rate — “how often does pressing leave us exposed?” Lower raw danger % → higher wedge. From **possession_danger** on OBE.
>
> Formula: **(Recovery pct + Block pct + Forced LB pct + (100 − Beaten pct) + (100 − Danger pct)) / 5** where the last two use percentile ranks of the raw rates

---

**Regains/Match** — *Ball recoveries per game*

When a pressing action directly causes the team to win the ball back, that's a "regain." This column counts all regains across the season and divides by the number of matches. A higher number means pressing frequently leads to winning the ball.

> **Data source:** Filters all OBE events for the team, then counts rows where **end_type** is "direct_regain" or "indirect_regain". Divides by the number of unique **match_id** values.

---

**Long Ball Delta** — *How much pressing increases long passes (percentage points)*

The pitch is divided into thirds. When the opponent tries to play out from their own defensive third (the deepest zone), we look at what percentage of their passes are "long" (over ~30 meters). We calculate this percentage **during high pressing** and **overall**, then subtract: **high pressing % minus overall %**. A **positive** number means pressing is forcing the opponent to hit longer, more desperate passes instead of building up calmly.

> **Data source:** Takes opponent Player Possessions (PP) where **third_start** = "defensive_third" and **end_type** = "pass". Calculates the ratio of **pass_range** = "long" to total passes. Then filters to only rows where **team_out_of_possession_phase_type** = "high_block" and recalculates.
>
> Formula: **long ratio during high block − long ratio overall**

---

**Block %** — *How often the opponent gets stuck in their own third*

When the opponent has the ball in their own defensive third, this measures how often they **fail** to advance it to the middle of the pitch. A **higher** percentage means pressing is locking the opponent in their own zone.

> **Data source:** Takes opponent PP where **third_start** = "defensive_third". Counts how many have **third_end** = "defensive_third" (stayed) vs **third_end** = "middle_third" or "attacking_third" (progressed).
>
> Formula: **stayed in D3 / total starting in D3 × 100**

---

**Bypass %** — *How often the opponent skips the press entirely*

This is the flip side of Block %. It measures how often the opponent goes directly from their own defensive third all the way to our defensive third — effectively bypassing our entire pressing structure. A **lower** number is better.

> **Data source:** Takes opponent PP where **third_start** = "defensive_third". Counts how many have **third_end** = "attacking_third" (our defensive third, since coordinates are flipped for the opponent).
>
> Formula: **bypassed to attacking third / total starting in D3 × 100**

---

**PPDA** — *Passes Per Defensive Action*

A widely-used pressing intensity metric. It counts how many passes the opponent completes for every one defensive pressing action we make. **Lower is more intense** — for example, a PPDA of 8 means we engage defensively every 8 opponent passes (very aggressive). A PPDA of 15+ means we sit back and let them pass around.

> **Data source:** Numerator: opponent PP where **end_type** = "pass". Denominator: all OBE events by our team.
>
> Formula: **opponent pass count / our OBE count**

---

**PPDA (HB)** — *PPDA during high-block phases only*

Same calculation as PPDA, but only counting moments when the team is in a "high block" — meaning they are pressing high up the pitch near the opponent's goal. This isolates pressing intensity during the most aggressive phases.

> **Data source:** Same as PPDA, but both numerator and denominator are filtered to **team_out_of_possession_phase_type** = "high_block".

---

**xT Disruption %** — *How much pressing reduces the quality of opponent passing options*

xThreat (expected threat) measures how dangerous a pass option is — specifically, the probability that a pass will lead to a goal within 10 seconds. This column compares the average xThreat of opponent passing options **during high pressing** vs **during other phases**, adjusted for pitch zone to remove positional bias. Without zone adjustment, disruption would appear artificially high (~95%) simply because high pressing happens when the opponent is deep in their own half where xThreat is naturally low.

> **Data source:** Takes opponent Passing Option (PO) events. For each zone (defensive, middle, attacking third), separately calculates xThreat under **team_out_of_possession_phase_type** = "high_block" vs other phases. The final value is a zone-weighted average disruption.
>
> Formula: **Σ (zone disruption × HB count in zone) / total HB count**, where zone disruption = **(1 − zone HB xThreat / zone non-HB xThreat) × 100**

---

**Opp Pass%(D3,HB)** — *Opponent pass accuracy in their own third under high press*

When we press high and the opponent tries to pass from their own defensive third, this shows their pass completion rate. A **lower** number compared to their overall pass accuracy means our pressing is disrupting their ability to pass accurately under pressure.

> **Data source:** Takes opponent PP where **end_type** = "pass", **third_start** = "defensive_third", and **team_out_of_possession_phase_type** = "high_block". Counts rows where **pass_outcome** = "successful".
>
> Formula: **successful passes / total passes × 100** (in D3 during high block)

---

**Beaten %** — *How often the press is broken (bypassed)*

When a pressing player engages the ball carrier, this measures how often the press is **beaten** — either by the ball carrier dribbling past them ("beaten by possession") or by a teammate making a run that the presser can't track ("beaten by movement"). Think: **frequency of the press failing in a duel**. A **lower** percentage means a more solid press.

> **Data source:** From all OBE events by our team, sums the boolean columns **beaten_by_possession** (ball carrier dribbled past the presser) and **beaten_by_movement** (opponent's off-ball run bypassed the presser between the final pass and reception).
>
> Formula: **(beaten_by_possession + beaten_by_movement) / total OBE count × 100**

---

**Danger %** — *How often the opponent becomes dangerous while you are pressing*

During a pressing engagement, if the opponent’s expected possession value (EPV — how likely they are to score from that moment) exceeds 3%, it is flagged as dangerous. Think of it as **threat when the press is engaged or breaking down**. This column is the % of your pressing actions where that happens. **Lower is better** — the press does not concede attacking momentum as often.

> **Data source:** From all OBE events by our team, counts rows where **possession_danger** = True. This flag is set by SkillCorner when the opponent's EPV (Expected Possession Value) exceeds 3% at any point during the engagement.
>
> Formula: **possession_danger True count / total OBE count × 100**

---

**Shots/Regain/M** — *Shots created from ball recoveries, per match*

After winning the ball through pressing, this counts how often a shot occurs within 10 seconds. Divided by matches played. A **higher** number means pressing isn't just defensive — it's creating attacking opportunities.

> **Data source:** From OBE events where **end_type** = "direct_regain" or "indirect_regain", counts rows where **lead_to_shot** = True. This SkillCorner flag indicates a shot occurred within 10 seconds of the event. Divides by unique **match_id** count.
>
> Formula: **regain events with lead_to_shot / match count**

---

**xShot after regains** — *Expected-goals-style value from possessions after ball wins*

SkillCorner does not ship a column named `xg`; it provides **xShot** on events tied to the following possession. For each OBE with **end_type** = direct/indirect regain, **xshot_player_possession_end** is summed. That total is an **xG-like** measure of how much quality the team generated in sequences that began with that regain. **xShot/Regain/M** divides the season total by matches; **xShot/Regain** is the average per regain row.

> **Data source:** OBE rows, **end_type** in {direct_regain, indirect_regain}, column **xshot_player_possession_end** (missing column → 0).

---

**Chains/Match** — *Collective pressing sequences per game*

A "pressing chain" is when two or more players press the opponent in rapid succession (within 4 seconds of each other). This column counts the total number of such coordinated sequences per match. More chains = more organized, collective pressing rather than individual efforts.

> **Data source:** From OBE events where **pressing_chain** = True, counts rows where **index_in_pressing_chain** = 1 (the start of each unique chain). Divides by unique **match_id** count. Chain length is stored in **pressing_chain_length**, and outcome in **pressing_chain_end_type** ("regain" or "disruption").
>
> Formula: **unique chain starts / match count**
""")

    display_cols = {
        "team": "Team",
        "effectiveness_score": "Score",
        "effectiveness_label": "Label",
        "regains_per_match": "Regains/Match",
        "forced_long_delta": "Long Ball Delta",
        "block_rate": "Block %",
        "bypass_rate": "Bypass %",
        "ppda": "PPDA",
        "ppda_high_block": "PPDA (HB)",
        "xt_disruption_pct": "xT Disruption %",
        "opp_pass_pct_d3_hb": "Opp Pass%(D3,HB)",
        "beaten_rate": "Beaten %",
        "danger_rate": "Danger %",
        "shots_from_regain_pm": "Shots/Regain/M",
        "xshot_after_regain_pm": "xShot/Regain/M",
        "xshot_per_regain": "xShot/Regain",
        "chains_per_match": "Chains/Match",
    }
    cols_ok = [k for k in display_cols if k in table.columns]
    display_df = table[cols_ok].rename(columns={k: display_cols[k] for k in cols_ok})
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.divider()

    # ── Scatter plots ──
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("PPDA vs Effectiveness Score")
        fig = px.scatter(table, x="ppda", y="effectiveness_score",
                         text="team", color="effectiveness_label",
                         color_discrete_map={"Wall": "#2ecc71", "Balanced": "#f39c12", "Gamble": "#e74c3c"},
                         labels={"ppda": "PPDA (lower = more intense)", "effectiveness_score": "Score"})
        fig.update_traces(textposition="top center", marker_size=12)
        fig.update_layout(height=400, margin=dict(t=30, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Bypass % vs Block %")
        fig = px.scatter(table, x="block_rate", y="bypass_rate",
                         text="team", color="effectiveness_label",
                         color_discrete_map={"Wall": "#2ecc71", "Balanced": "#f39c12", "Gamble": "#e74c3c"},
                         labels={"block_rate": "A1 Block %", "bypass_rate": "A1→A3 Bypass %"})
        fig.update_traces(textposition="top center", marker_size=12)
        fig.update_layout(height=400, margin=dict(t=30, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 2 – MATCH PRESSING ANALYSIS  (question-based structure)
# ─────────────────────────────────────────────────────────────────────────────
def page_match_analysis():
    st.header("Match Pressing Analysis")

    df = load_data()
    match_index = build_match_index(df)

    selected_label = st.selectbox("Select Match", match_index["label"].tolist())
    row = match_index[match_index["label"] == selected_label].iloc[0]
    match_id = row["match_id"]
    home = row["home_team"]
    away = row["away_team"]

    st.markdown(f"### {home} {row['home_score']} - {row['away_score']} {away}")
    st.caption(f"{row['date']}  |  {row['stadium']}")
    st.divider()

    mdf = df[df["match_id"] == match_id]
    teams_in_match = [home, away]
    analyse_team = st.radio("Analyse pressing of", teams_in_match, horizontal=True)
    opponent = away if analyse_team == home else home

    # Pre-compute all metrics
    rec = ball_recoveries(mdf, analyse_team, match_id)
    flb = forced_long_ball_ratio(mdf, analyse_team, match_id)
    prog = progression_filter(mdf, analyse_team, match_id)
    byp = bypass_rate(mdf, analyse_team, match_id)
    ppda_val = ppda(mdf, analyse_team, match_id)
    xt = xthreat_disruption(mdf, analyse_team, match_id)
    opc = opponent_pass_completion(mdf, analyse_team, match_id)
    cap = chances_after_pressing(mdf, analyse_team, match_id)
    cfr = chances_from_recovery(mdf, analyse_team, match_id)
    pca = pressing_chain_analysis(mdf, analyse_team, match_id)
    match_dist = get_match_distributions(df)
    pes = pressing_effectiveness_score(
        mdf, analyse_team, match_id, match_distributions=match_dist,
    )

    # ── Overall score header ──
    c1, c2, c3 = st.columns([1, 1, 2])
    c1.metric("Pressing Score", f"{pes['score']:.0f}/100", delta=pes["label"],
              help=HELP["effectiveness_score"])
    st.caption(
        "Score uses **percentiles vs all team-games** in the season (this match vs ~760 samples), "
        "not vs full-season team averages."
    )
    c2.metric("PPDA", ppda_val["ppda_overall"], help=HELP["ppda"])

    with c3:
        comp = pes["components"]
        categories = [
            "Recovery", "Block", "Forced LB",
            "Beaten\n(press bypass)", "Danger\n(under press)",
        ]
        values = [comp["recovery"], comp["block"], comp["forced_long_ball"],
                  comp["not_beaten"], comp["not_danger"]]
        fig = go.Figure(go.Scatterpolar(
            r=values + [values[0]],
            theta=categories + [categories[0]],
            fill="toself", fillcolor="rgba(46,204,113,0.3)", line_color="#2ecc71",
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            height=250, margin=dict(t=20, b=20, l=40, r=40), showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "**Beaten** = press bypass frequency; **Danger** = threat spikes while pressing. "
            "Higher wedges = you do **better** than the season’s team-game distribution (rarer breaks / less danger)."
        )

    st.divider()

    # ── 5 Questions as Tabs ──
    q1, q2, q3, q4, q5 = st.tabs([
        "Q1: Are we winning the ball?",
        "Q2: Are we forcing long balls?",
        "Q3: Are we disrupting build-up?",
        "Q4: Is the opponent creating chances?",
        "Q5: Are we creating chances?",
    ])

    # ── Q1: ARE WE WINNING THE BALL? ──
    with q1:
        st.subheader("Q1: Are we winning the ball back?")
        st.caption("Measures how often and where the team recovers possession through pressing.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Regains", rec["total_regains"], help=HELP["regains"])
        c2.metric("Chain Regains", rec["chain_regains"], help=HELP["chain_regain"])
        c3.metric("Pressing Chains", pca["total_chains"], help=HELP["chains"])
        c4.metric("Avg Chain Length", pca["avg_chain_length"], help=HELP["chain_length"])

        col_map, col_zone = st.columns([3, 2])
        with col_map:
            st.markdown("**Pressing Engagement Map**")
            obe = mdf[(mdf["event_type"] == "on_ball_engagement") & (mdf["team_shortname"] == analyse_team)]
            obe_valid = obe.dropna(subset=["x_start", "y_start"])

            fig = go.Figure()
            fig = draw_pitch(fig)
            for sub, color in OBE_COLORS.items():
                sub_data = obe_valid[obe_valid["event_subtype"] == sub]
                if len(sub_data) == 0:
                    continue
                regain_mask = sub_data["end_type"].isin({"direct_regain", "indirect_regain"})
                non_regain = sub_data[~regain_mask]
                regained = sub_data[regain_mask]
                if len(non_regain) > 0:
                    fig.add_trace(go.Scatter(
                        x=non_regain["x_start"], y=non_regain["y_start"],
                        mode="markers",
                        marker=dict(size=8, color=color, opacity=0.5,
                                    line=dict(width=0.5, color="white")),
                        name=f"{sub} ({len(non_regain)})",
                        hovertext=non_regain["player_name"], hoverinfo="text",
                    ))
                if len(regained) > 0:
                    fig.add_trace(go.Scatter(
                        x=regained["x_start"], y=regained["y_start"],
                        mode="markers",
                        marker=dict(size=12, color=color, opacity=1.0,
                                    symbol="star", line=dict(width=1, color="white")),
                        name=f"{sub} REGAIN ({len(regained)})",
                        hovertext=regained["player_name"], hoverinfo="text",
                    ))
            fig.update_layout(title=f"{analyse_team} – Pressing Actions (★ = regain)")
            st.plotly_chart(fig, use_container_width=True)

        with col_zone:
            st.markdown("**Regains by Zone**")
            zone_data = pd.DataFrame({
                "Zone": ["Attacking Third", "Middle Third", "Defensive Third"],
                "Regains": [
                    rec["regains_attacking_third"],
                    rec["regains_middle_third"],
                    rec["regains_defensive_third"],
                ],
            })
            fig = px.bar(zone_data, x="Regains", y="Zone", orientation="h",
                         color="Zone", color_discrete_map={
                             "Attacking Third": "#e74c3c",
                             "Middle Third": "#f39c12",
                             "Defensive Third": "#3498db",
                         })
            fig.update_layout(height=250, margin=dict(t=10, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("**Pressing Chain Outcomes**")
            chain_outcomes = pd.DataFrame({
                "Outcome": ["Regain", "Disruption", "Other"],
                "Count": [
                    pca["chain_end_regain"],
                    pca["chain_end_disruption"],
                    pca["total_chains"] - pca["chain_end_regain"] - pca["chain_end_disruption"],
                ],
            })
            chain_outcomes = chain_outcomes[chain_outcomes["Count"] > 0]
            if len(chain_outcomes) > 0:
                fig = px.pie(chain_outcomes, values="Count", names="Outcome", hole=0.4,
                             color="Outcome", color_discrete_map={
                                 "Regain": "#2ecc71", "Disruption": "#f39c12", "Other": "#95a5a6"})
                fig.update_layout(height=250, margin=dict(t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)

    # ── Q2: ARE WE FORCING LONG BALLS? ──
    with q2:
        st.subheader("Q2: Are we forcing long balls?")
        st.caption("Measures whether pressing forces the opponent to bypass their build-up with long passes.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Long Ball % (Overall)", f"{flb['long_ball_ratio_overall']}%",
                  help="Opponent long-ball ratio from D3 across all phases.")
        c2.metric("Long Ball % (High Block)", f"{flb['long_ball_ratio_high_block']}%",
                  help="Opponent long-ball ratio from D3 during our high-block pressing.")
        c3.metric("Delta", f"{flb['long_ball_ratio_delta']:+.1f}pp",
                  help=HELP["long_ball_delta"])
        c4.metric("Forced Backward", flb["forced_backward"], help=HELP["force_backward"])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**{opponent} – Pass Range Distribution from D3**")
            opp_pp = mdf[(mdf["event_type"] == "player_possession") & (mdf["team_shortname"] == opponent)]
            d3_passes = opp_pp[(opp_pp["third_start"] == "defensive_third") & (opp_pp["end_type"] == "pass")]
            if len(d3_passes) > 0:
                hb = d3_passes[d3_passes["team_out_of_possession_phase_type"] == "high_block"]
                non_hb = d3_passes[d3_passes["team_out_of_possession_phase_type"] != "high_block"]
                range_data = []
                for label, subset in [("High Block", hb), ("Other Phases", non_hb)]:
                    dist = subset["pass_range"].value_counts(normalize=True) * 100
                    for rng, pct in dist.items():
                        range_data.append({"Phase": label, "Pass Range": rng, "Ratio %": round(pct, 1)})
                if range_data:
                    fig = px.bar(pd.DataFrame(range_data), x="Pass Range", y="Ratio %",
                                 color="Phase", barmode="group",
                                 color_discrete_map={"High Block": "#e74c3c", "Other Phases": "#3498db"})
                    fig.update_layout(height=350, margin=dict(t=10, b=10))
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No opponent D3 passes found in this match.")

        with col2:
            st.markdown("**Summary**")
            st.markdown(f"""
- Opponent played **{flb['total_opp_passes_d3']}** passes from their defensive third
- Of those, **{flb['total_opp_long_d3']}** were long balls (**{flb['long_ball_ratio_overall']}%**)
- During high-block pressing: **{flb['high_block_long_d3']}** / **{flb['high_block_passes_d3']}** were long (**{flb['long_ball_ratio_high_block']}%**)
- **Delta: {flb['long_ball_ratio_delta']:+.1f}pp** {'— pressing is forcing longer passes' if flb['long_ball_ratio_delta'] > 0 else '— pressing is not increasing long-ball frequency'}
- **{flb['forced_backward']}** backward passes forced by pressing
""")

    # ── Q3: ARE WE DISRUPTING BUILD-UP? ──
    with q3:
        st.subheader("Q3: Are we disrupting their build-up?")
        st.caption("Measures whether the opponent can progress from their defensive third and maintain passing accuracy.")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("A1 Block Rate", f"{prog['block_rate']}%", help=HELP["block_rate"])
        c2.metric("A1→A3 Bypass", f"{byp['bypass_rate']}%", help=HELP["bypass_rate"])
        c3.metric("PPDA (High Block)", ppda_val["ppda_high_block"], help=HELP["ppda_hb"])
        c4.metric("xT Disruption", f"{xt['xt_disruption_pct']}%", help=HELP["xt_disruption"])
        c5.metric("Opp Pass% D3 (HB)", f"{opc['pass_pct_d3_high_block']}%", help=HELP["opp_pass_pct"])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Opponent Progression from D3**")
            prog_data = pd.DataFrame({
                "Outcome": ["Stayed in D3\n(blocked)", "Reached Middle", "Reached Attacking"],
                "Count": [
                    prog["stayed_in_a1"],
                    prog["progressed_to_a2"] - byp["bypassed_to_a3"],
                    byp["bypassed_to_a3"],
                ],
            })
            fig = px.bar(prog_data, x="Outcome", y="Count",
                         color="Outcome", color_discrete_sequence=["#2ecc71", "#f39c12", "#e74c3c"])
            fig.update_layout(height=350, margin=dict(t=10, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown(f"**{opponent} – Pass Completion by Zone**")
            opp_pp_all = mdf[(mdf["event_type"] == "player_possession") & (mdf["team_shortname"] == opponent)]
            opp_passes = opp_pp_all[opp_pp_all["end_type"] == "pass"]
            thirds = ["defensive_third", "middle_third", "attacking_third"]
            third_labels = {"defensive_third": "Defensive", "middle_third": "Middle", "attacking_third": "Attacking"}
            pct_data = []
            for t in thirds:
                tp = opp_passes[opp_passes["third_start"] == t]
                if len(tp) > 0:
                    succ = (tp["pass_outcome"] == "successful").sum()
                    pct_data.append({
                        "Zone": third_labels[t],
                        "Completion %": round(succ / len(tp) * 100, 1),
                        "Total": len(tp),
                    })
            if pct_data:
                fig = px.bar(pd.DataFrame(pct_data), x="Zone", y="Completion %",
                             text="Total", color="Completion %", color_continuous_scale="RdYlGn")
                fig.update_layout(height=350, margin=dict(t=10, b=10), coloraxis_showscale=False)
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Detailed Breakdown**")
        st.markdown(f"""
- **{prog['total_a1_possessions']}** opponent possessions started in their D3
- **{prog['stayed_in_a1']}** ({prog['block_rate']}%) were blocked before reaching the middle third
- **{byp['bypassed_to_a3']}** ({byp['bypass_rate']}%) bypassed the press entirely (D3 → A3)
- PPDA overall: **{ppda_val['ppda_overall']}** | High block: **{ppda_val['ppda_high_block']}**
- xThreat during high block: **{xt['xt_high_block']:.5f}** vs other phases: **{xt['xt_non_high_block']:.5f}** (disruption: **{xt['xt_disruption_pct']}%**)
- Opponent pass completion in D3: **{opc['pass_pct_d3']}%** overall | **{opc['pass_pct_d3_high_block']}%** under high block
""")

    # ── Q4: IS THE OPPONENT CREATING CHANCES? ──
    with q4:
        st.subheader("Q4: Is the opponent creating chances after our press?")
        st.caption("Measures the risk of pressing — how often the opponent generates danger when the press is broken.")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Shots After Press", cap["shots_after_pressing"], help=HELP["shots_after"])
        c2.metric("Goals After Press", cap["goals_after_pressing"], help=HELP["goals_after"])
        c3.metric("Beaten Rate", f"{cap['beaten_rate']}%", help=HELP["beaten_rate"])
        c4.metric("Danger Rate", f"{cap['danger_rate']}%", help=HELP["danger_rate"])
        c5.metric("Total Engagements", cap["total_engagements"])

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Defensive Outcome Breakdown**")
            outcome_data = pd.DataFrame({
                "Outcome": [
                    "Beaten by\nPossession", "Beaten by\nMovement",
                    "Possession\nDanger", "Shots\nConceded", "Goals\nConceded",
                ],
                "Count": [
                    cap["beaten_by_possession"], cap["beaten_by_movement"],
                    cap["possession_danger_count"], cap["shots_after_pressing"],
                    cap["goals_after_pressing"],
                ],
            })
            fig = go.Figure(go.Bar(
                x=outcome_data["Count"], y=outcome_data["Outcome"],
                orientation="h",
                marker_color=["#e74c3c", "#c0392b", "#f39c12", "#e67e22", "#d35400"],
            ))
            fig.update_layout(height=300, margin=dict(t=10, b=10, l=10))
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("**Risk Assessment**")
            risk_score = pes["components"]["not_beaten"] * 0.5 + pes["components"]["not_danger"] * 0.5
            if risk_score >= 70:
                verdict = "Low risk — pressing is secure, opponent rarely creates danger."
                color = "green"
            elif risk_score >= 40:
                verdict = "Moderate risk — pressing occasionally leaves gaps."
                color = "orange"
            else:
                verdict = "High risk — pressing is a gamble, frequently exposed."
                color = "red"
            st.markdown(f":{color}[**{verdict}**]")
            st.markdown(f"""
- **{cap['beaten_by_possession']}** times beaten by the ball carrier (positioning failure)
- **{cap['beaten_by_movement']}** times beaten by off-ball movement (tracking failure)
- **{cap['possession_danger_count']}** engagements where opponent EPV exceeded 3%
- **{cap['shots_after_pressing']}** shots and **{cap['goals_after_pressing']}** goals within 10s of engagement
- Beaten rate: **{cap['beaten_rate']}%** | Danger rate: **{cap['danger_rate']}%**
""")

    # ── Q5: ARE WE CREATING CHANCES? ──
    with q5:
        st.subheader("Q5: Are we creating chances from pressing?")
        st.caption(
            "Attacking reward: shots, goals, and SkillCorner **xShot** (xG-style) on possessions after a regain."
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Regains", cfr["total_regains"], help=HELP["regains"])
        c2.metric("Shots from Regain", cfr["shots_from_regain"], help=HELP["shots_from_regain"])
        c3.metric("Goals from Regain", cfr["goals_from_regain"],
                  help="Regain events where lead_to_goal = True. Goal scored within 10s of recovery.")
        c4.metric("Shot Conversion", f"{cfr['shot_conversion_rate']}%",
                  help="Shots from regain / total regains × 100. "
                       "How efficiently recoveries turn into shots.")

        x1, x2, x3, x4 = st.columns(4)
        x1.metric(
            "Σ xShot (after regains)",
            f"{cfr['xshot_after_regain_total']:.2f}",
            help=HELP["xshot_after_regain"],
        )
        x2.metric(
            "xShot / Match",
            f"{cfr['xshot_after_regain_per_match']:.3f}",
            help=HELP["xshot_after_regain_pm"],
        )
        x3.metric(
            "xShot / Regain",
            f"{cfr['xshot_after_regain_per_regain']:.4f}",
            help=HELP["xshot_per_regain"],
        )
        x4.metric(
            "Σ xShot (shot regains)",
            f"{cfr['xshot_on_shot_regains']:.2f}",
            help=HELP["xshot_on_shot_regains"],
        )
        st.caption(
            f"Among regains that led to a shot: **{cfr['xshot_per_shot_regain']:.3f}** xShot per such regain on average."
        )

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Recovery → Chance Pipeline**")
            pipeline = pd.DataFrame({
                "Stage": ["Total\nRegains", "Led to\nShot", "Led to\nGoal"],
                "Count": [cfr["total_regains"], cfr["shots_from_regain"], cfr["goals_from_regain"]],
            })
            fig = go.Figure(go.Funnel(
                y=pipeline["Stage"], x=pipeline["Count"],
                textinfo="value+percent initial",
                marker_color=["#3498db", "#f39c12", "#2ecc71"],
            ))
            fig.update_layout(height=300, margin=dict(t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("**Chain Pressing Contribution**")
            st.markdown(f"""
- **{pca['total_chains']}** pressing chains in this match
- **{pca['chain_end_regain']}** chains ended with ball recovery
- **{cfr['chain_regain_shots']}** shots originated from chain regains
- **{cfr['xshot_after_regain_total']:.2f}** total xShot after regains (**{cfr['xshot_after_regain_per_match']:.3f}** per match)
- Average chain length: **{pca['avg_chain_length']}** engagements
- Max chain length: **{pca['max_chain_length']}** engagements
""")
            if pca["subtypes_in_chains"]:
                st.markdown("**Engagement types in chains:**")
                for subtype, count in sorted(pca["subtypes_in_chains"].items(), key=lambda x: -x[1]):
                    st.markdown(f"- {subtype}: **{count}**")

        st.markdown("**Verdict**")
        if cfr["shot_conversion_rate"] >= 10:
            st.success(f"High attacking return — {cfr['shot_conversion_rate']}% of recoveries lead to shots.")
        elif cfr["shot_conversion_rate"] >= 5:
            st.warning(f"Moderate attacking return — {cfr['shot_conversion_rate']}% of recoveries lead to shots.")
        else:
            st.error(f"Low attacking return — only {cfr['shot_conversion_rate']}% of recoveries lead to shots.")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 3 – PLAYER PRESSING PROFILE
# ─────────────────────────────────────────────────────────────────────────────
def page_player_profile():
    st.header("Player Pressing Profile")

    df = load_data()
    teams = sorted(df["team_shortname"].dropna().unique())
    selected_team = st.selectbox("Team", teams)

    with st.spinner("Computing player stats..."):
        stats = player_pressing_stats(df, selected_team)

    if len(stats) == 0:
        st.warning("No pressing data found for this team.")
        return

    player_list = stats["player_name"].tolist()
    selected_player = st.selectbox("Player", player_list)
    player = stats[stats["player_name"] == selected_player].iloc[0]

    st.markdown(f"**Position:** {player['player_position']}  |  "
                f"**Matches:** {player['matches']}  |  "
                f"**Total Engagements:** {player['total_engagements']}")
    st.divider()

    # ── KPIs ──
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Engagements/Match", player["engagements_per_match"], help=HELP["engagements_per_match"])
    c2.metric("Regains", int(player["regains"]), help=HELP["regains"])
    c3.metric("Regain Rate", f"{player['regain_rate']}%", help=HELP["regain_rate"])
    c4.metric("Forced Backward", int(player["force_backward"]), help=HELP["force_backward"])
    c5.metric("Beaten Rate", f"{player['beaten_rate']}%", help=HELP["beaten_rate"])
    c6.metric("Chain Participation", int(player["in_chain"]), help=HELP["in_chain"])

    p1, p2, p3 = st.columns(3)
    p1.metric(
        "Σ xShot (after regains)",
        f"{player['xshot_from_regain']:.2f}",
        help="Sum of xshot_player_possession_end on this player's regain-ending OBE rows (xG-style).",
    )
    p2.metric(
        "xShot / Regain",
        f"{(player['xshot_from_regain'] / max(int(player['regains']), 1)):.4f}",
        help="Average xShot per ball recovery attributed to this player.",
    )
    p3.metric("Matches", int(player["matches"]))

    st.divider()

    # ── Engagement type breakdown ──
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Engagement Type Distribution")
        type_data = pd.DataFrame({
            "Type": ["Pressing", "Pressure", "Counter Press", "Recovery Press", "Other"],
            "Count": [
                player["pressing_count"], player["pressure_count"],
                player["counter_press_count"], player["recovery_press_count"],
                player["other_count"],
            ],
        })
        type_data = type_data[type_data["Count"] > 0]
        fig = px.pie(type_data, values="Count", names="Type", hole=0.4,
                     color="Type", color_discrete_map={
                         "Pressing": "#e74c3c", "Pressure": "#f39c12",
                         "Counter Press": "#3498db", "Recovery Press": "#2ecc71",
                         "Other": "#95a5a6",
                     })
        fig.update_layout(height=300, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Defensive Effectiveness")
        eff_data = pd.DataFrame({
            "Metric": ["Regains", "Forced\nBackward", "Stopped\nDanger",
                       "Reduced\nDanger", "Beaten\n(Possession)", "Beaten\n(Movement)"],
            "Count": [
                player["regains"], player["force_backward"],
                player["stop_danger"], player["reduce_danger"],
                player["beaten_by_possession"], player["beaten_by_movement"],
            ],
        })
        colors = ["#2ecc71", "#27ae60", "#2ecc71", "#82e0aa", "#e74c3c", "#c0392b"]
        fig = go.Figure(go.Bar(
            x=eff_data["Count"], y=eff_data["Metric"],
            orientation="h", marker_color=colors,
        ))
        fig.update_layout(height=300, margin=dict(t=10, b=10, l=10))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Pitch map ──
    st.subheader("Season Pressing Location Map")
    obe = df[
        (df["event_type"] == "on_ball_engagement") &
        (df["team_shortname"] == selected_team) &
        (df["player_name"] == selected_player)
    ].dropna(subset=["x_start", "y_start"])

    if len(obe) > 0:
        fig = go.Figure()
        fig = draw_pitch(fig)

        for sub, color in OBE_COLORS.items():
            sd = obe[obe["event_subtype"] == sub]
            if len(sd) == 0:
                continue
            fig.add_trace(go.Scatter(
                x=sd["x_start"], y=sd["y_start"],
                mode="markers",
                marker=dict(size=8, color=color, opacity=0.7,
                            line=dict(width=0.5, color="white")),
                name=f"{sub} ({len(sd)})",
            ))

        fig.update_layout(title=f"{selected_player} – Pressing Locations (Full Season)")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Team-wide comparison table ──
    st.subheader(f"{selected_team} – All Players")
    with st.expander("ℹ️ How are player stats calculated?"):
        st.markdown("""
Every stat below comes from **pressing engagements** — moments where a defender actively closes down the ball carrier.

**Eng/Match** — Average pressing actions per game. Higher = more active presser.

**Pressing** — Pressing actions that are part of a **collective chain** (a teammate also pressed within 4 seconds). This is coordinated team pressing.

**Pressure** — **Individual** pressing actions where the player closes down the ball carrier alone, without a coordinated team effort.

**C.Press** — **Counter-pressing**: pressing immediately (within 3 seconds) after the team lost the ball. Think of it as "we just lost it, win it right back."

**R.Press** — **Recovery press**: pressing while running back towards the team's own goal. The player is retreating but still applying pressure.

**Regains** — How many pressing actions ended with the player's team winning the ball back.

**Regain %** — Regains divided by total pressing actions × 100. What percentage of the time does this player's pressing actually win the ball? Higher = more effective.

**Forced Back** — How many times the player's pressing forced the opponent to play a backward pass instead of progressing forward.

**Beaten %** — How often the player gets bypassed during pressing — either the ball carrier dribbles past them, or an opponent's movement takes them out of the play. Lower = better.

**Chain** — How many of the player's pressing actions were part of a collective chain (coordinated pressing with teammates).

**xShot (regain)** — Sum of **xshot_player_possession_end** on rows where the player’s action ended in a ball regain (direct/indirect). Season total xG-style output from possessions following their recoveries.
""")

    display_stats = stats[[
        "player_name", "player_position", "matches", "total_engagements",
        "engagements_per_match", "pressing_count", "pressure_count",
        "counter_press_count", "recovery_press_count",
        "regains", "regain_rate", "xshot_from_regain", "force_backward",
        "beaten_rate", "in_chain",
    ]].rename(columns={
        "player_name": "Player", "player_position": "Position",
        "matches": "Matches", "total_engagements": "Total",
        "engagements_per_match": "Eng/Match",
        "pressing_count": "Pressing", "pressure_count": "Pressure",
        "counter_press_count": "C.Press", "recovery_press_count": "R.Press",
        "regains": "Regains", "regain_rate": "Regain %",
        "xshot_from_regain": "xShot (regain)",
        "force_backward": "Forced Back", "beaten_rate": "Beaten %",
        "in_chain": "Chain",
    })
    st.dataframe(display_stats, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────
PAGES = {
    "League Overview": page_league_overview,
    "Match Analysis": page_match_analysis,
    "Player Profile": page_player_profile,
}

with st.sidebar:
    st.title("🛡️ Pressing Analyst")
    st.caption("SkillCorner Dynamic Events\nPremier League 2024/25")
    st.divider()
    page = st.radio("Page", list(PAGES.keys()), label_visibility="collapsed")
    st.divider()
    st.markdown("""
    **5 Key Questions:**
    1. Are we winning the ball?
    2. Are we forcing long balls?
    3. Are we disrupting build-up?
    4. Is the opponent creating chances?
    5. Are we creating chances?

    **Effectiveness score** also tracks **beaten** (how often the press is bypassed) and **danger** (threat while pressing); higher = rarer / safer vs peers.
    """)
    st.divider()
    st.caption("378 matches | 20 teams | 143 columns")

PAGES[page]()
