# Pressing Analyst - Metrik Dokumantasyonu

**Teknik spesifikasyon (formül, veri sözleşmesi, Z_q eşlemesi, PDF için):**  
[`PRESSING_METRICS_SPECIFICATION.md`](PRESSING_METRICS_SPECIFICATION.md)

## Genel Bakis

Bu dokuman, Pressing Analyst uygulamasinda kullanilan her bir metrigin nasil hesaplandigi, hangi SkillCorner Dynamic Events sutunlarini kullandigi ve ne anlama geldigi hakkinda detayli bilgi verir.

### Özet tablo (Link To Data — slayt eşlemesi)

Lig ekranındaki özet skor tablosu; **Twelve** slaytındaki tanım–veri eşlemesine göre: PPDA(HB), Block %, Opp Pass%(D3,HB), Force long ball, xT disruption, Bypass (ters), Danger (ters), Beaten (ters), Regains/Match. **z_q_raw** = ağırlıklı z toplamı; **score** = lig içinde normalize.

### Terminoloji

| Terim | Aciklama |
|-------|----------|
| **Bizim takim** | Pressing yapan takim (savunmada olan, analiz edilen takim) |
| **Rakip** | Topa sahip olan, baski altindaki takim |
| **A1** | Rakibin savunma ucuncusu (bizim hucum ucuncumuz). Pressing burada baslar |
| **A2** | Orta ucuncu. Rakip buraya ulasirsa press asilmis olabilir |
| **A3** | Rakibin hucum ucuncusu (bizim savunma ucuncumuz). Buraya ulasirsa press delinmistir |
| **High Block** | Bizim takimin yuksek pressing yaptigi faz. SkillCorner'da `team_out_of_possession_phase_type == "high_block"` |
| **OBE** | On-Ball Engagement - savunma oyuncusunun top sahibine baskisi |
| **PP** | Player Possession - bir oyuncunun top kontrolu suresi |
| **PO** | Passing Option - pas icin potansiyel hedef |

### Saha Koordinat Sistemi

SkillCorner'da koordinatlar metreyle ifade edilir ve sahanin merkezi (0,0) noktasidir. Topa sahip takim her zaman **soldan saga** atak yapar. Bu nedenle:

- `x < -17.5` = Savunma ucuncusu (defensive_third)
- `-17.5 < x < 17.5` = Orta ucuncu (middle_third) 
- `x > 17.5` = Hucum ucuncusu (attacking_third)

### Veri Akisi

```
378 Parquet Dosyasi (mac basina ~4800 olay)
        |
        v
_pressing_cache.parquet (1,811,078 olay, 143 sutun)
        |
        v
pressing_metrics.py (11 metrik fonksiyonu)
        |
        v
pressing_app.py (Streamlit Dashboard)
```

---

## Metrik 1: Ball Recoveries (Top Kazanimi)

### Futbol Sorusu
> "Top kazaniyor muyuz?"

### Ne Olcer
Pressing aksiyonlari sonucunda topu ne siklikta ve sahanin neresinde kazandigimizi olcer.

### Kullanilan SkillCorner Sutunlari

| Sutun | Tablo | Aciklama |
|-------|-------|----------|
| `event_type` | Tumu | `"on_ball_engagement"` ile filtrelenir |
| `team_shortname` | OBE | Bizim takimi secmek icin |
| `end_type` | OBE | `"direct_regain"` veya `"indirect_regain"` = top kazanildi |
| `pressing_chain_end_type` | OBE | `"regain"` = pressing zinciri sonucu top kazanildi |
| `third_start` | OBE | Bolgeli analiz: `attacking_third` / `middle_third` / `defensive_third` |
| `match_id` | OBE | Mac bazli ve sezon bazli hesaplama icin |

### Hesaplama Adimi Adim

```
1. Tum OBE (On-Ball Engagement) olaylarini al
2. Sadece bizim takimin OBE'lerini filtrele (team_shortname == team)
3. end_type == "direct_regain" VEYA "indirect_regain" olanlari say → total_regains
4. pressing_chain_end_type == "regain" olanlari say → chain_regains
5. Regain'leri third_start'a gore grupla → bolge bazli dagilim
6. total_regains / mac_sayisi = regains_per_match
```

### Formul

```
regains_per_match = total_regains / n_matches
chain_regains_per_match = chain_regains / n_matches
```

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `total_regains` | Toplam top kazanma sayisi |
| `regains_per_match` | Mac basina ortalama top kazanma |
| `chain_regains` | Pressing zinciri sonucu kazanilanlar |
| `regains_attacking_third` | Rakibin savunma ucuncusunda kazanilanlar |
| `regains_middle_third` | Orta sahada kazanilanlar |
| `regains_defensive_third` | Kendi ucuncumuzda kazanilanlar |

