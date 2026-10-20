(() => {
  // One-shot diagnostic dump for the shopping pass: what the page actually is.
  const names = Array.from(
      document.querySelectorAll('li.search-snippet-view [class*="snippet-view__title"]'))
      .slice(0, 8)
      .map(a => a.textContent.trim());
  const bodies = Array.from(
      document.querySelectorAll('li.search-snippet-view [data-object="search-list-item"]'))
      .slice(0, 8)
      .map(a => a.getAttribute('data-coordinates'));
  const cats = new Set();
  for (const a of document.querySelectorAll('a')) {
    const m = (a.getAttribute('href') || '').match(/^\/maps\/(\d+)\/([a-z0-9-]+)\//);
    if (m) cats.add(m[1] + '/' + m[2]);
  }
  return JSON.stringify({
    url: location.href,
    title: document.title,
    snippets: document.querySelectorAll('li.search-snippet-view').length,
    orgLinks: document.querySelectorAll('a[href*="/maps/org/"]').length,
    scroll: document.querySelectorAll('.scroll__container').length,
    names: names,
    coords: bodies,
    cats: Array.from(cats),
    text: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 300)
  });
})()
