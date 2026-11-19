"""Plantilla de Reels narrados de Somos ASAR (1080x1920, MP4 H.264 + voz).

Uso:  python3 herramientas/reel.py reel.json carpeta_salida
reel.json = {"voz": "hombre" | "mujer" | "ninguna", "rapidez": 0.88 (menor = habla más rápido), "segundos": 3.2, "escenas": [
  {"tipo": "gancho", "titulo": "...", "sub": "...", "voz": "Lo que dice el narrador en esta escena"},
  {"tipo": "punto", "num": "01", "titulo": "...", "texto": "...", "voz": "..."},
  {"tipo": "cierre", "titulo": "...", "texto": "...", "cta": "Escríbenos por DM", "voz": "..."}
]}
Las escenas se alternan: blanca, morada, blanca, morada... y el cierre siempre es morado.
Cada escena dura lo que tarde su narración (mínimo "segundos").
Genera escena-N.jpg, portada.jpg, narracion.wav, reel.mp4 y guion.json.
Requiere playwright, Chrome, ffmpeg y piper-tts (se instala solo si falta). Las voces se descargan
la primera vez desde GitHub (modelos piper de sherpa-onnx).
"""
import asyncio, html, json, os, shutil, subprocess, sys, wave
from playwright.async_api import async_playwright

PRI, INK, MUT, BG, BD = "#6D28D9", "#17151F", "#6B6779", "#FAFAFC", "#ECE9F3"
VOCES = {"hombre": "es_MX-claude-high", "mujer": "es_AR-daniela-high"}
CACHE = os.path.expanduser("~/.cache/asar-voz")
e = lambda s: html.escape(str(s or "")).replace("\n", "<br>")

def morada(s, i):
    return s.get("tipo") == "cierre" or (s.get("tipo") == "punto" and i % 2 == 0)

def marco(cuerpo, oscuro):
    fondo, tinta, borde, mut = (PRI, "#FFFFFF", "#FFFFFF", "rgba(255,255,255,.8)") if oscuro else (BG, INK, PRI, MUT)
    return f"""<html><head><style>*{{box-sizing:border-box;margin:0}}
body{{width:1080px;height:1920px;background:{fondo};font-family:Inter;color:{tinta};display:flex;flex-direction:column;padding:200px 90px 400px}}
.box{{align-self:flex-start;border:4px solid {borde};color:{borde};font-weight:600;font-size:38px;letter-spacing:.2em;padding:12px 12px 12px 22px;border-radius:12px}}
.main{{flex:1;display:flex;flex-direction:column;justify-content:center}}
.foot{{font-size:34px;color:{mut};font-weight:500}}</style></head><body>
<span class="box">A.S.A.R.</span><div class="main">{cuerpo}</div><div class="foot">Somos ASAR · Automatización contable</div></body></html>"""

def escena(s, i):
    t, osc = s.get("tipo", "punto"), morada(s, i)
    if t == "gancho":
        return marco(f"""<div style="font-size:112px;font-weight:600;line-height:1.04;letter-spacing:-.02em">{e(s.get('titulo'))}</div>
<div style="font-size:48px;color:{MUT};margin-top:48px;line-height:1.35">{e(s.get('sub'))}</div>""", False)
    if t == "cierre":
        return marco(f"""<div style="font-size:100px;font-weight:600;line-height:1.06;letter-spacing:-.02em">{e(s.get('titulo'))}</div>
<div style="font-size:48px;margin-top:44px;line-height:1.4;opacity:.92">{e(s.get('texto'))}</div>
<div style="margin-top:72px"><span style="border:4px solid #fff;font-size:42px;font-weight:600;padding:22px 36px;border-radius:14px">{e(s.get('cta') or 'Escríbenos por DM')}</span></div>""", True)
    num_c, txt_c = ("#DDD6FE", "rgba(255,255,255,.92)") if osc else (PRI, "#2E2B38")
    return marco(f"""<div style="font-size:150px;font-weight:600;color:{num_c};line-height:1">{e(s.get('num'))}</div>
<div style="font-size:84px;font-weight:600;line-height:1.08;margin-top:36px;letter-spacing:-.01em">{e(s.get('titulo'))}</div>
<div style="font-size:50px;line-height:1.42;margin-top:40px;color:{txt_c}">{e(s.get('texto'))}</div>""", osc)

