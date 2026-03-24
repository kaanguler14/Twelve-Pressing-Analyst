"""
SkillCorner Dynamic Events CSV - Kullanım Rehberi ve Analiz Örnekleri
=====================================================================
Bu script, SkillCorner Dynamic Events CSV dataseti ile çalışmak için
temel yükleme, filtreleme ve analiz örneklerini içerir.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path


# =============================================================================
# 1) VERİYİ YÜKLEME
# =============================================================================

def load_dynamic_events(csv_path: str) -> pd.DataFrame:
    """
    SkillCorner Dynamic Events CSV dosyasını yükler ve temel ön işleme yapar.
    CSV ayracı genellikle virgül veya noktalı virgüldür - dosyanıza göre ayarlayın.
    """
    df = pd.read_csv(csv_path, low_memory=False)

    bool_cols = [
        "lead_to_shot", "lead_to_goal", "targeted", "received",
        "received_in_space", "one_touch", "quick_pass", "carry",
        "forward_momentum", "is_header", "penalty_area_start",
        "penalty_area_end", "organised_defense", "first_line_break",
        "second_last_line_break", "last_line_break", "give_and_go",
        "dangerous", "difficult_pass_target", "pass_ahead", "high_pass",
        "inside_defensive_shape_start", "inside_defensive_shape_end",
    ]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].map({"TRUE": True, "FALSE": False, True: True, False: False})

    float_cols = [
        "xthreat", "xpass_completion", "passing_option_score",
        "speed_avg", "distance_covered", "pass_distance",
        "x_start", "y_start", "x_end", "y_end", "duration",
        "separation_start", "separation_end",
    ]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# =============================================================================
# 2) OLAY TİPLERİNE GÖRE FİLTRELEME
# =============================================================================

def split_by_event_type(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Veriyi 4 olay tipine ayırır."""
    return {
        "player_possession": df[df["event_type"] == "player_possession"].copy(),
        "passing_option": df[df["event_type"] == "passing_option"].copy(),
        "off_ball_run": df[df["event_type"] == "off_ball_run"].copy(),
        "on_ball_engagement": df[df["event_type"] == "defensive_engagement"].copy(),
    }


# =============================================================================
# 3) TEMEL İSTATİSTİKLER
# =============================================================================

def match_summary(df: pd.DataFrame) -> None:
    """Maç bazında temel istatistikleri yazdırır."""
    print("=" * 60)
    print("MAÇ ÖZETİ")
    print("=" * 60)

    teams = df["team_shortname"].unique()
    print(f"Takımlar: {', '.join(str(t) for t in teams)}")

    event_counts = df["event_type"].value_counts()
    print(f"\nOlay Dağılımı:")
    for event_type, count in event_counts.items():
        print(f"  {event_type:30s}: {count}")

    print(f"\nToplam Olay: {len(df)}")
    print(f"Periyot Sayısı: {df['period'].nunique()}")

    if "duration" in df.columns:
        avg_dur = df.groupby("event_type")["duration"].mean()
        print(f"\nOrtalama Süre (saniye):")
        for et, dur in avg_dur.items():
            print(f"  {et:30s}: {dur:.2f}")


# =============================================================================
# 4) PAS ANALİZİ
# =============================================================================

def pass_analysis(pp: pd.DataFrame) -> pd.DataFrame:
    """
    Player Possession olaylarından pas analizi çıkarır.
    Sadece pas ile biten possession'ları filtreler.
    """
    passes = pp[pp["end_type"] == "pass"].copy()

    summary = passes.groupby("team_shortname").agg(
        toplam_pas=("event_id", "count"),
        basarili_pas=("pass_outcome", lambda x: (x == "successful").sum()),
        basarisiz_pas=("pass_outcome", lambda x: (x == "unsuccessful").sum()),
        ort_pas_mesafesi=("pass_distance_received", "mean"),
        ileri_pas=("pass_ahead", lambda x: x.sum() if x.dtype == bool else 0),
    ).reset_index()

    summary["pas_basari_orani"] = (
        summary["basarili_pas"] / summary["toplam_pas"] * 100
    ).round(1)

    print("\n" + "=" * 60)
    print("PAS ANALİZİ")
    print("=" * 60)
    print(summary.to_string(index=False))
    return summary


