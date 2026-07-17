# AI Trading Radar - Android Mobile App Design

## Project Overview

**Project Name:** AI Trading Radar Mobile  
**Type:** Native Android Application (Kotlin)  
**Purpose:** Mobile companion app for AI Trading Radar desktop application  
**Core Functionality:** Real-time trading monitoring, AI analysis dashboard, account management, and bot control from mobile devices

---

## 1. Concept & Vision

Aplikasi mobile companion untuk AI Trading Radar yang memberikan akses real-time ke:

- 📊 **Dashboard AI Analysis** - Pantau 20+ AI agents dan confidence score
- 💰 **Account Overview** - Balance, equity, margin dalam genggaman
- 📈 **Trade History** - Riwayat trading dengan detailed analysis
- ⚙️ **Bot Control** - Start/stop trading engine remotely
- 🔔 **Notifications** - Real-time alerts untuk signals dan trades

**Design Philosophy:** Professional, data-rich, dark theme dengan accent colors yang membedakan buy/sell signals. Fokus pada readability dan quick decision making.

---

## 2. Design Language

### 2.1 Aesthetic Direction

**Style:** Trading Terminal Professional  
**Theme:** Dark mode dengan neon accents (terinspirasi dari Bloomberg Terminal meets modern fintech)

```
Primary Background: #0D1117 (Deep dark)
Secondary Background: #161B22 (Card surfaces)
Surface: #21262D (Elevated elements)
Border: #30363D (Subtle dividers)
```

### 2.2 Color Palette

| Color | Hex | Usage |
|-------|-----|-------|
| Primary Green | #00FF88 | Buy signals, profit, positive |
| Primary Red | #FF4444 | Sell signals, loss, negative |
| Accent Cyan | #00D4FF | Primary actions, links |
| Accent Purple | #A855F7 | AI/ML indicators |
| Accent Orange | #FFAA00 | Warnings, pending |
| Text Primary | #F0F6FC | Main text |
| Text Secondary | #8B949E | Secondary info |
| Background | #0D1117 | App background |

### 2.3 Typography

```
Font Family: Inter (primary), JetBrains Mono (numbers/data)
Headings: Inter Bold, 20-24sp
Body: Inter Regular, 14-16sp
Data/Numbers: JetBrains Mono Medium, 14-18sp
Captions: Inter Regular, 12sp
```

### 2.4 Spatial System

```
Base unit: 8dp
Padding small: 8dp
Padding medium: 16dp
Padding large: 24dp
Card radius: 12dp
Button radius: 8dp
Icon size: 24dp (standard), 20dp (small)
```

### 2.5 Motion Philosophy

- **Page transitions:** Slide + fade, 300ms
- **Card animations:** Subtle scale on press (0.98), 150ms
- **Data updates:** Fade in with number animation (count up/down)
- **Loading states:** Shimmer effect, pulsing indicators
- **Bottom sheet:** Slide up with spring physics

---

## 3. Layout & Structure

### 3.1 Navigation Architecture

**Type:** Bottom Navigation Bar dengan 4 main sections

```
┌─────────────────────────────────────────────┐
│ Status Bar (Connection + Account)            │
├─────────────────────────────────────────────┤
│                                             │
│           Main Content Area                 │
│           (Scrollable/ViewPager)            │
│                                             │
├─────────────────────────────────────────────┤
│  🏠    📊    📈    ⚙️                       │
│ Home  AI    Trade  Settings                  │
└─────────────────────────────────────────────┘
```

### 3.2 Screen Structure

