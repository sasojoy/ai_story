// 量收藏冊每一枚印：圓的寬高、字的 Range 有沒有跑出圓（四個角到圓心的距離比半徑）、幾行
(() => {
  const album = document.querySelector('.dv-album');
  album.scrollIntoView({ block: 'center' });
  const cells = [...album.querySelectorAll('.dv-cell')];
  const out = { sw: document.documentElement.scrollWidth, iw: innerWidth, font: getComputedStyle(cells[0]).fontSize, cells: [] };
  for (const c of cells) {
    const r = c.getBoundingClientRect();
    const q = document.createRange(); q.selectNodeContents(c);
    const rects = [...q.getClientRects()];
    const k = q.getBoundingClientRect();
    const cx = (r.left + r.right) / 2, cy = (r.top + r.bottom) / 2, rad = r.width / 2 - 1;
    const far = Math.max(...[[k.left, k.top], [k.right, k.top], [k.left, k.bottom], [k.right, k.bottom]].map(([x, y]) => Math.hypot(x - cx, y - cy)));
    const lines = new Set(rects.map((t) => Math.round(t.top))).size;
    out.cells.push({ t: c.textContent, w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10, lines, out: Math.round((far - rad) * 10) / 10 });
  }
  return out;
})()