async def render(esc, out):
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        for i, s in enumerate(esc, 1):
            await pg.set_content(escena(s, i)); await pg.wait_for_timeout(250)
            await pg.screenshot(path=os.path.join(out, f"escena-{i}.jpg"), type="jpeg", quality=92)
        await b.close()

def modelo(voz):
    name = VOCES[voz]; d = os.path.join(CACHE, f"vits-piper-{name}"); onnx = os.path.join(d, f"{name}.onnx")
    if not os.path.exists(onnx):
        os.makedirs(CACHE, exist_ok=True); tar = os.path.join(CACHE, "v.tar.bz2")
        subprocess.run(["curl", "-sL", "-m", "300", "-o", tar,
                        f"https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-{name}.tar.bz2"], check=True)
        subprocess.run(["tar", "xjf", tar, "-C", CACHE], check=True); os.remove(tar)
    try:
        import piper  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "piper-tts"], check=True)
    return onnx

def dur(wav):
    with wave.open(wav) as w: return w.getnframes() / w.getframerate()

def narrar(esc, out, voz, rapidez=0.88):
    if voz == "ninguna" or not any(s.get("voz") for s in esc): return [None] * len(esc)
    onnx = modelo(voz); res = []
    for i, s in enumerate(esc, 1):
        txt = (s.get("voz") or "").strip()
        if not txt: res.append(None); continue
        f = os.path.join(out, f"voz-{i}.wav")
        subprocess.run([sys.executable, "-m", "piper", "-m", onnx, "--length-scale", str(rapidez), "-f", f], input=txt.encode("utf-8"), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res.append(f)
    return res

def video(n, out, durs, voces, fps=30, fade=0.45):
    total = sum(durs) + fade
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for i in range(n):
        args += ["-loop", "1", "-t", f"{durs[i] + fade:.2f}", "-i", os.path.join(out, f"escena-{i + 1}.jpg")]
    vin = [(i, v) for i, v in enumerate(voces) if v]
    for _, v in vin: args += ["-i", v]
    args += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=22050:cl=mono"]
    f = []
    for i in range(n):
        fr = int((durs[i] + fade) * fps)
        f.append(f"[{i}:v]scale=2160:3840,zoompan=z='min(zoom+0.0003,1.03)':d={fr}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={fps},setsar=1,format=yuv420p[v{i}]")
    prev, off = "v0", 0.0
    for i in range(1, n):
        off += durs[i - 1]
        f.append(f"[{prev}][v{i}]xfade=transition=smoothleft:duration={fade}:offset={off:.2f}[x{i}]"); prev = f"x{i}"
    starts, acc = [], 0.0
    for i in range(n): starts.append(acc + (fade if i else 0) + 0.15); acc += durs[i]
    alabels = []
    for k, (i, _) in enumerate(vin):
        ms = int(starts[i] * 1000)
        f.append(f"[{n + k}:a]aresample=22050,adelay={ms}|{ms}[a{k}]"); alabels.append(f"[a{k}]")
    sil = n + len(vin)
    f.append(f"[{sil}:a]{''.join(alabels)}amix=inputs={len(alabels) + 1}:normalize=0:duration=first,volume=1.4[aout]")
    args += ["-filter_complex", ";".join(f), "-map", f"[{prev}]", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-t", f"{total:.2f}",
             "-movflags", "+faststart", os.path.join(out, "reel.mp4")]
    subprocess.run(args, check=True)

def main(src, out):
    data = json.load(open(src, encoding="utf-8")); esc = data["escenas"]; seg = float(data.get("segundos", 3.2))
    voz = data.get("voz", "hombre")
    os.makedirs(out, exist_ok=True)
    asyncio.run(render(esc, out))
    voces = narrar(esc, out, voz, float(data.get("rapidez", 0.88)))
    durs = [max(seg, (dur(v) + 0.35) if v else 0) for v in voces]
    video(len(esc), out, durs, voces)
    for v in voces:
        if v: os.remove(v)
    shutil.copy(os.path.join(out, "escena-1.jpg"), os.path.join(out, "portada.jpg"))
    json.dump(data, open(os.path.join(out, "guion.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(os.path.join(out, "reel.mp4"), f"{sum(durs):.1f} s")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
