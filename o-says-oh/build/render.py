"""O Says OH! — "Is it scary... or fun-scary?" reel renderer.

Animates the six storyboard stills (camera push, squash/stretch bounce,
voice-driven mouth), pops in the titles and FUN-SCARY / TOO SCARY bubbles,
and mixes placeholder VO + synthesized music and SFX.
Swap the files in build/vo/line{1..6}.wav for the real voice and re-run.
"""
import math, random, subprocess, sys
import numpy as np, cv2, soundfile as sf
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = "/home/user/smoke-testing-sci/o-says-oh/"
IMG = ROOT + "scenes/"
VO = ROOT + "build/vo/"
FONT = ROOT + "assets/Baloo2.ttf"
OUT = ROOT + "o_says_oh_fun_scary.mp4"
W, H, FPS, SR = 1080, 1920, 30, 48000
XF = 0.3  # crossfade seconds
PURPLE, WHITE = (59, 22, 122), (255, 255, 255)
PREVIEW = "--preview" in sys.argv


def font(size, weight=800):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


# ---------------------------------------------------------------- scenes
# Source-image coordinates (941x1672). Times are local to the scene.
SCENES = [
    dict(img="1_intro.webp", dur=4.2, vo=1, vo_at=0.6,
         title=["Is it scary...", "or fun-scary?"], title_at=0.25, title_size=118,
         chars=[dict(c=(390, 870), r=(300, 330), base=1130, amp=0.014)],
         mouth=dict(c=(476, 872), w=34, h=30), focus=(470, 820), zoom=(1.0, 1.06)),
    dict(img="2_mask.webp", dur=4.0, vo=2, vo_at=0.35,
         title=["A mask?"], title_at=0.15, title_size=124,
         bubbles=(0.9, 1.05), choose=("fun", 1.37),
         chars=[dict(c=(330, 680), r=(260, 300), base=920, amp=0.014)],
         mouth=dict(c=(395, 740), w=44, h=34), focus=(470, 800), zoom=(1.0, 1.06)),
    dict(img="3_hallway.webp", dur=4.3, vo=3, vo_at=0.35,
         title=["A dark hallway?"], title_at=0.15, title_size=116,
         bubbles=(0.9, 1.05), choose=("too", 1.62),
         chars=[dict(c=(365, 840), r=(190, 340), base=1180, amp=0.007)],
         mouth=dict(c=(344, 838), w=26, h=28), focus=(420, 820), zoom=(1.0, 1.07)),
    dict(img="4_ghost.webp", dur=4.6, vo=4, vo_at=0.35,
         title=["A spooky sound?"], title_at=0.15, title_size=116,
         bubbles=(0.85, 1.0), choose=("fun", 1.95), boo=1.3, bub_y=1450,
         chars=[dict(c=(300, 830), r=(240, 330), base=1140, amp=0.014),
                dict(c=(700, 770), r=(270, 310), float=10, phase=1.3)],
         mouth=dict(c=(357, 833), w=28, h=36), focus=(470, 820), zoom=(1.0, 1.05)),
    dict(img="5_friend.webp", dur=4.0, vo=5, vo_at=0.35,
         title=["A friend in", "a costume?"], title_at=0.15, title_size=112,
         bubbles=(0.9, 1.05), choose=("fun", 1.73),
         chars=[dict(c=(290, 810), r=(240, 300), base=1050, amp=0.016),
                dict(c=(690, 790), r=(250, 290), base=1060, amp=0.016, phase=2.0)],
         mouth=dict(c=(338, 795), w=52, h=40), focus=(470, 800), zoom=(1.0, 1.05)),
    dict(img="6_final.webp", dur=9.0, vo=6, vo_at=0.5,
         title=["It's okay to", "take the mask off."], title_at=0.3, title_size=104,
         sub=["Halloween can feel fun...", "or too scary. Both are okay."], sub_at=2.46,
         hearts=2.6, outro=6.6,
         chars=[dict(c=(450, 800), r=(330, 370), base=1130, amp=0.012)],
         mouth=dict(c=(455, 777), w=62, h=42), focus=(470, 820), zoom=(1.0, 1.07)),
]

