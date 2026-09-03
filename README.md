# 🏹 ArcherSniper — DLSU Course Sniper & College Notification System

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Discord.py](https://img.shields.io/badge/discord.py-2.7+-blueviolet.svg)](https://discordpy.readthedocs.io/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**ArcherSniper** is a standalone, production-ready Discord Bot designed for De La Salle University (DLSU) students. It monitors course section capacity and enlisted counts in real-time on DLSU's CourseFinder portal (`archershub.dlsu.edu.ph`), streaming live drops to designated **College Feeds** and instantly sending **Direct Message (DM) slot alerts** to students.

---

## 🌟 Key Highlights

- 📬 **Direct Message (DM) Personal Alerts:** Instant private messages delivered to students when slots open up (`45/45 ➔ 44/45`) or fill up (`44/45 ➔ 45/45`).
- 🏛️ **DLSU College Feeds & GE/LC Live Stream:** Automatic routing of course slot changes to college-specific channels (`#🎯-ge-lc-feed`, `#💻-ccs-drops`, `#💼-rvrcob-drops`, `#⚙️-gcoe-drops`, `#📜-cla-drops`, `#🔬-cos-drops`, `#📚-bagced-drops`, `#📈-soe-drops`).
- 📊 **Drop Analytics (`!stats`):** Visual peak-hour activity windows (e.g. *8:00 AM – 10:00 AM*), course demand leaderboards, and recorded fill speeds.
- 🔍 **In-Discord CourseFinder Search (`!search`):** Search DLSU course codes, titles, and IDs directly in Discord.
- 🔒 **Admin Command Center & Gatekeeper:** Admin controls (`!start`, `!stop`, `!setupchannels`, `!setcurl`, `!userstatus`, `!prune`) with a gatekeeper that restricts non-admin member access while the bot is offline.
- 📬 **Private DM Mirror Log (`#📬-admin-dm-logs`):** Silent private channel mirroring all student DM alerts for transparency.
- 📢 **Public Announcements & Disconnect Watchdog:** Automatically broadcasts `@everyone` announcements when the bot is turned ON/OFF or when session disconnects occur.
- 💓 **1-Minute Pulse Logger:** Continuously probes DLSU CourseFinder every 60s and logs pulse confirmations silently in `#💓-admin-heartbeat-log`.
- ⏱️ **High-Speed 15s Poller:** Scrapes monitored courses every 15 seconds to ensure students catch slot drops rapidly.

---

## 🏛️ Server Channel Structure (`!setupchannels`)

Running `!setupchannels` automatically creates the following categories and channels:

```text
📢 ARCHERSNIPER ANNOUNCEMENTS
└── #📢-announcements        (Public read, @everyone pings: Bot ON/OFF, Disconnect)

🏛️ DLSU COLLEGE FEEDS
├── #🎯-ge-lc-feed           (General Education & Lasallian Core Live Drops)
├── #💻-ccs-drops            (College of Computer Studies)
├── #💼-rvrcob-drops         (RVR College of Business)
├── #⚙️-gcoe-drops           (Gokongwei College of Engineering)
├── #📜-cla-drops            (College of Liberal Arts)
├── #🔬-cos-drops            (College of Science)
├── #📚-bagced-drops         (Br. Andrew Gonzalez College of Education)
└── #📈-soe-drops            (School of Economics)

🔒 ADMIN HQ (Private to Admins)
├── #🔒-admin-commands       (Restricted admin terminal: !setcurl, !start, !stop)
├── #🚨-admin-disconnects    (Emergency HTTP 401 & session timeout alerts)
├── #💓-admin-heartbeat-log  (1-minute keep-alive pulse confirmation logs • Silent)
└── #📬-admin-dm-logs        (Private mirror log of student DM alerts • Silent)
```

---

## 🤖 Bot Commands

### 🎓 Student Commands
| Command | Syntax | Description |
| :--- | :--- | :--- |
| **`!watch`** | `!watch <COURSE> [SEC]` | Subscribe to slot drop DM alerts (e.g. `!watch STSWENG` or `!watch STSWENG S04`). |
| **`!unwatch`** | `!unwatch <COURSE> [SEC]` | Remove a course or subject from your watchlist. |
| **`!watchlist`** | `!watchlist` | View your watched subjects with live slot counts (e.g. `44/45 [1 Open]`). Expands all sections if course was added. |
| **`!monitored`** | `!monitored` | View a concise summary list of what you are tracking. |
| **`!search`** | `!search <query>` | Search DLSU courses by code or title keywords (e.g. `!search web dev`). |
| **`!stats`** | `!stats` | View course drop analytics, peak drop windows, and demand leaderboard. |
| **`!mute`** | `!mute` | Temporarily pause personal DM alerts without deleting your saved watchlist. |
| **`!unmute`** | `!unmute` | Resume personal DM alerts for your watchlist. |
| **`!status`** | `!status [codes...]` | View live capacity progress bars for any course. |
| **`!check`** | `!check` | Force an immediate live scrape across all tracked courses. |
| **`!help`** | `!help` | Open the interactive spacious command guide with button navigation (Student view). |

### 🛡️ Administrative Commands
| Command | Syntax | Description |
| :--- | :--- | :--- |
| **`!setupchannels`**| `!setupchannels` | Auto-provision all categories, college feeds, and admin channels. |
| **`!start`** | `!start` | Turn ON the bot for all students and announce in `#📢-announcements` (`@everyone`). |
| **`!stop`** | `!stop [reason]` | Turn OFF the bot (maintenance mode) and announce in `#📢-announcements` (`@everyone`). |
| **`!userstatus`** | `!userstatus <@member>` | Inspect a member's active watchlist, live section slots, and mute status. |
| **`!prune`** | `!prune` | Clear all student watchlist subscriptions for end-of-term maintenance. |
| **`!setcurl`** | `!setcurl <curl>` | Link / update master browser session cookies. |
| **`!startgelc`** | `!startgelc` | Enable live slot drop feed in `#🎯-ge-lc-feed`. |
| **`!stopgelc`** | `!stopgelc` | Disable live slot drop feed in `#🎯-ge-lc-feed`. |
| **`!interval`** | `!interval <time>` | Change scraper frequency (default: `15s`). |
| **`!health`** | `!health` | View live diagnostics, token validity, and polling stats. |
| **`!add`** | `!add <code>` | Add a course code to the global monitoring pool. |
| **`!remove`** | `!remove <code>` | Remove a course code from the global monitoring pool. |
| **`!sync`** | `!sync` | Sync full course catalog from DLSU CourseFinder API. |

---

## 🔑 How to Extract Master cURL & Cookies

1. Open **Google Chrome** and navigate to [archershub.dlsu.edu.ph/CourseFinder/](https://archershub.dlsu.edu.ph/CourseFinder/) (log in if asked).
2. Press <kbd>F12</kbd> $\rightarrow$ switch to the **Network** tab.
3. Select campus and type any course in the search box (e.g. `STSWENG`) to generate an active request.
4. Right-click the **`GetCFData`** request $\rightarrow$ **Copy as cURL (bash)** *(or Copy as cURL (cmd))*.
5. In your private `#🔒-admin-commands` channel, run:
   ```text
   !setcurl <paste_your_copied_curl_here>
   ```
6. Run `!start` to activate the bot for all students!

---

## 📚 Master Technical Documentation

For an exhaustive, deep-dive understanding of ArcherSniper's internal engine, design patterns, and architectural decisions, explore our complete documentation suite:

* 📖 **[Master Documentation Index](docs/INDEX.md)** — Complete navigation hub.
* 🏛️ **[Architecture & System Design](docs/ARCHITECTURE.md)** — Concurrency model (`asyncio`), in-memory cache vs SQLite, and database lock elimination.
* 🔐 **[4-Tier Authentication & 24/7 Session Keeper](docs/SESSION_KEEPER_AND_AUTH.md)** — Headless Playwright Chromium keeper, 5.5h refuel countdown, and silent re-baseline.
* 🌐 **[DLSU API Client & Scraper Pipeline](docs/API_AND_SCRAPER_ENGINE.md)** — Reverse-engineered endpoints, cookie tokens, and latency optimizations.
* 🎯 **[Course Classification & Dispatch](docs/COURSE_CLASSIFIER_AND_DISPATCH.md)** — Regex matching, college drop feeds, and zero-ping DM alerting.
* 💻 **[Code Explainer & Syntax Guide](docs/CODE_EXPLAINER_AND_SYNTAX_GUIDE.md)** — Syntax deep-dive, Python modern typing, Discord.py Cog architecture, and UI views.

---

## 🧪 Testing

Run the automated unit test suite:
```bash
python -m pytest -v
```

---

## 📄 License
MIT License. Built for De La Salle University students. Animo La Salle! 🏹