# =============================================================================
# 5) xTHREAT ANALİZİ (Passing Options)
# =============================================================================

def xthreat_analysis(po: pd.DataFrame) -> pd.DataFrame:
    """
    Passing Option olayları üzerinden xThreat analizi.
    xthreat: Pas tamamlandıktan sonra 10 sn içinde gol olma olasılığı.
    """
    po_valid = po.dropna(subset=["xthreat"])

    player_xthreat = po_valid.groupby(["player_name", "team_shortname"]).agg(
        toplam_xthreat=("xthreat", "sum"),
        ort_xthreat=("xthreat", "mean"),
        max_xthreat=("xthreat", "max"),
        tehlikeli_opsiyonlar=("dangerous", "sum"),
        toplam_opsiyon=("event_id", "count"),
    ).reset_index().sort_values("toplam_xthreat", ascending=False)

    print("\n" + "=" * 60)
    print("xTHREAT ANALİZİ - EN TEHLİKELİ PAS HEDEFLERİ")
    print("=" * 60)
    print(player_xthreat.head(10).to_string(index=False))
    return player_xthreat


# =============================================================================
# 6) OFF-BALL RUN ANALİZİ
# =============================================================================

def off_ball_run_analysis(obr: pd.DataFrame) -> pd.DataFrame:
    """Off-ball run tipleri ve etkinlik analizi."""
    run_summary = obr.groupby(["team_shortname", "event_subtype"]).agg(
        adet=("event_id", "count"),
        ort_hiz=("speed_avg", "mean"),
        ort_mesafe=("distance_covered", "mean"),
        hedeflenen=("targeted", "sum"),
        topa_ulasan=("received", "sum"),
    ).reset_index().sort_values(["team_shortname", "adet"], ascending=[True, False])

    print("\n" + "=" * 60)
    print("OFF-BALL RUN ANALİZİ")
    print("=" * 60)
    print(run_summary.to_string(index=False))
    return run_summary


# =============================================================================
# 7) ÇİZGİ KIRMA (LINE BREAK) ANALİZİ
# =============================================================================

def line_break_analysis(po: pd.DataFrame, pp: pd.DataFrame) -> None:
    """Çizgi kırma fırsatları ve gerçekleşme oranları."""
    organised = po[po["organised_defense"] == True]

    print("\n" + "=" * 60)
    print("ÇİZGİ KIRMA ANALİZİ")
    print("=" * 60)

    for team in organised["team_shortname"].unique():
        team_po = organised[organised["team_shortname"] == team]
        print(f"\n--- {team} ---")
        total = len(team_po)
        first = team_po["first_line_break"].sum() if "first_line_break" in team_po else 0
        second = team_po["second_last_line_break"].sum() if "second_last_line_break" in team_po else 0
        last = team_po["last_line_break"].sum() if "last_line_break" in team_po else 0

        print(f"  Organize savunmaya karşı pas opsiyonu: {total}")
        print(f"  İlk çizgi kırma fırsatı:              {first}")
        print(f"  Orta çizgi kırma fırsatı:              {second}")
        print(f"  Son çizgi kırma fırsatı:               {last}")

    pp_passes = pp[(pp["end_type"] == "pass") & (pp["organised_defense"] == True)]
    if len(pp_passes) > 0:
        print(f"\nGerçekleşen çizgi kırma pasları:")
        for team in pp_passes["team_shortname"].unique():
            team_pp = pp_passes[pp_passes["team_shortname"] == team]
            realized_first = team_pp["first_line_break"].sum() if "first_line_break" in team_pp else 0
            realized_last = team_pp["last_line_break"].sum() if "last_line_break" in team_pp else 0
            print(f"  {team}: İlk çizgi={realized_first}, Son çizgi={realized_last}")


# =============================================================================
# 8) BASKI (PRESSURE) ANALİZİ
# =============================================================================

