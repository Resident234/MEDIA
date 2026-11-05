(() => {
  const feed = document.querySelector('div[role="feed"]');
  if (!feed) return JSON.stringify({error: 'no_feed'});
  const anchors = feed.querySelectorAll('a[href*="/maps/place/"]');
  const seen = new Set();
  const items = [];
  for (const a of anchors) {
    const href = a.href.split('?')[0];
    const m = href.match(/0x[0-9a-fA-F]+:0x[0-9a-fA-F]+/);
    const fid = m ? m[0] : href;
    if (seen.has(fid)) continue;
    seen.add(fid);
    const h2 = a.querySelector('h2');
    let name = (a.getAttribute('aria-label') || '').trim();
    if (!name && h2) name = h2.textContent.trim();
    if (!name) name = (a.textContent || '').trim().slice(0, 120);
    if (!name) continue;
    const card = a.closest('div[jsaction]') || a.parentElement || a;
    const region = card ? (card.innerText || '') : '';
    const rM = region.match(/(\d+[.,]\d)\s*\((\d[\d\s\u00a0\u202F]*)\)/);
    const rating = rM ? parseFloat(rM[1].replace(',', '.')) : null;
    const reviews = rM ? parseInt(rM[2].replace(/[^\d]/g, ''), 10) : null;
    const lines = region.split('\n').map(s => s.trim()).filter(Boolean);
    items.push({
      fid: fid,
      name: name,
      href: href,
      rating: rating,
      reviews: reviews,
      text: region.slice(0, 500),
      lines: lines.slice(0, 8)
    });
  }
  return JSON.stringify({
    sh: feed.scrollHeight, ch: feed.clientHeight, st: feed.scrollTop,
    count: items.length, items: items
  });
})()
