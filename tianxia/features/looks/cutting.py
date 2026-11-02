"""去背、切格（功能包 looks；畫坊 studio 與 scripts/cut_look.py 共用）。只在主機的畫坊程式與管理者的切圖腳本用，伺服器不 import。

要 Pillow、numpy、scipy（requirements-studio.txt）。切法同走一趟與擂台斗笠小子（/mnt/project-files/design/走一趟/sprites.py）：
去白底、照格數切格、照斗笠的寬度定比例、腳底對到 (100, 212)，每格 220×220。法相、巨物那一張（art）只去白底、裁到東西的邊、邊長不超過 1024。
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image
from scipy import ndimage

from .studio import CutError, CutProblem  # 切不出來（整張白的、東西太小）：畫坊當作沒畫好，叫生圖的重畫

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
# 一張一個「標準身高」：照 web/img/arena 的斗笠小子量出來的（最高那一格；2026-11-02 量）。
# 為什麼不照斗笠寬（舊規則 s = 104 ÷ hat()）：
#   1. 自建形象不一定戴斗笠，量到的是頭髮或肩線，倍率失準——「魔教聖女」第一版高 190～200，
#      比預設的 155 大了四分之一，而 web/arena_anim.js 的 RING_HAND（每一格的手部座標）是照
#      155 高的身體寫死的，兵器就掛在錯的位置（Joy 2026-11-02「兵器套用上去就破圖了」）。
#   2. 連預設的圖都量不準：拿斗笠小子的 hero_bare_idle 重切，斗笠寬算出來是 199～200 高，原圖是 154。
# 照身高正規化則完全重現原圖（154/155、156/157，驗過），而且不管戴不戴斗笠都一樣準。
BODY = {
    "hero_bare_idle": 155, "hero_bare_hit": 161, "hero_bare_kneel": 154, "hero_bare_dodge": 168, "hero_bare_fall": 156,
    "hero_bare_block": 162, "hero_atk_slash": 157, "hero_atk_pole": 153, "hero_atk_fist": 154, "hero_atk_shoot": 154,
}
BODY_SLACK = 1.18  # 躺著、縮著的那幾格可能比最高的那一格矮：倍率照最高那一格算，這個數只給驗收用
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
    if ref_h:  # 照身高：最高那一格對到標準身高（看 BODY 那一段為什麼不照斗笠寬）
        s = ref_h / float(max(i[3] for i in info))
    elif kind == 'hero':
        s = 104 / float(np.median([i[0] for i in info]))  # 沒給標準身高時照舊（舊腳本 scripts/cut_look.py）
    else:
        ref = scale_from if scale_from else [i[3] for i in info[:4]]
        s = 190 / float(np.median(ref))
    strip = Image.new('RGBA', (CELL*len(fr), CELL), (0, 0, 0, 0))
    src_w, grid_cols = im.width, cols  # 原圖那一格的中線（水平對齊用，見下面）
    for k, ((x0, y0, x1, y1, keep, cx0, cy0), (w, ax, by, hh)) in enumerate(zip(fr, info)):
        m = Image.fromarray((keep*255).astype(np.uint8), 'L')
        piece = rgba.crop((cx0, cy0, cx0+keep.shape[1], cy0+keep.shape[0]))
        pa = np.asarray(piece).copy(); pa[..., 3] = np.minimum(pa[..., 3], np.asarray(m))
        piece = Image.fromarray(pa, 'RGBA')
        piece = piece.resize((max(1, int(piece.width*s)), max(1, int(piece.height*s))), Image.LANCZOS)
        # 水平：對齊「原圖那一格的中線」，不是每一格各自把人置中——各自置中會把整個人往前探的位移抹掉
        # （2026-11-02 量到的：拿斗笠小子的 hero_bare_idle 重切，前端擺幅 19 px → 2 px，實機就看不到前後晃動了，
        #  Joy「斗笠小子有在前後移動，但是我們新的模型不會…最嚴重的就是他往前的那一下」）。
        # 垂直照舊每一格各自把腳底對到 BY（腳要站在同一條地平線上）。
        grid_cx = ((k % grid_cols) + 0.5) * src_w / grid_cols
        px = int(round(AX - (grid_cx-cx0)*s)); py = int(round(BY - (by-cy0)*s))
        tmp = Image.new('RGBA', (CELL, CELL), (0, 0, 0, 0)); tmp.alpha_composite(piece, (max(px, -10**6), py)) if px >= 0 and py >= 0 else tmp.paste(piece, (px, py), piece)
        strip.alpha_composite(tmp, (k*CELL, 0))
    return strip


LAYOUT = {  # 十張 → (每排幾格, 幾排)；格數同 tianxia/features/looks/orders.py 的 SHEETS
    "hero_bare_idle": (4, 1), "hero_bare_hit": (3, 1), "hero_bare_kneel": (4, 1), "hero_bare_dodge": (4, 1), "hero_bare_fall": (3, 2), "hero_bare_block": (4, 1),
    "hero_atk_slash": (3, 2), "hero_atk_pole": (3, 2), "hero_atk_fist": (3, 2), "hero_atk_shoot": (3, 2),
}




MIN_INK = 600  # 一格至少要有這麼多不透明的點，不然算空的（220×220 的格子，一個小人大概四五千點）
EDGE = 2  # 上下緣留白至少幾列
LINE_SHARE = 0.8  # 一列橫跨格寬這麼多比例、而且上下都空 → 當成畫出來的地面線
# 相鄰兩格最多能有多像（形狀重疊率）：照 web/img/arena 的斗笠小子量出來的上限加 0.10 餘裕（2026-11-02 量）。
# 餘裕給 0.10 不給 0.05：0.05 連差一點的（block 0.785 對上限 0.78）都擋，重畫的次數與錢都要多花；
# 0.10 只擋明顯的——第一版「魔教聖女」的 idle 0.967、kneel 0.948、shoot 0.936 照樣擋得下來。
# 規則是「不准比斗笠小子更懶」——不能用單一門檻：hero_bare_fall 的第 5、6 格是「躺著不動」，本來就重疊 0.973，
# 而 hero_bare_idle 的斗笠小子是 0.845、第一版「魔教聖女」是 0.967（看起來完全不晃，Joy 2026-11-02
# 「原版斗笠小子會一直前後晃動，新模型不會」）。
# 另外壓一個下限 0.70：斗笠小子的 dodge（0.508）、hit（0.462）動作特別大，照它加 0.10 等於要求生圖每一格
# 都大幅改姿勢——實測 dodge 連擋三次（生圖做不到），而原始那一張 0.617 其實只是「比斗笠小子收斂」、不是不動。
# 這一關要抓的是「看起來完全靜止」（0.93 以上），不是逼每一張都跟斗笠小子一樣誇張。
MOVE_MAX = {  # 斗笠小子量到的上限：idle .845 hit .462 kneel .745 dodge .508 fall .973 block .721 slash .805 pole .818 fist .719 shoot .803
    "hero_bare_idle": 0.945, "hero_bare_hit": 0.700, "hero_bare_kneel": 0.845, "hero_bare_dodge": 0.700,
    "hero_bare_fall": 1.01,  # 第 5、6 格是躺著不動，本來就幾乎一樣：這一張不驗
    "hero_bare_block": 0.821, "hero_atk_slash": 0.905, "hero_atk_pole": 0.918, "hero_atk_fist": 0.819, "hero_atk_shoot": 0.903,
}


# 前後擺幅：一條裡「最前端」的 x 在各格之間要差多少（側面視角的前後＝水平）。照斗笠小子量到的三分之一。
# 為什麼要分開驗（Joy 2026-11-02 看實機：「斗笠小子有在前後移動，但是我們新的模型不會…最嚴重的就是他往前的那一下」）：
# 斗笠小子的待機是「第 3 格整個往前探一下再收回」——前端擺 19 px、垂直只有 3 px，重疊率卻有 0.845，
# 所以光看重疊率擋不住「原地抖兩下」那種（第一版重畫出來 0.93 過了關，看起來還是不動）。
# 斗笠小子量到的前端擺幅：idle 19 hit 52 kneel 44 dodge 20 fall 41 block 10 slash 19 pole 28 fist 39 shoot 32
SWAY_MIN = {
    "hero_bare_idle": 6, "hero_bare_hit": 17, "hero_bare_kneel": 14, "hero_bare_dodge": 6, "hero_bare_fall": 13,
    "hero_bare_block": 3, "hero_atk_slash": 6, "hero_atk_pole": 9, "hero_atk_fist": 13, "hero_atk_shoot": 10,
}


def sheet_problems(strip: "Image.Image", frames: int, name: str | None = None) -> tuple[list[str], str]:
    """切完的那一條自己先驗一遍（Joy 2026-11-02「把能過的方法模組化」）：這幾樣機器看得出來，
    不必花一次審圖的錢，也不會每次都要人重新判是生圖畫壞還是我們切壞。
    回（寫給管理者的中文問題, 丟回生圖的英文改法）；都沒問題回 ([], "")。

    驗四樣，每一樣都是實際踩過的：
      1. 空格——「第2格是空的，只有一條地面線」（2026-11-02 #3 hero_atk_slash）
      2. 貼到上下緣——頭被切掉那一類（#3 前十張，根因是 FIT，留著當回歸哨）
      3. 整條幾乎透明——去背把人吃掉了（#3 第二格「大片殘缺、呈半透明」）
      4. 橫跨整格的細橫線——生圖畫了地面線，去背留著它、切格被它帶歪
    """
    a = np.asarray(strip.convert("RGBA"))
    alpha = a[..., 3]
    bad: list[str] = []
    fixes: list[str] = []
    for k in range(frames):
        cell = alpha[:, k * CELL:(k + 1) * CELL]
        ink = int((cell > 32).sum())
        if ink < MIN_INK:
            bad.append(f"第 {k + 1} 格幾乎是空的（只有 {ink} 點）")
            fixes.append(f"frame {k + 1} is empty — draw the whole character in every frame")
            continue
        rows_with = np.nonzero((cell > 32).max(1))[0]
        if rows_with.min() < EDGE:
            bad.append(f"第 {k + 1} 格的人貼到上緣（第 {int(rows_with.min())} 列就有東西）")
            fixes.append("the whole character must be inside the frame, with empty space above the head")
        if rows_with.max() > BY + 2:  # 2 px 容差：縮放的四捨五入會讓腳底落在 BY+1
            bad.append(f"第 {k + 1} 格的人超過地平線（畫到第 {int(rows_with.max())} 列）")
            fixes.append("keep the feet on the ground line, nothing below it")
        # 地面線：那一列橫跨整格，但它上面幾列窄得多（人站在線上，所以要比「寬度」而不是「點數」）
        width = (cell > 32).sum(1)
        flat = [int(y) for y in rows_with
                if width[y] > CELL * LINE_SHARE and float(np.median(width[max(0, y - 8):max(1, y - 2)])) < width[y] * 0.5]
        if flat:
            bad.append(f"第 {k + 1} 格腳下有一條橫跨整格的線（第 {flat[0]} 列）")
            fixes.append("do NOT draw any ground line, horizon line, floor or platform")
    # 動得夠不夠：相鄰兩格的形狀重疊率不能比斗笠小子還高（MOVE_MAX）。比形狀（alpha）不比顏色——
    # 同一個人同一件衣服，顏色本來就幾乎一樣。name 是哪一張（sheet_bytes 一定會給；沒給就不驗這一項）。
    if not bad and name in MOVE_MAX:
        masks = [(alpha[:, k * CELL:(k + 1) * CELL] > 32) for k in range(frames)]
        for k in range(1, frames):
            a1, a2 = masks[k - 1], masks[k]
            union = int((a1 | a2).sum())
            if union and int((a1 & a2).sum()) / union > MOVE_MAX[name]:
                bad.append(f"第 {k} 與第 {k + 1} 格幾乎一樣（動作幅度太小）")
                fixes.append("every frame must be a clearly different pose — move the body, arms and legs between frames "
                             "as much as in the reference animation; do not redraw almost the same picture")
                break
    # 前後擺幅：整個人要像斗笠小子那樣往前探再收回，不是原地微動
    if not bad and name in SWAY_MIN:
        fronts = []
        for k in range(frames):
            cols = np.nonzero((alpha[:, k * CELL:(k + 1) * CELL] > 32).max(0))[0]
            if len(cols):
                fronts.append(int(cols.max()))
        if fronts and max(fronts) - min(fronts) < SWAY_MIN[name]:
            bad.append(f"整串幾乎沒有前後移動（最前端只差 {max(fronts) - min(fronts)} 像素，至少要 {SWAY_MIN[name]}）")
            fixes.append("the character must clearly move forward and back along the ground between frames — "
                         "in at least one frame the whole body leans or steps toward the right edge, lead fist pushed out, "
                         "then returns; moving only up and down is not enough")
    seen: list[str] = []
    for f in fixes:  # 同一句只留一次（一條十格很容易每格都中同一樣）
        if f not in seen:
            seen.append(f)
    return bad, " ".join(seen)


IDLE_STEPS = (0, 3, 21, 2)  # 待機四格各往前幾像素：對齊 web/arena_anim.js 的 RING_HAND.hero_bare_idle
# （那張表的手 x 是 132、132、153、134，位移 0、0、21、2——兵器掛在手上，身體走多少手就要走多少。
#   第 2 格借 3 px，不然跟第 1 格一模一樣，過不了「四格要動」那一關。）


def idle_from_stance(strip_bytes: bytes, frame: int = 0) -> bytes:
    """拿一張已經過關的站姿，合成待機那一條（Joy 2026-11-02 選的做法）。

    為什麼用合成的：待機要的就是「整個人往前探一下再收回」這個位移（量斗笠小子：前端擺 19 px、垂直只有 3 px），
    位移我們自己做得準，生圖反而連七次畫不出乾淨的四格（七種不同的理由、56 次生圖）。把生圖的額度留給出招
    那些真的需要重畫姿勢的動作。缺點講明：那一下是整個人平移，不是重畫的姿勢。

    frame 是來源那一條的第幾格（0 起算）；回傳四格的待機條（webp）。
    """
    src = Image.open(io.BytesIO(strip_bytes)).convert('RGBA')
    cell = src.crop((frame*CELL, 0, (frame+1)*CELL, CELL))
    a = np.asarray(cell)[..., 3] > 32
    if not a.any():
        raise CutError("來源那一格是空的")
    front = int(np.nonzero(a.max(0))[0].max())
    room = CELL - 1 - front  # 往前推不能推出格子
    out = Image.new('RGBA', (4*CELL, CELL), (0, 0, 0, 0))
    for k, step in enumerate(IDLE_STEPS):
        out.alpha_composite(cell, (k*CELL + min(step, room), 0))
    buf = io.BytesIO()
    out.save(buf, "WEBP", quality=82, method=6)
    return buf.getvalue()


def refit(strip_bytes: bytes, name: str) -> bytes:
    """把已經切好、但身高不對的一條重新排版到標準身高（BODY[name]），腳底照舊對到 BY、左右位置不動。

    給 2026-11-02 之前切的自建形象用：那時照斗笠寬縮放，沒戴斗笠的角色被放大（「魔教聖女」高 190～200，
    預設是 155），web/arena_anim.js 的 RING_HAND 按 155 寫死，兵器就掛歪。生圖的原圖沒留著，
    所以不重畫、直接把成品縮回標準身高（多一次重取樣，看不出來）。本來就對的那一條原樣回傳。
    """
    im = Image.open(io.BytesIO(strip_bytes)).convert('RGBA')
    frames = im.width // CELL
    a = np.asarray(im)[..., 3]
    tall = 0
    for k in range(frames):
        ys = np.nonzero((a[:, k*CELL:(k+1)*CELL] > 32).max(1))[0]
        if len(ys):
            tall = max(tall, int(ys.max() - ys.min() + 1))
    if not tall or abs(tall - BODY[name]) <= 1:
        return strip_bytes
    s = BODY[name] / float(tall)
    out = Image.new('RGBA', im.size, (0, 0, 0, 0))
    for k in range(frames):
        cell = im.crop((k*CELL, 0, (k+1)*CELL, CELL))
        m = np.asarray(cell)[..., 3] > 32
        if not m.any():
            continue
        ys, xs = np.nonzero(m)
        box = (int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1)
        piece = cell.crop(box)
        piece = piece.resize((max(1, int(round(piece.width*s))), max(1, int(round(piece.height*s)))), Image.LANCZOS)
        cx = (box[0] + box[2]) / 2
        px = int(round(k*CELL + cx - piece.width/2))
        py = int(round(BY - (box[3] - box[1])*s)) if box[3] >= BY - 2 else int(round(k*0 + box[1]*s))
        out.alpha_composite(piece, (max(0, px), max(0, py)))
    buf = io.BytesIO()
    out.save(buf, "WEBP", quality=82, method=6)
    return buf.getvalue()


def sheet_bytes(raw: bytes, name: str) -> bytes:
    """生圖工具給的一張原圖 → 擂台用的一條（webp，格數照 LAYOUT）。切完自己驗一遍（sheet_problems）：
    機器看得出來的壞法直接丟 CutProblem，畫坊照它帶的那一句重畫，不叫審圖。"""
    cols, rows = LAYOUT[name]
    try:
        strip = sheet(io.BytesIO(raw), cols, rows, ref_h=BODY[name])  # 跟預設的斗笠小子一樣高，兵器才掛得準
    except (ValueError, IndexError) as exc:  # 去背之後什麼都不剩、某一格是空的
        raise CutError(f"切不出 {cols * rows} 格：{exc}") from exc
    bad, fix = sheet_problems(strip, cols * rows, name)
    if bad:
        raise CutProblem(bad, fix)
    out = io.BytesIO()
    strip.save(out, "WEBP", quality=82, method=6)
    return out.getvalue()


ART_PX = 1024
MIN_PX = 64


def art_bytes(raw: bytes, max_px: int = ART_PX) -> bytes:
    """法相、巨物那一張：去白底、只留大塊的（雜點丟掉）、裁到東西的邊，邊長不超過 max_px，PNG。"""
    rgba, mask = cutout(Image.open(io.BytesIO(raw)))
    lab, n = ndimage.label(mask)
    if n == 0:
        raise CutError("去背之後什麼都不剩")
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, sz in enumerate(sizes) if sz >= max(300, 0.01 * sizes.max())])
    ys, xs = np.nonzero(keep)
    if len(ys) == 0 or ys.max() - ys.min() < MIN_PX or xs.max() - xs.min() < MIN_PX:
        raise CutError("東西太小")
    a = np.asarray(rgba).copy()
    a[..., 3] = np.where(keep, a[..., 3], 0)
    piece = Image.fromarray(a, "RGBA").crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    if max(piece.size) > max_px:
        s = max_px / max(piece.size)
        piece = piece.resize((max(1, int(piece.width * s)), max(1, int(piece.height * s))), Image.LANCZOS)
    out = io.BytesIO()
    piece.save(out, "PNG", optimize=True)
    return out.getvalue()
