(() => {
  const it = document.querySelector('.search-snippet-view');
  const res = {};
  res.html = it ? it.outerHTML.slice(0, 3000) : null;
  res.text = it ? it.innerText.slice(0, 500) : null;
  let el = it;
  const chain = [];
  while (el && el !== document.documentElement) {
    if (el.scrollHeight > el.clientHeight + 5) {
      chain.push({
        cls: String(el.className || el.tagName).slice(0, 90),
        sh: el.scrollHeight,
        ch: el.clientHeight
      });
    }
    el = el.parentElement;
  }
  res.scrollables = chain;
  res.count = document.querySelectorAll('.search-snippet-view').length;
  res.winScroll = { sh: document.scrollingElement.scrollHeight, ch: document.scrollingElement.clientHeight, top: document.scrollingElement.scrollTop };
  return JSON.stringify(res);
})()
