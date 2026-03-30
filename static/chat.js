(() => {
  const scriptTag = document.currentScript;
  if (!scriptTag) return;

  const websiteId = (scriptTag.dataset.crispWebsiteId || '').trim();
  if (!websiteId) return;

  window.$crisp = window.$crisp || [];
  window.CRISP_WEBSITE_ID = websiteId;

  const crispLoader = document.createElement('script');
  crispLoader.src = 'https://client.crisp.chat/l.js';
  crispLoader.async = true;
  document.head.appendChild(crispLoader);
})();