def pressure_analysis(pp: pd.DataFrame) -> None:
    """Player Possession'lar üzerinden baskı dağılımı analizi."""
    if "overall_pressure_start" not in pp.columns:
        print("Baskı verileri mevcut değil.")
        return

    print("\n" + "=" * 60)
    print("BASKI ANALİZİ")
    print("=" * 60)

    for team in pp["team_shortname"].unique():
        team_pp = pp[pp["team_shortname"] == team]
        pressure_dist = team_pp["overall_pressure_start"].value_counts(normalize=True) * 100
        print(f"\n--- {team} - Baskı Altında Top Alma Dağılımı ---")
        for level, pct in pressure_dist.items():
            print(f"  {str(level):25s}: %{pct:.1f}")


# =============================================================================
# 9) ON-BALL ENGAGEMENT ANALİZİ
# =============================================================================

def engagement_analysis(obe: pd.DataFrame) -> None:
    """Savunma baskı tipleri ve etkinlik analizi."""
    print("\n" + "=" * 60)
    print("ON-BALL ENGAGEMENT ANALİZİ")
    print("=" * 60)

    for team in obe["team_shortname"].unique():
        team_obe = obe[obe["team_shortname"] == team]
        subtype_counts = team_obe["event_subtype"].value_counts()
        print(f"\n--- {team} ---")
        for st, cnt in subtype_counts.items():
            print(f"  {str(st):20s}: {cnt}")

        if "beaten_by_possession" in team_obe.columns:
            beaten = team_obe["beaten_by_possession"].sum()
            print(f"  Geçilen baskılar:   {beaten}")
        if "force_backward" in team_obe.columns:
            forced = team_obe["force_backward"].sum()
            print(f"  Geri pas zorlatılan: {forced}")


# =============================================================================
# 10) OYUN FAZI (PHASE OF PLAY) ANALİZİ
# =============================================================================

def phase_of_play_analysis(df: pd.DataFrame) -> None:
    """Takım bazında oyun fazı dağılımı."""
    print("\n" + "=" * 60)
    print("OYUN FAZI DAĞILIMI")
    print("=" * 60)

    pp = df[df["event_type"] == "player_possession"]
    for team in pp["team_shortname"].unique():
        team_pp = pp[pp["team_shortname"] == team]
        phase_dist = team_pp["team_in_possession_phase_type"].value_counts()
        print(f"\n--- {team} (Topa Sahip İken) ---")
        for phase, cnt in phase_dist.items():
            print(f"  {str(phase):20s}: {cnt}")


# =============================================================================
# 11) SAHA VİZUALİZASYONU - Passing Options Haritası
# =============================================================================

def draw_pitch(ax: plt.Axes) -> None:
    """Yarı boyutlu futbol sahası çizer. Koordinatlar: merkez (0,0), metre cinsinden."""
    pitch_length, pitch_width = 105, 68
    half_l, half_w = pitch_length / 2, pitch_width / 2

    ax.set_xlim(-half_l - 3, half_l + 3)
    ax.set_ylim(-half_w - 3, half_w + 3)
    ax.set_aspect("equal")
    ax.set_facecolor("#2d5a27")

    line_color = "white"
    lw = 1.5

    ax.plot([-half_l, half_l, half_l, -half_l, -half_l],
            [-half_w, -half_w, half_w, half_w, -half_w], color=line_color, lw=lw)
    ax.plot([0, 0], [-half_w, half_w], color=line_color, lw=lw)
    circle = plt.Circle((0, 0), 9.15, color=line_color, fill=False, lw=lw)
    ax.add_patch(circle)

    for sign in [-1, 1]:
        penalty_x = sign * half_l
        box_x = sign * (half_l - 16.5)
        small_box_x = sign * (half_l - 5.5)
        ax.plot([penalty_x, box_x, box_x, penalty_x],
                [-20.15, -20.15, 20.15, 20.15], color=line_color, lw=lw)
        ax.plot([penalty_x, small_box_x, small_box_x, penalty_x],
                [-9.16, -9.16, 9.16, 9.16], color=line_color, lw=lw)

    ax.set_xticks([])
    ax.set_yticks([])


