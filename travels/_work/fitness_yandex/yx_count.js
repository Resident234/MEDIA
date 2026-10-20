(() => {
  // Find any text that looks like a result count ("Нашли 60 мест", "60 мест").
  const t = document.body.innerText;
  const m = t.match(/[^\n]{0,60}(место|мест|результат|найдено|Найден)[^\n]{0,40}/gi);
  const hdr = Array.from(document.querySelectorAll('[class*="search-result-count"],[data-object="search-result-count"]'));
  return JSON.stringify({
    url: location.href,
    matches: m ? m.slice(0, 12) : [],
    hdr: hdr.map(e => e.innerText),
    sh: (() => { const s = document.querySelector('.scroll__container'); return s ? [s.scrollTop, s.scrollHeight, s.clientHeight] : null; })()
  });
})()
