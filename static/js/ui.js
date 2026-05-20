// Shared UI helpers: toast notifications + theme toggle.
// Exposes window.toast(msg, kind) and wires up #themeToggle automatically.

(function () {
    'use strict';

    // --- Theme toggle ---------------------------------------------------
    const root = document.documentElement;
    const STORAGE_KEY = 'ids-theme';

    function applyTheme(theme) {
        if (theme === 'light') {
            root.setAttribute('data-theme', 'light');
        } else {
            root.removeAttribute('data-theme');
        }
        const btn = document.getElementById('themeToggle');
        if (btn) {
            const icon = btn.querySelector('.theme-toggle-icon');
            if (icon) icon.textContent = theme === 'light' ? '☀️' : '🌙';
            btn.setAttribute('aria-pressed', theme === 'light' ? 'true' : 'false');
        }
    }

    function currentTheme() {
        return root.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
    }

    document.addEventListener('DOMContentLoaded', () => {
        // sync icon with the theme we set pre-paint
        applyTheme(currentTheme());
        const btn = document.getElementById('themeToggle');
        if (!btn) return;
        btn.addEventListener('click', () => {
            const next = currentTheme() === 'light' ? 'dark' : 'light';
            applyTheme(next);
            try { localStorage.setItem(STORAGE_KEY, next); } catch (_) {}
        });
    });

    // --- Toasts ---------------------------------------------------------
    function ensureRoot() {
        let root = document.getElementById('toastRoot');
        if (!root) {
            root = document.createElement('div');
            root.id = 'toastRoot';
            root.className = 'toast-root';
            root.setAttribute('aria-live', 'polite');
            document.body.appendChild(root);
        }
        return root;
    }

    function toast(message, kind, opts) {
        kind = kind || 'info';
        opts = opts || {};
        const ms = typeof opts.duration === 'number' ? opts.duration : 4000;
        const root = ensureRoot();
        const el = document.createElement('div');
        el.className = 'toast toast-' + kind;
        el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
        el.textContent = message;
        root.appendChild(el);
        // trigger entry animation
        requestAnimationFrame(() => el.classList.add('toast-show'));
        const remove = () => {
            el.classList.remove('toast-show');
            setTimeout(() => el.remove(), 250);
        };
        const t = setTimeout(remove, ms);
        el.addEventListener('click', () => { clearTimeout(t); remove(); });
    }

    window.toast = toast;

    // --- Debounce helper ------------------------------------------------
    window.debounce = function (fn, wait) {
        let h;
        return function (...args) {
            clearTimeout(h);
            h = setTimeout(() => fn.apply(this, args), wait);
        };
    };
})();
