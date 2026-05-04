/* Shared chrome JS — sidebar drawer, topbar clock, user-avatar dropdown.
 * --------------------------------------------------------------------
 *
 * Both `base.html` (admin / employee / superadmin) and `base_owner.html`
 * (multi-store owner) ship the same topbar + sidebar shell. Until this
 * file existed, each base carried its own duplicate copy of the JS
 * wiring — and that copy drifted: the dropdown used a class-toggle
 * pattern in one shell and a `hidden`-only toggle in the other, so
 * owner login users couldn't open their avatar menu (no logout, no
 * profile, no nav). See https://github.com/snehilmak/cambio-express/pull/197
 * for the bug write-up.
 *
 * One file, two shells. If you change the chrome contract here you
 * change it everywhere. Anything that's truly admin-only (referral
 * crown, install prompt, announcement banners, time-tag localization)
 * stays in base.html — this file is only the cross-shell baseline.
 *
 * Each init is defensive — it queries for its own anchor element and
 * silently no-ops when the element isn't on the page. Callable
 * multiple times safely (idempotent listener attach via `dataset.bound`).
 *
 * Load with `defer` after the DOM is parsed; we re-run on
 * DOMContentLoaded as a belt-and-suspenders for the non-defer case.
 */
(function () {
  'use strict';

  // ── Topbar clock ─────────────────────────────────────────────
  // Refreshed every 30s. Displayed as e.g. "Mon, May 4 · 02:37 PM".
  function initClock() {
    var clockEl = document.getElementById('clock');
    if (!clockEl || clockEl.dataset.bound) return;
    clockEl.dataset.bound = '1';
    function update() {
      var now = new Date();
      clockEl.textContent =
        now.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) +
        ' · ' + now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }
    update();
    setInterval(update, 30000);
  }

  // ── Sidebar drawer (mobile) ──────────────────────────────────
  // Three triggers: hamburger button, close button (X inside the
  // drawer), and the dimming backdrop. Auto-closes on resize past
  // the 900px breakpoint and on link click (so a nav action
  // doesn't leave the drawer hanging open over the new page).
  function initSidebarDrawer() {
    var sidebar  = document.getElementById('sidebar');
    var toggle   = document.getElementById('menuToggle');
    var closeBtn = document.getElementById('sidebarClose');
    var backdrop = document.getElementById('sidebarBackdrop');
    if (!sidebar || sidebar.dataset.bound) return;
    sidebar.dataset.bound = '1';

    function open() {
      sidebar.classList.add('open');
      document.body.classList.add('nav-open');
    }
    function shut() {
      sidebar.classList.remove('open');
      document.body.classList.remove('nav-open');
    }
    if (toggle)   toggle.addEventListener('click', open);
    if (closeBtn) closeBtn.addEventListener('click', shut);
    if (backdrop) backdrop.addEventListener('click', shut);
    sidebar.addEventListener('click', function (e) {
      var a = e.target.closest('a');
      if (a && window.innerWidth <= 900) shut();
    });
    window.addEventListener('resize', function () {
      if (window.innerWidth > 900) shut();
    });
  }

  // ── User-avatar dropdown ─────────────────────────────────────
  // The dropdown CSS animates open/close via an `.is-open` class —
  // toggling only the `hidden` attribute leaves opacity:0 +
  // pointer-events:none active on the base styles, so the menu
  // ends up invisible AND unclickable. Open path: remove `hidden`,
  // force a paint, then add `.is-open`. Close path: remove
  // `.is-open`, then re-set `hidden` after the 200ms transition
  // settles.
  function initAvatarDropdown() {
    var avatar   = document.getElementById('userAvatar');
    var dropdown = document.getElementById('userDropdown');
    if (!avatar || !dropdown || avatar.dataset.bound) return;
    avatar.dataset.bound = '1';

    var closeTimer = null;
    function closeMenu() {
      dropdown.classList.remove('is-open');
      avatar.setAttribute('aria-expanded', 'false');
      clearTimeout(closeTimer);
      closeTimer = setTimeout(function () {
        if (!dropdown.classList.contains('is-open')) {
          dropdown.setAttribute('hidden', '');
        }
      }, 200);
    }
    function openMenu() {
      clearTimeout(closeTimer);
      dropdown.removeAttribute('hidden');
      // Force paint so the from-state commits before .is-open kicks in.
      void dropdown.offsetHeight;
      dropdown.classList.add('is-open');
      avatar.setAttribute('aria-expanded', 'true');
    }
    avatar.addEventListener('click', function (e) {
      e.stopPropagation();
      if (dropdown.classList.contains('is-open')) closeMenu();
      else                                         openMenu();
    });
    document.addEventListener('click', function (e) {
      if (!dropdown.contains(e.target) && e.target !== avatar) closeMenu();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeMenu();
    });
  }

  function initAll() {
    initClock();
    initSidebarDrawer();
    initAvatarDropdown();
  }

  // Run now if the DOM is already parsed (covers the synchronous
  // <script> case); otherwise wait for DOMContentLoaded (covers
  // defer / async).
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
