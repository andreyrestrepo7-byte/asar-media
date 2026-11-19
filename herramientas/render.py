"""Plantilla de carruseles de Somos ASAR (1080x1350, JPEG).

Uso:  python3 herramientas/render.py post.json carpeta_salida
post.json = {"slides": [
  {"tipo": "portada", "titulo": "...", "sub": "..."},
  {"tipo": "punto", "num": "01", "titulo": "...", "texto": "...", "dato": "(opcional)"},
  {"tipo": "cierre", "titulo": "...", "texto": "...", "cta": "Escríbenos por DM"}
]}
Genera 1.jpg, 2.jpg, ..., carrusel.pdf (todas las diapositivas en un PDF) y diapositivas.json en carpeta_salida.
Requiere playwright, Chrome y Pillow.
"""
import asyncio, html, json, os, sys
from playwright.async_api import async_playwright

PRI, INK, MUT, BG, BD, SOFT = "#6D28D9", "#17151F", "#6B6779", "#FAFAFC", "#ECE9F3", "#F4EFFF"
e = lambda s: html.escape(str(s or "")).replace("\n", "<br>")

def marco(cuerpo, n, total, fondo=BG, tinta=INK, borde=PRI, mut=MUT):
    return f"""<html><head><style>
*{{box-sizing:border-box;margin:0}}body{{width:1080px;height:1350px;background:{fondo};font-family:Inter;color:{tinta};
display:flex;flex-direction:column;padding:72px 80px 64px}}
.top{{display:flex;justify-content:space-between;align-items:center}}
.box{{border:3px solid {borde};color:{borde};font-weight:600;font-size:30px;letter-spacing:.2em;padding:10px 10px 10px 18px;border-radius:10px}}
.pg{{font-size:26px;color:{mut};font-variant-numeric:tabular-nums;font-weight:500}}
.main{{flex:1;display:flex;flex-direction:column;justify-content:center}}
.foot{{border-top:2px solid {BD if fondo==BG else 'rgba(255,255,255,.25)'};padding-top:26px;font-size:26px;color:{mut};display:flex;justify-content:space-between}}
</style></head><body><div class="top"><span class="box">A.S.A.R.</span><span class="pg">{n}/{total}</span></div>
<div class="main">{cuerpo}</div><div class="foot"><span>Somos ASAR</span><span>Automatización contable</span></div></body></html>"""

def slide(s, n, total):
    """Las diapositivas se alternan: blanca, morada, blanca... La portada es blanca y el cierre siempre morado."""
    t = s.get("tipo", "punto")
    if t == "portada":
        c = f"""<div style="font-size:92px;font-weight:600;line-height:1.04;letter-spacing:-.02em">{e(s.get('titulo'))}</div>
<div style="font-size:38px;color:{MUT};margin-top:36px;line-height:1.35">{e(s.get('sub'))}</div>
<div style="margin-top:64px"><span style="background:{PRI};color:#fff;font-size:30px;font-weight:600;padding:18px 30px;border-radius:12px">Desliza →</span></div>"""
        return marco(c, n, total)
    if t == "cierre":
        c = f"""<div style="font-size:80px;font-weight:600;line-height:1.06;letter-spacing:-.02em">{e(s.get('titulo'))}</div>
<div style="font-size:38px;margin-top:34px;line-height:1.4;opacity:.92">{e(s.get('texto'))}</div>
<div style="margin-top:60px"><span style="border:3px solid #fff;font-size:32px;font-weight:600;padding:18px 30px;border-radius:12px">{e(s.get('cta') or 'Escríbenos por DM')}</span></div>"""
        return marco(c, n, total, fondo=PRI, tinta="#FFFFFF", borde="#FFFFFF", mut="rgba(255,255,255,.8)")
    osc = n % 2 == 0
    num_c, txt_c = ("#DDD6FE", "rgba(255,255,255,.92)") if osc else (PRI, "#2E2B38")
    dato = s.get("dato")
    dbox = (f'background:rgba(255,255,255,.12);border:2px solid rgba(255,255,255,.3);color:#FFFFFF' if osc
            else f'background:{SOFT};border:2px solid {BD};color:{INK}')
    c = f"""<div style="font-size:120px;font-weight:600;color:{num_c};line-height:1">{e(s.get('num'))}</div>
<div style="font-size:64px;font-weight:600;line-height:1.08;margin-top:28px;letter-spacing:-.01em">{e(s.get('titulo'))}</div>
<div style="font-size:38px;line-height:1.42;margin-top:30px;color:{txt_c}">{e(s.get('texto'))}</div>
{f'<div style="margin-top:40px;{dbox};border-radius:16px;padding:26px 30px;font-size:32px;line-height:1.4">{e(dato)}</div>' if dato else ''}"""
    if osc:
        return marco(c, n, total, fondo=PRI, tinta="#FFFFFF", borde="#FFFFFF", mut="rgba(255,255,255,.8)")
    return marco(c, n, total)

async def main(src, out):
    data = json.load(open(src, encoding="utf-8"))
    sl = data["slides"]
    os.makedirs(out, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome")
        pg = await b.new_page(viewport={"width": 1080, "height": 1350})
        for i, s in enumerate(sl, 1):
            await pg.set_content(slide(s, i, len(sl)))
            await pg.wait_for_timeout(250)
            await pg.screenshot(path=os.path.join(out, f"{i}.jpg"), type="jpeg", quality=90)
        await b.close()
    from PIL import Image
    ims = [Image.open(os.path.join(out, f"{i}.jpg")).convert("RGB") for i in range(1, len(sl) + 1)]
    ims[0].save(os.path.join(out, "carrusel.pdf"), save_all=True, append_images=ims[1:], resolution=150)
    json.dump(data, open(os.path.join(out, "diapositivas.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(os.path.join(out, f"{i}.jpg") for i in range(1, len(sl) + 1)))

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
