(() => {
  const f = document.querySelector('div[role="feed"]');
  if (f) f.scrollTo(0, f.scrollHeight);
  return JSON.stringify({ok: !!f});
})()
