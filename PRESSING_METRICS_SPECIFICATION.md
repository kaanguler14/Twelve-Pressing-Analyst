# Pressing Analyst — Metrik Teknik Spesifikasyonu

**Kaynak kod:** `pressing_metrics.py`  
**Veri:** SkillCorner Dynamic Events (birleşik parquet: `_pressing_cache.parquet`)  
**Amaç:** Her metriğin *neden* tanımlandığı, *hangi olay/sütunlardan* türetildiği ve *nasıl* hesaplandığı; etkinlik skorunda (`Z_q`) hangi bileşenlerin kullanıldığı.

Bu belge PDF’e dönüştürülmek üzere yapılandırılmıştır (Markdown → PDF araçlarıyla).

---

## 1. Ortak kavramlar ve filtreler

### 1.1 Takım ve maç

- **Analiz takımı (“biz”):** Pressing ölçülen takım (`team_shortname == team`).
- **Rakip:** Aynı maçta topa sahip olan diğer takım.
- **Rakip PP / PO:** Sadece analiz takımının oynadığı maçlardaki rakip satırları kullanılır (`_team_match_ids` ile `match_id` filtresi). Aksi halde lig genelinde yanlış “rakip” verisi karışır.

### 1.2 Olay türleri (SkillCorner `event_type`)

| `event_type`            | Kısaltma | Kullanım özeti                                      |
|-------------------------|----------|-----------------------------------------------------|
| `player_possession`     | PP       | Rakip top kontrolü; pas, çıkış, üçte bitiş          |
| `on_ball_engagement`    | OBE      | Bizim savunmacının topa baskısı                     |
| `passing_option`        | PO       | Rakip pas hedefleri; xThreat vb.                    |
| `off_ball_run`          | OBR      | Bu spesifikasyonda çekirdek metriklerde kullanılmıyor |

### 1.3 Yardımcı fonksiyonlar (kod ile aynı isimler)

**`_opponent_pp(df, team)`**  
- `event_type == "player_possession"`  
- `match_id` ∈ (takımın oynadığı maçlar)  
- `team_shortname != team`  

**`_team_obe(df, team)`**  
- `event_type == "on_ball_engagement"`  
- `team_shortname == team`  

**`_obe_opponent_half(obe)`** — “Rakip yarısı” OBE  
- `third_start ∈ {"middle_third", "attacking_third"}` (takıma göre orta + hücum üçü).  
- `third_start` yoksa veya boş küme ise filtre uygulanmaz (tüm OBE).

### 1.4 Üçlü bölgeler (takım perspektifi)

- **A1 / D3 (rakip):** `third_start == "defensive_third"` — rakibin build-up bölgesi.  
- **A3 (rakip) / bizim savunma üçü:** `third_end == "attacking_third"` — tek possession içinde rakip topu bu üçe taşımış.  
- **Bypass’taki A1→A3:** `third_start == defensive_third` ve `third_end == attacking_third` (tek PP satırında).

### 1.5 Faz

- **`team_out_of_possession_phase_type == "high_block"`:** Bizim takım yüksek blokta (rakip genelde build-up fazında). Metriklerde “HB” olarak geçer.

---

## 2. Metrikler (sıra: kaynak dosyadaki fonksiyon sırası)

Her alt bölümde: **Amaç → Veri (sütunlar) → Algoritma → Formül(ler) → Çıktı anahtarları → Z_q’da yeri.**

---

### 2.1 `ball_recoveries`

**Amaç:** Baskı/mücadele sonrası top kazanımı sıklığı ve bölge dağılımı.

**Veri:** OBE, bizim takım.

| Sütun | Rol |
|-------|-----|
| `end_type` | `direct_regain` veya `indirect_regain` → kazanım |
| `pressing_chain_end_type` | Zincir sonu `regain` ayrı sayılır |
| `third_start` | Bölge kırılımı |
| `match_id` | Maç başına ortalamalar |

**Algoritma**

1. `obe = _team_obe(...)`.
2. `n_matches = obe["match_id"].nunique()`.
3. `regains = obe[obe["end_type"].isin({"direct_regain","indirect_regain"})]`.
4. `chain_regains`: `pressing_chain_end_type == "regain"`.
5. Regain’leri `third_start` ile grupla.

**Formül**

- `regains_per_match = round(total_regains / max(n_matches,1), 2)`  
- Benzer şekilde `chain_regains_per_match`.

**Çıktı:** `total_regains`, `regains_per_match`, `chain_regains`, bölgesel sayılar, `n_matches`.

**Z_q:** Doğrudan kullanılmaz; **recovery_rate** ayrı tanımlanır (2.11 / `_get_raw_components`).

---

### 2.2 `forced_long_ball_ratio`

