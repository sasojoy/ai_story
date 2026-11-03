// 量裝備庫每一列：鈕寬、鈕裡的小段有沒有超出鈕（Range 對鈕的內框）、小段有沒有被拆、名字那一欄多寬、一列多高、那一行數字折幾行
(() => {
  document.querySelector('.shop-more')?.click();
  const rows = [...document.querySelectorAll('.rk-row')];
  const out = { sw: document.documentElement.scrollWidth, iw: innerWidth, rows: [] };
  for (const row of rows) {
    const name = row.querySelector('.winfo b')?.textContent;
    const info = row.querySelector('.winfo').getBoundingClientRect();
    const line = row.querySelector('.winfo span');
    const lh = parseFloat(getComputedStyle(line).lineHeight) || 20;
    const btns = [...row.querySelectorAll('.rk-btn')].map((b) => {
      const r = b.getBoundingClientRect(), cs = getComputedStyle(b);
      const inner = [r.left + parseFloat(cs.paddingLeft) + parseFloat(cs.borderLeftWidth), r.right - parseFloat(cs.paddingRight) - parseFloat(cs.borderRightWidth)];
      const over = [...b.querySelectorAll('.nb, b')].map((s) => { const q = document.createRange(); q.selectNodeContents(s); const k = q.getBoundingClientRect(); return Math.max(inner[0] - k.left, k.right - inner[1]); });
      const split = [...b.querySelectorAll('.nb')].filter((s) => s.getClientRects().length > 1).length;
      return { w: Math.round(r.width * 10) / 10, top: Math.round(r.top), over: Math.round(Math.max(0, ...over) * 10) / 10, split, text: b.innerText.replace(/\s+/g, ' ') };
    });
    const lineSplit = [...line.querySelectorAll('.nb')].filter((s) => s.getClientRects().length > 1).length;
    out.rows.push({ name, h: Math.round(row.getBoundingClientRect().height), nameW: Math.round(info.width), lineLines: Math.round(line.getBoundingClientRect().height / lh), lineSplit, btns });
  }
  return out;
})()
