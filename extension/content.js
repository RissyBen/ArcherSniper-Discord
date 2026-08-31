/**
 * ArcherSniper - Client-Side Anti-Inactivity Content Script
 * Injected into archershub.dlsu.edu.ph to defeat browser DOM idle timers and modal popups.
 */

console.log("🏹 [ArcherSniper Anti-Idle] Content script initialized on Archer's Hub.");

// 1. Synthesize user activity (mouse movement, scroll, keypress) every 30 seconds
setInterval(() => {
  try {
    const mouseEvent = new MouseEvent("mousemove", {
      bubbles: true,
      cancelable: true,
      clientX: Math.floor(Math.random() * 500) + 100,
      clientY: Math.floor(Math.random() * 500) + 100,
    });
    document.dispatchEvent(mouseEvent);
    window.dispatchEvent(new Event("scroll"));
    window.dispatchEvent(new Event("focus"));
    // console.log("💓 [ArcherSniper Anti-Idle] Simulated user interaction event dispatched.");
  } catch (err) {
    // Ignore synthetic event errors
  }
}, 30000);

// 2. Automatically close or confirm any "Session Expiring" idle prompt modals
setInterval(() => {
  try {
    // Common session extender buttons and modal confirm buttons
    const extendButtons = document.querySelectorAll(
      "button, a, input[type='button'], input[type='submit']"
    );
    extendButtons.forEach((btn) => {
      const txt = (btn.innerText || btn.value || "").toLowerCase();
      if (
        txt.includes("extend") ||
        txt.includes("continue session") ||
        txt.includes("stay logged in") ||
        txt.includes("keep alive") ||
        txt.includes("i'm still here")
      ) {
        console.log("⚡ [ArcherSniper Anti-Idle] Auto-clicked session extender modal button:", txt);
        btn.click();
      }
    });
  } catch (modalErr) {
    // Ignore modal check errors
  }
}, 10000);

// 3. Keep-alive AJAX pulse directly from webpage origin every 2 minutes
setInterval(async () => {
  try {
    await fetch("https://archershub.dlsu.edu.ph/CourseFinder/GetAllDropDownList/", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: new URLSearchParams({ Campusno: "7" }),
    });
    // console.log("💓 [ArcherSniper Anti-Idle] In-page AJAX heartbeat pulse sent.");
  } catch (fetchErr) {
    // Ignore network errors
  }
}, 120000);