**Amaç:** Rakibin derin bölgeden uzun pas kullanımının, **yüksek blokta** genel eğilimine göre **artıp artmadığını** görmek (Twelve tarzı “delta”).

**Veri:** Rakip PP.

| Sütun | Rol |
|-------|-----|
| `third_start == "defensive_third"` | Sadece rakibin kendi savunma üçünden başlayan paslar |
| `end_type == "pass"` | Pas ile biten possession |
| `pass_range == "long"` | Uzun pas (SkillCorner tanımı, ~30 m) |
| `team_out_of_possession_phase_type` | `high_block` alt kümesi |

**Algoritma**

1. `opp_passes_d3` = rakip PP ∧ D3 başlangıç ∧ pas bitişi.
2. `ratio_overall = 100 * (uzun sayısı) / len(opp_passes_d3)`.
3. Aynı kümede HB filtreli alt küme için `ratio_high_block`.
4. `long_ball_ratio_delta = ratio_high_block - ratio_overall`.
5. Ek: `force_backward` bizim tüm OBE’lerde toplamı.

**Formül**

\[
\Delta_{\text{long}} = \text{HB’de D3 uzun \%} - \text{D3 tüm paslarda uzun \%}
\]

**Çıktı:** `long_ball_ratio_overall`, `long_ball_ratio_high_block`, `long_ball_ratio_delta`, sayım alanları, `forced_backward`.

**Z_q:** Evet — ham bileşen `long_ball_delta` = `long_ball_ratio_delta` (yüzde puanı olarak; skor içinde z-skoru alınır).

---

### 2.3 `forced_long_ball_strict`

**Amaç:** `is_available` olmadığı için **proxy:** D3 uzun pas anında `n_passing_options` çok düşükse “kısıtlı” kabul et; **sadece HB + düşük opsiyon** olanların, **tüm D3 uzun paslara** oranı.

**Veri:** Rakip PP.

| Sütun | Rol |
|-------|-----|
| `third_start`, `end_type`, `pass_range` | D3 uzun pas kümesi |
| `team_out_of_possession_phase_type` | `high_block` |
| `n_passing_options` | Eşik: `≤ FORCED_LONG_STRICT_MAX_PASSING_OPTIONS` (varsayılan 1); `NaN` → 999 ile doldurulup eşik dışı sayılır |

**Formül**