### Yorum
- `regains_attacking_third` yuksekse, takim yuksek pressing ile topu rakibin yarisinda kazaniyor
- `chain_regains` yuksekse, pressing **kolektif** olarak calisiyor (bireysel degil)

---

## Metrik 2: Forced Long-Ball Ratio (Zorlatilan Uzun Pas Orani)

### Futbol Sorusu
> "Uzun pas zorlattiyor muyuz?"

### Ne Olcer
Pressing baski altindayken rakibin kendi savunma ucuncusundan ne kadar fazla uzun pas (>30m) attigini olcer. Pressingin rakibin build-up'ini bozup bozmadigini gosterir.

### Kullanilan SkillCorner Sutunlari

| Sutun | Tablo | Aciklama |
|-------|-------|----------|
| `event_type` | PP | `"player_possession"` ile filtrelenir |
| `team_shortname` | PP | Rakip takimin (bizim olmayan) PP'leri secilir |
| `third_start` | PP | `"defensive_third"` = rakibin kendi savunma ucuncusundan basliyor |
| `end_type` | PP | `"pass"` = possession pas ile bitti |
| `pass_range` | PP | `"long"` = 30m ustu pas |
| `team_out_of_possession_phase_type` | PP | `"high_block"` = biz pressing yapiyoruz |
| `force_backward` | OBE | Savunmacinin geri pas zorlatip zorlatmadigi |

### Hesaplama Adimi Adim

```
0. PP'ler sadece analiz edilen takimin oynadigi maclara sinirlanir (match_id)
1. Rakip takimin PP'lerini al (team_shortname != team)
2. Sadece savunma ucuncusundan baslayip pas ile biten PP'leri filtrele
   → third_start == "defensive_third" AND end_type == "pass"
3. GENEL ORAN: pass_range == "long" olanlari say / toplam pas
4. HIGH BLOCK ORANI: Ayni filtre + team_out_of_possession_phase_type == "high_block"
   → high_block sirasindaki uzun pas / high_block sirasindaki toplam pas
5. DELTA: high_block_orani - genel_oran
6. OBE'lerden force_backward sayisini al
```

### Formul

```
long_ball_ratio_overall = (D3'teki uzun paslar / D3'teki tum paslar) * 100
long_ball_ratio_high_block = (HB sirasinda D3'teki uzun paslar / HB sirasinda D3'teki tum paslar) * 100
long_ball_ratio_delta = long_ball_ratio_high_block - long_ball_ratio_overall
```

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `long_ball_ratio_overall` | Rakibin D3'ten genel uzun pas orani (%) |
| `long_ball_ratio_high_block` | High block sirasinda uzun pas orani (%) |
| `long_ball_ratio_delta` | Fark (pozitif = pressing uzun pasi artirmis) |
| `forced_backward` | OBE'lerden geri pas zorlatma sayisi |

### Strict uzun pas (opsiyon proxy; lig tablosu — tek oran)

Ham veride PO bazli `is_available` yok; `n_passing_options` ≤ **M** (`FORCED_LONG_STRICT_MAX_PASSING_OPTIONS`, varsayilan M=1) **düşük opsiyon** proxy’si.

**Pay:** Rakibin D3'ten attigi uzun pas (`third_start == defensive_third`, `end_type == pass`, `pass_range == long`) satirlarindan hem `team_out_of_possession_phase_type == high_block` hem `n_passing_options` ≤ M olanlar.

**Payda:** Rakibin D3'ten attigi **tum** uzun pas sayisi (faz fark etmeksizin).

```
strict_long_hb_lowopt_rate = (HB ∧ dusuk-opt ∧ D3 uzun) / (rakibin tum D3 uzun paslari)
```

Lig tablosu sutunu: `strict_long_hb_lowopt_rate` (0–1). Ham sayim `strict_long_hb_lowopt_nt` = "pay/payda" (CSV’de opsiyonel sutun olarak kalabilir; UI’da yalnizca oran gosterilebilir).

### Yorum
- `delta > 0` ise pressing rakibi uzun pas atmaya zorluyor (iyi)
- `delta < 0` ise rakip pressing altinda daha kisa pas atiyor (pressing kisa pasa yonlendiriyor olabilir)
- `forced_backward` yuksekse savunmaci baski ile geri pas zorlatmis

---

## Metrik 3: Progression Filter (A1→A2 Gecis Engelleme)

### Futbol Sorusu
> "Rakibin build-up'ina engel olabiliyor muyuz?"

