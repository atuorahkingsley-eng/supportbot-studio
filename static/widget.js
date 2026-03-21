(function () {
  var script = document.currentScript;
  var botId = script.getAttribute('data-bot-id');
  var position = script.getAttribute('data-position') || 'right';
  var baseUrl = script.src.replace('/widget.js', '');

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
  frame.src = baseUrl + '/embed/' + botId;
  frame.style.cssText =
    'width:400px;height:600px;max-height:80vh;border:none;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.15);display:none;margin-bottom:12px;background:white;';
  frame.setAttribute('allow', 'microphone');

  // Notification badge
  var badge = document.createElement('div');
  badge.id = 'supportbot-badge';
  badge.textContent = '1';
  badge.style.cssText =
    'position:absolute;top:-4px;right:-4px;width:20px;height:20px;border-radius:50%;background:#EF4444;color:white;font-size:11px;font-weight:700;display:none;align-items:center;justify-content:center;';

  // Toggle chat
  var isOpen = false;
  bubble.onclick = function () {
    isOpen = !isOpen;
    frame.style.display = isOpen ? 'block' : 'none';
    badge.style.display = 'none';
    bubble.innerHTML = isOpen
      ? '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
      : '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  };

  bubble.onmouseover = function () { bubble.style.transform = 'scale(1.08)'; };
  bubble.onmouseout = function () { bubble.style.transform = 'scale(1)'; };

  // Fetch brand color
  fetch(baseUrl + '/api/config/public/' + botId)
    .then(function (r) { return r.json(); })
    .then(function (config) {
      bubble.style.background = config.brand_color || '#6366F1';
    })
    .catch(function () { /* keep default color */ });

  // Listen for messages from iframe
  window.addEventListener('message', function (event) {
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
  document.body.appendChild(container);
})();
