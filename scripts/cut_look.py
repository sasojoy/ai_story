"""把生圖工具生出來的九張原圖切成擂台形象用的九張（自建形象第二批；管理者在主機或自己的電腦上跑）。

python scripts/cut_look.py <原圖資料夾> <輸出資料夾>

原圖資料夾裡照九張的名字放（hero_bare_idle.png、hero_atk_slash.jpg……，副檔名 png／jpg／webp 都行），白底、側面朝右（提示詞在管理者區
「自建形象」那一格展開就有）。切法同走一趟與擂台斗笠小子（/mnt/project-files/design/走一趟/sprites.py）：去白底、照格數切格、照斗笠
的寬度定比例、腳底對到 (100, 212)，每格 220×220，輸出 webp。切好的九張到設定頁管理者區「自建形象」那一張訂單上傳。

要 Pillow、numpy、scipy（伺服器不用裝；跑之前 pip install pillow numpy scipy）。這支只動檔案，不碰資料庫、不叫任何外部服務。
"""
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

def cutout(im):
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    mn, mx = a.min(2), a.max(2)
    white = (mn > 228) & ((mx - mn) < 30)
    lab, n = ndimage.label(white)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bg = np.isin(lab, list(edge))
    alpha = np.where(bg, 0, 255).astype(np.float32)
    near = ndimage.binary_dilation(bg, iterations=2) & ~bg
    soft = np.clip((255 - mn) / (255 - 228), 0, 1) * 255
    alpha[near] = np.minimum(alpha[near], soft[near])
    rgba = np.dstack([a.astype(np.uint8), alpha.astype(np.uint8)])
    return Image.fromarray(rgba, 'RGBA'), ~bg

def runs(v, minlen=1):
    out=[];start=None
    for i,x in enumerate(list(v)+[False]):
        if x and start is None: start=i
        if not x and start is not None:
            if i-start>=minlen: out.append((start,i))
            start=None
    return out

def pick(rs, weights, k):
    rs=sorted(zip(rs,weights), key=lambda t:-t[1])[:k]
    return sorted(r for r,_ in rs)

def frames(mask, cols, rows):
    H, W = mask.shape
    clean = ndimage.binary_opening(mask, iterations=1)
    out = []
    for r in range(rows):
        y0, y1 = r*H//rows, (r+1)*H//rows
        band = clean[y0:y1]
        proj = band.sum(0).astype(float)
        cr = runs(ndimage.binary_dilation(proj > 2, iterations=4))
        tot = proj.sum()
        cr = [c for c in cr if proj[c[0]:c[1]].sum() > 0.02*tot]
        while len(cr) > cols:
            gaps = [cr[i+1][0]-cr[i][1] for i in range(len(cr)-1)]
            i = int(np.argmin(gaps)); cr[i:i+2] = [(cr[i][0], cr[i+1][1])]
        while len(cr) < cols:
            i = int(np.argmax([b-a for a,b in cr])); a,b = cr[i]
            sm = ndimage.uniform_filter1d(proj[a:b], 15); lo, hi = int((b-a)*.2), int((b-a)*.8)
            cut = a+lo+int(np.argmin(sm[lo:hi])); cr[i:i+1] = [(a,cut),(cut,b)]
        for (x0, x1) in cr:
            m = mask[y0:y1, x0:x1]
            lab, n = ndimage.label(m)
            sizes = ndimage.sum(m, lab, range(1, n+1))
            keep = np.isin(lab, [i+1 for i, sz in enumerate(sizes) if sz > 300])
            ys, xs = np.nonzero(keep)
            out.append((x0+xs.min(), y0+ys.min(), x0+xs.max()+1, y0+ys.max()+1, keep, x0, y0))
    return out

def hat(mask_crop):
    h = mask_crop.shape[0]
    best = (0, 0)
    for y in range(int(h*0.45)):
        row = mask_crop[y]
        lab, n = ndimage.label(row)
        if n == 0: continue
        lens = ndimage.sum(row, lab, range(1, n+1))
        i = int(np.argmax(lens))
        if lens[i] > best[0]:
            xs = np.nonzero(lab == i+1)[0]
            best = (lens[i], (xs.min()+xs.max())/2)
    return best

CELL, AX, BY = 220, 100, 212
def sheet(path, cols, rows, kind='hero', scale_from=None, ref_h=None):
    im = Image.open(path)
    rgba, mask = cutout(im)
    fr = frames(mask, cols, rows)
    info = []
    for (x0, y0, x1, y1, keep, cx0, cy0) in fr:
        crop = keep[y0-cy0:y1-cy0, x0-cx0:x1-cx0]
        if kind == 'hero':
            w, cx = hat(crop); info.append((w, x0+cx, y1, y1-y0))
        else:
            ys, xs = np.nonzero(crop); info.append((0, x0+xs.mean(), y1, y1-y0))
    if ref_h:
        s = ref_h / info[0][3]
    elif kind == 'hero':
        s = 104 / float(np.median([i[0] for i in info]))
    else:
        ref = scale_from if scale_from else [i[3] for i in info[:4]]
        s = 190 / float(np.median(ref))
    strip = Image.new('RGBA', (CELL*len(fr), CELL), (0, 0, 0, 0))
    for k, ((x0, y0, x1, y1, keep, cx0, cy0), (w, ax, by, hh)) in enumerate(zip(fr, info)):
        m = Image.fromarray((keep*255).astype(np.uint8), 'L')
        piece = rgba.crop((cx0, cy0, cx0+keep.shape[1], cy0+keep.shape[0]))
        pa = np.asarray(piece).copy(); pa[..., 3] = np.minimum(pa[..., 3], np.asarray(m))
        piece = Image.fromarray(pa, 'RGBA')
        piece = piece.resize((max(1, int(piece.width*s)), max(1, int(piece.height*s))), Image.LANCZOS)
        px = int(round(AX - (ax-cx0)*s)); py = int(round(BY - (by-cy0)*s))
        tmp = Image.new('RGBA', (CELL, CELL), (0, 0, 0, 0)); tmp.alpha_composite(piece, (max(px, -10**6), py)) if px >= 0 and py >= 0 else tmp.paste(piece, (px, py), piece)
        strip.alpha_composite(tmp, (k*CELL, 0))
    return strip


LAYOUT = {  # 十張 → (每排幾格, 幾排)；格數同 tianxia/features/looks/orders.py 的 SHEETS
    "hero_bare_idle": (4, 1), "hero_bare_hit": (3, 1), "hero_bare_kneel": (4, 1), "hero_bare_dodge": (4, 1), "hero_bare_fall": (3, 2), "hero_bare_block": (4, 1),
    "hero_atk_slash": (3, 2), "hero_atk_pole": (3, 2), "hero_atk_fist": (3, 2), "hero_atk_shoot": (3, 2),
}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    src, out = Path(argv[1]), Path(argv[2])
    out.mkdir(parents=True, exist_ok=True)
    missing = []
    for name, (cols, rows) in LAYOUT.items():
        path = next((p for ext in ("png", "jpg", "jpeg", "webp") for p in [src / f"{name}.{ext}"] if p.is_file()), None)
        if path is None:
            missing.append(name)
            continue
        strip = sheet(path, cols, rows)
        strip.save(out / f"{name}.webp", "WEBP", quality=82, method=6)
        print(f"{name}：{strip.width // CELL} 格 → {out / (name + '.webp')}")
    if missing:
        print(f"缺 {len(missing)} 張：{'、'.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv))
