# Analisis Antarmuka Pengguna — Bot Trading Crypto Indodax
## Referensi: Prinsip Interaksi Manusia dan Komputer (IMK/HCI)

---

## 1. PROFIL PENGGUNA (USER PERSONA)

### 1.1 Segmentasi Pengguna

| Tipe Pengguna | Deskripsi | Kebutuhan IMK |
|---|---|---|
| **Trader Pemula** | Baru mengenal crypto, minim pengalaman teknikal | Onboarding bertahap, penjelasan istilah, guidance eksplisit |
| **Trader Menengah** | Sudah paham candlestick, RSI, MACD tapi butuh konfirmasi | Dashboard terstruktur, sinyal terprioritas, notifikasi kontekstual |
| **Trader Pro** | Aktif 24/7, butuh efisiensi & alert real-time | Data dense, keyboard shortcut, filter advanced, API webhook |

### 1.2 User Journey Map

```
Ekspetasi → Onboarding → Eksplorasi → Rutin → Mastery
   │           │           │         │         │
   ▼           ▼           ▼         ▼         ▼
Awareness  Setup awal   First signal  Daily   Portfolio
   │          │           │          routine  optimization
   └──────────┴───────────┴──────────┴─────────┘
```

---

## 2. PRINSIP IMK YANG DITERAPKAN

### 2.1 Heuristik Nielsen (10 Usability Heuristics)

| # | Heuristik | Implementasi Saat Ini | Rekomendasi Perbaikan |
|---|---|---|---|
| 1 | **Visibility of system status** | Market mode (BULLISH/BEARISH/RANGING) ditampilkan di header | Tambahkan loading state saat fetch data, real-time progress bar untuk scan 500+ koin |
| 2 | **Match between system & real world** | Bahasa Indonesia, istilah crypto familiar (BELI KUAT, HOLD) | Tambahkan glossar istilah teknikal (RSI, MACD, Supertrend) dalam tooltip |
| 3 | **User control & freedom** | Tombol STOP/START scan, manual refresh | Tambahkan undo untuk aksi (kembalikan posisi sebelum sell), cancel button untuk long-running scan |
| 4 | **Consistency & standards** | Warna konsisten: hijau=bullish, merah=bearish | Standardisasi warna di SEMUA halaman (bukan hanya dashboard). Gunakan ikon standar (📈📉) |
| 5 | **Recognition rather than recall** | Top picks ditampilkan dengan score visual | Tambahkan visual confluence meter (bar chart) agar user tidak perlu hafal angka |
| 6 | **Flexibility & efficiency** | Filter by risk level, sort by score | Tambahkan keyboard shortcut, custom watchlist, saved views untuk power user |
| 7 | **Help & documentation** | README.md dengan setup guide | Tambahkan in-app tooltip tour, FAQ interaktif, context-sensitive help |
| 8 | **Error prevention** | Validasi input capital, minimum volume filter | Tambahkan confirmation dialog untuk aksi irreversible (sell semua, clear journal) |
| 9 | **Recovery from errors** | Fallback aman jika library tidak terinstall | Tambahkan error recovery dengan pesan jelas, retry mechanism, cache fallback |
| 10 | **Aesthetic & minimalist** | Dashboard bersih, fokus pada actionable data | Hapus informasi redundant, gunakan progressive disclosure (detail di expandable section) |

### 2.2 Model Mental Pengguna

```
Model Mental Pengguna          Model Sistem Aktual
┌─────────────────┐           ┌──────────────────────┐
│ "Coin naik/turun" │    ←→   │ EMA, RSI, MACD, BB... │
│ "Beli murah, jual mahal" │ ←→│ Entry zone, TP/SL     │
│ "Aman/tidak aman" │    ←→   │ Risk level, Kelly, Sharpe│
│ "Kapan masuk?"     │    ←→   │ Forecast 6h/24h prob  │
└─────────────────┘           └──────────────────────┘
```

**Gap Analysis:**
- Pengguna awam tidak paham istilah teknikal → perlu **abstraction layer**
- Sistem menampilkan banyak angka → perlu **information hierarchy**
- User butuh kepastian → sistem memberikan probabilitas → perlu **uncertainty communication**

---

## 3. ANALISIS LAYOUT & INFORMATION ARCHITECTURE

### 3.1 Hierarki Informasi Saat Ini

