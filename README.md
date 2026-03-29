# Twelve Pressing Analyst

SkillCorner **Dynamic Events** verisiyle pressing metriklerini inceleyen Streamlit uygulaması (`pressing_app.py`).

## Veriyi nereye koymalısın?

Uygulama tek bir **veri kök klasörü** (`DATA_DIR`) bekler. Bu klasörü diskte istediğin yere koyabilirsin; önemli olan yapı ve dosya adlarıdır.

### Klasör yapısı

```
<DATA_DIR>/
├── _pressing_cache.parquet    # Tüm maçların birleşik Dynamic Events tablosu
└── meta/
    ├── 12345.json             # match_id ile maç meta bilgisi (tarih, takımlar, skor, …)
    ├── 12346.json
    └── ...
```

- **`_pressing_cache.parquet`**: Maç bazlı parquet dosyalarının birleştirilmiş hali; satırlarda `match_id` ve Dynamic Events şemasındaki sütunlar bulunur (detay için `PRESSING_METRICS_DOCUMENTATION.md`).
- **`meta/`**: Her maç için `{match_id}.json` dosyaları. Maç seçici ve etiketler bu dosyalardan okunur.

> **Not:** Bu veri SkillCorner lisansıyla gelir; repoya büyük parquet/meta dosyalarını ekleme. Veriyi kendi makinede veya SkillCorner’ten aldığın konumda tut.

### Kodda konumu bağlama

`pressing_app.py` içinde `DATA_DIR` şu an sabit bir Windows yolu ile tanımlı:

```python
DATA_DIR = Path(r"D:\ContextEngineeringProject\dynamic_events_pl_24\dynamic_events_pl_24")
```

Kendi ortamında kullanmak için bu satırı **senin veri klasörünün tam yoluna** çevir (örnek):

```python
DATA_DIR = Path(r"C:\veri\dynamic_events_pl_24")
```

veya proje içindeyse:

```python
DATA_DIR = Path(__file__).resolve().parent / "dynamic_events_pl_24"
```

Aynı `DATA_DIR` mantığı `pressing_metrics.py` içindeki önbellek dosyaları için de kullanılır; tek kök klasör yeterlidir.

---

## Nasıl çalıştırılır?

### 1. Python ortamı

Python 3.10+ önerilir. Sanal ortam kullanman iyi olur:

```powershell
cd D:\ContextEngineeringProject
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Bağımlılıklar

```powershell
pip install -r requirements.txt
```

### 3. Uygulamayı aç

```powershell
streamlit run pressing_app.py
```

Tarayıcıda genelde `http://localhost:8501` açılır.

---

## İlgili dosyalar

| Dosya | Açıklama |
|-------|----------|
| `pressing_app.py` | Pressing Analyst arayüzü |
| `pressing_metrics.py` | Metrik hesapları |
| `PRESSING_METRICS_DOCUMENTATION.md` | Metrik açıklamaları |
| `PRESSING_METRICS_SPECIFICATION.md` | Formül / veri sözleşmesi |

`app.py` adlı eski dashboard varsa o dosya **`_all_events_cache.parquet`** ve `dynamic/` alt yapısını kullanır; Pressing Analyst ile aynı cache dosyası değildir.
