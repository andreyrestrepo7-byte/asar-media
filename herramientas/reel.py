"""Motor de Reels dinámicos de Somos ASAR (1080x1920, MP4 H.264 + narración + música).

Uso:  python3 herramientas/reel.py reel.json carpeta_salida [--borrador]
--borrador genera a 15 fps para revisar rápido; sin él, 30 fps final.

reel.json = {"voz": "alex" | "dora" | "santa" | "ninguna", "musica": true, "escenas": [ ... ]}
Tipos de escena (todas aceptan "voz": la frase que dice el narrador, que también sale como subtítulo animado):
  gancho        {"texto", "resaltar": ["palabras resaltadas"], "sub"}          palabras que entran una a una con golpe
  lista         {"titulo", "items": [...3-4], "icono": "x" | "check"}           ítems que entran deslizando con ✕ o ✓
  proceso       {"titulo", "pasos": [...3]}                                     pasos numerados que se encadenan con flechas
  pantalla      {"titulo", "app", "filas": 6, "listo"}                          ventana de app que se llena fila por fila
  antes_despues {"antes", "despues"}                                            pantalla dividida que cambia de antes a después
  dato          {"numero", "sufijo", "texto"}                                   número grande que cuenta (solo datos reales)
  frase         {"lineas": [...2-3], "grande": true}                            frase que aparece línea por línea
  cierre        {"texto": "Somos ASAR", "cta": "Escríbenos por DM"}             logo que se dibuja y llamado a la acción
Las escenas alternan fondo claro y morado; entre escenas hay un barrido. Cada escena dura lo que dura su narración.
Requiere playwright, Chrome, ffmpeg, numpy y kokoro-onnx (se instala solo; el modelo se descarga de GitHub la primera vez).
"""
import asyncio, json, os, subprocess, sys, wave
import numpy as np
from playwright.async_api import async_playwright

AQUI = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.expanduser("~/.cache/asar-voz/kokoro")
VOCES = {"alex": "em_alex", "dora": "ef_dora", "santa": "em_santa", "hombre": "em_alex", "mujer": "ef_dora"}
SR = 24000

def kokoro():
    os.makedirs(CACHE, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        p = os.path.join(CACHE, f)
        if not os.path.exists(p):
            subprocess.run(["curl", "-sL", "-m", "600", "-o", p,
                            f"https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/{f}"], check=True)
    try:
        from kokoro_onnx import Kokoro
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "kokoro-onnx"], check=True)
        from kokoro_onnx import Kokoro
    return Kokoro(os.path.join(CACHE, "kokoro-v1.0.onnx"), os.path.join(CACHE, "voices-v1.0.bin"))

def narrar(esc, voz, rapidez):
    if voz == "ninguna" or not any(s.get("voz") for s in esc):
        return [None] * len(esc)
    k = kokoro(); v = VOCES.get(voz, "em_alex"); out = []
    for s in esc:
        t = (s.get("voz") or "").strip()
        if not t: out.append(None); continue
        a, sr = k.create(t, voice=v, speed=rapidez, lang="es")
        if sr != SR:
            a = np.interp(np.linspace(0, len(a), int(len(a) * SR / sr), endpoint=False), np.arange(len(a)), a)
        out.append(np.asarray(a, dtype=np.float32))
    return out

def tiempos_palabras(texto, dur):
    ws = texto.split(); pesos = [len(w) + 2 for w in ws]; tot = sum(pesos) or 1; acc = 0; res = []
    for w, p in zip(ws, pesos):
        a = acc / tot * dur; acc += p; res.append({"w": w, "a": a, "b": acc / tot * dur})
    return res

