"""
Pressing Analyst Metrics Engine
================================
Pure pandas functions that compute pressing effectiveness metrics
from SkillCorner Dynamic Events data.

Key concepts:
- "our team" = the team whose pressing we analyse (the defending team)
- "opponent" = the team in possession being pressed
- A1 = opponent's defensive third (our attacking third)
- A2 = middle third
- A3 = opponent's attacking third (our defensive third)
- High block = our team is pressing high (opponent is in build_up phase)
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd


def _split(df: pd.DataFrame):
    pp = df[df["event_type"] == "player_possession"]
    po = df[df["event_type"] == "passing_option"]
    obr = df[df["event_type"] == "off_ball_run"]
    obe = df[df["event_type"] == "on_ball_engagement"]
    return pp, po, obr, obe


def _team_match_ids(df: pd.DataFrame, team: str) -> set:
    """Match IDs where the given team participated."""
    return set(df.loc[df["team_shortname"] == team, "match_id"].unique())


def _opponent_pp(df: pd.DataFrame, team: str) -> pd.DataFrame:
    """Player possessions by the opponent in matches where the team played."""
    team_matches = _team_match_ids(df, team)
    pp = df[(df["event_type"] == "player_possession") & (df["match_id"].isin(team_matches))]
    return pp[pp["team_shortname"] != team]


def _team_obe(df: pd.DataFrame, team: str) -> pd.DataFrame:
    """On-ball engagements performed by our team."""
    obe = df[df["event_type"] == "on_ball_engagement"]
    return obe[obe["team_shortname"] == team]


def _per_match(value: float, n_matches: int) -> float:
    return round(value / max(n_matches, 1), 2)


# SkillCorner: expected-goals-style value for the possession linked to the OBE (not a separate xG column).
XSHOT_REGAIN_COL = "xshot_player_possession_end"


def _xshot_sum_regains(regains: pd.DataFrame) -> float:
    if XSHOT_REGAIN_COL not in regains.columns or len(regains) == 0:
        return 0.0
    return float(regains[XSHOT_REGAIN_COL].sum(skipna=True))


# ─────────────────────────────────────────────────────────────────────────────
# 1. BALL RECOVERIES
# ─────────────────────────────────────────────────────────────────────────────
def ball_recoveries(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """
    Ball recoveries from pressing actions.
    Returns total, by zone, and per-match averages.
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    obe = _team_obe(data, team)
    n_matches = obe["match_id"].nunique()

    regain_types = {"direct_regain", "indirect_regain"}
    regains = obe[obe["end_type"].isin(regain_types)]
    chain_regains = obe[obe["pressing_chain_end_type"] == "regain"]

    by_third = regains.groupby("third_start").size().to_dict()

    return {
        "total_regains": len(regains),
        "regains_per_match": _per_match(len(regains), n_matches),
        "chain_regains": len(chain_regains),
        "chain_regains_per_match": _per_match(len(chain_regains), n_matches),
        "regains_attacking_third": by_third.get("attacking_third", 0),
        "regains_middle_third": by_third.get("middle_third", 0),
        "regains_defensive_third": by_third.get("defensive_third", 0),
        "n_matches": n_matches,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. FORCED LONG-BALL RATIO
# ─────────────────────────────────────────────────────────────────────────────
def forced_long_ball_ratio(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """
    Percentage of opponent passes from their defensive third that are 'long',
    compared under high-block pressing vs overall.
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    opp_pp = _opponent_pp(data, team)
    opp_passes_d3 = opp_pp[
        (opp_pp["third_start"] == "defensive_third") & (opp_pp["end_type"] == "pass")
    ]

    total = len(opp_passes_d3)
    long_total = (opp_passes_d3["pass_range"] == "long").sum()
    ratio_overall = round(long_total / max(total, 1) * 100, 1)

    high_block = opp_passes_d3[
        opp_passes_d3["team_out_of_possession_phase_type"] == "high_block"
    ]
    hb_total = len(high_block)
    hb_long = (high_block["pass_range"] == "long").sum()
    ratio_high_block = round(hb_long / max(hb_total, 1) * 100, 1)

    obe = _team_obe(data, team)
    forced_backward = obe["force_backward"].sum()

    return {
        "long_ball_ratio_overall": ratio_overall,
        "long_ball_ratio_high_block": ratio_high_block,
        "long_ball_ratio_delta": round(ratio_high_block - ratio_overall, 1),
        "total_opp_passes_d3": total,
        "total_opp_long_d3": int(long_total),
        "high_block_passes_d3": hb_total,
        "high_block_long_d3": int(hb_long),
        "forced_backward": int(forced_backward),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. A1→A2 PROGRESSION FILTER
# ─────────────────────────────────────────────────────────────────────────────
def progression_filter(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """
    How often the opponent is stopped in their defensive third (A1)
    before reaching the middle third (A2).
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    opp_pp = _opponent_pp(data, team)

    a1_starts = opp_pp[opp_pp["third_start"] == "defensive_third"]
    total_a1 = len(a1_starts)

    reached_a2 = a1_starts[a1_starts["third_end"].isin(["middle_third", "attacking_third"])]
    stayed_a1 = a1_starts[a1_starts["third_end"] == "defensive_third"]

    block_rate = round(len(stayed_a1) / max(total_a1, 1) * 100, 1)

    lost_in_phase = a1_starts["team_possession_loss_in_phase"].sum()

    return {
        "total_a1_possessions": total_a1,
        "stayed_in_a1": len(stayed_a1),
        "progressed_to_a2": len(reached_a2),
        "block_rate": block_rate,
        "possession_lost_in_phase": int(lost_in_phase),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. A1→A3 BYPASS RATE
# ─────────────────────────────────────────────────────────────────────────────
def bypass_rate(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """
    Possessions that go from opponent build-up zone (A1) directly to
    our defensive third (A3), indicating a 'punctured' press.
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    opp_pp = _opponent_pp(data, team)

    a1_starts = opp_pp[opp_pp["third_start"] == "defensive_third"]
    total_a1 = len(a1_starts)

    bypassed = a1_starts[a1_starts["third_end"] == "attacking_third"]
    rate = round(len(bypassed) / max(total_a1, 1) * 100, 1)

    return {
        "total_a1_possessions": total_a1,
        "bypassed_to_a3": len(bypassed),
        "bypass_rate": rate,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. PPDA (Passes Per Defensive Action)
# ─────────────────────────────────────────────────────────────────────────────
def ppda(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """
    Passes allowed per defensive action during pressing phases.
    Lower = more intense pressing.
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    opp_pp = _opponent_pp(data, team)
    obe = _team_obe(data, team)

    opp_passes = opp_pp[opp_pp["end_type"] == "pass"]
    total_passes = len(opp_passes)
    total_actions = len(obe)
    ppda_val = round(total_passes / max(total_actions, 1), 2)

    hb_passes = opp_passes[
        opp_passes["team_out_of_possession_phase_type"] == "high_block"
    ]
    hb_obe = obe[obe["team_out_of_possession_phase_type"] == "high_block"]
    ppda_hb = round(len(hb_passes) / max(len(hb_obe), 1), 2)

    return {
        "ppda_overall": ppda_val,
        "ppda_high_block": ppda_hb,
        "opponent_passes": total_passes,
        "defensive_actions": total_actions,
        "hb_opponent_passes": len(hb_passes),
        "hb_defensive_actions": len(hb_obe),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. xTHREAT DISRUPTION
# ─────────────────────────────────────────────────────────────────────────────
def xthreat_disruption(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """
    How much the opponent's xThreat is reduced during pressing phases
    vs their normal values, adjusted for pitch zone to remove positional bias.
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    if match_id is None:
        team_matches = _team_match_ids(data, team)
        opp_po = data[
            (data["event_type"] == "passing_option")
            & (data["match_id"].isin(team_matches))
            & (data["team_shortname"] != team)
        ]
    else:
        opp_po = data[
            (data["event_type"] == "passing_option") & (data["team_shortname"] != team)
        ]
    opp_po_valid = opp_po.dropna(subset=["xthreat"])

    xt_overall = opp_po_valid["xthreat"].mean() if len(opp_po_valid) > 0 else 0

    hb = opp_po_valid[opp_po_valid["team_out_of_possession_phase_type"] == "high_block"]
    xt_high_block = hb["xthreat"].mean() if len(hb) > 0 else 0

    non_hb = opp_po_valid[opp_po_valid["team_out_of_possession_phase_type"] != "high_block"]
    xt_non_hb = non_hb["xthreat"].mean() if len(non_hb) > 0 else 0

    weighted_num = 0.0
    weighted_den = 0
    for zone in ["defensive_third", "middle_third", "attacking_third"]:
        z = opp_po_valid[opp_po_valid["third_start"] == zone]
        z_hb = z[z["team_out_of_possession_phase_type"] == "high_block"]
        z_non = z[z["team_out_of_possession_phase_type"] != "high_block"]
        if len(z_hb) > 0 and len(z_non) > 0:
            zone_disr = (1 - z_hb["xthreat"].mean() / max(z_non["xthreat"].mean(), 1e-9)) * 100
            weighted_num += zone_disr * len(z_hb)
            weighted_den += len(z_hb)

    disruption_pct = round(weighted_num / max(weighted_den, 1), 1)

    return {
        "xt_overall": round(xt_overall, 5),
        "xt_high_block": round(xt_high_block, 5),
        "xt_non_high_block": round(xt_non_hb, 5),
        "xt_disruption_pct": disruption_pct,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. OPPONENT PASS COMPLETION %
# ─────────────────────────────────────────────────────────────────────────────
def opponent_pass_completion(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """
    Opponent pass completion rate in their defensive third,
    under pressing vs overall.
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    opp_pp = _opponent_pp(data, team)
    passes = opp_pp[opp_pp["end_type"] == "pass"]

    d3 = passes[passes["third_start"] == "defensive_third"]
    d3_total = len(d3)
    d3_succ = (d3["pass_outcome"] == "successful").sum()
    d3_pct = round(d3_succ / max(d3_total, 1) * 100, 1)

    d3_hb = d3[d3["team_out_of_possession_phase_type"] == "high_block"]
    d3_hb_total = len(d3_hb)
    d3_hb_succ = (d3_hb["pass_outcome"] == "successful").sum()
    d3_hb_pct = round(d3_hb_succ / max(d3_hb_total, 1) * 100, 1)

    all_total = len(passes)
    all_succ = (passes["pass_outcome"] == "successful").sum()
    all_pct = round(all_succ / max(all_total, 1) * 100, 1)

    return {
        "pass_pct_overall": all_pct,
        "pass_pct_d3": d3_pct,
        "pass_pct_d3_high_block": d3_hb_pct,
        "d3_passes": d3_total,
        "d3_successful": int(d3_succ),
        "d3_hb_passes": d3_hb_total,
        "d3_hb_successful": int(d3_hb_succ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. CHANCES AFTER PRESSING (opponent creates)
# ─────────────────────────────────────────────────────────────────────────────
def chances_after_pressing(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """
    Does the opponent create chances after/during our pressing?
    Measures how exposed the press leaves us.
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    obe = _team_obe(data, team)
    n_matches = obe["match_id"].nunique()
    total_obe = len(obe)

    beaten_pos = obe["beaten_by_possession"].sum()
    beaten_mov = obe["beaten_by_movement"].sum()
    poss_danger = obe["possession_danger"].sum()

    regain_types = {"direct_regain", "indirect_regain"}
    non_regain = obe[~obe["end_type"].isin(regain_types)]
    shots_after = non_regain["lead_to_shot"].sum()
    goals_after = non_regain["lead_to_goal"].sum()

    return {
        "shots_after_pressing": int(shots_after),
        "shots_per_match": _per_match(int(shots_after), n_matches),
        "goals_after_pressing": int(goals_after),
        "beaten_by_possession": int(beaten_pos),
        "beaten_by_movement": int(beaten_mov),
        "possession_danger_count": int(poss_danger),
        "danger_rate": round(int(poss_danger) / max(total_obe, 1) * 100, 1),
        "beaten_rate": round((int(beaten_pos) + int(beaten_mov)) / max(total_obe, 1) * 100, 1),
        "total_engagements": total_obe,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. CHANCES FROM RECOVERY (we create)
# ─────────────────────────────────────────────────────────────────────────────
def chances_from_recovery(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """
    How often we create chances after recovering the ball from pressing.
    Includes SkillCorner xShot sum on regain-ending OBE rows (possession-level expected goals proxy).
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    obe = _team_obe(data, team)
    n_matches = obe["match_id"].nunique()

    regain_types = {"direct_regain", "indirect_regain"}
    regains = obe[obe["end_type"].isin(regain_types)]
    total_regains = len(regains)

    shots_from_regain = regains["lead_to_shot"].sum()
    goals_from_regain = regains["lead_to_goal"].sum()

    chain_regains = obe[obe["pressing_chain_end_type"] == "regain"]
    shots_from_chain = chain_regains["lead_to_shot"].sum()

    xshot_total = _xshot_sum_regains(regains)
    shot_mask = regains["lead_to_shot"] == True
    xshot_on_shot_regains = _xshot_sum_regains(regains[shot_mask])

    return {
        "total_regains": total_regains,
        "shots_from_regain": int(shots_from_regain),
        "shots_from_regain_per_match": _per_match(int(shots_from_regain), n_matches),
        "goals_from_regain": int(goals_from_regain),
        "shot_conversion_rate": round(
            int(shots_from_regain) / max(total_regains, 1) * 100, 1
        ),
        "chain_regain_shots": int(shots_from_chain),
        "xshot_after_regain_total": round(xshot_total, 2),
        "xshot_after_regain_per_match": round(xshot_total / max(n_matches, 1), 3),
        "xshot_after_regain_per_regain": round(xshot_total / max(total_regains, 1), 4),
        "xshot_on_shot_regains": round(xshot_on_shot_regains, 2),
        "xshot_per_shot_regain": round(
            xshot_on_shot_regains / max(int(shots_from_regain), 1), 4
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10. PRESSING CHAIN ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
def pressing_chain_analysis(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """
    Analysis of pressing chains: frequency, length, outcomes.
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    obe = _team_obe(data, team)
    n_matches = obe["match_id"].nunique()

    chains = obe[obe["pressing_chain"] == True]
    non_chains = obe[obe["pressing_chain"] != True]

    chain_starts = chains[chains["index_in_pressing_chain"] == 1.0]
    total_chains = len(chain_starts)

    avg_length = chain_starts["pressing_chain_length"].dropna().mean()
    max_length = chain_starts["pressing_chain_length"].dropna().max()

    end_types = chains.dropna(subset=["pressing_chain_end_type"])
    end_type_dist = end_types["pressing_chain_end_type"].value_counts().to_dict()

    subtype_in_chains = chains["event_subtype"].value_counts().to_dict()

    return {
        "total_chains": total_chains,
        "chains_per_match": _per_match(total_chains, n_matches),
        "avg_chain_length": round(avg_length, 1) if not np.isnan(avg_length) else 0,
        "max_chain_length": int(max_length) if not np.isnan(max_length) else 0,
        "chain_engagements": len(chains),
        "non_chain_engagements": len(non_chains),
        "chain_end_regain": end_type_dist.get("regain", 0),
        "chain_end_disruption": end_type_dist.get("disruption", 0),
        "subtypes_in_chains": subtype_in_chains,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 11. PRESSING EFFECTIVENESS SCORE
# ─────────────────────────────────────────────────────────────────────────────
def _percentile_rank(value: float, all_values: np.ndarray) -> float:
    """Percentile rank of value within all_values, returned as 0-100."""
    if len(all_values) <= 1:
        return 50.0
    return float(np.sum(all_values <= value) / len(all_values) * 100)


def _get_raw_components(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """Extract the 5 raw component values for the effectiveness score."""
    rec = ball_recoveries(df, team, match_id)
    prog = progression_filter(df, team, match_id)
    flb = forced_long_ball_ratio(df, team, match_id)
    cap = chances_after_pressing(df, team, match_id)

    obe = _team_obe(df if match_id is None else df[df["match_id"] == match_id], team)
    total_obe = len(obe)

    return {
        "recovery_rate": rec["total_regains"] / max(total_obe, 1) * 100,
        "block_rate": prog["block_rate"],
        "long_ball_delta": flb["long_ball_ratio_delta"],
        "beaten_rate": cap["beaten_rate"],
        "danger_rate": cap["danger_rate"],
    }


def _build_league_distributions(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Compute raw component values for every team — used as percentile reference."""
    teams = sorted(df["team_shortname"].dropna().unique())
    dist: dict[str, list] = {
        "recovery_rate": [], "block_rate": [], "long_ball_delta": [],
        "beaten_rate": [], "danger_rate": [],
    }
    for team in teams:
        raw = _get_raw_components(df, team)
        for k in dist:
            dist[k].append(raw[k])
    return {k: np.array(v) for k, v in dist.items()}


def _build_match_level_distributions(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """
    One raw-component vector per (match_id, team) appearance.
    Used to percentile-rank a single match vs all team-games in the dataset.
    """
    dist: dict[str, list] = {
        "recovery_rate": [], "block_rate": [], "long_ball_delta": [],
        "beaten_rate": [], "danger_rate": [],
    }
    for mid, mdf in df.groupby("match_id", sort=False):
        mid = int(mid)
        teams = (
            mdf.loc[mdf["event_type"] == "on_ball_engagement", "team_shortname"]
            .dropna()
            .unique()
        )
        for t in teams:
            raw = _get_raw_components(mdf, t, match_id=mid)
            for k in dist:
                dist[k].append(raw[k])
    return {k: np.array(v) for k, v in dist.items()}


def pressing_effectiveness_score(
    df: pd.DataFrame,
    team: str,
    match_id: int | None = None,
    league_distributions: dict[str, np.ndarray] | None = None,
    match_distributions: dict[str, np.ndarray] | None = None,
) -> dict:
    """
    Composite score (0-100) combining key pressing metrics.
    Higher = more effective ("wall"), lower = more exposed ("gamble").

    Uses percentile normalization:
    - Season view (match_id is None): rank vs all 20 teams' season aggregates.
    - Match view (match_id set): rank vs all (match, team) samples in the data,
      unless you pass precomputed match_distributions / league_distributions.

    Components (equal weight); each is percentile-normalized (0–100), higher = better:
    - Recovery rate (regains / total engagements)
    - Progression block rate (opponent stuck in their D3)
    - Forced long-ball delta (from their D3, HB vs overall)
    - Beaten (press bypass) — raw beaten_rate: lower is better; score inverts percentile
    - Danger (under press) — raw danger_rate: lower is better; score inverts percentile
    """
    raw = _get_raw_components(df, team, match_id)

    if match_id is not None:
        dist = match_distributions
        if dist is None:
            dist = _build_match_level_distributions(df)
    else:
        dist = league_distributions
        if dist is None:
            dist = _build_league_distributions(df)

    s_recovery = _percentile_rank(raw["recovery_rate"], dist["recovery_rate"])
    s_block = _percentile_rank(raw["block_rate"], dist["block_rate"])
    s_long_ball = _percentile_rank(raw["long_ball_delta"], dist["long_ball_delta"])
    s_not_beaten = 100 - _percentile_rank(raw["beaten_rate"], dist["beaten_rate"])
    s_not_danger = 100 - _percentile_rank(raw["danger_rate"], dist["danger_rate"])

    composite = (s_recovery + s_block + s_long_ball + s_not_beaten + s_not_danger) / 5

    label = "Wall" if composite >= 60 else "Balanced" if composite >= 40 else "Gamble"

    return {
        "score": round(composite, 1),
        "label": label,
        "components": {
            "recovery": round(s_recovery, 1),
            "block": round(s_block, 1),
            "forced_long_ball": round(s_long_ball, 1),
            "not_beaten": round(s_not_beaten, 1),
            "not_danger": round(s_not_danger, 1),
        },
        "raw": {
            "recovery_rate": round(raw["recovery_rate"], 1),
            "block_rate": raw["block_rate"],
            "long_ball_delta": raw["long_ball_delta"],
            "beaten_rate": raw["beaten_rate"],
            "danger_rate": raw["danger_rate"],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# LEAGUE-WIDE COMPARISON
# ─────────────────────────────────────────────────────────────────────────────
def league_pressing_table(
    df: pd.DataFrame,
    league_distributions: dict[str, np.ndarray] | None = None,
) -> pd.DataFrame:
    """Build a league-wide pressing comparison table for all teams."""
    teams = sorted(df["team_shortname"].dropna().unique())

    if league_distributions is None:
        league_distributions = _build_league_distributions(df)

    rows = []
    for team in teams:
        rec = ball_recoveries(df, team)
        flb = forced_long_ball_ratio(df, team)
        prog = progression_filter(df, team)
        byp = bypass_rate(df, team)
        ppda_val = ppda(df, team)
        xt = xthreat_disruption(df, team)
        opc = opponent_pass_completion(df, team)
        cap = chances_after_pressing(df, team)
        cfr = chances_from_recovery(df, team)
        pca = pressing_chain_analysis(df, team)
        pes = pressing_effectiveness_score(df, team, league_distributions=league_distributions)

        rows.append({
            "team": team,
            "matches": rec["n_matches"],
            "effectiveness_score": pes["score"],
            "effectiveness_label": pes["label"],
            "regains_per_match": rec["regains_per_match"],
            "regains_att_third": rec["regains_attacking_third"],
            "chain_regains": rec["chain_regains"],
            "forced_long_pct": flb["long_ball_ratio_high_block"],
            "forced_long_delta": flb["long_ball_ratio_delta"],
            "forced_backward": flb["forced_backward"],
            "block_rate": prog["block_rate"],
            "bypass_rate": byp["bypass_rate"],
            "ppda": ppda_val["ppda_overall"],
            "ppda_high_block": ppda_val["ppda_high_block"],
            "xt_disruption_pct": xt["xt_disruption_pct"],
            "opp_pass_pct_d3": opc["pass_pct_d3"],
            "opp_pass_pct_d3_hb": opc["pass_pct_d3_high_block"],
            "shots_conceded_pm": cap["shots_per_match"],
            "beaten_rate": cap["beaten_rate"],
            "danger_rate": cap["danger_rate"],
            "shots_from_regain_pm": cfr["shots_from_regain_per_match"],
            "xshot_after_regain_pm": cfr["xshot_after_regain_per_match"],
            "xshot_per_regain": cfr["xshot_after_regain_per_regain"],
            "chains_per_match": pca["chains_per_match"],
            "avg_chain_length": pca["avg_chain_length"],
        })

    return pd.DataFrame(rows).sort_values("effectiveness_score", ascending=False).reset_index(drop=True)


def pressing_derived_bundle(
    df: pd.DataFrame,
    data_dir: Path,
    source_path: Path,
    schema: int,
) -> tuple[pd.DataFrame, dict[str, np.ndarray], dict[str, np.ndarray]]:
    """League table + league/match distributions; disk-backed when source parquet unchanged."""
    meta_fp = data_dir / "_pressing_derived.meta.json"
    tbl_fp = data_dir / "_pressing_derived_league_table.parquet"
    ld_fp = data_dir / "_pressing_derived_league_dist.pkl"
    md_fp = data_dir / "_pressing_derived_match_dist.pkl"

    try:
        mtime = float(source_path.stat().st_mtime)
    except OSError:
        mtime = 0.0

    if meta_fp.exists() and tbl_fp.exists() and ld_fp.exists() and md_fp.exists():
        with open(meta_fp, encoding="utf-8") as fh:
            meta = json.load(fh)
        if meta.get("mtime") == mtime and meta.get("schema") == schema:
            table = pd.read_parquet(tbl_fp)
            with open(ld_fp, "rb") as fh:
                league_dist = pickle.load(fh)
            with open(md_fp, "rb") as fh:
                match_dist = pickle.load(fh)
            return table, league_dist, match_dist

    league_dist = _build_league_distributions(df)
    table = league_pressing_table(df, league_distributions=league_dist)
    match_dist = _build_match_level_distributions(df)

    data_dir.mkdir(parents=True, exist_ok=True)
    table.to_parquet(tbl_fp, index=False)
    with open(ld_fp, "wb") as fh:
        pickle.dump(league_dist, fh, protocol=4)
    with open(md_fp, "wb") as fh:
        pickle.dump(match_dist, fh, protocol=4)
    with open(meta_fp, "w", encoding="utf-8") as fh:
        json.dump({"mtime": mtime, "schema": schema}, fh)

    return table, league_dist, match_dist


def player_pressing_stats(df: pd.DataFrame, team: str) -> pd.DataFrame:
    """Per-player pressing statistics for a given team."""
    obe = _team_obe(df, team)
    if len(obe) == 0:
        return pd.DataFrame()

    regain_types = {"direct_regain", "indirect_regain"}
    obe = obe.copy()
    if XSHOT_REGAIN_COL in obe.columns:
        is_regain = obe["end_type"].isin(regain_types)
        obe["_xshot_regain"] = np.where(
            is_regain,
            obe[XSHOT_REGAIN_COL].fillna(0.0),
            0.0,
        )
    else:
        obe["_xshot_regain"] = 0.0

    stats = obe.groupby(["player_name", "player_position"]).agg(
        total_engagements=("event_id", "count"),
        matches=("match_id", "nunique"),
        pressing_count=("event_subtype", lambda x: (x == "pressing").sum()),
        pressure_count=("event_subtype", lambda x: (x == "pressure").sum()),
        counter_press_count=("event_subtype", lambda x: (x == "counter_press").sum()),
        recovery_press_count=("event_subtype", lambda x: (x == "recovery_press").sum()),
        other_count=("event_subtype", lambda x: (x == "other").sum()),
        regains=("end_type", lambda x: x.isin({"direct_regain", "indirect_regain"}).sum()),
        force_backward=("force_backward", "sum"),
        beaten_by_possession=("beaten_by_possession", "sum"),
        beaten_by_movement=("beaten_by_movement", "sum"),
        stop_danger=("stop_possession_danger", "sum"),
        reduce_danger=("reduce_possession_danger", "sum"),
        in_chain=("pressing_chain", "sum"),
        lead_to_shot=("lead_to_shot", "sum"),
        lead_to_goal=("lead_to_goal", "sum"),
        xshot_from_regain=("_xshot_regain", "sum"),
        avg_speed=("speed_avg", "mean"),
        avg_distance=("distance_covered", "mean"),
    ).reset_index()

    stats["engagements_per_match"] = (stats["total_engagements"] / stats["matches"]).round(1)
    stats["regain_rate"] = (stats["regains"] / stats["total_engagements"] * 100).round(1)
    stats["beaten_rate"] = (
        (stats["beaten_by_possession"] + stats["beaten_by_movement"])
        / stats["total_engagements"] * 100
    ).round(1)
    stats["xshot_from_regain"] = stats["xshot_from_regain"].round(2)

    return stats.sort_values("total_engagements", ascending=False).reset_index(drop=True)
