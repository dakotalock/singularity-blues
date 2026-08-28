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

	var privateJobs = [];
	var nativeFetch = window.fetch.bind(window);
	function rememberPrivateJob(jobId) {
		if (!jobId || privateJobs.indexOf(jobId) !== -1) return;
		privateJobs.push(jobId);
	}
	function isPlayerPoll(url) {
		var endpoint = window.location.origin + '/now-playing';
		return url === endpoint || url.indexOf(endpoint + '?') === 0;
	}
	function isStatusPoll(url) {
		var path = '/episode/status';
		var endpoint = window.location.origin + path;
		return url === path || url.indexOf(path + '?') === 0 || url === endpoint || url.indexOf(endpoint + '?') === 0;
	}
	function absoluteSameOrigin(url) {
		return url.charAt(0) === '/' ? window.location.origin + url : url;
	}
	function publicFetch(input, init) {
		// WebKit can reject an otherwise valid Request when an unnecessary empty
		// init object is supplied. Preserve the browser's one-argument fetch path.
		return init && Object.keys(init).length ? nativeFetch(input, init) : nativeFetch(input);
	}
	function statusFetch(input, init, retries) {
		var url = typeof input === 'string' ? absoluteSameOrigin(input) : input;
		return publicFetch(url, init).catch(function (err) {
			if (retries <= 0) throw err;
			return new Promise(function (resolve) { window.setTimeout(resolve, 300); })
				.then(function () { return statusFetch(url, init, retries - 1); });
		});
	}
	window.fetch = function (input, init) {
		var url = typeof input === 'string' ? input : ((input && input.url) || '');
		var options = init || {};
		try {
			if (url.indexOf('/episode') !== -1 && url.indexOf('/episode/status') === -1 && url.indexOf('/episode/private-packet') === -1 && String(options.method || 'GET').toUpperCase() === 'POST') {
				var body = {};
				try { body = JSON.parse(options.body || '{}'); } catch (e) { body = {}; }
				var el = document.getElementById('sitcom-private');
				var wantsPrivate = !!(el && el.checked);
				body.private_showing = wantsPrivate;
				var postOptions = Object.assign({}, options, { body: JSON.stringify(body) });
				// Passing Safari the URL string plus a clean options object avoids reusing a
				// consumed Request body, which can throw a pattern-mismatch DOMException.
				return nativeFetch(url, postOptions).then(function (res) {
					if (wantsPrivate && res.ok) res.clone().json().then(function (result) {
						if (result && result.private && result.job_id) rememberPrivateJob(String(result.job_id));
					}).catch(function () {});
					return res;
				});
			}
			// Only Godot asks with the absolute URL. The page chrome polls the relative
			// public endpoint and must never consume a buyer's private handoff.
			if (privateJobs.length && isPlayerPoll(url)) {
				var jobId = privateJobs[0];
				var packetUrl = '/episode/private-packet?job_id=' + encodeURIComponent(jobId);
				return nativeFetch(packetUrl, { credentials: 'same-origin', cache: 'no-store' }).then(function (res) {
					if (res.ok) {
						privateJobs.shift();
						return res;
					}
					if (res.status === 404 || res.status === 410) privateJobs.shift();
					return publicFetch(input, options);
				}).catch(function () { return publicFetch(input, options); });
			}
		} catch (e) {}
		// The page polls this while voices render. A transient WebKit
		// pattern-mismatch DOMException must not turn a healthy server job into a
		// visible failure; normalize the URL and retry before surfacing it.
		if (isStatusPoll(url)) return statusFetch(input, options, 3);
		return publicFetch(input, options);
	};
})();
