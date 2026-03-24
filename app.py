"""
SkillCorner Dynamic Events - Premier League 2024/25 Dashboard
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
DATA_DIR = Path(r"D:\ContextEngineeringProject\dynamic_events_pl_24\dynamic_events_pl_24")
DYNAMIC_DIR = DATA_DIR / "dynamic"
META_DIR = DATA_DIR / "meta"
CACHE_FILE = DATA_DIR / "_all_events_cache.parquet"

CORE_COLUMNS = [
    "event_id", "match_id", "event_type", "event_type_id", "event_subtype",
    "player_id", "player_name", "player_position", "team_id", "team_shortname",
    "player_in_possession_name", "player_in_possession_position",
    "x_start", "y_start", "x_end", "y_end",
    "channel_start", "channel_end", "third_start", "third_end",
    "penalty_area_start", "penalty_area_end",
    "duration", "period", "minute_start",
    "game_state", "team_score", "opponent_team_score",
    "team_in_possession_phase_type", "team_out_of_possession_phase_type",
    "end_type", "start_type", "pass_outcome",
    "pass_distance", "pass_angle", "pass_direction", "pass_ahead",
    "high_pass", "pass_range",
    "speed_avg", "speed_avg_band", "distance_covered",
    "trajectory_direction", "trajectory_angle",
    "xthreat", "xpass_completion", "passing_option_score",
    "dangerous", "difficult_pass_target",
    "targeted", "received", "received_in_space",
    "lead_to_shot", "lead_to_goal",
    "one_touch", "quick_pass", "carry", "forward_momentum", "is_header",
    "give_and_go", "hand_pass", "initiate_give_and_go",
    "organised_defense", "defensive_structure", "n_defensive_lines",
    "first_line_break", "second_last_line_break", "last_line_break",
    "furthest_line_break", "furthest_line_break_type",
    "separation_start", "separation_end", "separation_gain",
    "last_defensive_line_height_start", "last_defensive_line_height_end",
    "inside_defensive_shape_start", "inside_defensive_shape_end",
    "overall_pressure_start", "overall_pressure_end",
    "reception_difficulty_start", "time_to_impact_start",
    "space_constraint_start", "passing_option_ease_start",
    "n_passing_options", "n_off_ball_runs",
    "n_passing_options_line_break", "n_passing_options_ahead",
    "beaten_by_possession", "beaten_by_movement",
    "force_backward", "stop_possession_danger", "reduce_possession_danger",
    "possession_danger",
    "n_opponents_bypassed",
    "xloss_player_possession_start", "xshot_player_possession_start",
]

st.set_page_config(
    page_title="SkillCorner Dynamic Events",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING  –  single cache file for all 378 matches
# ─────────────────────────────────────────────────────────────────────────────
def _build_cache() -> None:
    """Combine 378 parquet files into a single cache (runs once)."""
    import pyarrow.parquet as pq

    source_files = sorted(DYNAMIC_DIR.glob("*.parquet"))
    available_cols = set(pq.read_schema(source_files[0]).names)
    use_cols = [c for c in CORE_COLUMNS if c in available_cols]

    frames = []
    for f in source_files:
        frames.append(pd.read_parquet(f, columns=use_cols))
    combined = pd.concat(frames, ignore_index=True)
    combined.to_parquet(CACHE_FILE, index=False, engine="pyarrow")


@st.cache_data(show_spinner=False)
def load_all_events() -> pd.DataFrame:
    if not CACHE_FILE.exists() or CACHE_FILE.stat().st_size < 1000:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        with st.spinner("İlk çalıştırma: veriler birleştiriliyor (bir kere yapılır)..."):
            _build_cache()
    return pd.read_parquet(CACHE_FILE)


@st.cache_data(show_spinner=False)
def load_teams() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "teams.parquet")


@st.cache_data(show_spinner=False)
def load_players() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "players.parquet")


@st.cache_data(show_spinner=False)
def load_all_meta() -> dict:
    metas = {}
    for f in META_DIR.glob("*.json"):
        match_id = int(f.stem)
        with open(f, "r", encoding="utf-8") as fh:
            metas[match_id] = json.load(fh)
    return metas


@st.cache_data(show_spinner=False)
def build_match_index() -> pd.DataFrame:
    metas = load_all_meta()
    available_ids = {int(f.stem) for f in DYNAMIC_DIR.glob("*.parquet")}
    rows = []
    for mid, m in metas.items():
        if mid not in available_ids:
            continue
        rows.append({
            "match_id": mid,
            "date": m.get("date_time", "")[:10],
            "home_team": m["home_team"]["short_name"],
            "away_team": m["away_team"]["short_name"],
            "home_score": m.get("home_team_score", ""),
            "away_score": m.get("away_team_score", ""),
            "stadium": m.get("stadium", {}).get("name", ""),
            "home_team_id": m["home_team"]["id"],
            "away_team_id": m["away_team"]["id"],
        })
    df = pd.DataFrame(rows)
    df["label"] = (
        df["date"] + "  |  " +
        df["home_team"] + " " + df["home_score"].astype(str) +
        " - " + df["away_score"].astype(str) + " " + df["away_team"]
    )
    df = df.sort_values("date", ascending=False).reset_index(drop=True)
    return df


@st.cache_data(show_spinner=False)
def load_match_events(match_id: int) -> pd.DataFrame:
    all_df = load_all_events()
    return all_df[all_df["match_id"] == match_id]


# ─────────────────────────────────────────────────────────────────────────────
# PITCH DRAWING (Plotly)
# ─────────────────────────────────────────────────────────────────────────────
def draw_pitch_plotly(fig: go.Figure) -> go.Figure:
    hl, hw = 52.5, 34
    line_color = "white"

    shapes = [
        dict(type="rect", x0=-hl, y0=-hw, x1=hl, y1=hw, line=dict(color=line_color, width=2)),
        dict(type="line", x0=0, y0=-hw, x1=0, y1=hw, line=dict(color=line_color, width=2)),
        dict(type="circle", x0=-9.15, y0=-9.15, x1=9.15, y1=9.15, line=dict(color=line_color, width=1.5)),
        # Penalty areas
        dict(type="rect", x0=-hl, y0=-20.15, x1=-hl + 16.5, y1=20.15, line=dict(color=line_color, width=1.5)),
        dict(type="rect", x0=hl - 16.5, y0=-20.15, x1=hl, y1=20.15, line=dict(color=line_color, width=1.5)),
        # Goal areas
        dict(type="rect", x0=-hl, y0=-9.16, x1=-hl + 5.5, y1=9.16, line=dict(color=line_color, width=1.5)),
        dict(type="rect", x0=hl - 5.5, y0=-9.16, x1=hl, y1=9.16, line=dict(color=line_color, width=1.5)),
    ]

    fig.update_layout(
        shapes=shapes,
        plot_bgcolor="#2d7a3a",
        xaxis=dict(range=[-57, 57], showgrid=False, zeroline=False, showticklabels=False, fixedrange=True),
        yaxis=dict(range=[-38, 38], showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x", fixedrange=True),
        margin=dict(l=10, r=10, t=40, b=10),
        height=500,
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# PAGES
# ─────────────────────────────────────────────────────────────────────────────

def page_league_overview():
    st.header("Premier League 2024/25 - Genel Bakış")

    with st.spinner("Tüm maç verileri yükleniyor..."):
        all_df = load_all_events()

    teams_list = sorted(all_df["team_shortname"].dropna().unique())
    match_index = build_match_index()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Toplam Maç", len(match_index))
    col2.metric("Toplam Olay", f"{len(all_df):,}")
    col3.metric("Takım Sayısı", len(teams_list))
    col4.metric("Oyuncu Sayısı", all_df["player_name"].nunique())

    st.divider()

    pp = all_df[all_df["event_type"] == "player_possession"]
    po = all_df[all_df["event_type"] == "passing_option"]
    obr = all_df[all_df["event_type"] == "off_ball_run"]
    obe = all_df[all_df["event_type"] == "on_ball_engagement"]

    # Event type distribution
    event_counts = all_df["event_type"].value_counts().reset_index()
    event_counts.columns = ["Olay Tipi", "Adet"]
    event_type_labels = {
        "player_possession": "Player Possession",
        "passing_option": "Passing Option",
        "off_ball_run": "Off-Ball Run",
        "on_ball_engagement": "On-Ball Engagement",
    }
    event_counts["Olay Tipi"] = event_counts["Olay Tipi"].map(event_type_labels)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Olay Tipi Dağılımı")
        fig = px.pie(event_counts, values="Adet", names="Olay Tipi", hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_layout(height=350, margin=dict(t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

    # Passes per team
    passes = pp[pp["end_type"] == "pass"]
    team_pass = passes.groupby("team_shortname").agg(
        total=("event_id", "count"),
        successful=("pass_outcome", lambda x: (x == "successful").sum()),
    ).reset_index()
    team_pass["success_rate"] = (team_pass["successful"] / team_pass["total"] * 100).round(1)
    team_pass = team_pass.sort_values("success_rate", ascending=True)

    with c2:
        st.subheader("Takım Pas Başarı Oranları")
        fig = px.bar(team_pass, x="success_rate", y="team_shortname", orientation="h",
                     color="success_rate", color_continuous_scale="Greens",
                     labels={"success_rate": "Başarı %", "team_shortname": ""})
        fig.update_layout(height=350, margin=dict(t=30, b=10), showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    c1, c2 = st.columns(2)

    # xThreat leaders
    with c1:
        st.subheader("xThreat Liderleri (Toplam)")
        po_valid = po.dropna(subset=["xthreat"])
        xt_leaders = po_valid.groupby(["player_name", "team_shortname"])["xthreat"].sum().reset_index()
        xt_leaders = xt_leaders.sort_values("xthreat", ascending=False).head(15)
        fig = px.bar(xt_leaders, x="xthreat", y="player_name", orientation="h",
                     color="team_shortname",
                     labels={"xthreat": "Toplam xThreat", "player_name": "", "team_shortname": "Takım"})
        fig.update_layout(height=450, margin=dict(t=30, b=10), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    # Off-ball run subtypes
    with c2:
        st.subheader("Off-Ball Run Tipleri (Lig Geneli)")
        obr_types = obr["event_subtype"].value_counts().reset_index()
        obr_types.columns = ["Tip", "Adet"]
        fig = px.bar(obr_types, x="Adet", y="Tip", orientation="h",
                     color="Adet", color_continuous_scale="Oranges")
        fig.update_layout(height=450, margin=dict(t=30, b=10), showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Phase of play distribution
    st.subheader("Oyun Fazı Dağılımı (Tüm Takımlar)")
    phase_data = pp.groupby(["team_shortname", "team_in_possession_phase_type"]).size().reset_index(name="count")
    fig = px.bar(phase_data, x="team_shortname", y="count", color="team_in_possession_phase_type",
                 barmode="stack",
                 labels={"count": "Adet", "team_shortname": "", "team_in_possession_phase_type": "Faz"})
    fig.update_layout(height=400, margin=dict(t=30, b=10), xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    # Pressure distribution
    if "overall_pressure_start" in pp.columns:
        st.subheader("Baskı Altında Top Alma (Tüm Takımlar)")
        pp_pressure = pp.dropna(subset=["overall_pressure_start"])
        if len(pp_pressure) > 0:
            pressure_data = pp_pressure.groupby(
                ["team_shortname", "overall_pressure_start"]
            ).size().reset_index(name="count")
            fig = px.bar(pressure_data, x="team_shortname", y="count", color="overall_pressure_start",
                         barmode="stack",
                         labels={"count": "Adet", "team_shortname": "", "overall_pressure_start": "Baskı"},
                         color_discrete_map={
                             "No pressure": "#2ecc71", "Low pressure": "#82e0aa",
                             "Medium pressure": "#f9e79f", "High pressure": "#f0b27a",
                             "Very high pressure": "#e74c3c",
                         })
            fig.update_layout(height=400, margin=dict(t=30, b=10), xaxis_tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)


def page_match_analysis():
    st.header("Maç Analizi")

    match_index = build_match_index()

    selected_label = st.selectbox(
        "Maç Seçin",
        match_index["label"].tolist(),
        index=0,
    )
    selected_row = match_index[match_index["label"] == selected_label].iloc[0]
    match_id = selected_row["match_id"]

    df = load_match_events(match_id)
    metas = load_all_meta()
    meta = metas[match_id]

    # Match header
    c1, c2, c3 = st.columns([2, 1, 2])
    with c1:
        st.markdown(f"### {meta['home_team']['short_name']}")
    with c2:
        st.markdown(f"### {meta.get('home_team_score', '')} - {meta.get('away_team_score', '')}")
    with c3:
        st.markdown(f"### {meta['away_team']['short_name']}")

    st.caption(f"📅 {selected_row['date']}  |  🏟️ {selected_row['stadium']}")
    st.divider()

    teams = df["team_shortname"].unique()
    home_team = meta["home_team"]["short_name"]
    away_team = meta["away_team"]["short_name"]

    pp = df[df["event_type"] == "player_possession"]
    po = df[df["event_type"] == "passing_option"]
    obr = df[df["event_type"] == "off_ball_run"]
    obe = df[df["event_type"] == "on_ball_engagement"]

    # KPI cards
    for team in [home_team, away_team]:
        tpp = pp[pp["team_shortname"] == team]
        tpo = po[po["team_shortname"] == team]
        tobr = obr[obr["team_shortname"] == team]
        tobe = obe[obe["team_shortname"] == team]
        passes = tpp[tpp["end_type"] == "pass"]
        succ = (passes["pass_outcome"] == "successful").sum() if len(passes) > 0 else 0
        pass_pct = (succ / len(passes) * 100) if len(passes) > 0 else 0

        st.subheader(team)
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Top Kontrolü", len(tpp))
        k2.metric("Pas", f"{succ}/{len(passes)}")
        k3.metric("Pas %", f"{pass_pct:.0f}%")
        k4.metric("Pas Opsiyonu", len(tpo))
        k5.metric("Off-Ball Run", len(tobr))
        k6.metric("Baskı (OBE)", len(tobe))

    st.divider()

    # Pitch visualizations
    tab1, tab2, tab3, tab4 = st.tabs([
        "Pas Opsiyonları (xThreat)",
        "Off-Ball Run'lar",
        "Top Kontrolü",
        "On-Ball Engagement",
    ])

    with tab1:
        team_filter = st.radio("Takım", [home_team, away_team], horizontal=True, key="po_team")
        t_po = po[(po["team_shortname"] == team_filter)].dropna(subset=["x_start", "y_start"])
        fig = go.Figure()
        fig = draw_pitch_plotly(fig)

        xt_values = t_po["xthreat"].fillna(0)
        fig.add_trace(go.Scatter(
            x=t_po["x_start"], y=t_po["y_start"],
            mode="markers",
            marker=dict(
                size=8, color=xt_values, colorscale="YlOrRd",
                cmin=0, cmax=xt_values.quantile(0.95) if len(xt_values) > 0 else 0.05,
                colorbar=dict(title="xThreat"), opacity=0.7,
            ),
            text=t_po.apply(lambda r: f"{r['player_name']}<br>xT: {r.get('xthreat', 0):.3f}<br>xP: {r.get('xpass_completion', 0):.2f}", axis=1),
            hoverinfo="text",
        ))
        fig.update_layout(title=f"{team_filter} - Pas Opsiyonları (xThreat)")
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        team_filter2 = st.radio("Takım", [home_team, away_team], horizontal=True, key="obr_team")
        t_obr = obr[obr["team_shortname"] == team_filter2].dropna(subset=["x_start", "y_start", "x_end", "y_end"])

        subtype_colors = {
            "behind": "#e74c3c", "overlap": "#3498db", "underlap": "#2ecc71",
            "pulling_wide": "#f39c12", "pulling_half_space": "#9b59b6",
            "run_ahead_of_the_ball": "#1abc9c", "coming_short": "#e67e22",
            "dropping_off": "#95a5a6", "cross_receiver": "#e91e63", "support": "#607d8b",
        }

        fig = go.Figure()
        fig = draw_pitch_plotly(fig)

        for subtype, color in subtype_colors.items():
            sub_data = t_obr[t_obr["event_subtype"] == subtype]
            if len(sub_data) == 0:
                continue
            for _, row in sub_data.iterrows():
                fig.add_annotation(
                    x=row["x_end"], y=row["y_end"],
                    ax=row["x_start"], ay=row["y_start"],
                    xref="x", yref="y", axref="x", ayref="y",
                    showarrow=True, arrowhead=2, arrowsize=1.2,
                    arrowcolor=color, arrowwidth=1.8, opacity=0.7,
                )
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers",
                marker=dict(size=10, color=color),
                name=subtype, showlegend=True,
            ))

        fig.update_layout(title=f"{team_filter2} - Off-Ball Run'lar")
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        team_filter3 = st.radio("Takım", [home_team, away_team], horizontal=True, key="pp_team")
        t_pp = pp[pp["team_shortname"] == team_filter3].dropna(subset=["x_start", "y_start"])

        fig = go.Figure()
        fig = draw_pitch_plotly(fig)

        end_colors = {
            "pass": "#3498db", "shot": "#e74c3c", "clearance": "#f39c12",
            "possession_loss": "#95a5a6", "foul_suffered": "#9b59b6", "unknown": "#bdc3c7",
        }
        for et, color in end_colors.items():
            sub = t_pp[t_pp["end_type"] == et]
            if len(sub) == 0:
                continue
            fig.add_trace(go.Scatter(
                x=sub["x_start"], y=sub["y_start"],
                mode="markers",
                marker=dict(size=7, color=color, opacity=0.7),
                name=et,
                text=sub.apply(lambda r: f"{r['player_name']}<br>Bitiş: {r.get('end_type','')}<br>Süre: {r.get('duration',0):.1f}s", axis=1),
                hoverinfo="text",
            ))

        fig.update_layout(title=f"{team_filter3} - Top Kontrolü Başlangıç Noktaları")
        st.plotly_chart(fig, use_container_width=True)

    with tab4:
        team_filter4 = st.radio("Takım", [home_team, away_team], horizontal=True, key="obe_team")
        t_obe = obe[obe["team_shortname"] == team_filter4].dropna(subset=["x_start", "y_start"])

        fig = go.Figure()
        fig = draw_pitch_plotly(fig)

        obe_colors = {
            "pressing": "#e74c3c", "pressure": "#f39c12", "counter_press": "#3498db",
            "recovery_press": "#2ecc71", "other": "#95a5a6",
        }
        for st_type, color in obe_colors.items():
            sub = t_obe[t_obe["event_subtype"] == st_type]
            if len(sub) == 0:
                continue
            fig.add_trace(go.Scatter(
                x=sub["x_start"], y=sub["y_start"],
                mode="markers",
                marker=dict(size=7, color=color, opacity=0.7),
                name=st_type,
                text=sub.apply(lambda r: f"{r['player_name']}<br>Tip: {r.get('event_subtype','')}", axis=1),
                hoverinfo="text",
            ))

        fig.update_layout(title=f"{team_filter4} - On-Ball Engagement")
        st.plotly_chart(fig, use_container_width=True)

    # Line break summary
    st.divider()
    st.subheader("Çizgi Kırma Özeti")
    for team in [home_team, away_team]:
        tpo = po[(po["team_shortname"] == team) & (po["organised_defense"] == True)]
        if len(tpo) == 0:
            st.write(f"**{team}**: Organize savunmaya karşı veri yok")
            continue
        first_lb = tpo["first_line_break"].sum() if "first_line_break" in tpo else 0
        second_lb = tpo["second_last_line_break"].sum() if "second_last_line_break" in tpo else 0
        last_lb = tpo["last_line_break"].sum() if "last_line_break" in tpo else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.write(f"**{team}**")
        c2.metric("1. Çizgi Kırma", int(first_lb))
        c3.metric("2. Çizgi Kırma", int(second_lb))
        c4.metric("Son Çizgi Kırma", int(last_lb))


def page_player_analysis():
    st.header("Oyuncu Analizi")

    with st.spinner("Tüm veriler yükleniyor..."):
        all_df = load_all_events()

    teams_list = sorted(all_df["team_shortname"].dropna().unique())
    selected_team = st.selectbox("Takım Seçin", teams_list)

    team_df = all_df[all_df["team_shortname"] == selected_team]
    player_list = sorted(team_df["player_name"].dropna().unique())
    selected_player = st.selectbox("Oyuncu Seçin", player_list)

    pdf = team_df[team_df["player_name"] == selected_player]

    pp = pdf[pdf["event_type"] == "player_possession"]
    po = pdf[pdf["event_type"] == "passing_option"]
    obr = pdf[pdf["event_type"] == "off_ball_run"]
    obe = pdf[pdf["event_type"] == "on_ball_engagement"]

    position = pp["player_position"].mode().iloc[0] if len(pp) > 0 else "?"
    st.markdown(f"**Pozisyon:** {position}  |  **Maç Sayısı:** {pdf['match_id'].nunique()}")
    st.divider()

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Top Kontrolü", len(pp))
    c2.metric("Pas Opsiyonu Olarak", len(po))
    c3.metric("Off-Ball Run", len(obr))
    c4.metric("On-Ball Engagement", len(obe))

    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(["Top Kontrolü", "Pas Opsiyonu", "Off-Ball Run", "Savunma Baskısı"])

    with tab1:
        if len(pp) == 0:
            st.info("Bu oyuncunun top kontrolü verisi bulunamadı.")
        else:
            passes = pp[pp["end_type"] == "pass"]
            succ = (passes["pass_outcome"] == "successful").sum()
            shots = (pp["end_type"] == "shot").sum()
            carries = pp["carry"].sum() if "carry" in pp else 0
            fm = pp["forward_momentum"].sum() if "forward_momentum" in pp else 0
            one_t = pp["one_touch"].sum() if "one_touch" in pp else 0

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Pas", f"{succ}/{len(passes)}" if len(passes) > 0 else "0")
            c2.metric("Şut", int(shots))
            c3.metric("Taşıma", int(carries))
            c4.metric("İleri Momentum", int(fm))
            c5.metric("Tek Dokunuş", int(one_t))

            # End type distribution
            end_dist = pp["end_type"].value_counts().reset_index()
            end_dist.columns = ["Bitiş Tipi", "Adet"]
            fig = px.pie(end_dist, values="Adet", names="Bitiş Tipi", hole=0.4)
            fig.update_layout(height=300, margin=dict(t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)

            # Pitch heatmap
            pp_valid = pp.dropna(subset=["x_start", "y_start"])
            if len(pp_valid) > 0:
                fig = go.Figure()
                fig = draw_pitch_plotly(fig)
                fig.add_trace(go.Histogram2dContour(
                    x=pp_valid["x_start"], y=pp_valid["y_start"],
                    colorscale="Hot", reversescale=True,
                    ncontours=15, showscale=False, opacity=0.6,
                    contours=dict(showlines=False),
                ))
                fig.add_trace(go.Scatter(
                    x=pp_valid["x_start"], y=pp_valid["y_start"],
                    mode="markers", marker=dict(size=4, color="white", opacity=0.3),
                    showlegend=False, hoverinfo="skip",
                ))
                fig.update_layout(title="Top Alma Konumları (Isı Haritası)")
                st.plotly_chart(fig, use_container_width=True)

    with tab2:
        if len(po) == 0:
            st.info("Bu oyuncunun pas opsiyonu verisi bulunamadı.")
        else:
            targeted = po["targeted"].sum()
            received = po["received"].sum()
            avg_xt = po["xthreat"].mean() if "xthreat" in po else 0
            total_xt = po["xthreat"].sum() if "xthreat" in po else 0
            dang = po["dangerous"].sum() if "dangerous" in po else 0

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Hedeflenen", int(targeted))
            c2.metric("Topa Ulaşan", int(received))
            c3.metric("Toplam xThreat", f"{total_xt:.3f}")
            c4.metric("Ort. xThreat", f"{avg_xt:.4f}")
            c5.metric("Tehlikeli", int(dang))

            # xThreat per match
            po_by_match = po.groupby("match_id")["xthreat"].sum().reset_index()
            po_by_match = po_by_match.sort_values("match_id")
            fig = px.bar(po_by_match, x=po_by_match.index, y="xthreat",
                         labels={"index": "Maç Sırası", "xthreat": "Toplam xThreat"})
            fig.update_layout(height=300, margin=dict(t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)

            # Pitch map
            po_valid = po.dropna(subset=["x_start", "y_start"])
            if len(po_valid) > 0:
                fig = go.Figure()
                fig = draw_pitch_plotly(fig)
                xt_vals = po_valid["xthreat"].fillna(0)
                fig.add_trace(go.Scatter(
                    x=po_valid["x_start"], y=po_valid["y_start"],
                    mode="markers",
                    marker=dict(size=6, color=xt_vals, colorscale="YlOrRd",
                                cmin=0, cmax=xt_vals.quantile(0.95) if len(xt_vals) > 0 else 0.05,
                                colorbar=dict(title="xThreat"), opacity=0.7),
                    showlegend=False, hoverinfo="skip",
                ))
                fig.update_layout(title="Pas Opsiyonu Konumları")
                st.plotly_chart(fig, use_container_width=True)

    with tab3:
        if len(obr) == 0:
            st.info("Bu oyuncunun off-ball run verisi bulunamadı.")
        else:
            avg_speed = obr["speed_avg"].mean()
            avg_dist = obr["distance_covered"].mean()
            give_go = obr["give_and_go"].sum() if "give_and_go" in obr else 0

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Toplam Koşu", len(obr))
            c2.metric("Ort. Hız (km/h)", f"{avg_speed:.1f}" if not np.isnan(avg_speed) else "N/A")
            c3.metric("Ort. Mesafe (m)", f"{avg_dist:.1f}" if not np.isnan(avg_dist) else "N/A")
            c4.metric("Give & Go", int(give_go))

            run_types = obr["event_subtype"].value_counts().reset_index()
            run_types.columns = ["Koşu Tipi", "Adet"]
            fig = px.bar(run_types, x="Adet", y="Koşu Tipi", orientation="h",
                         color="Adet", color_continuous_scale="Oranges")
            fig.update_layout(height=300, margin=dict(t=30, b=10), showlegend=False, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

            # Runs on pitch
            obr_valid = obr.dropna(subset=["x_start", "y_start", "x_end", "y_end"])
            if len(obr_valid) > 0:
                subtype_colors = {
                    "behind": "#e74c3c", "overlap": "#3498db", "underlap": "#2ecc71",
                    "pulling_wide": "#f39c12", "pulling_half_space": "#9b59b6",
                    "run_ahead_of_the_ball": "#1abc9c", "coming_short": "#e67e22",
                    "dropping_off": "#95a5a6", "cross_receiver": "#e91e63", "support": "#607d8b",
                }
                fig = go.Figure()
                fig = draw_pitch_plotly(fig)
                for sub, col in subtype_colors.items():
                    sd = obr_valid[obr_valid["event_subtype"] == sub]
                    if len(sd) == 0:
                        continue
                    for _, row in sd.iterrows():
                        fig.add_annotation(
                            x=row["x_end"], y=row["y_end"],
                            ax=row["x_start"], ay=row["y_start"],
                            xref="x", yref="y", axref="x", ayref="y",
                            showarrow=True, arrowhead=2, arrowsize=1.2,
                            arrowcolor=col, arrowwidth=1.5, opacity=0.6,
                        )
                    fig.add_trace(go.Scatter(
                        x=[None], y=[None], mode="markers",
                        marker=dict(size=10, color=col), name=sub,
                    ))
                fig.update_layout(title="Off-Ball Run Haritası")
                st.plotly_chart(fig, use_container_width=True)

    with tab4:
        if len(obe) == 0:
            st.info("Bu oyuncunun savunma baskısı verisi bulunamadı.")
        else:
            beaten_pos = obe["beaten_by_possession"].sum() if "beaten_by_possession" in obe else 0
            beaten_mov = obe["beaten_by_movement"].sum() if "beaten_by_movement" in obe else 0
            force_bw = obe["force_backward"].sum() if "force_backward" in obe else 0
            stop_dng = obe["stop_possession_danger"].sum() if "stop_possession_danger" in obe else 0

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Toplam Baskı", len(obe))
            c2.metric("Geçilme (Pozisyon)", int(beaten_pos))
            c3.metric("Geçilme (Hareket)", int(beaten_mov))
            c4.metric("Geri Pas Zorlatma", int(force_bw))
            c5.metric("Tehlike Durdurma", int(stop_dng))

            obe_types = obe["event_subtype"].value_counts().reset_index()
            obe_types.columns = ["Baskı Tipi", "Adet"]
            fig = px.pie(obe_types, values="Adet", names="Baskı Tipi", hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Bold)
            fig.update_layout(height=300, margin=dict(t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)


def page_team_comparison():
    st.header("Takım Karşılaştırma")

    with st.spinner("Veriler yükleniyor..."):
        all_df = load_all_events()

    teams_list = sorted(all_df["team_shortname"].dropna().unique())
    c1, c2 = st.columns(2)
    with c1:
        team_a = st.selectbox("Takım A", teams_list, index=0)
    with c2:
        team_b = st.selectbox("Takım B", teams_list, index=min(1, len(teams_list) - 1))

    pp = all_df[all_df["event_type"] == "player_possession"]
    po = all_df[all_df["event_type"] == "passing_option"]
    obr = all_df[all_df["event_type"] == "off_ball_run"]
    obe = all_df[all_df["event_type"] == "on_ball_engagement"]

    def team_stats(team: str) -> dict:
        tpp = pp[pp["team_shortname"] == team]
        tpo = po[po["team_shortname"] == team]
        tobr = obr[obr["team_shortname"] == team]
        tobe = obe[obe["team_shortname"] == team]

        passes = tpp[tpp["end_type"] == "pass"]
        succ = (passes["pass_outcome"] == "successful").sum() if len(passes) > 0 else 0
        n_matches = tpp["match_id"].nunique()

        return {
            "Maç": n_matches,
            "Top Kontrolü / Maç": round(len(tpp) / max(n_matches, 1), 1),
            "Pas Başarı %": round(succ / max(len(passes), 1) * 100, 1),
            "Pas Opsiyonu / Maç": round(len(tpo) / max(n_matches, 1), 1),
            "Off-Ball Run / Maç": round(len(tobr) / max(n_matches, 1), 1),
            "On-Ball Engagement / Maç": round(len(tobe) / max(n_matches, 1), 1),
            "Ort. xThreat": round(tpo["xthreat"].mean(), 4) if len(tpo) > 0 else 0,
            "Toplam xThreat": round(tpo["xthreat"].sum(), 2) if len(tpo) > 0 else 0,
            "Toplam Çizgi Kırma (1.)": int(tpo["first_line_break"].sum()) if "first_line_break" in tpo else 0,
            "Toplam Çizgi Kırma (Son)": int(tpo["last_line_break"].sum()) if "last_line_break" in tpo else 0,
            "Pressing": int((tobe["event_subtype"] == "pressing").sum()) if len(tobe) > 0 else 0,
            "Counter Press": int((tobe["event_subtype"] == "counter_press").sum()) if len(tobe) > 0 else 0,
        }

    stats_a = team_stats(team_a)
    stats_b = team_stats(team_b)

    comp_df = pd.DataFrame({
        "Metrik": list(stats_a.keys()),
        team_a: list(stats_a.values()),
        team_b: list(stats_b.values()),
    })

    st.dataframe(comp_df, use_container_width=True, hide_index=True)

    st.divider()

    # Radar chart
    radar_metrics = ["Pas Başarı %", "Off-Ball Run / Maç", "On-Ball Engagement / Maç",
                     "Pas Opsiyonu / Maç", "Top Kontrolü / Maç"]
    vals_a = [stats_a[m] for m in radar_metrics]
    vals_b = [stats_b[m] for m in radar_metrics]

    max_vals = [max(a, b, 1) for a, b in zip(vals_a, vals_b)]
    norm_a = [v / m * 100 for v, m in zip(vals_a, max_vals)]
    norm_b = [v / m * 100 for v, m in zip(vals_b, max_vals)]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=norm_a + [norm_a[0]], theta=radar_metrics + [radar_metrics[0]],
        fill="toself", name=team_a, opacity=0.6,
    ))
    fig.add_trace(go.Scatterpolar(
        r=norm_b + [norm_b[0]], theta=radar_metrics + [radar_metrics[0]],
        fill="toself", name=team_b, opacity=0.6,
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 110])),
        height=450, margin=dict(t=40, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)


def page_data_explorer():
    st.header("Veri Gezgini")

    match_index = build_match_index()
    all_df = load_all_events()

    mode = st.radio("Veri Kaynağı", ["Tek Maç", "Tüm Lig"], horizontal=True)

    if mode == "Tek Maç":
        selected_label = st.selectbox("Maç", match_index["label"].tolist())
        selected_row = match_index[match_index["label"] == selected_label].iloc[0]
        df = all_df[all_df["match_id"] == selected_row["match_id"]]
    else:
        df = all_df

    event_types = st.multiselect(
        "Olay Tipi", df["event_type"].unique().tolist(),
        default=df["event_type"].unique().tolist(),
    )
    filtered = df[df["event_type"].isin(event_types)]

    teams = st.multiselect("Takım", sorted(filtered["team_shortname"].dropna().unique()))
    if teams:
        filtered = filtered[filtered["team_shortname"].isin(teams)]

    st.write(f"**{len(filtered):,}** olay gösteriliyor")

    columns_to_show = st.multiselect(
        "Gösterilecek Sütunlar",
        filtered.columns.tolist(),
        default=["event_id", "event_type", "event_subtype", "player_name", "team_shortname",
                 "x_start", "y_start", "duration", "xthreat", "xpass_completion",
                 "pass_outcome", "end_type", "speed_avg"],
    )
    st.dataframe(filtered[columns_to_show], use_container_width=True, height=500)

    csv = filtered[columns_to_show].to_csv(index=False).encode("utf-8")
    st.download_button("CSV İndir", csv, "filtered_events.csv", "text/csv")


# ─────────────────────────────────────────────────────────────────────────────
# NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────

PAGES = {
    "Lig Genel Bakış": page_league_overview,
    "Maç Analizi": page_match_analysis,
    "Oyuncu Analizi": page_player_analysis,
    "Takım Karşılaştırma": page_team_comparison,
    "Veri Gezgini": page_data_explorer,
}

with st.sidebar:
    st.title("⚽ SkillCorner")
    st.caption("Dynamic Events - PL 24/25")
    st.divider()
    page = st.radio("Sayfa", list(PAGES.keys()), label_visibility="collapsed")
    st.divider()
    st.caption("Veri: SkillCorner Dynamic Events\nLig: Premier League 2024/25\n378 maç | 20 takım")

PAGES[page]()
