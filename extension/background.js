/**
 * ArcherSniper - Background Auto-Relay & Perpetual Session Refresher (Manifest V3)
 * Keeps Archer's Hub active 24/7 by reloading the tab every 6 minutes and pushing fresh
 * cookies to ArcherSniper localhost:8080.
 */

const BOT_ENDPOINT = "http://34.126.187.63:8080/api/update_cookies";
const SYNC_ALARM_NAME = "archersniper_auto_sync";
const TAB_RELOAD_ALARM_NAME = "archersniper_tab_reload";
const SYNC_INTERVAL_MINUTES = 2;
const TAB_RELOAD_MINUTES = 6; // Reload tab every 6 minutes to guarantee fresh token generation

// Initialize alarms on install/startup
chrome.runtime.onInstalled.addListener(() => {
  console.log("🏹 [ArcherSniper Relay] Installed. Starting auto-sync & perpetual tab reload alarms...");
  chrome.alarms.create(SYNC_ALARM_NAME, { periodInMinutes: SYNC_INTERVAL_MINUTES });
  chrome.alarms.create(TAB_RELOAD_ALARM_NAME, { periodInMinutes: TAB_RELOAD_MINUTES });
  syncCookiesWithBot();
});

chrome.runtime.onStartup.addListener(() => {
  chrome.alarms.create(SYNC_ALARM_NAME, { periodInMinutes: SYNC_INTERVAL_MINUTES });
  chrome.alarms.create(TAB_RELOAD_ALARM_NAME, { periodInMinutes: TAB_RELOAD_MINUTES });
  syncCookiesWithBot();
});

// Alarm triggers
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === SYNC_ALARM_NAME) {
    await syncCookiesWithBot();
  } else if (alarm.name === TAB_RELOAD_ALARM_NAME) {
    await reloadArchersHubTab();
  }
});

// Automatically detect any cookie changes on DLSU domain and push immediately
chrome.cookies.onChanged.addListener((changeInfo) => {
  if (changeInfo.cookie && changeInfo.cookie.domain && changeInfo.cookie.domain.includes("dlsu.edu.ph")) {
    if (!changeInfo.removed && ["__Secure-SID", ".ASPXAUTH", "__RequestVerificationToken"].includes(changeInfo.cookie.name)) {
      console.log(`⚡ [ArcherSniper Relay] Key cookie '${changeInfo.cookie.name}' updated on DLSU. Syncing...`);
      syncCookiesWithBot();
    }
  }
});

// Listen for manual sync requests from Popup UI
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "manual_sync") {
    reloadArchersHubTab().then(() => {
      setTimeout(() => {
        syncCookiesWithBot().then((result) => {
          sendResponse(result);
        });
      }, 1500);
    });
    return true;
  }
});

/**
 * Reloads the Archer's Hub background tab to force DLSU server to issue fresh 25-minute tokens.
 */
async function reloadArchersHubTab() {
  try {
    const tabs = await chrome.tabs.query({ url: "*://archershub.dlsu.edu.ph/*" });
    if (tabs && tabs.length > 0) {
      console.log(`🔄 [ArcherSniper Relay] Refreshing Archer's Hub tab (${tabs[0].id}) for fresh session token generation...`);
      await chrome.tabs.reload(tabs[0].id);
      // Give page 2 seconds to load before capturing new cookies
      setTimeout(syncCookiesWithBot, 2000);
    }
  } catch (err) {
    console.debug("Tab reload notice:", err);
  }
}

/**
 * Extracts all cookies for Archer's Hub and sends them to the local Discord Bot webhook.
 */
async function syncCookiesWithBot() {
  try {
    // 1. Extract all cookies across all DLSU & Archer's Hub scopes
    const [domainCookies, urlCookies, dlsuCookies] = await Promise.all([
      chrome.cookies.getAll({ domain: "archershub.dlsu.edu.ph" }),
      chrome.cookies.getAll({ url: "https://archershub.dlsu.edu.ph/CourseFinder/" }),
      chrome.cookies.getAll({ domain: ".dlsu.edu.ph" }),
    ]);

    // Combine and deduplicate
    const cookieMap = new Map();
    [...domainCookies, ...urlCookies, ...dlsuCookies].forEach((c) => {
      if (c && c.name && c.value) {
        cookieMap.set(c.name, c.value);
      }
    });

    if (cookieMap.size === 0) {
      const msg = "No Archer's Hub cookies found. Please log in to CourseFinder in Chrome.";
      console.warn("⚠️ [ArcherSniper Relay]", msg);
      await updateStatus("warning", msg, 0);
      return { success: false, message: msg, count: 0 };
    }

    const cookieParts = [];
    cookieMap.forEach((val, name) => {
      cookieParts.push(`${name}=${val}`);
    });
    const cookieString = cookieParts.join("; ");

    // 2. Send payload to Bot Webhook
    const response = await fetch(BOT_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ cookies: cookieString }),
    });

    if (response.ok) {
      const data = await response.json();
      const successMsg = `Successfully synced ${cookieMap.size} cookies with ArcherSniper!`;
      console.log("🟢 [ArcherSniper Relay]", successMsg);
      await updateStatus("connected", successMsg, cookieMap.size);
      return { success: true, message: successMsg, count: cookieMap.size };
    } else {
      const errMsg = `Bot returned HTTP ${response.status}. Ensure 'python bot.py' is running.`;
      console.error("🔴 [ArcherSniper Relay]", errMsg);
      await updateStatus("error", errMsg, cookieMap.size);
      return { success: false, message: errMsg, count: cookieMap.size };
    }
  } catch (error) {
    const connErr = "Cannot reach bot on http://localhost:8080. Ensure 'python bot.py' is running.";
    console.error("🔴 [ArcherSniper Relay] Connection error:", error);
    await updateStatus("error", connErr, 0);
    return { success: false, message: connErr, count: 0 };
  }
}

/**
 * Updates local extension state and icon badge.
 */
async function updateStatus(state, message, count) {
  const now = new Date().toLocaleTimeString();
  await chrome.storage.local.set({
    lastSyncState: state,
    lastSyncMessage: message,
    lastSyncTime: now,
    cookieCount: count,
  });

  if (state === "connected") {
    chrome.action.setBadgeText({ text: "ON" });
    chrome.action.setBadgeBackgroundColor({ color: "#006837" }); // DLSU Green
  } else if (state === "warning") {
    chrome.action.setBadgeText({ text: "LOG" });
    chrome.action.setBadgeBackgroundColor({ color: "#F59E0B" }); // Gold
  } else {
    chrome.action.setBadgeText({ text: "OFF" });
    chrome.action.setBadgeBackgroundColor({ color: "#DC2626" }); // Red
  }
}
