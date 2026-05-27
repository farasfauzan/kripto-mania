# HCI Analysis - Kripto Mania Dashboard
## Human-Computer Interaction (Interaksi Manusia dan Komputer)

---

## 1. TEORI HCI YANG DIGUNAKAN

### 1.1 Nielsen's 10 Usability Heuristics
| # | Heuristic | Implementasi |
|---|-----------|-------------|
| 1 | Visibility of system status | Loading screen, progress bar, freshness badge, auto-refresh indicator |
| 2 | Match between system and real world | Bahasa Indonesia, format IDR, zona waktu WIB, kategori coin familiar |
| 3 | User control and freedom | Toggle auto-refresh, manual refresh, scan mandiri, portfolio management |
| 4 | Consistency and standards | Warna konsisten (hijau=bullish, merah=bearish), badge styling, font uniform |
| 5 | Error prevention | Confluence gate, anti-FOMO filter, multi-timeframe guard, form validation |
| 6 | Recognition rather than recall | Color-coded signals, visual indicators, category labels, learning notes |
| 7 | Flexibility and efficiency | Quick-add, quick-scan, tab navigation, auto-refresh toggle, cached data |
| 8 | Aesthetic and minimalist design | Clean dark theme, card-based layout, whitespace, typography hierarchy |
| 9 | Help users recognize/diagnose/recover | Clear error messages, fallback mechanisms, loading states, status indicators |
| 10 | Help and documentation | Tab "Cara Baca Sinyal", tooltips, disclaimer, AI Advisor, learning notes |

### 1.2 Norman's 7 Stages of Action
| Stage | Implementasi |
|-------|-------------|
| 1. Goal | User ingin tahu coin mana yang harus dibeli |
| 2. Formulate | User membuka dashboard, melihat rekomendasi |
| 3. Specify | User memilih coin tertentu untuk dianalisis |
| 4. Execute | User klik "Entry Valid" atau "Pantau di Indodax" |
| 5. Perceive | User melihat hasil analisis, score, sinyal |
| 6. Interpret | User memahami apakah coin layak dibeli |
| 7. Evaluate | User membandingkan dengan ekspektasi |

### 1.3 Cognitive Laws
| Law | Implementasi |
|-----|-------------|
| **Fitts's Law** | Tombol utama (BELI KUAT) besar dan mudah dijangkau |
| **Hick's Law** | Tab navigation membatasi pilihan per halaman |
| **Miller's Law** | Informasi dipecah dalam chunk: Score, Risk, Alokasi, TP, SL |
| **Jakob's Law** | Layout familiar seperti dashboard trading pada umumnya |
| **Law of Proximity** | Data terkait dikelompokkan dalam satu card |
| **Law of Similarity** | Warna hijau untuk profit, merah untuk loss di semua komponen |

---

## 2. PRINSIP DESAIN UI/UX

### 2.1 Visual Hierarchy
```
Level 1 (Paling Penting):
├── Action Signal (BELI KUAT / CICIL BELI / WATCH / JANGAN BELI)
├── Score (0-100)
└── Price + Change %

Level 2 (Informasi Pendukung):
├── TP1, TP2, Target, Stop Loss
├── RSI, ML, MTF
└── Volume

Level 3 (Detail Teknis):
├── Smart adj, Divergence, Candle
├── Regime, VWAP, Fib zone
└── Kelly, Learning, News
```

### 2.2 Color System
| Warna | Hex | Kegunaan |
|-------|-----|----------|
| Green | #047857 | Bullish, profit, buy signal, win |
| Red | #b91c1c | Bearish, loss, sell signal, lose |
| Yellow | #b45309 | Warning, watch, medium risk |
| Blue | #2563eb | Info, links, neutral |
| Gray | #64748b | Secondary text, labels, disabled |
| White | #ffffff | Primary text on dark bg |
| Black | #0f172a | Primary text on light bg |

