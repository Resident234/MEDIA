(() => {
  // Completeness probe on a search results page: is the list capped, and does
  // it end with a "show more" control?
  const sc = document.querySelector('.scroll__container');
  if (sc) sc.scrollTop = sc.scrollHeight;
  const items = Array.from(document.querySelectorAll('li.search-snippet-view'));
  const panel = document.querySelector('[class*="sidebar-view"]') || document;
  return JSON.stringify({
    url: location.href,
    rendered: items.length,
    last: items.length ? items[items.length - 1].innerText.replace(/\s+/g, ' ').slice(0, 120) : null,
    first: items.length ? items[0].innerText.replace(/\s+/g, ' ').slice(0, 80) : null,
    moreBtns: Array.from(panel.querySelectorAll('button, a')).map(b => (b.innerText || '').replace(/\s+/g, ' ').trim())
      .filter(t => /ещё|еще|раньше|показать|все результаты|Earlier|More/i.test(t)).slice(0, 10),
    footerText: Array.from(document.querySelectorAll('[class*="search-results-list-view"] , [class*="list-status"]'))
      .map(e => e.innerText.replace(/\s+/g, ' ').slice(0, 200)).slice(0, 4),
    scroll: sc ? [sc.scrollTop, sc.scrollHeight, sc.clientHeight] : null
  });
})()
