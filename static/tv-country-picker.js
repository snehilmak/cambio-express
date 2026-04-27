/*
 * tv-country-picker.js — turns any <select class="js-country-picker">
 * on the page into a searchable Choices.js combobox where each option
 * renders a flag-icons SVG flag + display name + ISO-2 code.
 *
 * Why: native HTML <select> can't render images inside <option>
 * elements (long-standing browser limitation), but operators expect
 * the standard "TV picker UX" (Netflix-style, also Xenok's style)
 * where the dropdown shows a flag + searchable list. Choices.js
 * supports custom item templates that emit arbitrary HTML.
 *
 * Form contract is unchanged — Choices.js wraps the existing
 * <select>, so its `value` is still the ISO-2 code, submitted as
 * the same form field name. Server-side handling is identical.
 *
 * The companion <input id="..."> with name="country_name" (synced
 * from data-name on each option) keeps working because we listen
 * for Choices.js's "change" event on the underlying <select> the
 * same way the previous handler did.
 */
(function () {
  // Defer until both Choices is loaded (it's <script defer>) and
  // the DOM is ready.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }

  function initAll() {
    if (typeof Choices === 'undefined') {
      // Choices.js failed to load (CDN issue / offline dev). Native
      // <select> still works — just skips the enhancement.
      return;
    }
    var pickers = document.querySelectorAll('select.js-country-picker');
    pickers.forEach(function (sel) { enhance(sel); });
  }

  function enhance(sel) {
    // Annotate each <option> with the ISO-2 code (lowercased) so
    // the custom template can build the flag-icons class. The
    // option's value is already the ISO-2 — we just lowercase a
    // copy onto data-iso for template use.
    Array.prototype.forEach.call(sel.options, function (opt) {
      var iso = (opt.value || '').toLowerCase();
      if (iso) opt.dataset.iso = iso;
    });

    var instance = new Choices(sel, {
      searchEnabled: true,
      searchPlaceholderValue: 'Search countries…',
      itemSelectText: '',
      shouldSort: false,            // preserve our intentional order
      allowHTML: true,              // required for flag SVG markup
      removeItemButton: false,
      classNames: {
        // Tag our wrapper so dark-mode CSS in design-tokens.css
        // can target it without bleeding into other Choices uses.
        containerOuter: 'choices db-country-picker',
      },
      callbackOnCreateTemplates: function (template) {
        var classNames = this.config.classNames;
        return {
          // Visible "selected pill" the trigger collapses into.
          item: function (cls, data) {
            return template(
              '<div class="' + cls.item + ' ' +
              (data.highlighted ? cls.highlightedState : cls.itemSelectable) +
              '" data-item data-id="' + data.id + '" data-value="' + data.value + '" ' +
              (data.active ? 'aria-selected="true"' : '') + ' ' +
              (data.disabled ? 'aria-disabled="true"' : '') + '>' +
              flagSpan(data.value) +
              '<span class="db-cp-label">' + escapeHtml(data.label) + '</span>' +
              '</div>'
            );
          },
          // Each row in the open dropdown.
          choice: function (cls, data) {
            return template(
              '<div class="' + cls.item + ' ' + cls.itemChoice +
              (data.disabled ? ' ' + cls.itemDisabled : ' ' + cls.itemSelectable) +
              '" data-select-text="" data-choice ' +
              (data.disabled ? 'data-choice-disabled aria-disabled="true"' : 'data-choice-selectable') +
              ' data-id="' + data.id + '" data-value="' + data.value + '" ' +
              (data.groupId > 0 ? 'role="treeitem"' : 'role="option"') + '>' +
              flagSpan(data.value) +
              '<span class="db-cp-label">' + escapeHtml(data.label) +
              (data.value ? ' <span class="db-cp-iso">(' + escapeHtml(data.value) + ')</span>' : '') +
              '</span>' +
              '</div>'
            );
          },
        };
      },
    });

    // Form-contract preservation: any code listening to the
    // underlying <select>'s change event keeps working — Choices.js
    // dispatches a synthetic change event on the wrapped <select>
    // when the user picks a different option.
  }

  function flagSpan(iso) {
    var c = (iso || '').toLowerCase();
    if (c.length !== 2 || !/^[a-z]{2}$/.test(c)) {
      return '<span class="db-cp-flag-empty" aria-hidden="true">🌐</span>';
    }
    return '<span class="db-cp-flag fi fi-' + c + '" aria-hidden="true"></span>';
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (ch) {
      return {
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
      }[ch];
    });
  }
})();