### 2.3 Typography Hierarchy
```
H1: 2.6rem (900) - Dashboard title
H2: 1.6rem (800) - Section titles
H3: 1.2rem (700) - Card titles
Body: 0.9rem (600) - Main content
Small: 0.75rem (700) - Labels, badges
Tiny: 0.65rem (900) - Metric labels
```

### 2.4 Spacing System
```
xs: 4px  - Tight spacing
sm: 8px  - Small gaps
md: 16px - Default spacing
lg: 24px - Large gaps
xl: 32px - Section spacing
```

---

## 3. INFORMATION ARCHITECTURE

```
Dashboard Kripto Mania
├── Header
│   ├── Title + Subtitle
│   ├── Freshness Badge (Live/Stale)
│   └── Quick Links (Indodax, Telegram)
│
├── Market Overview
│   ├── Market Mode Banner (Aggressive/Normal/Defensive)
│   ├── Market Stats (Green/Red count, Volume)
│   ├── Fear & Greed Index
│   └── News Sentiment
│
├── Main Content (Tabs)
│   ├── Tab 1: AI Auto-Pilot
│   │   └── Playbook harian dari AI
│   │
│   ├── Tab 2: Rekomendasi Beli
│   │   ├── Main Assets (BTC, ETH, SOL, dll)
│   │   └── Micin/Meme Coin (PEPE, DOGE, SHIB, dll)
│   │
│   ├── Tab 3: Portofolio Saya
│   │   ├── Input Modal
│   │   ├── Posisi Aktif
│   │   ├── P/L Real-time
│   │   └── Exposure Breakdown
│   │
│   ├── Tab 4: Statistik Bot
│   │   ├── Winrate, Profit Factor
│   │   ├── Sharpe, Sortino
│   │   ├── Max Drawdown
│   │   └── Equity Curve
│   │
│   ├── Tab 5: Semua Aset
│   │   └── Tabel semua coin dengan score
│   │
│   ├── Tab 6: Scan Koin Lain
│   │   └── Scan mandiri 500+ koin Indodax
│   │
│   ├── Tab 7: Tanya AI Advisor
│   │   └── Chat interaktif dengan AI
│   │
│   └── Tab 8: Cara Baca Sinyal
│       └── Edukasi lengkap
│
├── Sidebar
│   ├── Referral CTA
│   ├── Market Summary
│   ├── Top Picks
│   └── Bot Status
│
└── Footer
    ├── Disclaimer
    ├── Links (Indodax, Telegram)
    └── Copyright
```

---

## 4. INTERACTION DESIGN

### 4.1 User Flow: Analisis Koin
```
1. User buka dashboard
2. Lihat "Rekomendasi Beli Hari Ini"
3. Klik card coin yang menarik
4. Baca: Score, Action, Risk, Alokasi
5. Baca: TP1/TP2/Target, Stop Loss
6. Baca: Smart adj, Divergence, Candle pattern
7. Baca: Two Steps Ahead (roadmap)
8. Klik "Entry Valid" atau "Pantau di Indodax"
```

### 4.2 User Flow: Scan Koin Mandiri
```
1. User buka tab "Scan Koin Lain"
2. Pilih koin dari dropdown
3. Klik "Jalankan Analisis Cerdas"
4. Tunggu loading (progress bar)
5. Lihat hasil analisis lengkap
6. Bandingkan dengan rekomendasi otomatis
```

### 4.3 User Flow: Portfolio Tracking
```
1. User buka tab "Portofolio Saya"
2. Input modal total
3. Tambah posisi (symbol, qty, avg buy)
4. Lihat P/L real-time
5. Lihat exposure per kategori
6. Lihat warning (konsentrasi, exposure tinggi)
7. Edit/tutup/hapus posisi
```

---

## 5. ACCESSIBILITY FEATURES

### 5.1 Color Contrast
- Text on light bg: ≥ 4.5:1 (WCAG AA)
- Text on dark bg: ≥ 4.5:1 (WCAG AA)
- Large text on any bg: ≥ 3:1 (WCAG AA)

