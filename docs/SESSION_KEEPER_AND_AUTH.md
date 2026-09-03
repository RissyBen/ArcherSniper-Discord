# 🔐 4-Tier Authentication & 24/7 Session Keeper

This document details the multi-tier authentication architecture, the 24/7 Headless Chromium Persistent Session Keeper, session token lifetimes, and self-healing mechanisms.

---

## 1. The 4-Tier Zero-Touch Self-Healing Hierarchy

ArcherSniper operates an autonomous, 4-tier authentication recovery system designed to maintain 100% uptime with zero manual maintenance:

```text
┌────────────────────────────────────────────────────────┐
│  Tier 1: 10-Second Fast Portal Probe                   │
│  • Silently re-tests gateway on minor network drops    │
└──────────────────────────┬─────────────────────────────┘
                           ▼ (If failed)
┌────────────────────────────────────────────────────────┐
│  Tier 2: 24/7 Headless Chromium Persistent Keeper      │
│  • Reads live cookies from background browser context  │
│  • Autonomous 5-minute full page reload keep-alive     │
└──────────────────────────┬─────────────────────────────┘
                           ▼ (If failed)
┌────────────────────────────────────────────────────────┐
│  Tier 3: Localhost Webhook Web Server (:8080)          │
│  • Receives 1-click updates from Extension / Bookmarklet│
│  • Instantly updates DB and notifies Engine            │
└──────────────────────────┬─────────────────────────────┘
                           ▼ (If failed)
┌────────────────────────────────────────────────────────┐
│  Tier 4: Discord Admin Commands (!setcurl / !keeper)    │
│  • Manual fail-safe terminal for administrators        │
└────────────────────────────────────────────────────────┘
```

---

## 2. Tier 2: 24/7 Headless Chromium Session Keeper

### 2.1 Why a Headless Browser?
DLSU's CourseFinder requires valid session cookies originating from authenticated university Single Sign-On (SSO). If an admin closes their browser tab on their PC or phone, the session would historically terminate. 

To achieve 100% tab freedom, ArcherSniper launches an invisible **Chromium browser via Playwright** directly on your Cloud VM.

### 2.2 Persistent Context (`data/browser_profile/`)
Instead of launching an ephemeral browser that loses state on exit, the keeper uses:
```python
self._browser_context = await self._playwright.chromium.launch_persistent_context(
    user_data_dir=str(self.profile_dir),
    headless=True,
    args=[
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
    ]
)
```
* **Persistent Disk Profile:** All cookies, localStorage, session states, and verification tokens persist in `data/browser_profile/` across bot restarts.
* **Background Flags:** The Chromium flags prevent Linux from throttling background browser execution timers.

### 2.3 The 5-Minute Keep-Alive Pulse: AJAX vs. Full Page Reload
* **The Failure of Minor AJAX (`window.fetch`):** Initially, the keep-alive pulse sent small JavaScript `fetch()` calls to `/CourseFinder/GetAllDropDownList/`. However, on DLSU's ASP.NET IIS server, background AJAX calls **do not reset the server's session sliding timer**. The session still expired after 25 minutes.
* **The Solution — Full Page Navigation:** Every 5 minutes, the keeper performs a real navigation:
  ```python
  response = await self._page.goto(self.target_url, wait_until="domcontentloaded", timeout=25000)
  ```
  A full page navigation forces IIS to execute the complete ASP.NET page lifecycle, resetting the sliding expiration window continuously.

### 2.4 Login Page Overwrite Guard
When an unauthenticated session redirects to `/Account/Login`, the login page issues blank, unauthenticated cookies. 
The keeper features an active guard:
```python
if self._page and ("login" in self._page.url.lower() or "signin" in self._page.url.lower()):
    logger.warning("Headless page is at login URL. Suppressing cookie harvest.")
    return {}
```
This guarantees the database is **never overwritten** by unauthenticated login page tokens!

---

## 3. Sliding Expiration vs. Absolute Expiration

Understanding how DLSU terminates sessions:

| Timer Type | Duration | Description | Handled By |
| :--- | :--- | :--- | :--- |
| **Sliding Expiration** | 20–25 Minutes | Idle timeout. If no page request is received for 25 minutes, IIS kills the session. | **5-Minute Full Page Reload Pulse** keeps this alive 24/7. |
| **Absolute Expiration** | 6.0–8.0 Hours | Cryptographic SSO ticket lifetime. DLSU's central identity server puts a hard expiration date on the auth ticket. Once this runs out, the server rejects requests regardless of activity. | **Proactive 5.5-Hour Refuel Notice** notifies admin to tap extension. |

---

## 4. Proactive 5.5-Hour Refuel Countdown Notice

At **5 hours and 30 minutes** (30 minutes before the 6-hour token ceiling), the engine sends a proactive refuel card to `#🚨-admin-disconnects`:

```text
⏰ Master Session Refuel Notice (5.5+ Hours)
Current Archer's Hub browser session has been active for 5.5 hours.

⏱️ Estimated SSO Expiry: ~30 minutes remaining (6.0h DLSU max).
🛡️ Status: Currently connected & actively monitoring.

💡 Action (1-Tap): Click your ArcherSniper Extension (or 1-tap phone bookmarklet)
to reset your 6-hour runway before data goes stale!
```

---

## 5. Post-Reconnect Silent Re-Baseline

### 5.1 The Problem It Solves
When a session was reconnected after being disconnected or after a 6-hour refresh, DLSU seats had naturally opened up during the downtime. Historically, the bot saw all those open seats as "brand new drops" and dumped 15–20 course alerts at once, flooding channels and pinging students for old drops.

### 5.2 The Solution
In `engine.py`, reconnection sets a re-baseline flag:
```python
self.needs_rebaseline = True
```
During the first poll cycle after reconnecting:
```python
if self.total_poll_cycles <= 1 or self.needs_rebaseline:
    self.section_slot_cache[cache_key] = new_open
    return # Silently absorb into cache; 0 alerts sent!
```
At the end of Cycle 1, `needs_rebaseline` is reset to `False`. Starting on Cycle 2 (15 seconds later), only **fresh, live drops** that happen *from that moment forward* trigger alerts!
