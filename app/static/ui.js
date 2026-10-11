/*!
 * Shared UI behaviours: styled confirmation dialogs and toast notifications.
 *
 * Replaces the browser's native confirm()/alert() so destructive actions and
 * messages look like the rest of the app.
 *
 * Usage
 * -----
 * Declarative (preferred for forms and buttons):
 *
 *   <form method="post" action="..." data-confirm="Delete this expense?">
 *     <button>Delete</button>
 *   </form>
 *
 *   <button data-confirm="Undo this payment?">Undo</button>
 *
 * The element's own submit/click proceeds only if the user confirms.
 *
 * Imperative (for JS flows):
 *
 *   window.SchoolUI.confirm('Delete this expense?').then(function (ok) {
 *       if (ok) { ... }
 *   });
 *
 *   window.SchoolUI.toast('Attendance saved', 'success');
 */
(function () {
    'use strict';

    var CONFIRM_TITLE = 'Please confirm';
    var DEFAULT_VARIANT = 'primary';

    // Words that make a message read as destructive, so the button turns red.
    var DESTRUCTIVE = /(delete|remove|discard|erase|revert|undo|archive|unlock|replace|reset|clear)/i;

    function ready(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    // --------------------------------------------------------------------- //
    // Confirmation dialog
    // --------------------------------------------------------------------- //

    function dialogElement() {
        var el = document.getElementById('schoolConfirmModal');
        if (el) return el;

        el = document.createElement('div');
        el.className = 'modal fade';
        el.id = 'schoolConfirmModal';
        el.tabIndex = -1;
        el.setAttribute('aria-hidden', 'true');
        el.innerHTML =
            '<div class="modal-dialog modal-dialog-centered modal-sm">' +
              '<div class="modal-content">' +
                '<div class="modal-header bg-dark text-white">' +
                  '<h5 class="modal-title"><i class="fas fa-circle-question me-2"></i>' +
                    '<span data-confirm-title></span></h5>' +
                  '<button type="button" class="btn-close btn-close-white" ' +
                    'data-bs-dismiss="modal" aria-label="Close"></button>' +
                '</div>' +
                '<div class="modal-body"><p class="mb-0" data-confirm-message></p></div>' +
                '<div class="modal-footer">' +
                  '<button type="button" class="btn btn-outline-secondary btn-sm" ' +
                    'data-bs-dismiss="modal" data-confirm-cancel>Cancel</button>' +
                  '<button type="button" class="btn btn-sm" data-confirm-ok>Confirm</button>' +
                '</div>' +
              '</div>' +
            '</div>';
        document.body.appendChild(el);
        return el;
    }

    function confirmDialog(message, options) {
        options = options || {};
        return new Promise(function (resolve) {
            if (!window.bootstrap || !window.bootstrap.Modal) {
                // Bootstrap unavailable: never block the user's action silently.
                resolve(window.confirm(message));
                return;
            }
            var el = dialogElement();
            var title = options.title || CONFIRM_TITLE;
            var okLabel = options.okLabel || 'Confirm';
            var cancelLabel = options.cancelLabel || 'Cancel';
            var variant = options.variant ||
                (DESTRUCTIVE.test(message) ? 'danger' : DEFAULT_VARIANT);

            el.querySelector('[data-confirm-title]').textContent = title;
            el.querySelector('[data-confirm-message]').textContent = message;
            var okButton = el.querySelector('[data-confirm-ok]');
            okButton.textContent = okLabel;
            okButton.className = 'btn btn-sm btn-' + variant;
            el.querySelector('[data-confirm-cancel]').textContent = cancelLabel;

            var settled = false;
            function settle(value) {
                if (settled) return;
                settled = true;
                okButton.removeEventListener('click', onOk);
                el.removeEventListener('hidden.bs.modal', onHidden);
                resolve(value);
            }
            function onOk() {
                // Hide first, then settle, so the click never leaks to the page.
                var instance = window.bootstrap.Modal.getOrCreateInstance(el);
                instance.hide();
                settle(true);
            }
            function onHidden() {
                settle(false);
            }

            okButton.addEventListener('click', onOk);
            el.addEventListener('hidden.bs.modal', onHidden);
            window.bootstrap.Modal.getOrCreateInstance(el).show();
        });
    }

    // --------------------------------------------------------------------- //
    // Toast notifications
    // --------------------------------------------------------------------- //

    var TOAST_VARIANTS = {
        success: 'text-bg-success',
        danger: 'text-bg-danger',
        error: 'text-bg-danger',
        warning: 'text-bg-warning',
        info: 'text-bg-primary',
        primary: 'text-bg-primary',
        secondary: 'text-bg-secondary'
    };
    var TOAST_ICONS = {
        success: 'fa-circle-check',
        danger: 'fa-circle-exclamation',
        warning: 'fa-triangle-exclamation',
        info: 'fa-circle-info',
        primary: 'fa-circle-info',
        secondary: 'fa-circle-info'
    };

    function toastContainer() {
        var el = document.getElementById('schoolToastContainer');
        if (el) return el;
        el = document.createElement('div');
        el.id = 'schoolToastContainer';
        el.className = 'toast-container position-fixed top-0 end-0 p-3 no-print';
        el.style.zIndex = '1090';
        el.setAttribute('aria-live', 'polite');
        el.setAttribute('aria-atomic', 'true');
        document.body.appendChild(el);
        return el;
    }

    function toast(message, variant) {
        variant = (variant || 'info').toLowerCase();
        var cssClass = TOAST_VARIANTS[variant] || TOAST_VARIANTS.info;
        var icon = TOAST_ICONS[variant] || TOAST_ICONS.info;
        var body = String(message === undefined || message === null ? '' : message);

        var wrapper = document.createElement('div');
        wrapper.className = 'toast ' + cssClass + ' border-0';
        wrapper.setAttribute('role', 'status');
        wrapper.setAttribute('aria-live', 'polite');
        wrapper.innerHTML =
            '<div class="d-flex">' +
              '<div class="toast-body"><i class="fas ' + icon + ' me-2"></i></div>' +
              '<button type="button" class="btn-close btn-close-white me-2 m-auto" ' +
                'data-bs-dismiss="toast" aria-label="Close"></button>' +
            '</div>';
        // Set text via textContent so a message can never inject markup.
        wrapper.querySelector('.toast-body').appendChild(
            document.createTextNode(body));

        toastContainer().appendChild(wrapper);

        if (window.bootstrap && window.bootstrap.Toast) {
            var instance = new window.bootstrap.Toast(wrapper, { delay: 5000 });
            wrapper.addEventListener('hidden.bs.toast', function () {
                wrapper.remove();
            });
            instance.show();
        } else {
            // No Bootstrap: show it briefly, then remove.
            setTimeout(function () { wrapper.remove(); }, 5000);
        }
        return wrapper;
    }

    // --------------------------------------------------------------------- //
    // Declarative wiring
    // --------------------------------------------------------------------- //

    function confirmMessageFor(el) {
        var message = el.getAttribute('data-confirm');
        if (message !== null) return message;
        return null;
    }

    function readOptions(el) {
        return {
            title: el.getAttribute('data-confirm-title') || undefined,
            okLabel: el.getAttribute('data-confirm-ok') || undefined,
            cancelLabel: el.getAttribute('data-confirm-cancel') || undefined,
            variant: el.getAttribute('data-confirm-variant') || undefined
        };
    }

    function interceptSubmit(el) {
        el.addEventListener('submit', function (event) {
            if (el.dataset.confirmed === '1') {
                // Second pass, already confirmed.
                delete el.dataset.confirmed;
                return;
            }
            event.preventDefault();
            var message = confirmMessageFor(el);
            confirmDialog(message, readOptions(el)).then(function (ok) {
                if (!ok) return;
                el.dataset.confirmed = '1';
                if (typeof el.requestSubmit === 'function') {
                    el.requestSubmit();
                } else {
                    el.submit();
                }
            });
        });
    }

    function interceptClick(el) {
        el.addEventListener('click', function (event) {
            if (el.dataset.confirmed === '1') {
                delete el.dataset.confirmed;
                return;                       // let the click through
            }
            event.preventDefault();
            event.stopImmediatePropagation();
            var message = confirmMessageFor(el);
            confirmDialog(message, readOptions(el)).then(function (ok) {
                if (!ok) return;
                el.dataset.confirmed = '1';
                // Re-issue the interaction so href / onclick handlers run.
                if (el.tagName === 'A' && el.getAttribute('href')) {
                    window.location.href = el.getAttribute('href');
                } else {
                    el.click();
                }
            });
        });
    }

    function wireDeclarative() {
        document.querySelectorAll('[data-confirm]').forEach(function (el) {
            if (el.dataset.confirmWired === '1') return;
            el.dataset.confirmWired = '1';
            if (el.tagName === 'FORM') {
                interceptSubmit(el);
            } else {
                interceptClick(el);
            }
        });
    }

    ready(wireDeclarative);

    window.SchoolUI = {
        confirm: confirmDialog,
        toast: toast,
        wire: wireDeclarative,
        toastContainer: toastContainer
    };
})();
