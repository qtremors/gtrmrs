/**
 * gtrmrs: Interactive Scripts
 * Tab switcher, quick copy, and command table search.
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Terminal Tabs
  const tabButtons = document.querySelectorAll(".term-tab");
  const tabPanes = document.querySelectorAll(".term-pane");

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab");

      tabButtons.forEach((b) => b.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));

      btn.classList.add("active");
      const targetPane = document.getElementById(`pane-${target}`);
      if (targetPane) {
        targetPane.classList.add("active");
      }
    });
  });

  // 2. One-click Copy
  const copyButtons = document.querySelectorAll("[data-copy]");
  copyButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const textToCopy = btn.getAttribute("data-copy");
      if (!textToCopy) return;

      navigator.clipboard.writeText(textToCopy).then(() => {
        const originalHtml = btn.innerHTML;
        btn.innerHTML = `
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="#10b981" stroke-width="2.5">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        `;
        setTimeout(() => {
          btn.innerHTML = originalHtml;
        }, 1800);
      });
    });
  });

  // 3. Command Table Filter
  const searchInput = document.getElementById("cmdSearch");
  const tableRows = document.querySelectorAll("#cmdTable tbody tr");

  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      const query = e.target.value.toLowerCase().trim();
      tableRows.forEach((row) => {
        const text = row.innerText.toLowerCase();
        row.style.display = (!query || text.includes(query)) ? "" : "none";
      });
    });
  }

  // 4. Live GitHub Stats (Stars & Forks only, no downloads)
  fetchGitHubStats();
});

const numberFormatter = new Intl.NumberFormat();
const reduceMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

function animateCounter(element, target) {
  if (!element || !Number.isFinite(target)) return;

  const endValue = Math.max(0, Math.trunc(target));
  if (reduceMotionQuery.matches || endValue === 0) {
    element.textContent = numberFormatter.format(endValue);
    return;
  }

  const duration = 800;
  const startTime = performance.now();

  function updateCounter(currentTime) {
    const progress = Math.min((currentTime - startTime) / duration, 1);
    const easedProgress = 1 - Math.pow(1 - progress, 3);
    element.textContent = numberFormatter.format(Math.round(endValue * easedProgress));

    if (progress < 1) {
      requestAnimationFrame(updateCounter);
    }
  }

  requestAnimationFrame(updateCounter);
}

async function fetchGitHubStats() {
  try {
    const res = await fetch("https://api.github.com/repos/qtremors/gtrmrs");
    if (res.ok) {
      const data = await res.json();
      if (data.stargazers_count !== undefined) {
        animateCounter(document.getElementById("gh-stars"), data.stargazers_count);
      }
      if (data.forks_count !== undefined) {
        animateCounter(document.getElementById("gh-forks"), data.forks_count);
      }
    }
  } catch (err) {
    // Graceful fallback to default placeholder
  }
}