```
┌─────────────────────────────────────────────┐
│  HEADER: Status Bot + Market Overview        │  ← Attention (top)
├─────────────────────────────────────────────┤
│  TOP PICKS: 3-5 coin terbaik dengan score    │  ← Primary action
├─────────────────────────────────────────────┤
│  AI PILOT PLAYBOOK: Rekomendasi harian        │  ← Guidance
├─────────────────────────────────────────────┤
│  PORTFOLIO: Posisi terbuka + P/L             │  ← Personal context
├─────────────────────────────────────────────┤
│  NEWS SENTIMENT: Sentimen global             │  ← Context
├─────────────────────────────────────────────┤
│  LEARNING PROFILE: Statistik historis         │  ← Feedback
└─────────────────────────────────────────────┘
```

### 3.2 Fitts's Law — Interaksi Terdekat

| Aksi | Lokasi Saat Ini | Rekomendasi |
|---|---|---|
| Refresh data | Tombol di atas | Pindahkan ke posisi jangkauan mouse (kanan atas) |
| Copy sinyal | Tidak ada | Tambahkan tombol copy di setiap sinyal |
| Switch tab | Sidebar (Streamlit default) | Custom tab navigation dengan icon |
| Export data | Tidak ada | Tambahkan tombol export CSV/JSON |

### 3.3 Hick's Law — Kompleksitas Keputusan

**Masalah:** Dashboard menampilkan 10+ metrik sekaligus → decision fatigue

**Solusi:** Progressive disclosure
```
Level 1 (Overview):
  - Market mode (BULLISH/BEARISH/RANGING)
  - Top 3 picks dengan score
  - AI Playbook summary

Level 2 (Detail - click to expand):
  - Semua 10+ top picks
  - Detail teknikal per coin
  - Portfolio breakdown

Level 3 (Advanced - click to expand):
  - Learning profile lengkap
  - Journal history
  - Advanced metrics (Sharpe, Sortino, Kelly)
```

---

## 4. PRINSIP PERCEPTUAL COGNITION

### 4.1 Gestalt Principles

| Prinsip | Aplikasi | Implementasi |
|---|---|---|
| **Proximity** | Data terkait dikelompokkan | Score + action + risk dalam 1 card per coin |
| **Similarity** | Item serupa terlihat sama | Semua sinyal BELI menggunakan styling hijau |
| **Closure** | User melengkapi informasi | Ringkasan market mode di header, detail di bawah |
| **Continuity** | Aliran visual yang smooth | Score bar dari 0→100, trend line di chart |
| **Figure/Ground** | Fokus pada yang penting | Top picks highlight, data lain muted |

### 4.2 Visual Hierarchy (Eye-Tracking Principles)

```
Z-PATTERN SCANNING PATTERN:

┌─────────────────────────────────────────────┐
│  Logo/Title          Market Status ● BULL   │  ← Scan pertama
├─────────────────────────────────────────────┤
│  TOP PICKS  │  AI PLAYBOOK                  │  ← Scan kedua
│  Coin A ★   │  🌤 Outlook: Bullish          │
│  Coin B ★   │  🎯 Aksi: Buy X, Hold Y       │
│  Coin C ★   │  💼 Portfolio: +3.5%          │
├─────────────────────────────────────────────┤
│  PORTFOLIO │ NEWS │ LEARNING                │  ← Scan ketiga
└─────────────────────────────────────────────┘
```

### 4.3 Color Theory & Accessibility

| Elemen | Warna Saat Ini | WCAG Contrast | Rekomendasi |
|---|---|---|---|
| Bullish (hijau) | #00C853 | ✓ 7.2:1 (on white) | OK, tambahkan icon 📈 |
| Bearish (merah) | #FF5252 | ✓ 4.6:1 (on white) | Tambah icon 📉 untuk colorblind |
| Neutral (abu) | #9E9E9E | ✗ 2.3:1 (on white) | Gelapkan ke #616161 |
| Warning (kuning) | #FFD600 | ✗ 1.4:1 (on white) | Gelapkan ke #FFAB00 |

**Colorblind Consideration:**
- 8% pria memiliki colorblind (deuteranopia/protanopia)
- Solusi: Gunakan pattern/shape tambahan (★ untuk strong, ○ untuk weak)
- Jangan andalkan warna saja → selalu sertakan text label

---

## 5. INTERACTION DESIGN

### 5.1 Feedback Loops

```
User Action → System Response → Feedback → Next Action
    │              │                │            │
    ▼              ▼                │            ▼
Klik SCAN    → Loading 5-30s → Progress bar → Klik STOP
Klik COPY    → Clipboard OK → Toast notif   → Lanjut
Klik SELL    → Confirm dlg → Success banner → Review
```

