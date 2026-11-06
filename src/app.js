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
  const floor = $(".floor");
  const num = $("[data-floor]");
  const setFloor = (n, dir) => {
    if (num.textContent !== String(n)) num.textContent = n;
    floor.dataset.dir = dir;
  };
  const rows = $$("[data-floor-of]");
  if (rows.length) {
    let lastY = scrollY, idle;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) setFloor(en.target.dataset.floorOf, scrollY >= lastY ? "down" : "up");
      });
      lastY = scrollY;
      clearTimeout(idle);
      idle = setTimeout(() => (floor.dataset.dir = "idle"), 900);
    }, { rootMargin: "-45% 0px -50% 0px" });
    rows.forEach((r) => io.observe(r));
    // back above the building: we're on the 7th floor again
    const top = new IntersectionObserver(([en]) => { if (en.isIntersecting) setFloor(num.dataset.home || "7", "idle"); });
    const hero = $(".hero, .page-head");
    if (hero) top.observe(hero);
  }
  num.dataset.home = num.textContent;

  // arrival: the indicator counts up to the floor on first load of the home page
  if (document.body.dataset.page === "home" && !reduce && !sessionStorage.getItem("arrived")) {
    try { sessionStorage.setItem("arrived", "1"); } catch {}
    let i = 1; floor.dataset.dir = "up"; num.textContent = i;
    const tick = setInterval(() => {
      i += 1; num.textContent = i;
      if (i >= 7) { clearInterval(tick); setTimeout(() => (floor.dataset.dir = "idle"), 500); }
    }, 130);
  } else {
    floor.dataset.dir = "idle";
  }
})();
