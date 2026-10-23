(() => {
  /* One scroll pass over the virtualized result list plus a dump of the
     business objects the page keeps in its state snapshot. */
  const sc = document.querySelector('.scroll__container');
  if (sc) {
    if (!window.__yxPass) {
      window.__yxPass = 1;
      sc.scrollTop = 0;
    } else {
      window.__yxPass++;
      const step = Math.max(300, sc.clientHeight - 60);
      sc.scrollTop = sc.scrollTop + step;
    }
  }
  const out = {
    pass: window.__yxPass || 0,
    top: sc ? Math.round(sc.scrollTop) : -1,
    sh: sc ? sc.scrollHeight : -1,
    ch: sc ? sc.clientHeight : -1,
    snippets: document.querySelectorAll('li.search-snippet-view').length,
    none: /ничего не нашлось|Ничего не нашлось/.test(document.body.innerText || ''),
    limited: /^limited$/.test((document.body.innerText || '').trim()),
    total: null,
    items: []
  };
  const s = document.querySelector('script.state-view');
  if (s) {
    let st = null;
    try { st = JSON.parse(s.textContent); } catch (e) { st = null; }
    if (st) {
      const results = [];
      const stack = st.stack || [];
      for (const lvl of stack) {
        if (lvl && lvl.results && Array.isArray(lvl.results.items)) results.push(lvl.results);
      }
      if (!results.length) {
        const rs = st.search && st.search.results;
        if (rs && Array.isArray(rs.items)) results.push(rs);
      }
      for (const r of results) {
        if (out.total === null && r.totalResultCount) out.total = r.totalResultCount;
        for (const n of r.items) {
          if (!n || n.type !== 'business' || !n.id) continue;
          out.items.push({
            id: String(n.id),
            title: n.title || n.shortTitle || null,
            address: n.address || n.fullAddress || null,
            fullAddress: n.fullAddress || null,
            coords: n.coordinates || null,
            seoname: n.seoname || null,
            geoId: n.geoId || null,
            country: n.country || null,
            ratingData: n.ratingData || null,
            categories: n.categories || null,
            phones: n.phones || null,
            urls: n.urls || null,
            socialLinks: n.socialLinks || null,
            businessLinks: n.businessLinks || null,
            workingTime: n.workingTimeText || null,
            references: n.references || null
          });
        }
      }
    }
  }
  return JSON.stringify(out);
})()