### 5.2 Readability
- Font: Plus Jakarta Sans (highly readable)
- Line height: 1.5-1.6
- Max line length: 720px
- Font size minimum: 0.65rem

### 5.3 Keyboard Navigation
- Tab order: logical flow
- Focus indicators: visible outline
- Action buttons: keyboard accessible

### 5.4 Screen Reader Support
- Semantic HTML structure
- ARIA labels on interactive elements
- Descriptive alt text for visual elements

---

## 6. RESPONSIVE DESIGN

### 6.1 Breakpoints
```
Mobile: < 768px
Tablet: 768px - 1024px
Desktop: > 1024px
```

### 6.2 Mobile Adaptations
- Single column layout
- Smaller font sizes
- Collapsible cards
- Touch-friendly button sizes (min 44x44px)
- Simplified navigation

---

## 7. FEEDBACK MECHANISMS

### 7.1 Real-time Feedback
- Freshness badge: Live/Stale/Offline
- Progress bar: Analysis in progress
- Auto-refresh: ON/OFF indicator
- Market mode: Color-coded banner

### 7.2 Error Feedback
- API timeout: Cache fallback with warning
- Data error: Clear error message
- Form validation: Inline error messages

### 7.3 Success Feedback
- Position added: Success message
- Position updated: Confirmation
- Signal saved: Journal entry confirmation

---

## 8. PERFORMANCE CONSIDERATIONS

### 8.1 Loading States
- Skeleton screen: First load
- Progress bar: Analysis in progress
- Spinner: AI generation
- Cached data: Immediate display

### 8.2 Data Caching
- Tickers: 60s TTL
- News: 15min TTL
- Candles: 5min TTL
- Pilot cache: 5min TTL

### 8.3 Parallel Processing
- Candle fetching: ThreadPoolExecutor (5 workers)
- Analysis: Parallel per coin
- Forecast: Multi-horizon simultaneous

---

## 9. USER METRICS (Usability)

### 9.1 Learnability
- First-time user: Understand dashboard in < 30 seconds
- Core task: Find buy signal in < 10 seconds
- Advanced task: Scan any coin in < 15 seconds

### 9.2 Efficiency
- Time to view recommendations: < 5 seconds
- Time to scan a coin: < 10 seconds
- Time to add portfolio position: < 15 seconds

### 9.3 Satisfaction
- Clear, actionable signals
- No confusing jargon
- Beautiful, professional UI
- Helpful AI Advisor

---

## 10. IMPROVEMENTS YANG SUDAH DIIMPLEMENTASIKAN

### 10.1 Visual Design
- ✅ Dark theme dengan accent colors
- ✅ Card-based layout dengan hover effects
- ✅ Gradient backgrounds untuk visual interest
- ✅ Consistent border radius (8px, 12px, 16px, 20px)
- ✅ Box shadows untuk depth

### 10.2 Navigation
- ✅ Tab navigation untuk organized content
- ✅ Sidebar untuk quick access
- ✅ Quick links di header
- ✅ Breadcrumb-like structure

### 10.3 Data Presentation
- ✅ Metric chips untuk technical indicators
- ✅ Color-coded signals (hijau/merah/kuning)
- ✅ Progress bars untuk loading states
- ✅ Badges untuk status indicators
- ✅ Tables untuk structured data

### 10.4 User Control
- ✅ Toggle auto-refresh
- ✅ Manual refresh button
- ✅ Scan koin mandiri
- ✅ Portfolio management (edit/close/delete)
- ✅ Quick prompt buttons untuk AI

### 10.5 Error Prevention
- ✅ Confluence gate (min 4/5 indicators valid)
- ✅ Anti-FOMO filter (prevent entry at peaks)
- ✅ Multi-timeframe guard
- ✅ Form validation (qty > 0, price > 0)
- ✅ Fallback data (cache, shared tickers)