### Ne Olcer
Rakip takimin kendi savunma ucuncusundan (A1) orta ucuncuya (A2) gecisini ne oranda engelledigimizi olcer. Pressingin "duvar" etkisi.

### Kullanilan SkillCorner Sutunlari

| Sutun | Tablo | Aciklama |
|-------|-------|----------|
| `event_type` | PP | `"player_possession"` |
| `team_shortname` | PP | Rakip takimin PP'leri |
| `third_start` | PP | `"defensive_third"` = A1'de baslayan possession'lar |
| `third_end` | PP | Possession'in bittigi bolge |
| `team_possession_loss_in_phase` | PP | O fazda top kaybi olup olmadigi |

### Hesaplama Adimi Adim

```
1. Rakibin savunma ucuncusunda baslayan tum PP'leri al
   → third_start == "defensive_third"
2. Bunlardan third_end == "defensive_third" olanlari say → stayed_in_a1
3. third_end == "middle_third" veya "attacking_third" olanlari say → progressed_to_a2
4. block_rate = stayed_in_a1 / total_a1 * 100
5. team_possession_loss_in_phase == True olanlari say → possession_lost_in_phase
```

### Formul

```
block_rate = (A1'de kalan PP sayisi / A1'de baslayan toplam PP sayisi) * 100
```

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `total_a1_possessions` | A1'de baslayan toplam possession sayisi |
| `stayed_in_a1` | A1'de kalan (ilerlemeyen) possession sayisi |
| `progressed_to_a2` | A2'ye ilerleyen possession sayisi |
| `block_rate` | Engelleme orani (%) |
| `possession_lost_in_phase` | O fazda top kaybedilen possession sayisi |

### Yorum
- `block_rate` yuksekse (%80+) pressing cok etkili, rakip cikamiyor
- `block_rate` dusukse pressing kolayca asilabiliyor

---

## Metrik 4: Bypass Rate (A1→A3 Gecis Orani)

### Futbol Sorusu
> "Pressing delinerek rakip direkt son ucuncumuza geliyor mu?"

### Ne Olcer
Rakibin kendi savunma ucuncusundan (A1) direkt olarak bizim savunma ucuncumuza (A3) ulasma oranini olcer. Bu, pressingin tamamen delindigini gosterir.

### Kullanilan SkillCorner Sutunlari

| Sutun | Tablo | Aciklama |
|-------|-------|----------|
| `event_type` | PP | `"player_possession"` |
| `team_shortname` | PP | Rakip takim |
| `third_start` | PP | `"defensive_third"` = A1 |
| `third_end` | PP | `"attacking_third"` = A3 (bizim savunma ucuncumuz) |

### Hesaplama Adimi Adim

```
1. Rakibin A1'de baslayan tum PP'lerini al
2. Bunlardan third_end == "attacking_third" olanlari say → bypassed_to_a3
3. bypass_rate = bypassed_to_a3 / total_a1 * 100
```

### Formul

```
bypass_rate = (A1'den A3'e gecen PP sayisi / A1'de baslayan toplam PP sayisi) * 100
```

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `total_a1_possessions` | A1'de baslayan toplam possession sayisi |
| `bypassed_to_a3` | Direkt A3'e gecen possession sayisi |
| `bypass_rate` | Bypass orani (%) |

### Yorum
- `bypass_rate` dusukse (<1%) pressing saglam, rakip direkt gecemiyor
- `bypass_rate` yuksekse pressing delik, uzun toplarla veya hizli gecislerle asilabiliyor

---

## Metrik 5: PPDA (Passes Per Defensive Action)

### Futbol Sorusu
> "Ne kadar yogun pressing yapiyoruz?"

### Ne Olcer
Rakibin kac pas atmasina karsilik bizim bir savunma aksiyonu yaptigimizi olcer. Pressing yogunlugunun standart olcusu.

### Kullanilan SkillCorner Sutunlari

| Sutun | Tablo | Aciklama |
|-------|-------|----------|
| `event_type` | PP/OBE | `"player_possession"` (rakip) ve `"on_ball_engagement"` (biz) |
| `team_shortname` | PP/OBE | Rakip PP'ler ve bizim OBE'ler |
| `end_type` | PP | `"pass"` = pas ile biten possession'lar |
| `team_out_of_possession_phase_type` | PP/OBE | `"high_block"` filtresi |

### Hesaplama Adimi Adim

```
1. Rakibin pas ile biten tum PP'lerini say → opponent_passes
2. Bizim tum OBE'lerimizi say → defensive_actions
3. ppda_overall = opponent_passes / defensive_actions
4. High block icin ayri hesapla:
   - Rakip paslari (HB sirasinda) / Bizim OBE'lerimiz (HB sirasinda)
```

