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


# Team-relative thirds: middle + attacking = opponent half (beyond halfway, toward their goal).
OBE_OPPONENT_HALF_THIRDS = frozenset({"middle_third", "attacking_third"})


def _obe_opponent_half(obe: pd.DataFrame) -> pd.DataFrame:
    """OBE rows where the engagement starts in the pressing team's opponent half."""
    if len(obe) == 0:
        return obe
    if "third_start" not in obe.columns:
        return obe
    return obe[obe["third_start"].isin(OBE_OPPONENT_HALF_THIRDS)]


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


# Ham exportta PO satırında `is_available` yok; D3 uzun pas anındaki `n_passing_options`
# ile “kısa opsiyon kısıtlı” proxy’si (≤ bu eşik → zorlanmış say).
FORCED_LONG_STRICT_MAX_PASSING_OPTIONS = 1


def forced_long_ball_strict(
    df: pd.DataFrame,
    team: str,
    match_id: int | None = None,
    *,
    max_passing_options: int = FORCED_LONG_STRICT_MAX_PASSING_OPTIONS,
) -> dict:
    """
    Tek oran: rakibin D3'ten attığı **tüm** uzun paslara göre, bunların kaçında hem
    **high_block** hem de `n_passing_options` ≤ eşik (düşük opsiyon proxy).

    Pay: HB ∧ düşük-opt ∧ uzun (D3). Payda: rakibin D3 uzun pas sayısı (tüm fazlar).
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    opp_pp = _opponent_pp(data, team)
    d3_passes = opp_pp[
        (opp_pp["third_start"] == "defensive_third") & (opp_pp["end_type"] == "pass")
    ]
    longs = d3_passes[d3_passes["pass_range"] == "long"].copy()
    n_opt = longs["n_passing_options"].fillna(999)
    den = len(longs)
    mask = (longs["team_out_of_possession_phase_type"] == "high_block") & (
        n_opt <= max_passing_options
    )
    num = int(mask.sum())
    rate = num / max(den, 1)

    return {
        "strict_long_hb_lowopt_rate": round(rate, 4),
        "strict_long_hb_lowopt_nt": f"{num}/{den}",
        "strict_long_hb_lowopt_max_options": max_passing_options,
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

    Beaten counts and beaten_rate use only OBE rows with third_start in the opponent half
    (middle_third + attacking_third, team-relative). Danger and shot metrics still use all OBE.
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    obe = _team_obe(data, team)
    n_matches = obe["match_id"].nunique()
    total_obe = len(obe)

    obe_oh = _obe_opponent_half(obe)
    n_oh = len(obe_oh)
    beaten_pos = int(obe_oh["beaten_by_possession"].sum())
    beaten_mov = int(obe_oh["beaten_by_movement"].sum())
    poss_danger = obe["possession_danger"].sum()

    regain_types = {"direct_regain", "indirect_regain"}
    non_regain = obe[~obe["end_type"].isin(regain_types)]
    shots_after = non_regain["lead_to_shot"].sum()
    goals_after = non_regain["lead_to_goal"].sum()

    return {
        "shots_after_pressing": int(shots_after),
        "shots_per_match": _per_match(int(shots_after), n_matches),
        "goals_after_pressing": int(goals_after),
        "beaten_by_possession": beaten_pos,
        "beaten_by_movement": beaten_mov,
        "possession_danger_count": int(poss_danger),
        "danger_rate": round(int(poss_danger) / max(total_obe, 1) * 100, 1),
        "beaten_rate": round((beaten_pos + beaten_mov) / max(n_oh, 1) * 100, 1),
        "total_engagements": total_obe,
        "opp_half_engagements": n_oh,
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


def collective_chain_regain_opponent_half(
    df: pd.DataFrame,
    team: str,
    match_id: int | None = None,
) -> dict:
    """
    Kollektif pres (pressing_chain) başına rakip yarısında top kazanımı.

    Payda: Rakip yarısında (`third_start` middle/attacking) başlayan zincirler —
    benzersiz (match_id, pressing_chain_index).

    Pay: Bu zincirlere ait OBE satırlarından, yine rakip yarısında ve
    end_type ∈ {direct_regain, indirect_regain} olanlar.

    Böylece zincir kendi yarıda başlamış olsa sayılmaz; kazanım da OH içinde olmalı.
    """
    data = df if match_id is None else df[df["match_id"] == match_id]
    obe = _team_obe(data, team)
    obe_oh = _obe_opponent_half(obe)

    chains_oh = obe_oh[obe_oh["pressing_chain"] == True]
    chain_starts_oh = chains_oh[chains_oh["index_in_pressing_chain"] == 1.0]
    if len(chain_starts_oh) == 0:
        return {
            "chain_regain_per_oh_chain": 0.0,
            "chain_regain_per_oh_chain_nt": "0/0",
            "chain_starts_opp_half": 0,
            "collective_regains_opp_half": 0,
        }

    start_keys = chain_starts_oh[["match_id", "pressing_chain_index"]].drop_duplicates()
    n_chains_oh = len(start_keys)

    merged = obe.merge(start_keys, on=["match_id", "pressing_chain_index"], how="inner")
    merged_oh = _obe_opponent_half(merged)
    regain_types = {"direct_regain", "indirect_regain"}
    regains = merged_oh[merged_oh["end_type"].isin(regain_types)]
    n_regains = len(regains)

    rate = n_regains / max(n_chains_oh, 1)

    return {
        "chain_regain_per_oh_chain": round(rate, 3),
        "chain_regain_per_oh_chain_nt": f"{n_regains}/{n_chains_oh}",
        "chain_starts_opp_half": int(n_chains_oh),
        "collective_regains_opp_half": int(n_regains),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 11. PRESSING EFFECTIVENESS SCORE
# ─────────────────────────────────────────────────────────────────────────────
# (raw column key, weight, higher_raw_is_better) — Twelve-style z-scores then weighted sum.
_EFFECTIVENESS_METRIC_SPEC: tuple[tuple[str, float, bool], ...] = (
    ("recovery_rate", 0.30, True),
    ("long_ball_delta", 0.20, True),
    ("xt_disruption_pct", 0.20, True),
    ("bypass_rate", 0.10, False),
    ("danger_rate", 0.10, False),
    ("beaten_rate", 0.05, False),
    ("ppda", 0.05, False),
)


def _z_scores_column(arr: np.ndarray, higher_is_better: bool) -> np.ndarray:
    """Per-sample z-scores for a reference vector (μ, σ from full arr)."""
    if len(arr) == 0:
        return np.array([])
    mu = float(np.mean(arr))
    sig = float(np.std(arr, ddof=0))
    sig = max(sig, 1e-9)
    if higher_is_better:
        return (arr - mu) / sig
    return (mu - arr) / sig


def _z_scalar(x: float, arr: np.ndarray, higher_is_better: bool) -> float:
    if len(arr) == 0:
        return 0.0
    mu = float(np.mean(arr))
    sig = max(float(np.std(arr, ddof=0)), 1e-9)
    if higher_is_better:
        return (x - mu) / sig
    return (mu - x) / sig


def _composite_z_vector(dist: dict[str, np.ndarray]) -> np.ndarray:
    """Weighted sum of metric z-scores for each parallel row in dist (same length arrays)."""
    first = next(iter(dist.values()), None)
    if first is None or len(first) == 0:
        return np.array([])
    n = len(first)
    total = np.zeros(n, dtype=float)
    for key, weight, hib in _EFFECTIVENESS_METRIC_SPEC:
        total += weight * _z_scores_column(dist[key], hib)
    return total


def _get_raw_components(df: pd.DataFrame, team: str, match_id: int | None = None) -> dict:
    """Raw values for effectiveness score (before z-score normalization)."""
    flb = forced_long_ball_ratio(df, team, match_id)
    xt = xthreat_disruption(df, team, match_id)
    byp = bypass_rate(df, team, match_id)
    cap = chances_after_pressing(df, team, match_id)
    pp = ppda(df, team, match_id)

    obe = _team_obe(df if match_id is None else df[df["match_id"] == match_id], team)
    obe_oh = _obe_opponent_half(obe)
    regain_types = {"direct_regain", "indirect_regain"}
    regains_oh = obe_oh[obe_oh["end_type"].isin(regain_types)]

    return {
        "recovery_rate": len(regains_oh) / max(len(obe_oh), 1) * 100,
        "long_ball_delta": flb["long_ball_ratio_delta"],
        "xt_disruption_pct": xt["xt_disruption_pct"],
        "bypass_rate": byp["bypass_rate"],
        "beaten_rate": cap["beaten_rate"],
        "danger_rate": cap["danger_rate"],
        "ppda": pp["ppda_overall"],
    }


def _build_league_distributions(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Compute raw component values for every team — μ, σ and Z_q reference pool."""
    teams = sorted(df["team_shortname"].dropna().unique())
    dist: dict[str, list] = {
        "recovery_rate": [],
        "long_ball_delta": [],
        "xt_disruption_pct": [],
        "bypass_rate": [],
        "beaten_rate": [],
        "danger_rate": [],
        "ppda": [],
    }
    for team in teams:
        raw = _get_raw_components(df, team)
        for k in dist:
            dist[k].append(raw[k])
    return {k: np.array(v) for k, v in dist.items()}


