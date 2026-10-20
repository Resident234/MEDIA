(() => {
  const t = document.body ? document.body.innerText : "";
  return JSON.stringify({
    url: location.href,
    title: document.title,
    htmlLen: document.documentElement.outerHTML.length,
    textLen: t.length,
    text: t.slice(0, 1500)
  });
})()