# global start times
t = 0.0
for s in SCENES:
    s["start"] = t
    t += s["dur"] - XF
TOTAL = SCENES[-1]["start"] + SCENES[-1]["dur"]
NF = int(round(TOTAL * FPS))


# ---------------------------------------------------------------- audio helpers
def load_vo(i):
    a, sr = sf.read(f"{VO}line{i}.wav")
    if a.ndim > 1:
        a = a.mean(1)
    if sr != SR:
        a = np.interp(np.arange(0, len(a), sr / SR), np.arange(len(a)), a)
    return a.astype(np.float32)


VOS = {s["vo"]: load_vo(s["vo"]) for s in SCENES}


def envelope(a):
    """Per-video-frame mouth openness 0..1."""
    hop = SR // FPS
    e = np.array([np.sqrt((a[j:j + hop] ** 2).mean()) for j in range(0, len(a), hop)])
    e = np.clip((e - 0.015) / 0.09, 0, 1)
    out = np.zeros_like(e)  # fast attack, slower release
    for k in range(len(e)):
        prev = out[k - 1] if k else 0
        out[k] = e[k] if e[k] > prev else prev * 0.55 + e[k] * 0.45
    return out


ENVS = {k: envelope(v) for k, v in VOS.items()}


def vo_env(s, lt):
    e = ENVS[s["vo"]]
    k = int((lt - s["vo_at"]) * FPS)
    return float(e[k]) if 0 <= k < len(e) else 0.0


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def back_out(x):
    x = clamp(x)
    c1 = 1.9
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ease_io(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def pop(lt, at, d=0.38):
    """scale for a pop-in starting at `at`"""
    return back_out((lt - at) / d) if lt >= at else 0.0


# ---------------------------------------------------------------- sprites
def text_sprite(lines, size, fill=PURPLE, stroke=14, line_gap=0.92):
    f = font(size)
    asc, desc = f.getmetrics()
    lh = int(size * line_gap)
    widths = [f.getbbox(l, stroke_width=stroke)[2] for l in lines]
    w = max(widths) + 60
    h = lh * (len(lines) - 1) + asc + desc + 60
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(layer), ImageDraw.Draw(shadow)
    for i, l in enumerate(lines):
        x = (w - widths[i]) // 2 + stroke // 2
        y = 24 + i * lh
        ds.text((x + 4, y + 9), l, font=f, fill=(40, 10, 90, 150), stroke_width=stroke,
                stroke_fill=(40, 10, 90, 150))
        d.text((x, y), l, font=f, fill=fill, stroke_width=stroke, stroke_fill=WHITE)
    shadow = shadow.filter(ImageFilter.GaussianBlur(7))
    return Image.alpha_composite(shadow, layer)


def bubble_sprite(lines, top, bottom, tail_left):
    bw, bh, pad = 268, 196, 40
    S = 2  # supersample
    im = Image.new("RGBA", ((bw + 2 * pad) * S, (bh + 2 * pad + 40) * S), (0, 0, 0, 0))
    # gradient fill
    grad = Image.new("RGBA", im.size)
    gd = ImageDraw.Draw(grad)
    for y in range(im.size[1]):
        k = y / im.size[1]
        gd.line([(0, y), (im.size[0], y)],
                fill=tuple(int(top[i] * (1 - k) + bottom[i] * k) for i in range(3)) + (255,))
    mask = Image.new("L", im.size, 0)
    md = ImageDraw.Draw(mask)
    box = (pad * S, pad * S, (pad + bw) * S, (pad + bh) * S)
    md.rounded_rectangle(box, radius=90 * S, fill=255)
    tx = (pad + (60 if tail_left else bw - 60)) * S
    ty = (pad + bh - 12) * S
    tail = [(tx - 26 * S, ty - 10 * S), (tx + 26 * S, ty - 10 * S),
            (tx + (-30 if tail_left else 30) * S, ty + 46 * S)]
    md.polygon(tail, fill=255)
    outline = mask.filter(ImageFilter.MaxFilter(17))
    shadow = outline.filter(ImageFilter.GaussianBlur(10))
    base = Image.new("RGBA", im.size, (0, 0, 0, 0))
    base.paste((40, 10, 90, 110), (6 * S, 12 * S), shadow)
    base.paste((255, 255, 255, 255), (0, 0), outline)
    base.paste(grad, (0, 0), mask)
    # glossy highlight
    hl = Image.new("L", im.size, 0)
    ImageDraw.Draw(hl).rounded_rectangle(
        ((pad + 26) * S, (pad + 14) * S, (pad + bw - 70) * S, (pad + 52) * S), radius=20 * S, fill=70)
    base.paste((255, 255, 255, 255), (0, 0), hl.filter(ImageFilter.GaussianBlur(6 * S)))
    d = ImageDraw.Draw(base)
    f = font(62 * S)
    for i, l in enumerate(lines):
        tw = f.getbbox(l, stroke_width=4 * S)[2]
        d.text(((im.size[0] - tw) // 2, (pad + 26 + i * 64) * S), l, font=f, fill=PURPLE,
               stroke_width=4 * S, stroke_fill=WHITE)
    return base.resize((im.size[0] // S, im.size[1] // S), Image.LANCZOS)


def glow_sprite(r, color):
    s = 4 * r
    y, x = np.mgrid[0:s, 0:s] - s / 2
    a = np.exp(-(x ** 2 + y ** 2) / (2 * (r * 0.55) ** 2))
    core = np.exp(-(x ** 2 + y ** 2) / (2 * (r * 0.16) ** 2))
    arr = np.zeros((s, s, 4), np.uint8)
    arr[..., 0], arr[..., 1], arr[..., 2] = color
    arr[..., 3] = np.clip((a * 0.55 + core) * 255, 0, 255)
    return Image.fromarray(arr, "RGBA")


def star_sprite(r, color=(255, 214, 64)):
    S = 3
    im = Image.new("RGBA", (r * 2 * S + 8, r * 2 * S + 8), (0, 0, 0, 0))
    c = im.size[0] / 2
    pts = []
    for k in range(10):
        ang = -math.pi / 2 + k * math.pi / 5
        rr = r * S if k % 2 == 0 else r * S * 0.45
        pts.append((c + rr * math.cos(ang), c + rr * math.sin(ang)))
    d = ImageDraw.Draw(im)
    d.polygon(pts, fill=color + (255,), outline=WHITE + (255,))
    return im.resize((im.size[0] // S, im.size[1] // S), Image.LANCZOS)


def heart_sprite(size, color=(122, 72, 214)):
    S = 4
    n = size * S
    im = Image.new("RGBA", (n + 40, n + 40), (0, 0, 0, 0))
    pts = []
    for k in range(200):
        th = k / 200 * 2 * math.pi
        x = 16 * math.sin(th) ** 3
        y = -(13 * math.cos(th) - 5 * math.cos(2 * th) - 2 * math.cos(3 * th) - math.cos(4 * th))
        pts.append((im.size[0] / 2 + x * n / 34, im.size[1] / 2 + y * n / 34))
    d = ImageDraw.Draw(im)
    d.line(pts + [pts[0]], fill=WHITE + (255,), width=10 * S, joint="curve")
    d.line(pts + [pts[0]], fill=color + (255,), width=5 * S, joint="curve")
    return im.resize((im.size[0] // S, im.size[1] // S), Image.LANCZOS)


def burst_sprite(text):
    S = 2
    R = 150
    im = Image.new("RGBA", (R * 2 * S + 60, R * 2 * S + 60), (0, 0, 0, 0))
    c = im.size[0] / 2
    pts = []
    rnd = random.Random(3)
    for k in range(26):
        ang = k * 2 * math.pi / 26
        rr = (R if k % 2 == 0 else R * 0.72) * S * (0.94 + 0.12 * rnd.random())
        pts.append((c + rr * math.cos(ang), c + rr * 0.72 * math.sin(ang)))
    d = ImageDraw.Draw(im)
    big = [(c + (x - c) * 1.07, c + (y - c) * 1.07) for x, y in pts]
    d.polygon(big, fill=PURPLE + (255,))
    d.polygon(pts, fill=(255, 252, 244, 255))
    f = font(104 * S)
    bb = f.getbbox(text)
    d.text((c - (bb[2] - bb[0]) / 2 - bb[0], c - (bb[3] - bb[1]) / 2 - bb[1]), text, font=f, fill=PURPLE)
    return im.resize((im.size[0] // S, im.size[1] // S), Image.LANCZOS)


def dash_sprite():
    im = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for ang in (-150, -115, -80):
        a = math.radians(ang)
        x0, y0 = 60 + 22 * math.cos(a), 60 + 22 * math.sin(a)
        x1, y1 = 60 + 52 * math.cos(a), 60 + 52 * math.sin(a)
        d.line((x0, y0, x1, y1), fill=(255, 210, 40, 255), width=9)
    return im


SPR = {}
for i, s in enumerate(SCENES):
    s["title_spr"] = text_sprite(s["title"], s["title_size"])
    if "sub" in s:
        s["sub_spr"] = text_sprite(s["sub"], 66, stroke=10, line_gap=1.0)
SPR["fun"] = bubble_sprite(["FUN-", "SCARY!"], (178, 240, 110), (98, 196, 52), True)
SPR["too"] = bubble_sprite(["TOO", "SCARY!"], (255, 196, 92), (255, 136, 24), False)
SPR["glow"] = glow_sprite(14, (255, 230, 170))
SPR["star"] = star_sprite(16)
SPR["heart"] = heart_sprite(64)
SPR["boo"] = burst_sprite("BOO!")
SPR["dash"] = dash_sprite()
SPR["logo"] = text_sprite(["O Says OH!"], 150)
SPR["tag"] = text_sprite(["Curious about everything."], 62, stroke=9)


def paste(canvas, spr, cx, cy, scale=1.0, rot=0.0, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    im = spr
    if abs(scale - 1) > 1e-3:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    if abs(rot) > 0.05:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999:
        a = im.getchannel("A").point(lambda v: int(v * alpha))
        im = im.copy()
        im.putalpha(a)
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


# ---------------------------------------------------------------- image warping
for s in SCENES:
    src = cv2.imread(IMG + s["img"], cv2.IMREAD_COLOR)
    s["src"] = src
    hh, ww = src.shape[:2]
    gy, gx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    s["grid"] = (gx, gy)
    for ch in s["chars"]:
        cx, cy = ch["c"]
        rx, ry = ch["r"]
        d = np.sqrt(((gx - cx) / rx) ** 2 + ((gy - cy) / ry) ** 2)
        ch["wt"] = np.clip((1.35 - d) / 0.55, 0, 1).astype(np.float32) ** 1.5
    m = s["mouth"]
    mcx, mcy = m["c"]
    d = np.sqrt(((gx - mcx) / (m["w"] * 1.1)) ** 2 + ((gy - (mcy + m["h"] * 0.15)) / (m["h"] * 1.35)) ** 2)
    s["mwt"] = np.clip((1.25 - d) / 0.5, 0, 1).astype(np.float32)
    # random particles per scene
    rnd = random.Random(hash(s["img"]) & 0xffff)
    s["parts"] = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(0.4, 1.0), rnd.uniform(0, 6.28),
                   rnd.uniform(18, 45)) for _ in range(18)]


def warped(s, lt, env):
    gx, gy = s["grid"]
    mx, my = gx.copy(), gy.copy()
    for ch in s["chars"]:
        ph = ch.get("phase", 0.0)
        if "float" in ch:
            dy = ch["float"] * math.sin(2 * math.pi * 0.55 * lt + ph)
            dx = 4 * math.sin(2 * math.pi * 0.3 * lt + ph)
            mx -= ch["wt"] * dx
            my -= ch["wt"] * dy
            continue
        amp = ch["amp"] * (1 + (1.2 * env if ch is s["chars"][0] else 0))
        sq = amp * math.sin(2 * math.pi * 0.62 * lt + ph)
        sy, sx = 1 + sq, 1 - sq * 0.6
        cx, base = ch["c"][0], ch["base"]
        tx = cx + (gx - cx) / sx
        ty = base + (gy - base) / sy
        mx += ch["wt"] * (tx - gx)
        my += ch["wt"] * (ty - gy)
    if env > 0.01:
        m = s["mouth"]
        top = m["c"][1] - m["h"] * 0.5
        sy, sx = 1 + 0.75 * env, 1 - 0.12 * env
        tx = m["c"][0] + (gx - m["c"][0]) / sx
        ty = top + (gy - top) / sy
        mx += s["mwt"] * (tx - gx)
        my += s["mwt"] * (ty - gy)
    return cv2.remap(s["src"], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def camera(s, img, lt, shake=(0, 0)):
    hh, ww = img.shape[:2]
    base = max(W / ww, H / hh)
    z0, z1 = s["zoom"]
    z = base * (z0 + (z1 - z0) * ease_io(lt / s["dur"]))
    fx, fy = s["focus"]
    # keep focus point drifting from frame-centre toward focus
    k = ease_io(lt / s["dur"])
    cx = ww / 2 + (fx - ww / 2) * 0.35 * k
    cy = hh / 2 + (fy - hh / 2) * 0.35 * k
    M = np.float32([[z, 0, W / 2 - cx * z + shake[0]], [0, z, H / 2 - cy * z + shake[1]]])
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


# ---------------------------------------------------------------- overlays
BUB_X = {"fun": 370, "too": 720}


def overlays(s, lt, canvas):
    # drifting sparkle particles
    for (x, y, sc, ph, sp) in s["parts"]:
        yy = (y - sp * lt) % H
        tw = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(lt * 2.6 + ph))
        paste(canvas, SPR["glow"], x + 10 * math.sin(lt * 0.8 + ph), yy, sc, alpha=0.55 * tw)

    outro = s.get("outro")
    fade_out = 1 - ease_io((lt - outro) / 0.4) if outro else 1.0

    # title
    sc = pop(lt, s["title_at"], 0.45)
    wob = 1 + 0.015 * math.sin(lt * 3.1)
    ty = 215 if len(s["title"]) == 1 else 255
    paste(canvas, s["title_spr"], W / 2, ty, sc * wob, rot=1.5 * math.sin(lt * 1.7), alpha=fade_out)

    # bubbles
    if "bubbles" in s:
        by = s.get("bub_y", 1400)
        choice, ct = s["choose"]
        for key, at in zip(("fun", "too"), s["bubbles"]):
            sc = pop(lt, at, 0.4)
            rot = 4 if key == "fun" else -4
            alpha = 1.0
            yoff = 6 * math.sin(lt * 2.4 + (0 if key == "fun" else 1.5))
            if lt > ct:
                k = clamp((lt - ct) / 0.35)
                if key == choice:
                    sc *= 1 + 0.22 * back_out(k) + 0.03 * math.sin((lt - ct) * 9)
                    rot += 6 * math.sin(min(lt - ct, 0.6) * 22) * (1 - k)
                else:
                    sc *= 1 - 0.18 * ease_io(k)
                    alpha = 1 - 0.55 * ease_io(k)
            paste(canvas, SPR[key], BUB_X[key], by + yoff, sc, rot, alpha)
            if key == choice and lt > ct:
                # celebratory stars
                e = lt - ct
                for j in range(7):
                    ang = j * 2 * math.pi / 7 + 0.3
                    r = 70 + 260 * ease_io(e / 0.7)
                    a = clamp(1 - (e - 0.25) / 0.6)
                    paste(canvas, SPR["star"], BUB_X[key] + r * math.cos(ang),
                          by - 10 + r * 0.8 * math.sin(ang), 0.9, rot=e * 200, alpha=a)
        # little yellow "excited" dashes
        d0 = s["bubbles"][0]
        paste(canvas, SPR["dash"], BUB_X["fun"] - 150, by - 90, pop(lt, d0 + 0.1, 0.3) * 1.1, rot=10)

    if "boo" in s:
        b = s["boo"]
        if lt > b:
            e = lt - b
            sc = back_out(e / 0.25) * (1 + 0.05 * math.sin(e * 30) * clamp(1 - e / 0.6))
            paste(canvas, SPR["boo"], 640, 1060, sc * 0.9, rot=-8 + 3 * math.sin(e * 25) * clamp(1 - e))

    if "sub" in s:
        paste(canvas, s["sub_spr"], W / 2, 1435, pop(lt, s["sub_at"], 0.4), alpha=fade_out)
    if "hearts" in s:
        h0 = s["hearts"]
        for j, (x, y, sz) in enumerate([(880, 500, 0.8), (150, 1350, 0.65), (920, 1290, 0.55)]):
            sc = pop(lt, h0 + j * 0.25, 0.4) * sz * (1 + 0.08 * math.sin(lt * 6 + j))
            paste(canvas, SPR["heart"], x, y + 8 * math.sin(lt * 2 + j), sc, rot=-10 + j * 12, alpha=fade_out)
    if outro:
        sc = pop(lt, outro + 0.3, 0.5)
        paste(canvas, SPR["logo"], W / 2, 240, sc * (1 + 0.02 * math.sin(lt * 3)))
        paste(canvas, SPR["tag"], W / 2, 360, pop(lt, outro + 0.6, 0.4))


def scene_frame(s, lt):
    env = vo_env(s, lt)
    img = warped(s, lt, env)
    shake = (0, 0)
    if "boo" in s and 0 < lt - s["boo"] < 0.45:
        e = lt - s["boo"]
        a = 12 * (1 - e / 0.45)
        shake = (a * math.sin(e * 90), a * math.cos(e * 70))
    frame = camera(s, img, lt, shake)
    canvas = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGBA")
    overlays(s, lt, canvas)
    return np.asarray(canvas.convert("RGB"))


def frame_at(t):
    act = [s for s in SCENES if s["start"] <= t < s["start"] + s["dur"]]
    if len(act) == 1:
        return scene_frame(act[0], t - act[0]["start"])
    a, b = act[0], act[1]
    k = ease_io((t - b["start"]) / XF)
    fa = scene_frame(a, t - a["start"]).astype(np.float32)
    fb = scene_frame(b, t - b["start"]).astype(np.float32)
    return (fa * (1 - k) + fb * k).astype(np.uint8)


# ---------------------------------------------------------------- music + sfx
def tone(freq, dur, decay=3.0, parts=((1, 1.0), (2, 0.35), (3, 0.12), (4.2, 0.08))):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    y = sum(a * np.sin(2 * np.pi * freq * m * tt) * np.exp(-decay * m ** 0.5 * tt) for m, a in parts)
    att = np.minimum(1, tt / 0.004)
    return (y * att).astype(np.float32)


def note(n):  # MIDI -> Hz
    return 440 * 2 ** ((n - 69) / 12)


def add(buf, x, at, gain=1.0):
    i = int(at * SR)
    j = min(len(buf), i + len(x))
    if i < len(buf):
        buf[i:j] += x[:j - i] * gain


def music(total):
    buf = np.zeros(int(total * SR) + SR, np.float32)
    bpm = 104
    beat = 60 / bpm
    # cute-spooky music box: Em - C - Am - B7
    chords = [[64, 67, 71, 76], [60, 64, 67, 72], [57, 60, 64, 69], [59, 63, 66, 71]]
    bass = [40, 36, 45, 47]
    patt = [0, 2, 1, 3, 2, 1, 3, 2]
    melody = {0: 83, 3: 81, 4: 79, 6: 78}
    bar = 0
    t = 0.0
    while t < total:
        ch = chords[bar % 4]
        add(buf, tone(note(bass[bar % 4]), 1.6, 2.5, ((1, 1), (2, 0.4))), t, 0.22)
        for k, p in enumerate(patt):
            add(buf, tone(note(ch[p] + 12), 0.9, 5.0), t + k * beat / 2, 0.11)
        if bar % 2 == 1:
            for k, n in melody.items():
                add(buf, tone(note(n - (2 if bar % 4 == 3 else 0)), 1.2, 3.2), t + k * beat / 2, 0.09)
        t += 4 * beat
        bar += 1
    return buf


def sfx_pop():
    n = int(0.09 * SR)
    tt = np.arange(n) / SR
    f = 950 * np.exp(-tt * 18) + 260
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 38)).astype(np.float32)


def sfx_ding():
    return tone(1318.5, 1.0, 3.5, ((1, 1), (2.76, 0.4), (5.4, 0.15))) + tone(1975.5, 1.0, 4.5) * 0.5


def sfx_whoosh(d=0.5):
    n = int(d * SR)
    noise = np.random.default_rng(1).standard_normal(n).astype(np.float32)
    out = np.zeros(n, np.float32)
    y = 0.0
    for i in range(n):  # sweeping one-pole lowpass
        k = 0.02 + 0.25 * math.sin(math.pi * i / n)
        y += k * (noise[i] - y)
        out[i] = y
    return out * np.sin(np.linspace(0, np.pi, n)) * 2.2


def sfx_chime():
    buf = np.zeros(int(1.6 * SR), np.float32)
    for k, n in enumerate([76, 79, 83, 88, 91]):
        add(buf, tone(note(n), 1.0, 4.0), k * 0.08, 0.35)
    return buf


def build_audio():
    tot = int((TOTAL + 0.5) * SR)
    voice = np.zeros(tot, np.float32)
    fx = np.zeros(tot, np.float32)
    for s in SCENES:
        g = s["start"]
        add(voice, VOS[s["vo"]], g + s["vo_at"], 1.0)
        add(fx, sfx_pop(), g + s["title_at"], 0.35)
        if "bubbles" in s:
            for at in s["bubbles"]:
                add(fx, sfx_pop(), g + at, 0.3)
            add(fx, sfx_ding(), g + s["choose"][1], 0.22 if s["choose"][0] == "fun" else 0.0)
            if s["choose"][0] == "too":
                add(fx, tone(196, 0.6, 4, ((1, 1), (1.5, 0.3))), g + s["choose"][1], 0.25)
        if "boo" in s:
            add(fx, sfx_whoosh(0.55), g + s["boo"] - 0.12, 0.5)
        if "sub" in s:
            add(fx, sfx_pop(), g + s["sub_at"], 0.3)
        if "hearts" in s:
            add(fx, sfx_chime(), g + s["hearts"], 0.6)
        if "outro" in s:
            add(fx, sfx_chime(), g + s["outro"] + 0.3, 0.8)
    mus = music(TOTAL + 0.5)[:tot]
    # duck music under the voice
    hop = SR // 100
    e = np.array([np.abs(voice[j:j + hop]).max() for j in range(0, tot, hop)])
    duck = np.repeat(np.where(e > 0.02, 0.45, 1.0), hop)[:tot]
    duck = np.convolve(duck, np.ones(SR // 8) / (SR // 8), mode="same")
    fade = np.ones(tot, np.float32)
    fl = int(1.2 * SR)
    fade[-fl:] = np.linspace(1, 0, fl)
    fade[:int(0.3 * SR)] = np.linspace(0, 1, int(0.3 * SR))
    mix = voice + fx + mus * duck * fade * 0.8
    mix = np.tanh(mix * 1.1) / 1.1
    sf.write(ROOT + "build/mix.wav", np.stack([mix, mix], 1), SR)


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    if PREVIEW:
        for t in [1.5, 5.5, 9.4, 13.4, 14.2, 18.0, 22.0, 25.0, 29.0]:
            Image.fromarray(frame_at(min(t, TOTAL - 0.05))).save(f"{ROOT}build/prev_{t:05.1f}.jpg", quality=85)
        sys.exit()
    build_audio()
    ff = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", ROOT + "build/mix.wav", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT],
        stdin=subprocess.PIPE)
    for i in range(NF):
        ff.stdin.write(frame_at(i / FPS).tobytes())
        if i % 90 == 0:
            print(f"frame {i}/{NF}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done", OUT, round(TOTAL, 2), "s")
