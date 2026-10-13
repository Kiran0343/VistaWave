(() => {
  const scriptTag = document.currentScript;
  if (!scriptTag) return;

  const websiteId = (scriptTag.dataset.crispWebsiteId || '').trim();
  if (!websiteId) return;

  window.$crisp = window.$crisp || [];
  window.CRISP_WEBSITE_ID = websiteId;

  let loaded = false;
  let idleTimer = null;

  const loadCrisp = () => {
    if (loaded) return;
    loaded = true;

    if (idleTimer) {
      window.clearTimeout(idleTimer);
      idleTimer = null;
    }

    const crispLoader = document.createElement('script');
    crispLoader.src = 'https://client.crisp.chat/l.js';
    crispLoader.async = true;
    document.head.appendChild(crispLoader);

    window.removeEventListener('pointerdown', loadCrisp);
    window.removeEventListener('keydown', loadCrisp);
    window.removeEventListener('scroll', loadCrisp);
  };

  // Load chat on first real interaction, or after a short idle delay.
  window.addEventListener('pointerdown', loadCrisp, { once: true, passive: true });
  window.addEventListener('keydown', loadCrisp, { once: true });
  window.addEventListener('scroll', loadCrisp, { once: true, passive: true });
  idleTimer = window.setTimeout(loadCrisp, 10000);
})();