#### Screen 1: Home Dashboard
```
┌────────────────────────────────────────┐
│ MT5 Account Info (Server + Login)      │
│ Connection Status Indicator             │
├────────────────────────────────────────┤
│ Balance Card                           │
│ ┌──────────────────────────────────┐   │
│ │ Balance     | Equity             │   │
│ │ $10,000.00  | $10,250.00  (+2.5)│   │
│ └──────────────────────────────────┘   │
├────────────────────────────────────────┤
│ Quick Stats Row                        │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  │
│ │Margin│ │Free  │ │Open  │ │P/L   │  │
│ │$500  │ │$9,500│ │ 2    │ │+$250 │  │
│ └──────┘ └──────┘ └──────┘ └──────┘  │
├────────────────────────────────────────┤
│ Current Position (if any)              │
│ ┌──────────────────────────────────┐   │
│ │ XAUUSD | BUY | +15.50 | 0.5 lot │   │
│ │ Entry: 2350.50 | SL: 2348 | TP  │   │
│ └──────────────────────────────────┘   │
├────────────────────────────────────────┤
│ Recent Signals                         │
│ ┌──────────────────────────────────┐   │
│ │ 14:30 | BUY | Confidence: 85%   │   │
│ │ 14:25 | SELL| Confidence: 72%   │   │
│ └──────────────────────────────────┘   │
├────────────────────────────────────────┤
│ [▶ Start Bot] / [⏹ Stop Bot]          │
└────────────────────────────────────────┘
```

#### Screen 2: AI Analysis Dashboard
```
┌────────────────────────────────────────┐
│ Market Overview Card                   │
│ ┌──────────────────────────────────┐   │
│ │ XAUUSD 2350.50  ▲ +0.25%         │   │
│ │ Time: 14:30:00 | Session: London │   │
│ └──────────────────────────────────┘   │
├────────────────────────────────────────┤
│ Chief Trader Decision                  │
│ ┌──────────────────────────────────┐   │
│ │ 🏆 DECISION: BUY                  │   │
│ │ Confidence: 78%                  │   │
│ │ Reason: Strong uptrend confirmed │   │
│ └──────────────────────────────────┘   │
├────────────────────────────────────────┤
│ Agent Voting (Expandable Grid)          │
│ ┌──────────────────────────────────┐   │
│ │ ✓ Trend: BUY (90%)               │   │
│ │ ✓ Volume: BUY (85%)              │   │
│ │ ✓ RSI: NEUTRAL (55%)             │   │
│ │ ✓ MACD: BUY (80%)                │   │
│ │ ✓ Structure: BUY (75%)           │   │
│ │ ... (tap to expand all 20+)       │   │
│ └──────────────────────────────────┘   │
├────────────────────────────────────────┤
│ Key Factors                            │
│ • London Session Active                │
│ • No High-Impact News                  │
│ • Low Volatility Regime                │
└────────────────────────────────────────┘
```

#### Screen 3: Trade History
```
┌────────────────────────────────────────┐
│ Filter: [All] [Wins] [Losses] [Today]  │
├────────────────────────────────────────┤
│ Summary Stats                          │
│ ┌──────────────────────────────────┐   │
│ │ Total: 45 | Wins: 32 | Loss: 13  │   │
│ │ Win Rate: 71.1% | Avg R:R: 1.85  │   │
│ │ Total P/L: +$1,250.00            │   │
│ └──────────────────────────────────┘   │
├────────────────────────────────────────┤
│ Trade List (RecyclerView)               │
│ ┌──────────────────────────────────┐   │
│ │ XAUUSD BUY @ 2348.50            │   │
│ │ Closed: 2350.00 | +$150 (+1.5%) │   │
│ │ Duration: 15 min | SL: 2346     │   │
│ │ Agents: Trend✓ Volume✓ RSI✓     │   │
│ └──────────────────────────────────┘   │
│ ┌──────────────────────────────────┐   │
│ │ XAUUSD SELL @ 2352.00           │   │
│ │ Closed: 2351.50 | +$75 (+0.7%) │   │
│ │ Duration: 8 min | SL: 2354      │   │
│ └──────────────────────────────────┘   │
└────────────────────────────────────────┘
```

