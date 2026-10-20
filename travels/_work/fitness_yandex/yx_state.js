(() => {
  const q = (s) => document.querySelectorAll(s).length;
  return JSON.stringify({
    url: location.href,
    title: document.title,
    snippets: q('li.search-snippet-view'),
    orgLinks: q('a[href*="/org/"]'),
    scroll: q('.scroll__container'),
    captcha: q('input[type="checkbox"]'),
    bodyHead: document.body ? document.body.innerText.slice(0, 400) : null
  });
})()
