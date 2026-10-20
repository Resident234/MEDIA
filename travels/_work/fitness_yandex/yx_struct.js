(() => {
  const cands = [
    '.search-snippet-view',
    '.organization-snippet-view',
    '.api-organization-item-view',
    '.organic-view',
    '.serp-item',
    'a[href*="/org/"]',
    '[class*="rating"]',
    '[class*="list-view"]'
  ];
  const o = {};
  for (const s of cands) {
    try { o[s] = document.querySelectorAll(s).length; } catch (e) { o[s] = 'ERR'; }
  }
  o.hrefs = Array.from(document.querySelectorAll('a[href*="/org/"]'))
    .slice(0, 5)
    .map(a => a.getAttribute('href').slice(0, 130));
  o.classes = Array.from(document.querySelectorAll('a[href*="/org/"]'))
    .slice(0, 3)
    .map(a => (a.closest('li,article,div') || {}).className || '');
  return JSON.stringify(o);
})()