def musica(total, cortes):
    n = int(total * SR); t = np.arange(n) / SR; m = np.zeros(n, np.float32); bpm = 104; beat = 60 / bpm
    acordes = [[261.6, 329.6, 392.0, 493.9], [220.0, 261.6, 329.6, 392.0], [174.6, 220.0, 261.6, 329.6], [196.0, 246.9, 293.7, 392.0]]
    for b in range(int(total / beat) + 1):
        i0 = int(b * beat * SR)
        if i0 >= n: break
        L = min(int(.35 * SR), n - i0); tt = np.arange(L) / SR
        m[i0:i0 + L] += (np.sin(2 * np.pi * 55 * tt * (1 + 2 * np.exp(-tt * 30))) * np.exp(-tt * 9) * .55).astype(np.float32)
        h0 = int((b + .5) * beat * SR)
        if h0 < n:
            Lh = min(int(.06 * SR), n - h0); nz = np.random.default_rng(b).standard_normal(Lh)
            m[h0:h0 + Lh] += (np.diff(nz, prepend=0) * np.exp(-np.arange(Lh) / SR * 70) * .08).astype(np.float32)
    bar = beat * 4
    for c in range(int(total / bar) + 1):
        i0 = int(c * bar * SR); L = min(int(bar * SR), n - i0)
        if L <= 0: break
        tt = np.arange(L) / SR; env = np.minimum(1, tt / .3) * np.minimum(1, (bar - tt) / .3)
        for f in acordes[c % 4]:
            m[i0:i0 + L] += (np.sin(2 * np.pi * f * tt) * .045 * env).astype(np.float32)
    for c in cortes:
        i0 = int(max(0, c - .25) * SR); L = min(int(.5 * SR), n - i0)
        if L <= 0: continue
        nz = np.random.default_rng(int(c * 100)).standard_normal(L); env = np.sin(np.linspace(0, np.pi, L)) ** 2
        m[i0:i0 + L] += (np.convolve(nz, np.ones(12) / 12, "same") * env * .18).astype(np.float32)
    fade = int(1.2 * SR); m[-fade:] *= np.linspace(1, 0, fade)
    return m

async def video(data, out, fps):
    total = data["_total"]; frames = int(total * fps)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg",
                           "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                           os.path.join(out, "_video.mp4")], stdin=subprocess.PIPE)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = await b.new_page(viewport={"width": 1080, "height": 1920})
        await pg.goto("file://" + os.path.join(AQUI, "reel_motor", "escena.html"))
        await pg.evaluate("d=>init(d)", data)
        await pg.wait_for_timeout(400)
        for f in range(frames):
            t = f / fps
            await pg.evaluate(f"render({t:.4f})")
            ff.stdin.write(await pg.screenshot(type="jpeg", quality=90))
            if abs(t - data["escenas"][0]["_d"] * .6) < .5 / fps:
                await pg.screenshot(path=os.path.join(out, "portada.jpg"), type="jpeg", quality=92)
        await b.close()
    ff.stdin.close(); ff.wait()

def main(src, out, borrador=False):
    data = json.load(open(src, encoding="utf-8")); esc = data["escenas"]
    os.makedirs(out, exist_ok=True)
    voces = narrar(esc, data.get("voz", "alex"), float(data.get("rapidez", 1.05)))
    V0 = .25
    for s, v in zip(esc, voces):
        vd = len(v) / SR if v is not None else 0
        base = {"gancho": 2.6, "cierre": 3.2}.get(s.get("tipo"), 3.0)
        s["_d"] = round(max(base, V0 + vd + .45), 3); s["_v0"] = V0
        s["_words"] = tiempos_palabras(s.get("voz", ""), vd) if vd else []
    data["_total"] = sum(s["_d"] for s in esc)
    asyncio.run(video(data, out, 15 if borrador else 30))
    n = int(data["_total"] * SR); voz = np.zeros(n, np.float32); acc = 0; cortes = []
    for s, v in zip(esc, voces):
        if v is not None:
            i0 = int((acc + V0) * SR); L = min(len(v), n - i0); voz[i0:i0 + L] += v[:L]
        acc += s["_d"]; cortes.append(acc)
    mix = voz * 1.0 + (musica(data["_total"], cortes[:-1]) * (0.55 if data.get("musica", True) else 0))
    mix = np.clip(mix / max(1e-6, np.abs(mix).max()) * .92, -1, 1)
    wav = os.path.join(out, "_audio.wav")
    with wave.open(wav, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype(np.int16).tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(out, "_video.mp4"), "-i", wav, "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-shortest", "-movflags", "+faststart",
                    os.path.join(out, "reel.mp4")], check=True)
    os.remove(wav); os.remove(os.path.join(out, "_video.mp4"))
    limpio = {k: v for k, v in data.items() if not k.startswith("_")}
    limpio["escenas"] = [{k: v for k, v in s.items() if not k.startswith("_")} for s in esc]
    json.dump(limpio, open(os.path.join(out, "guion.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(os.path.join(out, "reel.mp4"), f"{data['_total']:.1f} s")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--borrador" in sys.argv)