def plot_passing_options_map(po: pd.DataFrame, team: str | None = None) -> None:
    """Passing option konumlarını saha üzerinde gösterir, xthreat ile renklenir."""
    fig, ax = plt.subplots(figsize=(14, 9))
    draw_pitch(ax)

    data = po.dropna(subset=["x_start", "y_start", "xthreat"])
    if team:
        data = data[data["team_shortname"] == team]

    scatter = ax.scatter(
        data["x_start"], data["y_start"],
        c=data["xthreat"], cmap="YlOrRd",
        s=30, alpha=0.6, edgecolors="white", linewidths=0.3,
        vmin=0, vmax=data["xthreat"].quantile(0.95),
    )
    plt.colorbar(scatter, ax=ax, label="xThreat", shrink=0.8)
    title = f"Passing Options - xThreat Haritası"
    if team:
        title += f" ({team})"
    ax.set_title(title, fontsize=14, fontweight="bold", color="white")
    plt.tight_layout()
    plt.savefig("passing_options_xthreat_map.png", dpi=150, bbox_inches="tight")
    plt.show()


def plot_off_ball_runs(obr: pd.DataFrame, team: str | None = None) -> None:
    """Off-ball run başlangıç ve bitiş noktalarını saha üzerinde ok olarak çizer."""
    fig, ax = plt.subplots(figsize=(14, 9))
    draw_pitch(ax)

    data = obr.dropna(subset=["x_start", "y_start", "x_end", "y_end"])
    if team:
        data = data[data["team_shortname"] == team]

    subtype_colors = {
        "behind": "#e74c3c", "overlap": "#3498db", "underlap": "#2ecc71",
        "pulling_wide": "#f39c12", "pulling_half_space": "#9b59b6",
        "run_ahead_of_the_ball": "#1abc9c", "coming_short": "#e67e22",
        "dropping_off": "#95a5a6", "cross_receiver": "#e91e63",
        "support": "#607d8b",
    }

    for _, row in data.iterrows():
        color = subtype_colors.get(row.get("event_subtype", ""), "#ffffff")
        ax.annotate(
            "", xy=(row["x_end"], row["y_end"]),
            xytext=(row["x_start"], row["y_start"]),
            arrowprops=dict(arrowstyle="->", color=color, lw=1.2, alpha=0.7),
        )

    legend_handles = [
        plt.Line2D([0], [0], color=c, lw=2, label=s)
        for s, c in subtype_colors.items()
    ]
    ax.legend(handles=legend_handles, loc="upper left", fontsize=8,
              facecolor="black", labelcolor="white", framealpha=0.8)

    title = "Off-Ball Run Haritası"
    if team:
        title += f" ({team})"
    ax.set_title(title, fontsize=14, fontweight="bold", color="white")
    plt.tight_layout()
    plt.savefig("off_ball_runs_map.png", dpi=150, bbox_inches="tight")
    plt.show()


# =============================================================================
# 12) OYUNCU PERFORMANS KARTI
# =============================================================================

