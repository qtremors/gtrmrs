"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const tabs = Array.from(document.querySelectorAll("[data-tab]"));
  const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));
  const command = document.getElementById("demo-command");
  const demoCopy = document.getElementById("demo-copy");
  const status = document.getElementById("copy-status");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function activate(name, focus = false) {
    const selected = tabs.find((tab) => tab.dataset.tab === name);
    const panel = document.getElementById("panel-" + name);
    if (!selected || !panel) return;
    tabs.forEach((tab) => {
      const active = tab === selected;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    panels.forEach((item) => { item.hidden = item !== panel; });
    command.textContent = panel.dataset.command;
    demoCopy.dataset.copy = panel.dataset.command;
    if (focus) selected.focus();
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(tab.dataset.tab));
    tab.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabs.length - 1;
      else return;
      event.preventDefault();
      activate(tabs[next].dataset.tab, true);
    });
  });

  document.querySelectorAll("[data-demo]").forEach((button) => {
    button.addEventListener("click", () => {
      activate(button.dataset.demo, true);
      document.getElementById("playground").scrollIntoView({
        behavior: reduceMotion.matches ? "auto" : "smooth", block: "start"
      });
    });
  });

  document.querySelectorAll("[data-copy]").forEach((button) => {
    let reset;
    const original = button.innerHTML;
    button.addEventListener("click", async () => {
      clearTimeout(reset);
      try {
        if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
        await navigator.clipboard.writeText(button.dataset.copy);
        button.textContent = "Copied!";
        status.textContent = "Command copied to clipboard.";
      } catch {
        button.textContent = "Select to copy";
        status.textContent = "Clipboard unavailable. Select and copy the command text.";
      }
      reset = setTimeout(() => { button.innerHTML = original; }, 1800);
    });
  });
});