#### Screen 4: Settings
```
┌────────────────────────────────────────┐
│ Account Settings                       │
│ ├─ MT5 Server (FinexBisnisSolusi-Demo)│
│ ├─ MT5 Login (60779778)               │
│ ├─ [Change Password]                  │
├────────────────────────────────────────┤
│ Trading Settings                       │
│ ├─ Auto Trading: [ON/OFF]             │
│ ├─ Max Positions: 2                   │
│ ├─ Risk per Trade: 2%                 │
│ ├─ Trading Mode: [Aggressive/Balanced]│
├────────────────────────────────────────┤
│ Notifications                           │
│ ├─ Signal Alerts: [ON]                │
│ ├─ Trade Notifications: [ON]          │
│ ├─ Daily Summary: [ON]                │
├────────────────────────────────────────┤
│ Connection                             │
│ ├─ Bot IP:Port (192.168.1.100:9190)   │
│ ├─ [Test Connection]                   │
├────────────────────────────────────────┤
│ About                                  │
│ ├─ Version: 2.0.0                     │
│ ├─ [Check for Updates]                │
│ ├─ [View Documentation]               │
└────────────────────────────────────────┘
```

---

## 4. Features & Interactions

### 4.1 Core Features

#### F1: Real-time Dashboard
- **Description:** Display live account metrics and bot status
- **Data Flow:** WebSocket/SSE from desktop bot → Mobile app
- **Update Frequency:** Real-time (1-5 seconds)
- **Fallback:** Polling every 10 seconds if WebSocket disconnects

#### F2: AI Agent Monitor
- **Description:** View all 20+ AI agents' analysis and voting
- **Layout:** Expandable cards showing each agent's decision + confidence
- **Color Coding:** Green (BUY), Red (SELL), Gray (NEUTRAL)
- **Tap Action:** Expand to show detailed analysis text

#### F3: Trade Execution Control
- **Start Bot:** Sends command to desktop bot to start trading
- **Stop Bot:** Emergency stop with confirmation dialog
- **Status Indicator:** Real-time connection status

#### F4: Position Management
- **View Open Positions:** Symbol, direction, lot size, P/L
- **Close Position:** Manual close with confirmation
- **Modify SL/TP:** Edit pending orders (future feature)

#### F5: Trade History
- **Filtering:** By date, by symbol, by outcome (win/loss)
- **Statistics:** Win rate, average R:R, total P/L
- **Detail View:** Full trade analysis with agent voting breakdown

#### F6: Push Notifications
- **Signal Alerts:** New AI signal detected
- **Trade Updates:** Position opened/closed
- **Price Alerts:** Configurable price levels
- **Daily Summary:** End of day performance recap

### 4.2 Interaction Details

| Element | Tap | Long Press | Swipe |
|---------|-----|------------|-------|
| Trade Card | Expand details | Quick close option | - |
| Agent Card | Expand analysis | - | - |
| Balance | Copy to clipboard | - | - |
| Position Card | View chart | Close position | - |
| Signal Item | View full analysis | Dismiss | Dismiss |

### 4.3 Error States

| Scenario | UI Response |
|----------|-------------|
| Connection Lost | Banner "Reconnecting..." + retry button |
| Invalid Credentials | Inline error under form field |
| Bot Not Running | Prompt to start bot on desktop |
| No Data | Empty state illustration + refresh button |
| API Error | Snackbar with retry action |

---

## 5. Component Inventory

### 5.1 Cards

**AccountSummaryCard**
- Balance, Equity, Margin, Free Margin
- Gradient background based on P/L (green tint if profit, red if loss)
- States: Loading (shimmer), Loaded, Error (retry)

**PositionCard**
- Symbol, Direction arrow, Lot size, Entry price, Current P/L
- Color-coded border: Green (BUY), Red (SELL)
- States: Open, Closing (loading), Closed (grayed)

**SignalCard**
- Timestamp, Direction, Confidence bar, Brief reason
- Confidence bar with gradient (red→yellow→green)
- States: New (highlighted), Read (normal), Dismissed (hidden)

**AgentCard**
- Agent name, Icon, Decision badge, Confidence percentage
- Expandable content showing full analysis text
- States: Collapsed, Expanded, Loading

### 5.2 Buttons

