// 7° andar — audio player, floor indicator, lazy YouTube.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const audio = $("[data-audio]");
  const np = $("[data-np]");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let current = null; // { src, num, title, href }

  const fmt = (t) => {
    t = Math.max(0, Math.floor(t || 0));
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0");
  };

  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };

  function syncButtons() {
    const playing = current && !audio.paused;
    $$("[data-play]").forEach((b) => b.setAttribute("aria-pressed", String(!!(playing && b.dataset.src === current.src))));
    if (!current) return;
    np.hidden = false;
    np.toggleAttribute("data-paused", audio.paused);
    $("[data-np-toggle]").setAttribute("aria-label", audio.paused ? "Continuar" : "Pausar");
  }

  function load(btn) {
    current = { src: btn.dataset.src, num: btn.dataset.num, title: btn.dataset.title, href: btn.dataset.href };
    audio.src = current.src;
    $("[data-np-num]").textContent = "Andar " + current.num;
    $("[data-np-title]").textContent = current.title;
    $("[data-np-link]").href = current.href;
    const saved = store.get("pos:" + current.src);
    if (saved && saved > 5) audio.addEventListener("loadedmetadata", () => { audio.currentTime = saved; }, { once: true });
    if ("mediaSession" in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: current.title, artist: "7° andar", album: "Episódio " + current.num,
        artwork: [{ src: "/assets/icon-512.png", sizes: "512x512", type: "image/png" }],
      });
    }
  }

  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-play]");
    if (btn) {
      ev.preventDefault();
      if (!current || current.src !== btn.dataset.src) load(btn);
      audio.paused ? audio.play() : audio.pause();
      const scrub = btn.closest("[data-player]")?.querySelector("[data-scrub]");
      if (scrub) scrub.hidden = false;
      return;
    }
    if (ev.target.closest("[data-np-toggle]") && current) audio.paused ? audio.play() : audio.pause();

    const yt = ev.target.closest("[data-yt]");
    if (yt && !yt.querySelector("iframe")) {
      audio.pause();
      const f = document.createElement("iframe");
      f.src = `https://www.youtube-nocookie.com/embed/${yt.dataset.yt}?autoplay=1&rel=0`;
      f.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
      f.title = "Vídeo do episódio no YouTube";
      yt.append(f);
    }
  });

  ["play", "pause", "ended"].forEach((t) => audio.addEventListener(t, syncButtons));
  let lastSave = 0;
  audio.addEventListener("timeupdate", () => {
    if (!current) return;
    const d = audio.duration || 0, t = audio.currentTime;
    $("[data-np-time]").textContent = fmt(t);
    $("[data-np-bar]").style.width = d ? (t / d) * 100 + "%" : "0";
    const seek = $(`[data-player][data-src="${CSS.escape(current.src)}"] [data-seek]`);
    if (seek && !seek.matches(":active")) { seek.value = t; seek.closest("[data-scrub]").querySelector("[data-cur]").textContent = fmt(t); }
    if (Date.now() - lastSave > 4000) { store.set("pos:" + current.src, t); lastSave = Date.now(); }
  });
  $$("[data-seek]").forEach((r) => r.addEventListener("input", () => {
    const p = r.closest("[data-player]");
    if (current && p.dataset.src === current.src) audio.currentTime = +r.value;
    p.querySelector("[data-cur]").textContent = fmt(+r.value);
  }));

  // ---------------------------------------------------------------- floor indicator
  // The page is a 7-storey building: the top of the page is the 7th floor and the
  // bottom is "P" (térreo/portaria, as Brazilian elevators show it). The floor comes
  // from scroll progress alone, so it only ever moves one way as you scroll.
  const floor = $(".floor");
  const num = $("[data-floor]");
  const FLOORS = ["7", "6", "5", "4", "3", "2", "1", "P"];
  const rank = (v) => FLOORS.length - FLOORS.indexOf(v); // P lowest, 7 highest
  const fixed = !FLOORS.includes(num.textContent);       // e.g. the 404 page shows "?"
  let shown = num.textContent, idle, arriving = false;
  const show = (v) => {
    if (v === shown) return;
    floor.dataset.dir = rank(v) > rank(shown) ? "up" : "down";
    num.textContent = shown = v;
    clearTimeout(idle);
    idle = setTimeout(() => (floor.dataset.dir = "idle"), 900);
  };
  const floorAt = () => {
    const max = document.documentElement.scrollHeight - innerHeight;
    if (max <= 0) return "7";
    const p = Math.min(1, Math.max(0, scrollY / max));
    return FLOORS[Math.min(FLOORS.length - 1, Math.floor(p * FLOORS.length))];
  };

  // On the home page the nav follows the section in view, so "Ouvir" lights up on #ouvir.
  const isHome = document.body.dataset.page === "home";
  const listen = isHome && $("#ouvir");
  const navLinks = $$(".top-nav a, .dock a");
  const markNav = () => {
    // "Ouvir" while the section sits in the upper half of the screen, below the header
    const r = listen.getBoundingClientRect(), head = $(".top").getBoundingClientRect().bottom;
    const key = r.top <= innerHeight * 0.5 && r.bottom > head + 40 ? "/#ouvir" : "/";
    navLinks.forEach((a) => {
      const h = a.getAttribute("href");
      if (h === "/" || h === "/#ouvir") h === key ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current");
    });
  };

  let ticking = false;
  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      ticking = false;
      if (!fixed && !arriving) show(floorAt());
      if (listen) markNav();
    });
  };
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", onScroll);

  // arrival: on the first visit the elevator rides up from P to the 7th floor
  if (isHome && !reduce && !sessionStorage.getItem("arrived") && scrollY < 50) {
    try { sessionStorage.setItem("arrived", "1"); } catch {}
    arriving = true;
    let i = FLOORS.length - 1; floor.dataset.dir = "up"; num.textContent = shown = FLOORS[i];
    const tick = setInterval(() => {
      i -= 1; num.textContent = shown = FLOORS[i];
      if (i <= 0) { clearInterval(tick); arriving = false; setTimeout(() => (floor.dataset.dir = "idle"), 500); onScroll(); }
    }, 140);
  } else {
    floor.dataset.dir = "idle";
    onScroll();
  }
})();