### Formul

```
ppda_overall = Rakip pas sayisi / Bizim OBE sayimiz
ppda_high_block = HB sirasinda rakip pas / HB sirasinda bizim OBE
```

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `ppda_overall` | Genel PPDA degeri |
| `ppda_high_block` | High block sirasinda PPDA |
| `opponent_passes` | Rakibin toplam pas sayisi |
| `defensive_actions` | Bizim toplam OBE sayimiz |

### Yorum
- PPDA **dusukse** pressing yogun (ornek: 8-10 = cok yogun, 15+ = dusuk yogunluk)
- `ppda_high_block < ppda_overall` ise high block'ta daha yogun pressing yapiliyor

---

## Metrik 6: xThreat Disruption (Tehdit Dusurme)

### Futbol Sorusu
> "Rakibin tehdit degerlerini dusurme kapasitemiz ne?"

### Ne Olcer
Pressing sirasinda (high block) rakibin pas opsiyonlarinin xThreat degerlerinin ne kadar dustugunu olcer. Pressingin tehlikeli pas yollarini kapatip kapatmadigini gosterir.

### Kullanilan SkillCorner Sutunlari

| Sutun | Tablo | Aciklama |
|-------|-------|----------|
| `event_type` | PO | `"passing_option"` |
| `team_shortname` | PO | Rakip takimin pas opsiyonlari |
| `xthreat` | PO | Pas tamamlanirsa 10 sn icinde gol olma olasiligi |
| `team_out_of_possession_phase_type` | PO | `"high_block"` vs diger fazlar |

### SkillCorner xThreat Aciklamasi
`xthreat`, bir oyuncuya pas tamamlanirsa 10 saniye icinde gol olma olasiligini olcer. Deger ne kadar yuksekse, o pas opsiyonu o kadar tehlikelidir.

### Hesaplama Adimi Adim

```
1. Rakibin tum PO (passing option) olaylarini al
2. xthreat degeri olan (null olmayan) satirlari filtrele
3. HIGH BLOCK sirasindaki ortalama xthreat → xt_high_block
4. Diger fazlardaki ortalama xthreat → xt_non_high_block
5. disruption_pct = (1 - xt_high_block / xt_non_high_block) * 100
```

### Formul

```
xt_disruption_pct = (1 - xt_high_block / xt_non_high_block) * 100
```

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `xt_overall` | Rakibin genel ortalama xThreat'i |
| `xt_high_block` | High block sirasinda ortalama xThreat |
| `xt_non_high_block` | Diger fazlarda ortalama xThreat |
| `xt_disruption_pct` | xThreat dusurme yuzdesi |

### Yorum
- `xt_disruption_pct` yuksekse (%80+) pressing tehlikeli pas yollarini cok etkili kapatiyor
- Bu deger kismen dogal olarak yuksek cikabilir cunku high block genelde rakibin kendi yarisindayken olur ve orada xThreat zaten dusuktur

---

## Metrik 7: Opponent Pass Completion (Rakip Pas Basari Orani)

### Futbol Sorusu
> "Rakibin pas basari oranini dusurebiliyor muyuz?"

### Ne Olcer
Pressing altindayken rakibin pas basari oraninin ne kadar dustugunu olcer. Ozellikle rakibin kendi savunma ucuncusundaki (D3) pas basarisina odaklanir.

### Kullanilan SkillCorner Sutunlari

| Sutun | Tablo | Aciklama |
|-------|-------|----------|
| `event_type` | PP | `"player_possession"` |
| `team_shortname` | PP | Rakip takim |
| `end_type` | PP | `"pass"` |
| `pass_outcome` | PP | `"successful"` veya `"unsuccessful"` |
| `third_start` | PP | `"defensive_third"` filtresi |
| `team_out_of_possession_phase_type` | PP | `"high_block"` filtresi |

### Hesaplama Adimi Adim

```
1. Rakibin pas ile biten tum PP'lerini al
2. GENEL: basarili pas / toplam pas * 100 → pass_pct_overall
3. D3 GENEL: D3'ten baslayan basarili pas / D3'ten baslayan toplam pas → pass_pct_d3
4. D3 HIGH BLOCK: D3 + high_block sirasindaki basarili / toplam → pass_pct_d3_high_block
```

### Formul

```
pass_pct_d3 = (D3'teki basarili paslar / D3'teki toplam paslar) * 100
pass_pct_d3_high_block = (D3 + HB'deki basarili paslar / D3 + HB'deki toplam paslar) * 100
```

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `pass_pct_overall` | Rakibin genel pas basari orani |
| `pass_pct_d3` | D3'teki pas basari orani |
| `pass_pct_d3_high_block` | D3'te high block sirasindaki pas basari orani |

