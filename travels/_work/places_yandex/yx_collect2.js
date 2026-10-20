(() => {
  // Same dump as yx_collect.js, but the FIRST pass on a freshly loaded page
  // rewinds the container to scrollTop 0 instead of scrolling forward, so the
  // very first snippets of the virtualized list are never skipped.
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
  const items = Array.from(document.querySelectorAll('li.search-snippet-view')).map(it => {
    const body = it.querySelector('[data-object="search-list-item"]') || it;
    const a = it.querySelector('a.link-overlay') || it.querySelector('a[href*="/org/"]');
    const badge = it.querySelector('[class*="business-rating-badge-view"]');
    const title = it.querySelector('[class*="snippet-view__title"]');
    return {
      id: body.getAttribute('data-id'),
      coords: body.getAttribute('data-coordinates'),
      href: a ? a.getAttribute('href') : null,
      name: title ? title.textContent.trim() : null,
      ratingAria: badge ? badge.getAttribute('aria-label') : null,
      text: it.innerText.replace(/\s*\n+\s*/g, ' | ')
    };
  });
  return JSON.stringify({
    pass: window.__yxPass || 0,
    top: sc ? Math.round(sc.scrollTop) : -1,
    sh: sc ? sc.scrollHeight : -1,
    ch: sc ? sc.clientHeight : -1,
    rendered: items.length,
    items: items
  });
})()