### 10.6 Feedback
- ✅ Freshness badge (Live/Stale)
- ✅ Progress bar (analysis in progress)
- ✅ Loading screen (first load)
- ✅ Success/error messages
- ✅ Market mode banner

### 10.7 Documentation
- ✅ Tab "Cara Baca Sinyal" (complete education)
- ✅ Tooltips dan help text
- ✅ Disclaimer yang jelas
- ✅ AI Advisor untuk interactive Q&A
- ✅ Learning notes yang menjelaskan adjustment

---

## 11. EVALUASI HCI

### 11.1 Heuristic Evaluation Score
| Heuristic | Score (1-5) | Notes |
|-----------|-------------|-------|
| Visibility of system status | 5 | Loading screen, progress bar, freshness badge |
| Match between system and real world | 5 | Bahasa Indonesia, IDR format, WIB timezone |
| User control and freedom | 4 | Good control, could add more customization |
| Consistency and standards | 5 | Consistent colors, fonts, spacing |
| Error prevention | 5 | Confluence gate, anti-FOMO, validation |
| Recognition rather than recall | 5 | Color-coded, visual indicators, labels |
| Flexibility and efficiency | 4 | Good efficiency, could add keyboard shortcuts |
| Aesthetic and minimalist design | 5 | Clean, professional, beautiful |
| Help users recognize/diagnose/recover | 4 | Good error messages, could add more help |
| Help and documentation | 5 | Complete education tab, AI Advisor |
| **Average** | **4.7/5** | **Excellent** |

### 11.2 Cognitive Load Analysis
- **Intrinsic Load**: Managed by chunking information into cards
- **Extraneous Load**: Minimized by clean design, consistent layout
- **Germane Load**: Supported by education tab, learning notes

### 11.3 User Mental Model Alignment
- Dashboard follows familiar trading dashboard patterns
- Color conventions match user expectations (green=up, red=down)
- Terminology matches crypto trading community
- Layout follows F-pattern reading behavior

---

## 12. FUTURE IMPROVEMENTS (Roadmap)

### 12.1 Short-term (1-3 months)
- [ ] Dark/Light theme toggle
- [ ] Customizable dashboard layout (drag & drop)
- [ ] Keyboard shortcuts (R=refresh, S=scan, etc.)
- [ ] Export data to CSV/PDF
- [ ] Price alerts/notifications

### 12.2 Medium-term (3-6 months)
- [ ] Mobile app (React Native)
- [ ] Multi-language support (EN, ID, CN)
- [ ] Social features (share signals, follow experts)
- [ ] Backtesting tool (test strategy historically)
- [ ] Paper trading mode (simulate trading)

### 12.3 Long-term (6-12 months)
- [ ] AI-powered portfolio optimization
- [ ] Real-time news sentiment dashboard
- [ ] On-chain data integration
- [ ] Multi-exchange support (Binance, Coinbase, etc.)
- [ ] Community signals (crowdsourced analysis)

---

## 13. REFERENCES

1. **Nielsen, J.** (1994). "10 Usability Heuristics for User Interface Design"
2. **Norman, D.** (2013). "The Design of Everyday Things"
3. **Krug, S.** (2014). "Don't Make Me Think"
4. **Lidwell, W.** (2010). "Universal Principles of Design"
5. **WCAG 2.1** - Web Content Accessibility Guidelines
6. **Gestalt Principles** - Proximity, Similarity, Closure, Continuity
7. **Cognitive Load Theory** - Sweller, J. (1988)
8. **Fitts's Law** - Fitts, P.M. (1954)
9. **Hick's Law** - Hick, W.E. (1952)
10. **Miller's Law** - Miller, G.A. (1956)

---

*Dokumentasi ini dibuat untuk evaluasi mata kuliah Interaksi Manusia dan Komputer (IMK)*
*Dashboard: Kripto Mania - Trading Dashboard*
*Version: 1.0*