**Current Gaps:**
- ❌ Tidak ada loading indicator saat scan berjalan
- ❌ Tidak ada toast notification untuk aksi copy
- ❌ Tidak ada confirmation dialog untuk aksi sell

### 5.2 Microinteractions

| Komponen | Microinteraction | Fungsi |
|---|---|---|
| Score badge | Animasi count-up (0→72) | Visual feedback score terupdate |
| Signal card | Hover shadow increase | Affordance clickable |
| Market status dot | Pulse animation (green) | Real-time status indicator |
| Copy button | Icon berubah ✓ saat hover | Affordance + feedback |
| Portfolio P/L | Color flash (green→red) | Visual P/L change |

### 5.3 Error Handling & Edge Cases

| Error | Pesan Saat Ini | Rekomendasi IMK |
|---|---|---|
| Koneksi gagal | "Gagal fetch data" | "⚠️ Koneksi ke Indodax gagal. Periksa internet Anda, lalu coba lagi" |
| Data tidak cukup | Fallback default | "📊 Data belum cukup untuk analisis. Butuh minimal 30 candle" |
| API quota habis | "Quota exceeded" | "🔑 Kuota AI habis. Gunakan API key atau tunggu 1 menit" |
| Input invalid | "Invalid input" | "💰 Modal harus angka positif. Contoh: 10000000" |

---

## 6. COGNITIVE LOAD MANAGEMENT

### 6.1 Chunking Information

**Prinsip Miller's Law (7±2 items):**

```
❌ SEKARANG: Menampilkan 10+ coin sekaligus → cognitive overload

✅ REKOMENDASI:
  Tab 1: 🎯 TOP PICKS (3-5 coin terbaik)
  Tab 2: 📊 ALL SIGNALS (semua sinyal, filterable)
  Tab 3: 💼 PORTFOLIO (posisi terbuka)
  Tab 4: 📈 LEARNING (statistik historis)
  Tab 5: 📰 NEWS (sentimen & headline)
```

### 6.2 Abstraction Level Management

```
Level 0: Executive Summary (untuk trader sibuk)
  - Market mode + Top 3 picks + AI Playbook summary

Level 1: Tactical View (untuk trader aktif)
  - Semua level 0 + Portfolio P/L + Signal detail

Level 2: Deep Analysis (untuk trader pro)
  - Semua level 1 + Advanced metrics + Journal history
```

### 6.3 Terminology Mapping

| Istilah Teknis | Analogi IMK | Penjelasan |
|---|---|---|
| RSI | "Termometer harga" | >70 = kepanasan (overbought), <30 = dingin (oversold) |
| MACD Cross | "Sinyal lalu lintas" | Bullish cross = lampu hijau, Bearish cross = lampu merah |
| Support | "Lantai" | Harga sulit turun lebih rendah dari support |
| Resistance | "Langit-langit" | Harga sulit tembus resistance tanpa volume |
| ATR | "Ukuran guncangan" | Semakin besar ATR, semakin berisiko |
| Kelly % | "Takaran optimal" | Semakin tinggi edge, semakin besar alokasi |

---

## 7. ACCESSIBILITY (A11Y) COMPLIANCE

### 7.1 WCAG 2.1 Checklist

