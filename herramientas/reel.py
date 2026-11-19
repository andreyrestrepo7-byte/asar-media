"""Plantilla de Reels de Somos ASAR (1080x1920, MP4 H.264).

Uso:  python3 herramientas/reel.py reel.json carpeta_salida
reel.json = {"segundos": 3.5, "escenas": [
  {"tipo": "gancho", "titulo": "...", "sub": "..."},
  {"tipo": "punto", "num": "01", "titulo": "...", "texto": "..."},
  {"tipo": "cierre", "titulo": "...", "texto": "...", "cta": "Escríbenos por DM"}
]}
Genera escena-N.jpg, portada.jpg, reel.mp4 (con pista de audio silenciosa) y guion.json.
Requiere playwright, Chrome y ffmpeg. Duración ideal: 15 a 30 s (4 a 8 escenas).
"""
import asyncio, html, json, os, shutil, subprocess, sys
from playwright.async_api import async_playwright

PRI, INK, MUT, BG, BD = "#6D28D9", "#17151F", "#6B6779", "#FAFAFC", "#ECE9F3"
e = lambda s: html.escape(str(s or "")).replace("\n", "<br>")

def marco(cuerpo, fondo=BG, tinta=INK, borde=PRI, mut=MUT):
    return f"""<html><head><style>*{{box-sizing:border-box;margin:0}}
body{{width:1080px;height:1920px;background:{fondo};font-family:Inter;color:{tinta};display:flex;flex-direction:column;padding:200px 90px 400px}}
.box{{align-self:flex-start;border:4px solid {borde};color:{borde};font-weight:600;font-size:38px;letter-spacing:.2em;padding:12px 12px 12px 22px;border-radius:12px}}
.main{{flex:1;display:flex;flex-direction:column;justify-content:center}}
.foot{{font-size:34px;color:{mut};font-weight:500}}</style></head><body>
<span class="box">A.S.A.R.</span><div class="main">{cuerpo}</div><div class="foot">Somos ASAR · Automatización contable</div></body></html>"""

def escena(s):
    t = s.get("tipo", "punto")
    if t == "gancho":
        return marco(f"""<div style="font-size:112px;font-weight:600;line-height:1.04;letter-spacing:-.02em">{e(s.get('titulo'))}</div>
<div style="font-size:48px;color:{MUT};margin-top:48px;line-height:1.35">{e(s.get('sub'))}</div>""")
    if t == "cierre":
        return marco(f"""<div style="font-size:100px;font-weight:600;line-height:1.06;letter-spacing:-.02em">{e(s.get('titulo'))}</div>
<div style="font-size:48px;margin-top:44px;line-height:1.4;opacity:.92">{e(s.get('texto'))}</div>
<div style="margin-top:72px"><span style="border:4px solid #fff;font-size:42px;font-weight:600;padding:22px 36px;border-radius:14px">{e(s.get('cta') or 'Escríbenos por DM')}</span></div>""",
            fondo=PRI, tinta="#FFFFFF", borde="#FFFFFF", mut="rgba(255,255,255,.8)")
    return marco(f"""<div style="font-size:150px;font-weight:600;color:{PRI};line-height:1">{e(s.get('num'))}</div>
<div style="font-size:84px;font-weight:600;line-height:1.08;margin-top:36px;letter-spacing:-.01em">{e(s.get('titulo'))}</div>
<div style="font-size:50px;line-height:1.42;margin-top:40px;color:#2E2B38">{e(s.get('texto'))}</div>""")

async def render(esc, out):
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        for i, s in enumerate(esc, 1):
            await pg.set_content(escena(s)); await pg.wait_for_timeout(250)
            await pg.screenshot(path=os.path.join(out, f"escena-{i}.jpg"), type="jpeg", quality=92)
        await b.close()

def video(n, out, seg, fps=30, fade=0.45):
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for i in range(1, n + 1):
        args += ["-loop", "1", "-t", f"{seg + fade:.2f}", "-i", os.path.join(out, f"escena-{i}.jpg")]
    args += ["-f", "lavfi", "-t", f"{n * seg + fade:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
    f, frames = [], int((seg + fade) * fps)
    for i in range(n):
        f.append(f"[{i}:v]scale=2160:3840,zoompan=z='min(zoom+0.0003,1.03)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={fps},setsar=1,format=yuv420p[v{i}]")
    prev = "v0"
    for i in range(1, n):
        f.append(f"[{prev}][v{i}]xfade=transition=smoothleft:duration={fade}:offset={i * seg:.2f}[x{i}]"); prev = f"x{i}"
    args += ["-filter_complex", ";".join(f), "-map", f"[{prev}]", "-map", f"{n}:a", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart",
             os.path.join(out, "reel.mp4")]
    subprocess.run(args, check=True)

def main(src, out):
    data = json.load(open(src, encoding="utf-8")); esc = data["escenas"]; seg = float(data.get("segundos", 3.5))
    os.makedirs(out, exist_ok=True)
    asyncio.run(render(esc, out)); video(len(esc), out, seg)
    shutil.copy(os.path.join(out, "escena-1.jpg"), os.path.join(out, "portada.jpg"))
    json.dump(data, open(os.path.join(out, "guion.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(os.path.join(out, "reel.mp4"))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