### Yorum
- `pass_pct_d3_high_block < pass_pct_d3` ise pressing rakibin D3'teki paslarini bozuyor
- Bu fark ne kadar buyukse pressing o kadar etkili

---

## Metrik 8: Chances After Pressing (Pressing Sonrasi Rakip Sans Yaratma)

### Futbol Sorusu
> "Rakip, pressing fazimizdan sonra sans yaratabiliyor mu?"

### Ne Olcer
Pressingin ne kadar risk tasidigini olcer. Press kirildiginda rakibin sut, gol veya tehlikeli pozisyon yaratip yaratmadigini gosterir.

### Kullanilan SkillCorner Sutunlari

| Sutun | Tablo | Aciklama |
|-------|-------|----------|
| `event_type` | OBE | `"on_ball_engagement"` |
| `team_shortname` | OBE | Bizim takim |
| `lead_to_shot` | OBE | 10 sn icinde sut oldu mu? (True/False) |
| `lead_to_goal` | OBE | 10 sn icinde gol oldu mu? (True/False) |
| `third_start` | OBE | Rakip yarisi filtresi: `middle_third` / `attacking_third` (beaten icin) |
| `beaten_by_possession` | OBE | Savunmaci top sahibi tarafindan gecildi mi? |
| `beaten_by_movement` | OBE | Savunmaci hareket ile gecildi mi? (pas almadan once) |
| `possession_danger` | OBE | Rakibin EPV'si %3'un uzerine cikti mi? |

### SkillCorner Sutun Detaylari

- **`lead_to_shot`**: Olaydan sonraki 10 saniye icinde herhangi bir sut olup olmadigini gosterir
- **`beaten_by_possession`**: Savunmacinin top sahibi tarafindan gecilmesi. Rakibin gol olasiliklarinin belirgin sekilde artmasi ve savunmacinin bunu engelleyememesi
- **`beaten_by_movement`**: Son pas ile resepsiyon arasinda savunmacinin gecilmesi. Savunmaci kontrol pozisyonundaydi ama top alicisini engelleyemedi
- **`possession_danger`**: Engagement sirasinda rakibin EPV (Expected Possession Value) degerinin en az bir frame'de %3'un uzerine cikmasi

### Hesaplama Adimi Adim

```
1. Bizim takimin tum OBE'lerini al
2. lead_to_shot == True olanlari say → shots_after (tum OBE)
3. lead_to_goal == True olanlari say → goals_after
4. Rakip yarisi: third_start in {middle_third, attacking_third} olan OBE alt kumesi → obe_oh
5. obe_oh uzerinde beaten_by_possession / beaten_by_movement toplamlari → beaten_pos, beaten_mov
6. possession_danger == True olanlari say → poss_danger (tum OBE)
7. danger_rate = poss_danger / total_obe * 100
8. beaten_rate = (beaten_pos + beaten_mov) / len(obe_oh) * 100
```

### Formul

```
danger_rate = (possession_danger True sayisi / toplam OBE) * 100
beaten_rate = ((beaten_by_possession + beaten_by_movement) / rakip yarisi OBE sayisi) * 100
```

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `shots_after_pressing` | Pressing sonrasi 10 sn icindeki sut sayisi |
| `goals_after_pressing` | Pressing sonrasi 10 sn icindeki gol sayisi |
| `beaten_by_possession` | Rakip yarisi OBE'lerde top ile gecilme sayisi |
| `beaten_by_movement` | Rakip yarisi OBE'lerde hareket ile gecilme sayisi |
| `danger_rate` | Tehlike orani (%) |
| `beaten_rate` | Rakip yarisi OBE'lerde gecilme orani (%) |
| `opp_half_engagements` | Rakip yarisi OBE sayisi (payda) |

### Yorum
- `danger_rate` yuksekse pressing cok riskli (kumar)
- `beaten_rate` yuksekse (ozellikle rakip yarisinda) pressing kolayca kiriliyor
- `shots_per_match` yuksekse pressing sonrasi cok fazla sut yeniliyor

---

## Metrik 9: Chances From Recovery (Top Kazanimi Sonrasi Sans Yaratma)

### Futbol Sorusu
> "Top kazandiktan sonra sans yaratabiliyor muyuz?"

### Ne Olcer
Pressing ile top kazandiktan sonra sut ve gol uretme kapasitesini olcer. Pressingin sadece savunma degil, hucum acisindan da degerini gosterir.