\[
\text{strict\_long\_hb\_lowopt\_rate} = \frac{\#\{\text{D3 uzun} \land \text{HB} \land (n_{\text{opt}}\le M)\}}{\#\{\text{D3 uzun}\}}
\]

**Çıktı:** `strict_long_hb_lowopt_rate`, `strict_long_hb_lowopt_nt` (`"pay/payda"`).

**Z_q:** Hayır (lig tablosu / ek analiz).

---

### 2.4 `progression_filter` (Block %)

**Amaç:** Rakip A1’de başlayan possession’ların ne kadarının **hâlâ A1’de bitmediği** (yani orta/ileri üçe çıktığı) yerine **A1’de kalması** — build-up’ı kilitleme.

**Veri:** Rakip PP.

**Algoritma**

- `a1_starts`: `third_start == defensive_third"`.
- `stayed_a1`: `third_end == defensive_third"`.
- `block_rate = 100 * len(stayed_a1) / len(a1_starts)`.

**Z_q:** Hayır (tabloda `block_rate` olarak durur).

---

### 2.5 `bypass_rate`

**Amaç:** Rakibin **A1’den tek possession’da A3’e** (bizim derin bölgeye) “delinmiş” çıkışı — presin tamamen aşılması.

**Veri:** Rakip PP.

**Algoritma**

- `a1_starts` = `third_start == defensive_third`.
- `bypassed` = `third_end == attacking_third"`.
- `bypass_rate = 100 * len(bypassed) / len(a1_starts)`.

**Z_q:** Evet — `bypass_rate` ham değer; **düşük daha iyi** → z’de `(μ−x)/σ`.

---

### 2.6 `ppda`

**Amaç:** Rakip kaç pas atıyor / biz kaç savunma aksiyonu (OBE) yapıyoruz — klasik PPDA okuması.

**Veri:** Rakip PP (pas biten) + bizim OBE.

**Formül (genel)**

\[
\text{PPDA} = \frac{\#\{\text{rakip PP}, \text{end\_type}=\text{pass}\}}{\#\{\text{bizim OBE}\}}
\]

HB varyantı: hem pay hem payda HB fazında.

**Z_q:** Evet — `ppda_overall`; **düşük daha iyi**.

---

### 2.7 `xthreat_disruption`

**Amaç:** Pozisyon önyargısını azaltmak için **üçü bölge bazında** rakip PO xThreat’te HB vs non-HB karşılaştırması; sonra HB satır sayısı ile ağırlıklı ortalama.

**Veri:** Rakip PO, `xthreat` null olmayan satırlar.

**Algoritma (kod ile birebir)**

Her `zone ∈ {defensive_third, middle_third, attacking_third}` için:

- \(z\) bölgesindeki HB PO’lar: `z_hb`, ortalama xThreat \(\bar{x}_{hb,z}\).
- Aynı bölgede non-HB: `z_non`, ortalama \(\bar{x}_{non,z}\).
- Bölge bozulması: \(\text{zone\_disr}_z = \left(1 - \frac{\bar{x}_{hb,z}}{\max(\bar{x}_{non,z}, \epsilon)}\right) \times 100\).
- Ağırlıklı toplam:  
  \(\text{xt\_disruption\_pct} = \frac{\sum_z \text{zone\_disr}_z \cdot |z_{hb}|}{\sum_z |z_{hb}|}\).

**Not:** Tek satırlık “global \(1 - \bar{x}_{hb}/\bar{x}_{non}\)” formülü kullanılmaz; bölge ağırlıklıdır.

**Z_q:** Evet — `xt_disruption_pct`.

---

### 2.8 `opponent_pass_completion`

**Amaç:** Rakibin pas isabeti; D3 ve D3+HB kırılımları (lig tablosunda görünür).

**Veri:** Rakip PP, `pass_outcome`, `third_start`, faz.

**Z_q:** Hayır.

---

### 2.9 `chances_after_pressing`

**Amaç:** Baskı sonrası rakibin şut/gol/tehlike ve **beaten** sinyalleri.

**Veri:** Bizim OBE.

| Metrik | Payda / kural |
|--------|----------------|
| `danger_rate` | `possession_danger` toplamı / **tüm** OBE |
| `beaten_rate` | `(beaten_by_possession + beaten_by_movement)` toplamı / **rakip yarısı OBE** (`_obe_opponent_half`) |
| `shots_after` vb. | `end_type` regain olmayan OBE’lerde `lead_to_shot` (çift sayım önlenmiş mantık veri tarafında) |

**Z_q:** `danger_rate`, `beaten_rate` kullanılır; beaten için **düşük daha iyi**.

---

### 2.10 `chances_from_recovery`

**Amaç:** Kazanım sonrası şut, gol, **xShot** (`xshot_player_possession_end` toplamı).

**Z_q:** Hayır (tabloda `shots_from_regain_pm`, `xshot_*` vb.).

---

### 2.11 `pressing_chain_analysis`

**Amaç:** Kolektif pressing zinciri sıklığı ve uzunluğu.

**Veri:** OBE; `pressing_chain == True`, `index_in_pressing_chain == 1.0` → zincir başı sayısı.

**Z_q:** Hayır.

---

### 2.12 `_get_raw_components` → etkinlik skoru ham vektörü

**Amaç:** `pressing_effectiveness_score` için **tek satırda** toplanan ham sayılar.

| Anahtar | Kaynak fonksiyon | Tanım (özet) |
|---------|------------------|--------------|
| `recovery_rate` | `_team_obe` + `_obe_opponent_half` | Rakip yarısı OBE’lerde regain / rakip yarısı OBE × 100 |
| `long_ball_delta` | `forced_long_ball_ratio` | `long_ball_ratio_delta` |
| `xt_disruption_pct` | `xthreat_disruption` | Bölge ağırlıklı disruption % |
| `bypass_rate` | `bypass_rate` | A1→A3 % |
| `beaten_rate` | `chances_after_pressing` | Rakip yarısı beaten % |
| `danger_rate` | `chances_after_pressing` | Tüm OBE danger % |
| `ppda` | `ppda` | `ppda_overall` |

**Not:** `recovery_rate` ile `ball_recoveries`’deki `regains_per_match` farklı birimdir (oran vs maç başına sayı).

---

### 2.13 `pressing_effectiveness_score` (Z_q)

**Amaç:** Twelve tarzı bileşik kalite: önce her metrikte lig (veya maç-takım) havuzunda z-skoru, sonra ağırlıklı toplam, sonra bu toplamların tekrar normalize edilmesi.

**Ağırlıklar (`_EFFECTIVENESS_METRIC_SPEC`)**

| Sıra | Ham anahtar | w | İyi yön |
|------|-------------|---|--------|
| 1 | `recovery_rate` | 0.30 | yüksek |
| 2 | `long_ball_delta` | 0.20 | yüksek |
| 3 | `xt_disruption_pct` | 0.20 | yüksek |
| 4 | `bypass_rate` | 0.10 | düşük |
| 5 | `danger_rate` | 0.10 | düşük |
| 6 | `beaten_rate` | 0.05 | düşük |
| 7 | `ppda` | 0.05 | düşük |

**Z-skoru (popülasyon std, ddof=0):**

- İyi = yüksek: \(z = (x-\mu)/\sigma\).
- İyi = düşük: \(z = (\mu-x)/\sigma\).

**Bileşik ham adım**

\[
Z_q^{\text{raw}} = \sum_m w_m z_m
\]

**Lig modu:** Havuz = her takım için bir \(Z_q^{\text{raw}}\) vektörü yerine, önce her takımın ham metrikleri → z’ler → \(Z_q^{\text{raw}}\). Referans: `_composite_z_vector(dist)` ile tüm takımların aynı metrik dizilerinden üretilen \(Z_q^{\text{raw}}\) değerleri.

\[
Z_q = \frac{Z_q^{\text{raw}} - \mu_{Z_q^{\text{raw}}}}{\sigma_{Z_q^{\text{raw}}}}
\]

(`\sigma` alt sınır `1e-9`.)

**Çıktı:** `score` = \(Z_q\), `z_composite_raw` = \(Z_q^{\text{raw}}\), `components` (ör. `recovery`, `forced_long_ball`, …), `raw` (yuvarlanmış ham değerler), `label`: Wall / Balanced / Gamble (eşik ±1).

---

### 2.14 `collective_chain_regain_opponent_half`

**Amaç:** Rakip yarısında başlayan **pressing zinciri** başına, yine rakip yarısında ölçülen **direct/indirect regain** sayısı (kollektif pres → top kazanımı verimi).

**Veri:** Bizim OBE; `pressing_chain`, `index_in_pressing_chain`, `pressing_chain_index`, `match_id`, `third_start`, `end_type`.

**Algoritma:** Rakip yarısı zincir başlarını `(match_id, pressing_chain_index)` ile seç; aynı zincirlere ait tüm OBE satırlarını birleştir; bunların rakip yarısındaki regain satırlarını say. Oran = regain sayısı / zincir başı sayısı.

**Z_q:** Hayır.

---

### 2.15 `player_pressing_stats`

**Amaç:** Oyuncu bazında OBE özetleri (subtype sayıları, regain, beaten, xShot toplamı).

**Veri:** Bizim OBE, `groupby player_name, player_position`.

**Z_q:** Hayır.

---

## 3. Lig tablosu (`league_pressing_table`) — sütunların kökeni

| Sütun (ör.) | Ana kaynak |
|-------------|------------|
| `effectiveness_score`, `z_q_raw`, `z_*` | `pressing_effectiveness_score` |
| `recovery_rate`, ham `raw` | `_get_raw_components` / `raw` |
| `forced_long_pct`, `forced_long_delta` | `forced_long_ball_ratio` |
| `strict_long_hb_lowopt_*` | `forced_long_ball_strict` |
| `block_rate` | `progression_filter` |
| `bypass_rate`, `ppda`, `xt_disruption_pct` | ilgili fonksiyonlar |
| `beaten_rate`, `danger_rate` | `chances_after_pressing` |
| `chains_per_match`, `avg_chain_length` | `pressing_chain_analysis` |
| `chain_regain_per_oh_chain`, `chain_regain_per_oh_chain_nt` | `collective_chain_regain_opponent_half` |
| `regains_per_match` | `ball_recoveries` |

---

## 4. Sınırlamalar ve yorum notları

1. **`is_available` / PO mesafesi:** Ham parquet’te yok; “strict long” `n_passing_options` eşiği ile proxy’lenir.  
2. **Beaten %:** Payda geniş (rakip yarısı tüm OBE); oranlar sıkışık çıkabilir; SkillCorner beaten tanımı dar olabilir.  
3. **xThreat disruption:** Dokümantasyondaki eski “tek oran” anlatımı yerine **bölge ağırlıklı** formül geçerlidir (bu spesifikasyon 2.7).  
4. **Bypass vs beaten:** Bypass = PP hattında A1→A3; beaten = OBE’de model bayrakları — aynı olay değil.  
5. **Şema sürümü:** Önbellek dosyaları `_CACHE_SCHEMA` değişince yeniden üretilir (`pressing_app.py`).

---

## 5. PDF üretimi

Örnek (Pandoc yüklüyse):

```bash
pandoc PRESSING_METRICS_SPECIFICATION.md -o PRESSING_METRICS_SPECIFICATION.pdf --pdf-engine=xelatex -V geometry:margin=1in
```

Veya VS Code / Cursor “Markdown PDF” eklentisi ile bu dosyadan dışa aktarım.

---

*Belge, `pressing_metrics.py` ile senkron tutulmalıdır; mantık değişikliklerinde bu dosya güncellenir.*