| Kriterium | Status | Aksi |
|---|---|---|
| 1.1 Text alternatives | ❌ | Tambahkan alt text untuk semua icon/emoji |
| 1.4.1 Use of color | ⚠️ | Tambahkan pattern/label selain warna |
| 1.4.3 Contrast (Minimum) | ⚠️ | Fix neutral text (#9E9E9E → #616161) |
| 2.1 Keyboard accessible | ❌ | Tambahkan keyboard navigation |
| 2.4.3 Focus order | ❌ | Pastikan tab order logical |
| 3.3.1 Error identification | ⚠️ | Tambahkan inline error messages |
| 4.1.2 Name, role, value | ❌ | ARIA labels untuk semua interactive elements |

### 7.2 Multi-Device Adaptation

| Device | Layout | Prioritas |
|---|---|---|
| Desktop (1920px) | Full dashboard, semua panel | Advanced analysis |
| Tablet (768px) | 2-column grid, collapsible panels | Portfolio + Top picks |
| Mobile (375px) | Single column, card-based | AI Playbook + Alerts |

---

## 8. TRUST & TRANSPARENCY DESIGN

### 8.1 Explainable AI (XAI)

Pengguna perlu mempercayai sistem trading → sistem harus menjelaskan **MENGAPA** memberi sinyal:

```
SIGNAL CARD STRUCTURE:
┌─────────────────────────────────────────┐
│ ETH  🟢 BELI KUAT  Score: 78/100        │
├─────────────────────────────────────────┤
│ 📊 Konfirmasi Teknikal:                 │
│   ✅ EMA 5 > 12 > 21 (Bullish)         │
│   ✅ MACD Bullish Cross                │
│   ✅ RSI 58 (Sweet spot)               │
│   ✅ Supertrend Bullish                │
│   ⚠️  BB Overbought (85%)              │
│   ─────────────────                     │
│   4/5 indikator konfirmasi (80%)        │
├─────────────────────────────────────────┤
│ 🎯 Entry: Rp 10.250  TP1: Rp 10.800    │
│ 🛡 SL: Rp 9.900   RR: 1:2.1            │
├─────────────────────────────────────────┤
│ ⚠️  Bukan saran keuangan. DYOR.         │
└─────────────────────────────────────────┘
```

### 8.2 Risk Communication

```
Risk Level → Visual → Penjelasan
─────────────────────────────────────────
TINGGI     │ 🔴🔴🔴 │ Volatilitas tinggi, potensi loss besar
SEDANG     │ 🟡🟡⬜ │ Risiko moderat, sesuai profil
RENDAH     │ 🟢⬜⬜ │ Stabil, volatilitas rendah
BUTUH DATA │ ⬜⬜⬜   │ Data belum cukup untuk penilaian
```

### 8.3 Uncertainty Communication

| Konsep | Metode Visual | Contoh |
|---|---|---|
| Probabilitas | Progress bar + persentase | `72% ↑ [████████░░]` |
| Confidence | Label + icon | `🟢 TINGGI` / `🟡 SEDANG` / `🔴 RENDAH` |
| Range forecast | Range bar | `Rp 10.000 — Rp 11.500 (median: Rp 10.800)` |

---

## 9. NOTIFICATION & ALERT DESIGN

### 9.1 Notification Hierarchy

```
Priority 1 (Real-time, popup):
  - Signal BELI KUAT dengan score > 75
  - TP/SL tercapai untuk posisi terbuka
  - Market mode berubah (BULL → BEAR)

Priority 2 (In-app banner):
  - Scan selesai, top picks ready
  - News sentiment berubah signifikan
  - AI Playbook generated

Priority 3 (Email/Telegram):
  - Daily summary playbook
  - Weekly performance report
  - Portfolio rebalance reminder
```

### 9.2 Notification Content Pattern

```
[ICON] [TITLE]
[BODY: 1-2 kalimat konteks + action]
[ACTION BUTTON: Lihat Detail / Tutup / Snooze]
[timestamp: 2 menit lalu]
```

---

## 10. METRIK USABILITY YANG DIUKUR

### 10.1 Quantitative Metrics

| Metrik | Formula | Target |
|---|---|---|
| **Time to First Signal** | Waktu dari buka app sampai lihat sinyal | < 30 detik |
| **Signal Comprehension** | % user yang paham arti sinyal dalam 5 detik | > 80% |
| **Task Success Rate** | % user yang berhasil eksekusi sinyal | > 70% |
| **Error Rate** | % user yang salah klik | < 5% |
| **Completion Time** | Waktu untuk review semua sinyal | < 3 menit |

### 10.2 Qualitative Metrics (SUS Score)

**System Usability Scale (10 pertanyaan):**

1. Saya senang menggunakan bot ini sering
2. Saya menemukan bot ini unnecessarily complex
3. Saya pikir saya bisa mengoperasikan bot tanpa tutorial
4. Saya butuh tutorial banyak untuk mengoperasikan
5. Saya menemukan fungsi-fungsi terorganisir dengan baik
6. Saya selalu bingung fungsi dimana
7. Saya merasa nyaman mengoperasikan bot ini
8. Saya butuh dukungan teknis sering
9. Saya bisa mengoperasikan dari pertama kali
10. Saya butuh belajar banyak sebelum nyaman

**Scoring:**
- SUS < 50: Poor (perlu redesign besar)
- SUS 50-70: Average (perlu perbaikan)
- SUS 70-85: Good (OK, ada ruang improvement)
- SUS > 85: Excellent (sudah baik)

---

## 11. REKOMENDASI IMPLEMENTASI PRIORITAS

### 11.1 Priority Matrix (Impact vs Effort)

| Prioritas | Fitur | Impact | Effort | Alasan IMK |
|---|---|---|---|---|
| **P0** | Loading indicator + progress bar | Tinggi | Rendah | Visibility of system status (Heuristik #1) |
| **P0** | Risk level visual (🔴🟡🟢) | Tinggi | Rendah | Recognition over recall (Heuristik #5) |
| **P0** | Confirmation dialog untuk sell | Tinggi | Rendah | Error prevention (Heuristik #8) |
| **P1** | Tab navigation (Progressive disclosure) | Tinggi | Sedang | Hick's law, cognitive load reduction |
| **P1** | Copy signal button | Tinggi | Rendah | User control (Heuristik #3) |
| **P1** | Tooltip glossar istilah teknikal | Sedang | Rendah | Match system & real world (Heuristik #2) |
| **P2** | Portfolio P/L animation | Sedang | Sedang | Microinteraction feedback |
| **P2** | Export CSV/JSON | Sedang | Sedang | Flexibility & efficiency (Heuristik #6) |
| **P3** | Mobile responsive layout | Tinggi | Tinggi | Multi-device accessibility |
| **P3** | Keyboard shortcuts | Sedang | Sedang | Power user efficiency |

### 11.2 Wireframe Rekomendasi — Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 AI TRADING BOT                    🟢 LIVE  ⚙️ 📢 🔔     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🌤 MARKET MODE: BULLISH  │  📊 72% coin hijau              │
│  📈 BTC: $97,500 (+2.3%)  │  💰 Volume: Rp 2.5T           │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  🎯 TOP PICKS (3)          │  📋 AI PLAYBOOK                │
│                                                             │
│  ┌──────────────────────┐  │  🌤 Outlook: Bullish           │
│  │ ETH  🟢 BELI KUAT ⭐ │  │  🎯 3 Aksi Prioritas:          │
│  │ Score: 82/100        │  │  1. BELI ETH @ 10.2-10.3     │
│  │ Confluence: 5/5 ✅   │  │  2. HOLD BTC, geser SL        │
│  │ Forecast 6h: 74% ↑   │  │  3. TAKE PROFIT SOL di TP1    │
│  └──────────────────────┘  │  ⚠️ Hindari: DOGE (overbought) │
│  ┌──────────────────────┐  └────────────────────────────────┘
│  │ SOL  🟡 CICIL BELI   │
│  │ Score: 71/100        │  ┌──────────────────────────────┐
│  │ Confluence: 4/5 ✅   │  │  💼 PORTFOLIO (3 posisi)      │
│  └──────────────────────┘  │  ETH +3.5%  BTC +1.2%  SOL -0.5│
│  ┌──────────────────────┐  │  Total P/L: +4.2%              │
│  │ BTC  🟡 HOLD         │  │  [Lihat Detail →]             │
│  │ Score: 68/100        │  └────────────────────────────────┘
│  └──────────────────────┘
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  📊 ALL SIGNALS  │  📈 LEARNING  │  📰 NEWS  │  ⚙️ SETTINGS  │
└─────────────────────────────────────────────────────────────┘
```

---

## 12. TEORI IMK YANG RELEVAN

### 12.1 Donnellan's Model of Interaction

```
Goal → Strategy → Specify → Execute → Observe → Evaluate
   │       │           │           │          │         │
   ▼       ▼           ▼           ▼          ▼         ▼
User:    "Ingin     "Cari coin   Klik SCAN,  Lihat hasil,  "Signal ETH
          profit     yang cocok   filter risk review playbook  BELI KUAT
          hari ini" di portfolio"              dengan AI     dengan 5/5
                                                                 │
                                                                Evaluate:
                                                                "Edge 78/100,
                                                                 entry zone
                                                                 jelas → eksekusi"
```

**Gap:** Sistem memberikan data tapi kurang membantu user di tahap "Evaluate" → perlu AI Playbook yang lebih actionable.

### 12.2 Norman's Action Cycle

```
What happens?
  System displays market data → User sees signals → User interprets → User acts

User's Question:              System's Response:
  "Bagaimana pasar?"     →    Dashboard + market mode
  "Apa yang harus saya   →    AI Playbook + top picks  
     lakukan?"
  "Apakah saya sudah     →    Portfolio P/L + learning stats
     berhasil?"
```

### 12.3 GOMS Model (Goals, Operators, Methods, Selection Rules)

**Task: Review dan eksekusi sinyal harian**

```
GOAL: Eksekusi top pick signal
├─ OPERATOR: Buka dashboard
├─ OPERATOR: Baca AI Playbook
├─ OPERATOR: Klik coin di top picks
├─ OPERATOR: Baca entry zone, TP, SL
├─ OPERATOR: Switch ke exchange (Indodax web)
├─ OPERATOR: Input harga entry
├─ OPERATOR: Input quantity
├─ OPERATOR: Klik BUY
└─ EVALUATE: Konfirmasi order berhasil

Time estimate: ~2-3 menit per signal (dengan cognitive overhead)
Error-prone: Switching between apps (copy-paste harga) → perlu copy button
```

---

## 13. ADVANCED HCI CONSIDERATIONS

### 13.1 Social Cognitive Theory in Trading Bots

| Komponen | Implementasi |
|---|---|
| **Self-efficacy** | Tampilkan winrate historis → build confidence |
| **Outcome expectation** | Show success stories → "Signal ETH BELI KUAT → TP tercapai +5.2%" |
| **Goal setting** | Suggest daily targets → "Target: 2% daily return" |
| **Self-regulation** | Portfolio tracking → user monitor progress sendiri |

### 13.2 Persuasive Design (B.J. Fogg)

```
Fogg Behavior Model: B = MAP
  Behavior = Motivation + Ability + Prompt

Motivation:   Tampilkan profit user → "Anda sudah profit +12.5% bulan ini"
Ability:      Simplifikasi aksi → 1-click copy signal
Prompt:       Notification saat signal kuat → "ETH BELI KUAT score 82!"
```

### 13.3 Gamification Elements

| Element | Fungsi | Contoh |
|---|---|---|
| **Badges** | Reward milestone | "First Profit", "10 Trades", "7-Day Streak" |
| **Progress bars** | Visual progress | "Winrate: 65% → 70% (5% lagi ke next badge)" |
| **Leaderboard** | Social comparison | (Optional) Top trader comparison |
| **Streaks** | Habit formation | "3 hari berturut-turut eksekusi sinyal" |

---

## 14. IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Week 1-2)
- [ ] Loading states & progress indicators
- [ ] Risk level visual badges (🔴🟡🟢)
- [ ] Confirmation dialogs untuk sell/exit
- [ ] Copy signal button dengan toast notification

### Phase 2: Clarity (Week 3-4)
- [ ] Tab-based progressive disclosure
- [ ] Tooltip glossar istilah teknikal
- [ ] Color contrast fix (WCAG AA compliance)
- [ ] Portfolio P/L animation

### Phase 3: Delight (Week 5-6)
- [ ] Micro-interactions (hover, click, count-up)
- [ ] Export CSV/JSON functionality
- [ ] Mobile responsive layout
- [ ] Keyboard shortcuts untuk power user

### Phase 4: Optimization (Week 7-8)
- [ ] User testing (SUS score measurement)
- [ ] A/B testing layout variants
- [ ] Heatmap analysis (click patterns)
- [ ] Iterative refinement berdasarkan feedback

---

## 15. KESIMPULAN

### Strengths (Sudah Baik)
1. ✅ **Information density** — semua data penting tersedia
2. ✅ **Language** — bahasa Indonesia, familiar untuk target user
3. ✅ **Actionable output** — sinyal dengan entry/TP/SL jelas
4. ✅ **AI integration** — playbook memberikan guidance kontekstual

### Weaknesses (Perlu Perbaikan)
1. ❌ **Loading feedback** — tidak ada indikator saat proses berjalan
2. ❌ **Cognitive load** — terlalu banyak data sekaligus tanpa progressive disclosure
3. ❌ **Error handling** — pesan error kurang informatif
4. ❌ **Accessibility** — color contrast, keyboard navigation belum optimal
5. ❌ **Trust building** — tidak ada explanation WHY sinyal diberikan

### Key HCI Principles to Apply
1. **Visibility of system status** — loading, progress, real-time status
2. **Progressive disclosure** — overview → detail → advanced
3. **Recognition over recall** — visual indicators, icons, color coding
4. **Error prevention** — confirmation dialogs, input validation
5. **Flexibility** — keyboard shortcuts, custom watchlist, saved views

---

*Dokumen ini disusun berdasarkan prinsip-prinsip Interaksi Manusia dan Komputer (HCI/IMK) yang mencakup Nielsen's Heuristics, Fitts's Law, Hick's Law, Gestalt Principles, Cognitive Load Theory, dan Norman's Action Cycle.*
