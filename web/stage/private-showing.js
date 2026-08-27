/* Private Showing — skip the public wait. This episode is still saved to the library
   and memory; Private Showing just lets you prompt without waiting on others.
   Ask the Selector. Field: private_showing. id="sitcom-private" */
(function () {
	if (!document.body || document.body.classList.contains('broadcast')) return;

	var style = document.createElement('style');
	style.textContent = '#sitcom-private-wrap{display:flex;flex-direction:column;gap:4px;font-size:14px}#sitcom-private-wrap label{display:flex;align-items:center;gap:8px;cursor:pointer}#sitcom-private-help{margin:0;opacity:.8;font-size:12px}@media (max-width:720px){#sitcom-private-help{display:none}}';
	document.head.appendChild(style);

	var wrap = document.createElement('div');
	wrap.id = 'sitcom-private-wrap';
	wrap.innerHTML = '<label><input id="sitcom-private" type="checkbox" /> Private Showing</label><p id="sitcom-private-help">Skip the public wait. This episode is still saved to the library and memory; Private Showing just lets you prompt without waiting on others.</p>';
	var meta = document.getElementById('sitcom-meta-row') || document.getElementById('sitcom-chrome-inner') || document.body;
	var pin = document.getElementById('sitcom-pin-wrap');
	if (pin && pin.parentNode) pin.parentNode.insertBefore(wrap, pin.nextSibling);
	else meta.appendChild(wrap);

	var privateOverride = null;
	var privateHits = 0;
	var nativeFetch = window.fetch.bind(window);
	function installPrivatePacket(packet) {
		if (!packet || !packet.beats || document.body.classList.contains('broadcast')) return;
		privateOverride = packet;
		privateHits = 0;
	}
	window.fetch = function (input, init) {
		var url = typeof input === 'string' ? input : ((input && input.url) || '');
		init = init || {};
		try {
			if (url.indexOf('/episode') !== -1 && url.indexOf('/episode/status') === -1 && String(init.method || 'GET').toUpperCase() === 'POST') {
				var body = {};
				try { body = JSON.parse(init.body || '{}'); } catch (e) { body = {}; }
				var el = document.getElementById('sitcom-private');
				body.private_showing = !!(el && el.checked);
				init = Object.assign({}, init, { body: JSON.stringify(body) });
				return nativeFetch(input, init);
			}
			if (url.indexOf('/episode/status') !== -1) {
				return nativeFetch(input, init).then(function (res) {
					res.clone().json().then(function (s) {
						if (s && s.private && s.packet) installPrivatePacket(s.packet);
					}).catch(function () {});
					return res;
				});
			}
			if (privateOverride && url.indexOf('/now-playing') !== -1 && !document.body.classList.contains('broadcast')) {
				privateHits += 1;
				var payload = JSON.stringify(privateOverride);
				if (privateHits >= 1) {
					var captured = privateOverride;
					setTimeout(function () {
						if (privateOverride === captured) privateOverride = null;
					}, 8000);
				}
				return Promise.resolve(new Response(payload, { status: 200, headers: { 'Content-Type': 'application/json' } }));
			}
		} catch (e) {}
		return nativeFetch(input, init);
	};
})();
