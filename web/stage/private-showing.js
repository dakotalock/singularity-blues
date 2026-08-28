/* Private Showing — UI only. The generated stage HTML submits private_showing
   directly and Godot requests its buyer-bound handoff with ?player=1. Never
   monkeypatch window.fetch here: Safari correctly treats fetch as a host API. */
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
})();
