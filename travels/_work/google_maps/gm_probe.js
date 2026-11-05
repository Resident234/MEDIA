(() => JSON.stringify({
  url: location.href,
  title: document.title,
  feed: document.querySelectorAll('div[role="feed"]').length,
  anchors: document.querySelectorAll('a[href*="/maps/place/"]').length,
  h1: (document.querySelector('h1.DUwDvf, h1') || {}).textContent,
  capthcha: /unusual traffic|captcha|not a robot|\/service\/static\/error/i.test(
    (document.body && document.body.innerText) || "")
}))()