def player_card(df: pd.DataFrame, player_name: str) -> None:
    """Belirli bir oyuncu için kapsamlı performans kartı oluşturur."""
    events = split_by_event_type(df)
    player_pp = events["player_possession"][
        events["player_possession"]["player_name"] == player_name
    ]
    player_po = events["passing_option"][
        events["passing_option"]["player_name"] == player_name
    ]
    player_obr = events["off_ball_run"][
        events["off_ball_run"]["player_name"] == player_name
    ]

    print("\n" + "=" * 60)
    print(f"OYUNCU KARTI: {player_name}")
    print("=" * 60)

    if len(player_pp) > 0:
        team = player_pp["team_shortname"].iloc[0]
        position = player_pp["player_position"].iloc[0]
        print(f"Takım: {team} | Pozisyon: {position}")

    print(f"\n--- Top Kontrolü (Player Possession) ---")
    print(f"  Toplam PP: {len(player_pp)}")
    if len(player_pp) > 0:
        passes = player_pp[player_pp["end_type"] == "pass"]
        successful = passes[passes["pass_outcome"] == "successful"] if "pass_outcome" in passes.columns else pd.DataFrame()
        print(f"  Pas Girişimi: {len(passes)}")
        print(f"  Başarılı Pas: {len(successful)}")
        if len(passes) > 0:
            print(f"  Pas Başarı: %{len(successful) / len(passes) * 100:.1f}")

        shots = player_pp[player_pp["end_type"] == "shot"]
        print(f"  Şut: {len(shots)}")

        if "carry" in player_pp.columns:
            carries = player_pp[player_pp["carry"] == True]
            print(f"  Taşıma (Carry): {len(carries)}")
        if "forward_momentum" in player_pp.columns:
            fm = player_pp[player_pp["forward_momentum"] == True]
            print(f"  İleri Momentum: {len(fm)}")

    print(f"\n--- Pas Opsiyonu Olarak ---")
    print(f"  Toplam PO: {len(player_po)}")
    if len(player_po) > 0:
        targeted_po = player_po[player_po["targeted"] == True]
        received_po = player_po[player_po["received"] == True]
        print(f"  Hedeflenen: {len(targeted_po)}")
        print(f"  Topa Ulaşan: {len(received_po)}")
        if "xthreat" in player_po.columns:
            avg_xt = player_po["xthreat"].mean()
            total_xt = player_po["xthreat"].sum()
            print(f"  Toplam xThreat: {total_xt:.3f}")
            print(f"  Ort. xThreat: {avg_xt:.4f}")

    print(f"\n--- Off-Ball Run ---")
    print(f"  Toplam OBR: {len(player_obr)}")
    if len(player_obr) > 0:
        subtype_dist = player_obr["event_subtype"].value_counts()
        for st, cnt in subtype_dist.items():
            print(f"    {st}: {cnt}")
        if "speed_avg" in player_obr.columns:
            avg_speed = player_obr["speed_avg"].mean()
            print(f"  Ort. Koşu Hızı: {avg_speed:.1f} km/h")


# =============================================================================
# ANA ÇALIŞTIRMA
# =============================================================================

if __name__ == "__main__":
    CSV_PATH = "dynamic_events.csv"  # <-- Kendi dosya yolunuzu yazın

    if not Path(CSV_PATH).exists():
        print(f"'{CSV_PATH}' bulunamadı.")
        print("Lütfen CSV_PATH değişkenini gerçek dosya yolunuzla değiştirin.")
        print("\nÖrnek kullanım:")
        print('  df = load_dynamic_events("path/to/your/dynamic_events.csv")')
        print('  match_summary(df)')
        print('  events = split_by_event_type(df)')
        print('  pass_analysis(events["player_possession"])')
        print('  xthreat_analysis(events["passing_option"])')
        print('  off_ball_run_analysis(events["off_ball_run"])')
        print('  line_break_analysis(events["passing_option"], events["player_possession"])')
        print('  pressure_analysis(events["player_possession"])')
        print('  engagement_analysis(events["on_ball_engagement"])')
        print('  phase_of_play_analysis(df)')
        print('  plot_passing_options_map(events["passing_option"], team="Liverpool")')
        print('  plot_off_ball_runs(events["off_ball_run"], team="Liverpool")')
        print('  player_card(df, "T. Alexander-Arnold")')
    else:
        df = load_dynamic_events(CSV_PATH)
        match_summary(df)

        events = split_by_event_type(df)
        pp = events["player_possession"]
        po = events["passing_option"]
        obr = events["off_ball_run"]
        obe = events["on_ball_engagement"]

        pass_analysis(pp)
        xthreat_analysis(po)
        off_ball_run_analysis(obr)
        line_break_analysis(po, pp)
        pressure_analysis(pp)
        engagement_analysis(obe)
        phase_of_play_analysis(df)

        teams = df["team_shortname"].unique()
        if len(teams) > 0:
            plot_passing_options_map(po, team=str(teams[0]))
            plot_off_ball_runs(obr, team=str(teams[0]))

        players = pp["player_name"].value_counts()
        if len(players) > 0:
            player_card(df, players.index[0])
