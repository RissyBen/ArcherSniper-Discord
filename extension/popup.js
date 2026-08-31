/**
 * ArcherSniper Popup Script
 */

document.addEventListener("DOMContentLoaded", async () => {
  const statusCard = document.getElementById("status-card");
  const statusText = document.getElementById("status-text");
  const statusDetail = document.getElementById("status-detail");
  const statCount = document.getElementById("stat-count");
  const statTime = document.getElementById("stat-time");
  const syncBtn = document.getElementById("sync-btn");

  // Load stored state
  async function loadState() {
    const data = await chrome.storage.local.get([
      "lastSyncState",
      "lastSyncMessage",
      "lastSyncTime",
      "cookieCount",
    ]);

    const state = data.lastSyncState || "unknown";
    statusCard.className = `status-card ${state}`;

    if (state === "connected") {
      statusText.textContent = "Relay Active (Connected)";
      statusDetail.textContent = data.lastSyncMessage || "Session is active and syncing with ArcherSniper.";
    } else if (state === "warning") {
      statusText.textContent = "Archer's Hub Login Required";
      statusDetail.textContent = data.lastSyncMessage || "Please open Archer's Hub and log in.";
    } else if (state === "error") {
      statusText.textContent = "Bot Offline (Check Terminal)";
      statusDetail.textContent = data.lastSyncMessage || "Cannot reach http://localhost:8080. Start bot with 'python bot.py'.";
    } else {
      statusText.textContent = "Ready to Sync";
      statusDetail.textContent = "Click 'Sync Now' to connect with ArcherSniper.";
    }

    statCount.textContent = data.cookieCount !== undefined ? data.cookieCount : "--";
    statTime.textContent = data.lastSyncTime || "Never";
  }

  await loadState();

  // Trigger manual sync
  syncBtn.addEventListener("click", async () => {
    syncBtn.disabled = true;
    syncBtn.innerHTML = "<span class='btn-icon'>⏳</span> Syncing...";

    chrome.runtime.sendMessage({ action: "manual_sync" }, async (response) => {
      await loadState();
      syncBtn.disabled = false;
      syncBtn.innerHTML = "<span class='btn-icon'>⚡</span> Sync Now";
    });
  });
});