**PrimaryButton**
- Background: Cyan (#00D4FF)
- Text: White, bold
- States: Default, Pressed (darker), Disabled (50% opacity), Loading (spinner)

**BotControlButton**
- Start: Green (#00FF88)
- Stop: Red (#FF4444)
- Size: Large (56dp height), full width
- States: Idle, Loading (spinner), Disabled

**IconButton**
- Size: 48dp touch target, 24dp icon
- Background: Transparent or surface color
- States: Default, Pressed (ripple), Disabled

### 5.3 Input Fields

**TextField**
- Background: Surface (#21262D)
- Border: 1dp, Border color
- Label: Floating or top-aligned
- States: Empty, Filled, Focused (cyan border), Error (red border + message)

**DropdownField**
- Same as TextField + dropdown icon
- Options in bottom sheet with search (if >10 items)

### 5.4 Status Indicators

**ConnectionBadge**
- Connected: Green dot + "Connected"
- Connecting: Orange dot + pulsing + "Connecting..."
- Disconnected: Red dot + "Disconnected"

**ConfidenceBar**
- Horizontal bar, 0-100%
- Gradient: 0-40% red, 40-70% yellow, 70-100% green
- Animated fill on data update

---

## 6. Technical Approach

### 6.1 Architecture

**Pattern:** MVVM with Clean Architecture layers

```
┌─────────────────────────────────────────────┐
│ Presentation Layer (UI)                     │
│ - Activities, Fragments, ViewModels         │
│ - Compose UI (or XML layouts)               │
├─────────────────────────────────────────────┤
│ Domain Layer                                │
│ - Use Cases                                 │
│ - Repository Interfaces                     │
│ - Domain Models                             │
├─────────────────────────────────────────────┤
│ Data Layer                                  │
│ - Repository Implementations                │
│ - Remote Data Sources (WebSocket, REST)     │
│ - Local Data Sources (Room, DataStore)      │
│ - DTOs, Mappers                             │
└─────────────────────────────────────────────┘
```

### 6.2 Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Kotlin 1.9+ |
| Min SDK | 26 (Android 8.0) |
| Target SDK | 34 (Android 14) |
| UI Framework | Jetpack Compose (recommended) or XML |
| Architecture | MVVM + Clean Architecture |
| DI | Hilt (Dagger) |
| Networking | Retrofit + OkHttp (REST), OkHttp WebSocket |
| Async | Kotlin Coroutines + Flow |
| Local Storage | Room Database, DataStore Preferences |
| Navigation | Jetpack Navigation Compose |
| Charts | MPAndroidChart or Vico |
| Push Notifications | Firebase Cloud Messaging |
| Image Loading | Coil |
| Serialization | Kotlinx Serialization |

### 6.3 API Integration

**Desktop Bot API (HTTP + WebSocket)**

```kotlin
// REST Endpoints (existing web dashboard)
GET  /api/status          // Bot status, connection
GET  /api/account         // MT5 account info
GET  /api/positions       // Open positions
GET  /api/history         // Trade history
GET  /api/signals         // Recent signals
POST /api/bot/start       // Start trading
POST /api/bot/stop        // Stop trading

// WebSocket Events (SSE)
ws://bot-ip:9190/ws
Events:
- account_update
- position_update
- signal_new
- bot_status_change
```

### 6.4 Data Models

```kotlin
data class AccountInfo(
    val login: String,
    val server: String,
    val balance: Double,
    val equity: Double,
    val margin: Double,
    val freeMargin: Double,
    val leverage: Int
)

data class Position(
    val ticket: Int,
    val symbol: String,
    val type: TradeType, // BUY or SELL
    val lotSize: Double,
    val entryPrice: Double,
    val currentPrice: Double,
    val profit: Double,
    val sl: Double,
    val tp: Double,
    val openTime: Instant
)

data class AiSignal(
    val id: String,
    val timestamp: Instant,
    val symbol: String,
    val direction: TradeType,
    val confidence: Int,
    val chiefDecision: String,
    val agentVotes: List<AgentVote>,
    val entryPrice: Double,
    val sl: Double,
    val tp: Double
)

data class AgentVote(
    val agentName: String,
    val decision: VoteDecision, // BUY, SELL, NEUTRAL
    val confidence: Int,
    val analysis: String
)
```

### 6.5 Project Structure (Android)

```
app/
├── src/main/
│   ├── java/com/aitradingradar/mobile/
│   │   ├── di/                     # Hilt modules
│   │   ├── data/
│   │   │   ├── remote/
│   │   │   │   ├── api/
│   │   │   │   └── websocket/
│   │   │   ├── repository/
│   │   │   └── local/
│   │   ├── domain/
│   │   │   ├── model/
│   │   │   ├── repository/
│   │   │   └── usecase/
│   │   ├── presentation/
│   │   │   ├── ui/
│   │   │   │   ├── home/
│   │   │   │   ├── ai/
│   │   │   │   ├── trades/
│   │   │   │   └── settings/
│   │   │   ├── components/
│   │   │   └── theme/
│   │   └── App.kt
│   └── res/
│       ├── values/
│       ├── drawable/
│       └── layout/
```

---

## 7. Screen Flows

### 7.1 Onboarding Flow

```
Splash Screen
    ↓
Connection Setup (first time only)
    ├─ Enter Bot IP/Port
    ├─ Test Connection
    └─ Save
    ↓
Main Dashboard
```

### 7.2 Trading Flow

```
Signal Detected (Push Notification)
    ↓
Open Signal Detail
    ├─ View AI Analysis
    ├─ View Agent Votes
    └─ Open Position (triggers on desktop)
    ↓
Position Opened
    ↓
Monitor in Positions Tab
    ↓
Position Closed (TP or SL)
    ↓
View in Trade History
```

---

## 8. Non-Functional Requirements

### 8.1 Performance

- App launch: < 2 seconds
- Screen transitions: < 300ms
- Data refresh: < 1 second for WebSocket updates
- Offline mode: Show cached data with "Last updated" timestamp

### 8.2 Security

- Store bot connection URL in encrypted SharedPreferences
- No storage of trading credentials (always connect to running bot)
- SSL pinning for production API calls
- Biometric/PIN lock for app access (optional setting)

### 8.3 Accessibility

- Content descriptions for all interactive elements
- Minimum touch target: 48dp
- Color contrast ratio: 4.5:1 minimum
- Support for system font scaling

### 8.4 Compatibility

- Support portrait and landscape orientations
- Tablet layout: Master-detail for larger screens
- Dark mode only (matching trading terminal aesthetic)

---

## 9. Future Enhancements (v2.0+)

- **Chart Integration:** TradingView webview for price charts
- **Multi-Bot Support:** Connect to multiple trading bots
- **Widget:** Home screen widget showing quick stats
- **Watchlist:** Monitor multiple symbols
- **Advanced Orders:** Place manual orders from app
- **Performance Analytics:** Detailed P&L charts and reports

---

## 10. Implementation Priorities

### Phase 1 (MVP)
1. ✅ Home Dashboard with account info
2. ✅ Connection management
3. ✅ Bot start/stop control
4. ✅ Basic notifications

### Phase 2
5. ✅ AI Agent dashboard
6. ✅ Trade history
7. ✅ Position monitoring
8. ✅ Real-time updates via WebSocket

### Phase 3
9. ✅ Charts integration
10. ✅ Advanced filters
11. ✅ Performance analytics
12. ✅ Widget support

---

## 11. Asset Requirements

### Icons (Material Design + Custom)
- Navigation: Home, Dashboard, Chart, Settings
- Actions: Play, Stop, Refresh, Filter, Export
- Status: Connected, Disconnected, Warning
- Trade: Buy arrow, Sell arrow, Close
- Agents: Brain/AI icon (for agent section)

### Illustrations
- Empty state: No positions, No signals, No connection
- Onboarding: Connection setup illustration
- Error states: Connection error, Server unreachable

### Logo
- Match desktop app branding
- App icon: Radar sweep with XAUUSD symbol
- Adaptive icon for Android 8+

---

*Dokumen ini dapat digunakan sebagai spesifikasi untuk development. Revisi dan penyesuaian dapat dilakukan sesuai kebutuhan development team.*