### Kullanilan SkillCorner Sutunlari

| Sutun | Tablo | Aciklama |
|-------|-------|----------|
| `event_type` | OBE | `"on_ball_engagement"` |
| `team_shortname` | OBE | Bizim takim |
| `end_type` | OBE | `"direct_regain"` / `"indirect_regain"` |
| `lead_to_shot` | OBE | 10 sn icinde sut oldu mu? |
| `lead_to_goal` | OBE | 10 sn icinde gol oldu mu? |
| `pressing_chain_end_type` | OBE | `"regain"` = zincir ile kazanim |
| `xshot_player_possession_end` | OBE | Kazanim satirinda: sonraki possession icin SkillCorner **xShot** (xG-benzeri) |

Veri setinde ayri bir `xg` sutunu yok; beklenen gol benzeri cikti icin bu xShot alani kullanilir.

### Hesaplama Adimi Adim

```
1. Bizim OBE'lerden end_type == "direct_regain" veya "indirect_regain" olanlari filtrele → regains
2. Regain'lerden lead_to_shot == True olanlari say → shots_from_regain
3. Regain'lerden lead_to_goal == True olanlari say → goals_from_regain
4. Pressing zinciri kazanimlarindan sut olanlari say → chain_regain_shots
5. shot_conversion_rate = shots_from_regain / total_regains * 100
6. Her regain satirinda xshot_player_possession_end toplami → sezon xShot; mac sayisina bol → xShot/Regain/M; regain sayisina bol → xShot/Regain
7. Sadece lead_to_shot == True regain satirlarinda xShot toplami → sutla biten kazanimlardaki xShot
```

### Formul

```
shot_conversion_rate = (kazanimdan sonra sut / toplam kazanim) * 100
```

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `total_regains` | Toplam top kazanma |
| `shots_from_regain` | Kazanimdan sonra sut sayisi |
| `goals_from_regain` | Kazanimdan sonra gol sayisi |
| `shot_conversion_rate` | Kazanimdan suta donusum orani (%) |
| `chain_regain_shots` | Zincir kazanimlarindan sut sayisi |
| `xshot_after_regain_total` | Tum regain'lerde xShot toplami (xG-benzeri) |
| `xshot_after_regain_per_match` | Mac basina xShot (regain sonrasi) |
| `xshot_after_regain_per_regain` | Kazanim basina ortalama xShot |
| `xshot_on_shot_regains` | Sutla eslesen regain satirlarinda xShot toplami |

### Yorum
- `shot_conversion_rate` yuksekse pressing sadece savunma degil, gecis oyununda da etkili
- `chain_regain_shots` yuksekse kolektif pressing direkt hucum firsati yaratiyor
- `xshot_after_regain_*` sut sayisindan farkli bilgi verir: her kazanimdan sonra gelisen possession'in kalitesini (xG-benzeri) toplar

---

## Metrik 10: Pressing Chain Analysis (Pressing Zinciri Analizi)

### Futbol Sorusu
> "Pressing aksiyonlarimiz kolektif ve koordineli mi?"

### Ne Olcer
Pressing zincirlerinin sikligini, uzunlugunu ve sonuclarini olcer. Zincir, 4 saniye icinde arka arkaya ayni takimdan 2+ OBE olmasidir.

### SkillCorner Pressing Zinciri Tanimi
Bir pressing zinciri, 4 saniye icinde gerceklesen en az 2 player possession'in pressing veya recovery press almasi durumudur. Zincir sadece build_up, direct veya create fazlarinda olusan pressing ve recovery press olaylarini icerir.

### Kullanilan SkillCorner Sutunlari

| Sutun | Tablo | Aciklama |
|-------|-------|----------|
| `pressing_chain` | OBE | True = bu OBE bir zincirin parcasi |
| `pressing_chain_length` | OBE | Zincirdeki toplam OBE sayisi |
| `pressing_chain_end_type` | OBE | `"regain"` / `"disruption"` / None |
| `pressing_chain_index` | OBE | Zincirin mac icindeki sirasi |
| `index_in_pressing_chain` | OBE | Bu OBE'nin zincir icindeki sirasi (1, 2, 3...) |
| `event_subtype` | OBE | `pressing` / `pressure` / `counter_press` / `recovery_press` / `other` |

### Hesaplama Adimi Adim

```
1. pressing_chain == True olan OBE'leri filtrele → chains
2. index_in_pressing_chain == 1.0 olan satirlari say → total_chains (benzersiz zincir sayisi)
3. pressing_chain_length ortalamasini al → avg_chain_length
4. pressing_chain_end_type dagilimini al → regain / disruption / None
5. Zincir icindeki event_subtype dagilimini al
```