def _build_match_level_distributions(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """
    One raw-component vector per (match_id, team) appearance.
    Used to build μ, σ and composite-z reference over all team-games in the dataset.
    """
    dist: dict[str, list] = {
        "recovery_rate": [],
        "long_ball_delta": [],
        "xt_disruption_pct": [],
        "bypass_rate": [],
        "beaten_rate": [],
        "danger_rate": [],
        "ppda": [],
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
    Twelve-style quality score:

    1. Per metric: z = (x−μ)/σ (or (μ−x)/σ when lower raw is better).
    2. Z_q_raw = Σ w_m z_m with weights 0.30 / 0.20 / 0.20 / 0.10 / 0.10 / 0.05 / 0.05.
    3. Z_q = (Z_q_raw − μ_Z) / σ_Z over all reference units (league teams or team-games).

    **z_composite** is Z_q (step 3). **z_composite_raw** is Z_q_raw (step 2).

    **score** is **Z_q** (Twelve final quality score; pool mean ≈ 0, std ≈ 1).
    **label** is a UI band on Z_q: Wall if Z_q ≥ 1, Gamble if Z_q ≤ −1, else Balanced (≈1σ).
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

    z_q_raw_all = _composite_z_vector(dist)
    comp_keys = (
        "recovery",
        "forced_long_ball",
        "xt_disruption",
        "bypass",
        "danger",
        "beaten",
        "ppda",
    )
    z_parts: dict[str, float] = {}
    z_q_raw = 0.0
    for (key, weight, hib), ck in zip(_EFFECTIVENESS_METRIC_SPEC, comp_keys, strict=True):
        zv = _z_scalar(raw[key], dist[key], hib)
        z_parts[ck] = round(zv, 2)
        z_q_raw += weight * zv

    if len(z_q_raw_all) > 0:
        mu_z = float(np.mean(z_q_raw_all))
        sig_z = max(float(np.std(z_q_raw_all, ddof=0)), 1e-9)
        z_q = (z_q_raw - mu_z) / sig_z
    else:
        z_q = 0.0

    if z_q >= 1.0:
        label = "Wall"
    elif z_q <= -1.0:
        label = "Gamble"
    else:
        label = "Balanced"

    return {
        "score": round(z_q, 3),
        "label": label,
        "z_composite_raw": round(z_q_raw, 3),
        "z_composite": round(z_q, 3),
        "components": z_parts,
        "raw": {
            "recovery_rate": round(raw["recovery_rate"], 1),
            "long_ball_delta": raw["long_ball_delta"],
            "xt_disruption_pct": raw["xt_disruption_pct"],
            "bypass_rate": raw["bypass_rate"],
            "beaten_rate": raw["beaten_rate"],
            "danger_rate": raw["danger_rate"],
            "ppda": raw["ppda"],
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

        fls = forced_long_ball_strict(df, team)
        prog = progression_filter(df, team)
        byp = bypass_rate(df, team)
        ppda_val = ppda(df, team)
        xt = xthreat_disruption(df, team)
        opc = opponent_pass_completion(df, team)
        cap = chances_after_pressing(df, team)
        cfr = chances_from_recovery(df, team)
        pca = pressing_chain_analysis(df, team)
        ccr = collective_chain_regain_opponent_half(df, team)
        pes = pressing_effectiveness_score(df, team, league_distributions=league_distributions)
        comp = pes["components"]
        rawp = pes["raw"]

        rows.append({
            "team": team,
            "matches": rec["n_matches"],
            "effectiveness_score": pes["score"],
            "z_q_raw": pes["z_composite_raw"],
            "effectiveness_label": pes["label"],
            "recovery_rate": rawp["recovery_rate"],
            "z_recovery": comp["recovery"],
            "z_forced_long_ball": comp["forced_long_ball"],
            "z_xt_disruption": comp["xt_disruption"],
            "z_bypass": comp["bypass"],
            "z_danger": comp["danger"],
            "z_beaten": comp["beaten"],
            "z_ppda": comp["ppda"],
            "regains_per_match": rec["regains_per_match"],
            "regains_att_third": rec["regains_attacking_third"],
            "chain_regains": rec["chain_regains"],
            "forced_long_pct": flb["long_ball_ratio_high_block"],
            "forced_long_delta": flb["long_ball_ratio_delta"],
            "strict_long_hb_lowopt_rate": fls["strict_long_hb_lowopt_rate"],
            "strict_long_hb_lowopt_nt": fls["strict_long_hb_lowopt_nt"],
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
            "chain_regain_per_oh_chain": ccr["chain_regain_per_oh_chain"],
            "chain_regain_per_oh_chain_nt": ccr["chain_regain_per_oh_chain_nt"],
        })

    return pd.DataFrame(rows).sort_values("effectiveness_score", ascending=False).reset_index(drop=True)


def pressing_league_bundle(
    df: pd.DataFrame,
    data_dir: Path,
    source_path: Path,
    schema: int,
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """League table + league distributions only (fast path for League Overview)."""
    meta_fp = data_dir / "_pressing_league.meta.json"
    tbl_fp = data_dir / "_pressing_league_table.parquet"
    ld_fp = data_dir / "_pressing_league_dist.pkl"

    try:
        mtime = float(source_path.stat().st_mtime)
    except OSError:
        mtime = 0.0

    if meta_fp.exists() and tbl_fp.exists() and ld_fp.exists():
        with open(meta_fp, encoding="utf-8") as fh:
            meta = json.load(fh)
        if meta.get("mtime") == mtime and meta.get("schema") == schema:
            table = pd.read_parquet(tbl_fp)
            with open(ld_fp, "rb") as fh:
                league_dist = pickle.load(fh)
            return table, league_dist

    league_dist = _build_league_distributions(df)
    table = league_pressing_table(df, league_distributions=league_dist)

    data_dir.mkdir(parents=True, exist_ok=True)
    table.to_parquet(tbl_fp, index=False)
    with open(ld_fp, "wb") as fh:
        pickle.dump(league_dist, fh, protocol=4)
    with open(meta_fp, "w", encoding="utf-8") as fh:
        json.dump({"mtime": mtime, "schema": schema}, fh)

    return table, league_dist


def pressing_match_distributions_bundle(
    df: pd.DataFrame,
    data_dir: Path,
    source_path: Path,
    schema: int,
) -> dict[str, np.ndarray]:
    """
    Match-level percentile reference (~760 team-games). Built only when Match Analysis
    needs it — not on initial league load.
    """
    meta_fp = data_dir / "_pressing_match.meta.json"
    md_fp = data_dir / "_pressing_match_dist.pkl"

    try:
        mtime = float(source_path.stat().st_mtime)
    except OSError:
        mtime = 0.0

    if meta_fp.exists() and md_fp.exists():
        with open(meta_fp, encoding="utf-8") as fh:
            meta = json.load(fh)
        if meta.get("mtime") == mtime and meta.get("schema") == schema:
            with open(md_fp, "rb") as fh:
                return pickle.load(fh)

    match_dist = _build_match_level_distributions(df)

    data_dir.mkdir(parents=True, exist_ok=True)
    with open(md_fp, "wb") as fh:
        pickle.dump(match_dist, fh, protocol=4)
    with open(meta_fp, "w", encoding="utf-8") as fh:
        json.dump({"mtime": mtime, "schema": schema}, fh)

    return match_dist


def player_pressing_stats(df: pd.DataFrame, team: str) -> pd.DataFrame:
    """Per-player pressing statistics for a given team.

    beaten_by_* counts and beaten_rate use only engagements in the opponent half
    (third_start in middle_third or attacking_third), consistent with chances_after_pressing.
    """
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
        stop_danger=("stop_possession_danger", "sum"),
        reduce_danger=("reduce_possession_danger", "sum"),
        in_chain=("pressing_chain", "sum"),
        lead_to_shot=("lead_to_shot", "sum"),
        lead_to_goal=("lead_to_goal", "sum"),
        xshot_from_regain=("_xshot_regain", "sum"),
        avg_speed=("speed_avg", "mean"),
        avg_distance=("distance_covered", "mean"),
    ).reset_index()

    obe_oh = _obe_opponent_half(obe)
    if len(obe_oh) > 0:
        oh = obe_oh.groupby(["player_name", "player_position"]).agg(
            opp_half_engagements=("event_id", "count"),
            beaten_by_possession=("beaten_by_possession", "sum"),
            beaten_by_movement=("beaten_by_movement", "sum"),
        ).reset_index()
    else:
        oh = pd.DataFrame(
            columns=[
                "player_name",
                "player_position",
                "opp_half_engagements",
                "beaten_by_possession",
                "beaten_by_movement",
            ]
        )

    stats = stats.merge(oh, on=["player_name", "player_position"], how="left")
    stats["opp_half_engagements"] = stats["opp_half_engagements"].fillna(0).astype(int)
    stats["beaten_by_possession"] = stats["beaten_by_possession"].fillna(0).astype(int)
    stats["beaten_by_movement"] = stats["beaten_by_movement"].fillna(0).astype(int)

    den = stats["opp_half_engagements"].to_numpy()
    num = (stats["beaten_by_possession"] + stats["beaten_by_movement"]).to_numpy()
    stats["beaten_rate"] = np.where(den > 0, num / den * 100, 0.0)
    stats["beaten_rate"] = stats["beaten_rate"].round(1)

    stats["engagements_per_match"] = (stats["total_engagements"] / stats["matches"]).round(1)
    stats["regain_rate"] = (stats["regains"] / stats["total_engagements"] * 100).round(1)
    stats["xshot_from_regain"] = stats["xshot_from_regain"].round(2)

    return stats.sort_values("total_engagements", ascending=False).reset_index(drop=True)
