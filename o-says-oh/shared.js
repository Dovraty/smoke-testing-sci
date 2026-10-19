// Shared helpers for the O says Oh! game pages: saving, sounds, O's voice, the top bar and the win card.
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(r => setTimeout(r, ms));

// Progress is saved only in this browser.
const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem("oSaysOh." + key); return v === null ? fallback : JSON.parse(v); }
    catch (e) { return fallback; }
  },
  set(key, value) { try { localStorage.setItem("oSaysOh." + key, JSON.stringify(value)); } catch (e) {} },
};

// ===== SOUND =====
let soundOn = store.get("sound", true), audioCtx = null;
function tone(freq, dur = .12, type = "triangle", vol = .16, when = 0) {
  if (!soundOn) return;
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const t = audioCtx.currentTime + when, o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t);
    g.gain.setValueAtTime(.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + .02);
    g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(g).connect(audioCtx.destination); o.start(t); o.stop(t + dur + .05);
  } catch (e) {}
}
const chime = () => [523, 659, 784, 1047].forEach((f, i) => tone(f, .25, "triangle", .15, i * .1));
const buzz = () => { tone(180, .25, "sawtooth", .06); tone(130, .3, "sawtooth", .05, .1); };

// ===== O'S VOICE (the browser's voice until O's recorded lines are added) =====
function speak(text) {
  if (!soundOn || !("speechSynthesis" in window)) return;
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US"; u.rate = .9; u.pitch = 1.5;
    speechSynthesis.speak(u);
  } catch (e) {}
}
let lastLine = "";
function say(bubbleId, text, voice = text) {
  const b = $(bubbleId);
  b.textContent = text;
  b.classList.remove("pop"); b.offsetWidth; b.classList.add("pop");
  lastLine = voice;
  speak(voice);
}
function think(bubbleId) {
  $(bubbleId).innerHTML = '<span class="thinking" aria-label="O is thinking"><i></i><i></i><i></i></span>';
}
function animateO(id, cls) {
  const o = $(id);
  o.classList.remove("cheer", "oops"); o.offsetWidth; o.classList.add(cls);
}

const ICONS = {
  home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11 12 4l9 7"/><path d="M5.5 9.5V20h13V9.5"/><path d="M10 20v-5h4v5"/></svg>',
  sound: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3" fill="currentColor"/><circle cx="17" cy="16" r="3" fill="currentColor"/></svg>',
  say: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9H4z" fill="currentColor"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L8.5 3.64A1 1 0 0 0 7 4.5z"/></svg>',
  star: '<svg viewBox="0 0 24 24"><path d="M12 2.6l2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17l-5.7 3.1 1.2-6.4-4.7-4.4 6.4-.8z" fill="#F4B637" stroke="#C98A12" stroke-width="1.3" stroke-linejoin="round"/></svg>',
  starEmpty: '<svg viewBox="0 0 24 24"><path d="M12 2.6l2.8 5.9 6.4.8-4.7 4.4 1.2 6.4L12 17l-5.7 3.1 1.2-6.4-4.7-4.4 6.4-.8z" fill="#D4C1F6"/></svg>',
  yes: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  no: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
};
const starRow = list => list.map(on => on ? ICONS.star : ICONS.starEmpty).join("");

// Top bar: home button (back to all games), hear-again button, sound on/off.
function setupBar() {
  document.querySelectorAll(".home-btn").forEach(a => { a.innerHTML = ICONS.home; a.href = "index.html"; a.setAttribute("aria-label", "All games"); });
  document.querySelectorAll(".say-btn").forEach(b => { b.innerHTML = ICONS.say; b.setAttribute("aria-label", "Hear it again"); b.addEventListener("click", () => speak(lastLine)); });
  const paint = () => document.querySelectorAll(".sound-btn").forEach(b => {
    b.setAttribute("aria-pressed", soundOn); b.setAttribute("aria-label", soundOn ? "Sound on" : "Sound off");
  });
  document.querySelectorAll(".sound-btn").forEach(b => {
    b.innerHTML = ICONS.sound;
    b.addEventListener("click", () => {
      soundOn = !soundOn; store.set("sound", soundOn); paint();
      if (!soundOn && "speechSynthesis" in window) speechSynthesis.cancel();
    });
  });
  paint();
}

// ===== CONFETTI =====
function confetti(fromEl) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let cv = $("fx");
  if (!cv) { cv = document.createElement("canvas"); cv.id = "fx"; document.body.appendChild(cv); }
  const ctx = cv.getContext("2d"), dpr = devicePixelRatio || 1;
  cv.width = innerWidth * dpr; cv.height = innerHeight * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const colors = ["#F4B637", "#8B52DB", "#F49BB6", "#2FB57E", "#FFFFFF"];
  const box = fromEl ? fromEl.getBoundingClientRect() : { left: innerWidth / 2, top: innerHeight / 3, width: 0, height: 0 };
  const bits = Array.from({ length: 100 }, () => ({
    x: box.left + box.width / 2, y: box.top + box.height / 2,
    vx: (Math.random() - .5) * 12, vy: -Math.random() * 13 - 4,
    s: Math.random() * 7 + 5, rot: Math.random() * 6, vr: (Math.random() - .5) * .4,
    c: colors[Math.floor(Math.random() * colors.length)],
  }));
  let frames = 0;
  (function tick() {
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    bits.forEach(b => {
      b.vy += .35; b.x += b.vx; b.y += b.vy; b.rot += b.vr;
      ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.rot); ctx.fillStyle = b.c;
      ctx.fillRect(-b.s / 2, -b.s / 4, b.s, b.s / 2); ctx.restore();
    });
    if (++frames < 140) requestAnimationFrame(tick); else ctx.clearRect(0, 0, innerWidth, innerHeight);
  })();
}

// ===== WIN CARD =====
// showWin({ title, text, stars: [true, false, ...], again: "Play again", onAgain })
function showWin({ title, text = "", stars = [], again = "Play again", onAgain }) {
  let back = $("winCard");
  if (!back) {
    back = document.createElement("div");
    back.className = "card-back"; back.id = "winCard";
    back.innerHTML = `<div class="card" role="dialog" aria-modal="true" aria-labelledby="winTitle">
      <img src="o.webp" alt="">
      <h2 id="winTitle"></h2><p id="winText"></p><div class="stars" id="winStars"></div>
      <div class="row"><a class="btn quiet" href="index.html">All games</a><button class="btn" type="button" id="winAgain"></button></div>
    </div>`;
    document.body.appendChild(back);
  }
  $("winTitle").textContent = title;
  $("winText").textContent = text;
  $("winText").hidden = !text;
  $("winStars").innerHTML = starRow(stars);
  $("winAgain").textContent = again;
  $("winAgain").onclick = () => { back.hidden = true; onAgain && onAgain(); };
  back.hidden = false;
  $("winAgain").focus();
}
