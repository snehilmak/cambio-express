/* Shared debounced live-search helper.
   --------------------------------------------------------------------
   Used by /return-checks and /owner/locations — two pages whose JS
   was structurally identical: one search input, debounce keystrokes,
   abort the in-flight request when a new one starts, swap the result
   region with the response HTML, and keep the URL in sync so the
   filters are bookmarkable.

   The helper handles the universal mechanics; each caller plugs in
   its own URL builder + result-render callback so page-specific
   concerns (multiple result targets, custom meta text, action
   re-binding after a swap) stay in the page's JS.

   /transfers does NOT use this helper — its search watches every
   form-wide input change (not just one box) and surfaces a
   status-text indicator. Forcing it into this signature would push
   the helper into 5+ parameters, so it stays bespoke. Per the
   project's CLAUDE.md, two callers + clear shared shape is the
   threshold for an abstraction; three different shapes is not.

   Usage:

       attachSearchDebounce({
           input:       document.getElementById('mySearch'),
           buildUrl:    function (q) {
               // Return the full URL (path + query string) to fetch.
               return '/things?' + new URLSearchParams({
                   partial: '1', q: q, foo: currentFoo()
               }).toString();
           },
           onResult:    function (data, q) {
               // Called with the parsed JSON and the trimmed query.
               document.getElementById('result').innerHTML = data.html;
           },
           syncUrl:     true,    // optional, default true: history.replaceState
           debounceMs:  300,     // optional, default 300
           minLength:   2,       // optional, default 2 (empty q always allowed)
       });
*/
(function () {
    function attach(opts) {
        var input = opts.input;
        if (!input) return;
        var buildUrl    = opts.buildUrl;
        var onResult    = opts.onResult;
        var debounceMs  = opts.debounceMs != null ? opts.debounceMs : 300;
        var minLength   = opts.minLength  != null ? opts.minLength  : 2;
        var syncUrl     = opts.syncUrl    !== false;  // default true

        var timer = null;
        var ctrl  = null;

        function pushQueryToHistory(q) {
            if (!syncUrl) return;
            var url = new URL(window.location.href);
            if (q) url.searchParams.set('q', q);
            else   url.searchParams.delete('q');
            history.replaceState(null, '', url);
        }

        function fetchAndRender(q) {
            if (ctrl) ctrl.abort();
            ctrl = new AbortController();
            var url = buildUrl(q);
            fetch(url, {
                headers: { 'X-Requested-With': 'fetch' },
                signal: ctrl.signal,
            })
            .then(function (r) { return r.json(); })
            .then(function (data) { onResult(data, q); })
            .catch(function (e) {
                if (e.name !== 'AbortError') console.error(e);
            });
        }

        input.addEventListener('input', function () {
            var q = input.value.trim();
            if (timer) clearTimeout(timer);
            // Empty `q` is fine (clears the search). 1 char is too
            // broad — wait for at least minLength chars.
            if (q.length > 0 && q.length < minLength) return;
            timer = setTimeout(function () {
                pushQueryToHistory(q);
                fetchAndRender(q);
            }, debounceMs);
        });
    }

    window.attachSearchDebounce = attach;
})();