### Formul

```
chains_per_match = toplam benzersiz zincir / mac sayisi
avg_chain_length = zincir uzunluklarinin ortalamasi
```

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `total_chains` | Toplam benzersiz pressing zinciri sayisi |
| `chains_per_match` | Mac basina zincir sayisi |
| `avg_chain_length` | Ortalama zincir uzunlugu |
| `max_chain_length` | En uzun zincir |
| `chain_end_regain` | Top kazanimiyla biten zincirler |
| `chain_end_disruption` | Bozulmayla biten zincirler |
| `subtypes_in_chains` | Zincir icindeki OBE tipleri dagilimisubtype |

### Rakip yarisinda kolektif pres basina top kazanimi (`collective_chain_regain_opponent_half`)

**Amaç:** Sadece **pressing zinciri** (kollektif pres) icinde, **rakip yarisinda** gerceklesen **direct/indirect regain** sayisini, **rakip yarisinda baslayan** zincir basina bolmek.

**Payda:** `third_start` ∈ {middle_third, attacking_third} ve `index_in_pressing_chain == 1` olan satirlardan benzersiz `(match_id, pressing_chain_index)` zincir sayisi.

**Pay:** Bu zincirlere ait tum OBE satirlari (mac icinde) ile eslesen, sonra yine rakip yarisinda filtrelenen `end_type` ∈ {direct_regain, indirect_regain} satirlari.

```
chain_regain_per_oh_chain = collective_regains_opp_half / chain_starts_opp_half
```

Lig tablosu: `chain_regain_per_oh_chain` (ondalik), `chain_regain_per_oh_chain_nt` (pay/payda metni). **Z_q’da kullanilmaz.**

### Yorum
- `chains_per_match` yuksekse takim kolektif pressing yapiyor
- `avg_chain_length` yuksekse (4+) pressing uzun sureli ve organize
- `chain_end_regain / total_chains` orani zincirin ne kadar etkili oldugunu gosterir
- `chain_regain_per_oh_chain` yuksekse, rakip yarisinda baslayan kolektif press zincirleri basina daha cok top kazanimi (OH icinde) gerceklesiyor

---

## Metrik 11: Pressing Effectiveness Score (Pressing Etkinlik Skoru)

### Futbol Sorusu
> "Pressingimiz ilerleyisi durduran bir duvar mi, yoksa bizi acik birakan bir kumar mi?"

### Ne Olcer
Twelve “Calculating qualities” ile ayni: (1) metrik z’leri, (2) **Z_q_raw = Σ w·z**, (3) **Z_q = (Z_q_raw − μ_Z) / σ_Z**. **Nihai kalite skoru yalnizca Z_q** (havuzda ort ~0, std ~1). Tabloda **effectiveness_score** = **Z_q**; **z_q_raw** = **Z_q_raw**. UI etiketleri: Wall Z_q≥1, Gamble Z_q≤−1, arada Balanced (Twelve slaytinda yok; gorsel icin).

### Rakip verisi (PP / PO) — onemli

Rakip `player_possession` ve `passing_option` satirlari **sadece analiz edilen takimin oynadigi maclar** ile sinirlanir (`match_id` filtresi). Aksi halde ligdeki diger maclarin verisi "rakip" sanilarak tum takimlarin metrikleri birbirine yaklasirdi.

### Bilesenler

| Bilesen | Agirlik | Ham Deger Kaynagi | Z (havuz μ, σ; populasyon std ddof=0) |
|---------|---------|-------------------|----------------------------------------|
| **Recovery** | 0.30 | Rakip yarisi OBE: regain / opp_half_obe * 100 (`third_start` middle + attacking) | (x−μ)/σ |
| **Forced Long Ball** | 0.20 | long_ball_delta (Metrik 2) | (x−μ)/σ |
| **xT Disruption** | 0.20 | xt_disruption_pct (Metrik 6) | (x−μ)/σ |
| **Bypass** | 0.10 | bypass_rate (Metrik 4) | (μ−x)/σ |
| **Danger** | 0.10 | danger_rate (Metrik 8) | (μ−x)/σ |
| **Beaten** | 0.05 | beaten_rate (Metrik 8, rakip yarisi) | (μ−x)/σ |
| **PPDA** | 0.05 | ppda_overall (Metrik 5) | (μ−x)/σ |

*Not:* Bileske skorda **block_rate** (Metrik 3) artik yok; lig tablosunda ayri sutun olarak duruyor.

**Lig:** Once her takim icin Z_q_raw, sonra Z_q = (Z_q_raw − ortalama(Z_q_raw)) / std(Z_q_raw) ( populasyon std, ddof=0).

