(function () {
  // Trim a trailing slash off `base` and ensure `path` starts with exactly one
  // leading slash before concatenation. Without this, `baseUrl` (which ends in
  // `/` when widget.js is served from the site root) + an absolute path like
  // `/embed/...` produced `https://host//embed/...`. The double-slash 404s on
  // Render's path normalisation and was the cause of the iframe failing to
  // load when the bubble was clicked.
  function joinUrl(base, path) {
    return base.replace(/\/$/, '') + (path.startsWith('/') ? path : '/' + path);
  }

  var script = document.currentScript;
  var botId = script.getAttribute('data-bot-id');
  var position = script.getAttribute('data-position') || 'right';
  var baseUrl = (function(src) {
    var url = new URL(src, window.location.href);
    url.pathname = url.pathname.replace(/\/widget\.js$/, '');
    url.search = '';
    return url.origin + url.pathname;
  })(script.src);

  // Allowed origin for inbound postMessage events. Derived from the script
  // src so the same URL that serves widget.js (and the iframe) is the one
  // we trust — no manual config drift between deployment and code. URL()
  // parsing yields just the scheme+host+port, matching what event.origin
  // returns from the iframe.
  var ALLOWED_ORIGIN = null;
  try {
    ALLOWED_ORIGIN = new URL(baseUrl).origin;
  } catch (e) {
    // baseUrl wasn't a valid absolute URL; leave ALLOWED_ORIGIN null so
    // the listener below rejects every message rather than failing open.
  }

  // Known message types. Strings (not object envelopes) match the existing
  // iframe protocol; widening to objects would be a wire-format change
  // beyond the scope of this fix.
  var ALLOWED_MESSAGES = ['supportbot:notify', 'supportbot:close'];

  if (!botId) {
    console.error('SupportBot: data-bot-id attribute is required');
    return;
  }

  // Prevent double-loading
  if (document.getElementById('supportbot-widget')) return;

  // Container
  var container = document.createElement('div');
  container.id = 'supportbot-widget';
  container.style.cssText =
    'position:fixed;bottom:20px;' + position + ':20px;z-index:99999;font-family:sans-serif;';

  // Chat bubble button
  var bubble = document.createElement('div');
  bubble.id = 'supportbot-bubble';
  bubble.innerHTML =
    '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  bubble.style.cssText =
    'width:60px;height:60px;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,0.2);transition:transform 0.2s;background:#6366F1;';

  // iframe (hidden initially)
  var frame = document.createElement('iframe');
  frame.id = 'supportbot-frame';
  frame.src = joinUrl(baseUrl, '/embed/' + botId);
  frame.style.cssText =
    'width:min(400px,calc(100vw - 40px));height:600px;max-height:80vh;border:none;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.15);display:none;margin-bottom:12px;background:white;';
  frame.setAttribute('allow', 'microphone');

  // Notification badge
  var badge = document.createElement('div');
  badge.id = 'supportbot-badge';
  badge.textContent = '1';
  badge.style.cssText =
    'position:absolute;top:-4px;right:-4px;width:20px;height:20px;border-radius:50%;background:#EF4444;color:white;font-size:11px;font-weight:700;display:none;align-items:center;justify-content:center;';

  // Auto-greeting state (declared before bubble.onclick so the toggle can clear them)
  var GREETING_DELAY_MS = 5000;
  var GREETING_DISMISS_KEY = 'supportbot_greeting_dismissed_' + botId;
  var greetingTimer = null;
  var tooltip = null;

  function removeTooltip() {
    if (tooltip && tooltip.parentNode) tooltip.parentNode.removeChild(tooltip);
    tooltip = null;
  }

  function cancelGreeting() {
    if (greetingTimer) { clearTimeout(greetingTimer); greetingTimer = null; }
    removeTooltip();
  }

  // Toggle chat
  var isOpen = false;
  bubble.onclick = function () {
    cancelGreeting();
    isOpen = !isOpen;
    frame.style.display = isOpen ? 'block' : 'none';
    badge.style.display = 'none';
    bubble.innerHTML = isOpen
      ? '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
      : '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  };

  bubble.onmouseover = function () { bubble.style.transform = 'scale(1.08)'; };
  bubble.onmouseout = function () { bubble.style.transform = 'scale(1)'; };

  function showGreeting(message) {
    // Skip if dismissed earlier this session, already open, or already showing.
    try { if (sessionStorage.getItem(GREETING_DISMISS_KEY) === '1') return; } catch (e) {}
    if (isOpen || tooltip) return;

    tooltip = document.createElement('div');
    tooltip.id = 'supportbot-greeting';
    tooltip.style.cssText =
      'position:absolute;bottom:74px;' + (position === 'left' ? 'left:0' : 'right:0') + ';' +
      'background:white;color:#1F2937;padding:10px 32px 10px 14px;border-radius:14px;' +
      'box-shadow:0 4px 20px rgba(0,0,0,0.15);' +
      'font-size:14px;font-weight:500;line-height:1.4;' +
      'max-width:200px;cursor:pointer;' +
      'white-space:normal;word-wrap:break-word;overflow-wrap:break-word;' +
      'animation:supportbot-fade-in 0.3s ease-out;';

    // Message text — kept in its own span so the emoji span next to it
    // renders independently. JS string literals don't go through the
    // SQL migration / server encoding pipeline that broke the inline emoji.
    var msgSpan = document.createElement('span');
    msgSpan.textContent = message;
    tooltip.appendChild(msgSpan);

    var wave = document.createElement('span');
    wave.textContent = '👋';
    wave.setAttribute('aria-hidden', 'true');
    wave.style.cssText = 'display:inline-block;margin-left:6px;font-size:16px;';
    tooltip.appendChild(wave);

    var close = document.createElement('span');
    close.textContent = '×';
    close.setAttribute('aria-label', 'Dismiss');
    close.style.cssText =
      'position:absolute;top:2px;right:8px;font-size:18px;line-height:1;' +
      'color:#9CA3AF;cursor:pointer;font-weight:600;padding:2px 4px;';
    close.onclick = function (e) {
      e.stopPropagation();
      try { sessionStorage.setItem(GREETING_DISMISS_KEY, '1'); } catch (e2) {}
      removeTooltip();
    };
    tooltip.appendChild(close);

    // Click anywhere else on the tooltip → open chat.
    tooltip.onclick = function () {
      removeTooltip();
      bubble.click();
    };

    bubbleWrapper.appendChild(tooltip);
  }

  // Fetch brand color + greeting message
  fetch(joinUrl(baseUrl, '/api/config/public/' + botId))
    .then(function (r) { return r.json(); })
    .then(function (config) {
      bubble.style.background = config.brand_color || '#6366F1';
      var greeting = (config && config.greeting_message) || 'Hi! Need help?';
      try { if (sessionStorage.getItem(GREETING_DISMISS_KEY) === '1') return; } catch (e) {}
      greetingTimer = setTimeout(function () { showGreeting(greeting); }, GREETING_DELAY_MS);
    })
    .catch(function () {
      // Even on fetch failure, show a default greeting so engagement still triggers.
      try { if (sessionStorage.getItem(GREETING_DISMISS_KEY) === '1') return; } catch (e) {}
      greetingTimer = setTimeout(function () { showGreeting('Hi! Need help?'); }, GREETING_DELAY_MS);
    });

  // Listen for messages from iframe.
  //
  // Two gates before any handler runs:
  //   1. event.origin must match the origin that served widget.js (and
  //      therefore the iframe). If ALLOWED_ORIGIN never resolved (bad
  //      baseUrl), we reject every message — fail closed.
  //   2. event.data must be one of the known string commands. Without
  //      this, any page on the same origin (e.g. a dev console, a
  //      sibling iframe, a malicious script that opened a same-origin
  //      window) could fire 'supportbot:close' or trigger the badge.
  window.addEventListener('message', function (event) {
    if (!ALLOWED_ORIGIN || event.origin !== ALLOWED_ORIGIN) return;
    if (typeof event.data !== 'string' || ALLOWED_MESSAGES.indexOf(event.data) === -1) return;

    if (event.data === 'supportbot:notify') {
      if (!isOpen) {
        badge.style.display = 'flex';
      }
    }
    if (event.data === 'supportbot:close') {
      isOpen = false;
      frame.style.display = 'none';
      bubble.innerHTML =
        '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
    }
  });

  // Assemble
  var wrapper = document.createElement('div');
  wrapper.style.cssText =
    'display:flex;flex-direction:column;align-items:' +
    (position === 'left' ? 'flex-start' : 'flex-end') + ';';
  wrapper.appendChild(frame);

  var bubbleWrapper = document.createElement('div');
  bubbleWrapper.style.cssText = 'position:relative;';
  bubbleWrapper.appendChild(bubble);
  bubbleWrapper.appendChild(badge);
  wrapper.appendChild(bubbleWrapper);

  container.appendChild(wrapper);

  // Animation keyframes for the greeting tooltip — injected once per page.
  if (!document.getElementById('supportbot-styles')) {
    var styleEl = document.createElement('style');
    styleEl.id = 'supportbot-styles';
    styleEl.textContent =
      '@keyframes supportbot-fade-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }';
    document.head.appendChild(styleEl);
  }

  document.body.appendChild(container);
})();
