document.getElementById("navToggle")?.addEventListener("click", () => {
  const menu = document.getElementById("mobileMenu");
  const btn = document.getElementById("navToggle");
  const open = menu.classList.toggle("open");
  btn.setAttribute("aria-expanded", open ? "true" : "false");
});

document.querySelectorAll("#mobileMenu a[href^='#']").forEach((link) => {
  link.addEventListener("click", () => {
    document.getElementById("mobileMenu")?.classList.remove("open");
    document.getElementById("navToggle")?.setAttribute("aria-expanded", "false");
  });
});

document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener("click", (e) => {
    const id = anchor.getAttribute("href");
    if (!id || id === "#") return;
    const target = document.querySelector(id);
    if (!target) return;
    e.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});