**Mac:** Ayni mantik ~756 (mac, takim) ornegi uzerinde.

### Hesaplama Adimi Adim

```
1. Yedi ham metrik vektoru (lig veya mac-takim ornekleri)
2. Her metrik icin z (μ, σ havuzdan; ddof=0)
3. Z_q_raw = agirlikli z toplami (ayni w'ler)
4. μ_Z = mean(Z_q_raw tum birimler), σ_Z = std(Z_q_raw); σ_Z < epsilon ise epsilon
5. Z_q = (Z_q_raw - μ_Z) / σ_Z
```

### Formul

```
Z_q_raw = Σ_m w_m * z_m
Z_q = (Z_q_raw - μ_Z) / σ_Z
```

`score` (API) = `Z_q` (yuvarlanmis).

### Etiketleme (yalniz UI; Twelve slaytinda tanimli degil)

| Kosul | Etiket |
|-------|--------|
| Z_q ≥ 1 | **Wall** |
| −1 < Z_q < 1 | **Balanced** |
| Z_q ≤ −1 | **Gamble** |

### Cikti Degerleri

| Deger | Aciklama |
|-------|----------|
| `score` | Z_q (Twelve nihai kalite) |
| `z_composite_raw` | Z_q_raw |
| `z_composite` | Z_q (score ile ayni) |
| `label` | Wall / Balanced / Gamble (yukaridaki bantlar) |
| `components` | Metrik basina z |
| `raw` | Ham metrikler |

### Lig tablosu ek sutunlar

| Sutun | Aciklama |
|-------|----------|
| `effectiveness_score` | Z_q |
| `z_q_raw` | Z_q_raw |

### Yorum
- Siralama **Z_q**’ya gore (yuksek = daha iyi)
- Radar: metrik z’leri (adim 1); bilesik ozet **Z_q** (adim 3)

---

## Ek Fonksiyonlar

### league_pressing_table(df)
Tum 20 takim icin yukaridaki 11 metrigin hepsini hesaplayip tek bir DataFrame'de birlestirir. `effectiveness_score`'a gore siralar.

### player_pressing_stats(df, team)
Belirli bir takimin her oyuncusu icin asagidaki OBE bazli istatistikleri hesaplar:

| Istatistik | Aciklama |
|-----------|----------|
| `total_engagements` | Toplam OBE sayisi |
| `pressing_count` | "pressing" (zincir icindeki) OBE sayisi |
| `pressure_count` | "pressure" (bireysel) OBE sayisi |
| `counter_press_count` | "counter_press" OBE sayisi |
| `recovery_press_count` | "recovery_press" OBE sayisi |
| `regains` | Top kazanma sayisi |
| `regain_rate` | Top kazanma orani (%) |
| `force_backward` | Geri pas zorlatma sayisi |
| `beaten_by_possession` | Rakip yarisi OBE'lerde top ile gecilme |
| `beaten_by_movement` | Rakip yarisi OBE'lerde hareket ile gecilme |
| `opp_half_engagements` | Rakip yarisi OBE sayisi |
| `beaten_rate` | Rakip yarisi gecilme orani (%) |
| `in_chain` | Pressing zincirlerine katilim sayisi |
| `avg_speed` | Ortalama hiz (km/h) |
| `avg_distance` | Ortalama mesafe (m) |

---

## SkillCorner OBE Tipleri Referansi

| Tip | Aciklama |
|-----|----------|
| **pressing** | Pressing zinciri icinde yapilan baski. Takim arkadasi da baski yapiyorsa kolektif pressing |
| **pressure** | Bireysel baski. Zincir disinda, tek basina yapilan baski |
| **counter_press** | Top kaybindan sonra 3 sn icinde yapilan baski (gegenpressing) |
| **recovery_press** | Savunmacinin geriye dogru kosurak baski yapmasi |
| **other** | Jokeyleme, contested duel, veya pasif pozisyon kontrolu |

## SkillCorner Faz Referansi (Top Olmayan Takim)

| Faz | Aciklama |
|-----|----------|
| **high_block** | Yuksek pressing. Rakip kendi yarisinda, baski altinda |
| **medium_block** | Orta blok. Varsayilan faz, genelde orta sahada |
| **low_block** | Alcan blok. Savunma yarisinda, ceza alani yakininda |
| **defending_transition** | Gecis savunmasi. Rakip kendi yarisindan hizla ilerliyor |
| **defending_quick_break** | Hizli atak savunmasi |
| **defending_set_play** | Duran top savunmasi |
| **chaotic** | Kaotik faz. Kisa, catismasli top degisimi |
