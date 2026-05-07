/**
 * validation.js — Real-time form validation with debounced API checks
 */
(function () {
    'use strict';

    function debounce(fn, ms) {
        let t;
        return function (...args) {
            clearTimeout(t);
            t = setTimeout(() => fn.apply(this, args), ms);
        };
    }

    function setFieldState(field, valid, message) {
        const wrapper = field.closest('.form-group, .mb-3, .mb-4') || field.parentElement;
        field.classList.remove('is-valid', 'is-invalid');
        wrapper.querySelectorAll('.field-feedback').forEach(el => el.remove());

        if (valid === true) {
            field.classList.add('is-valid');
        } else if (valid === false) {
            field.classList.add('is-invalid');
            if (message) {
                const fb = document.createElement('div');
                fb.className = 'invalid-feedback field-feedback d-block';
                fb.textContent = message;
                field.after(fb);
            }
        }
    }

    function clearFieldState(field) {
        field.classList.remove('is-valid', 'is-invalid');
        const wrapper = field.closest('.form-group, .mb-3, .mb-4') || field.parentElement;
        wrapper.querySelectorAll('.field-feedback').forEach(el => el.remove());
    }

    /* ── Built-in validators ── */
    const VALIDATORS = {
        required: (val) => val.trim() !== '' || 'هذا الحقل مطلوب',
        email: (val) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val) || 'البريد الإلكتروني غير صحيح',
        minlength: (val, param) => val.length >= parseInt(param, 10) || `الحد الأدنى ${param} أحرف`,
        maxlength: (val, param) => val.length <= parseInt(param, 10) || `الحد الأقصى ${param} أحرف`,
        phone: (val) => /^(\+?962|0)?7[789]\d{7}$/.test(val.replace(/\s/g, '')) || 'رقم الجوال غير صحيح',
        number: (val) => !isNaN(parseFloat(val)) || 'يجب إدخال رقم صحيح',
    };

    function validateField(field) {
        const rules = field.dataset.validate?.split('|') ?? [];
        if (!rules.length) return true;

        const val = field.type === 'checkbox' ? (field.checked ? 'on' : '') : field.value;

        for (const rule of rules) {
            const [name, param] = rule.split(':');
            const validator = VALIDATORS[name];
            if (!validator) continue;

            const result = validator(val, param);
            if (result !== true) {
                setFieldState(field, false, result);
                return false;
            }
        }

        setFieldState(field, true, null);
        return true;
    }

    /* ── Async uniqueness check ── */
    async function checkUnique(field) {
        const endpoint = field.dataset.uniqueEndpoint;
        if (!endpoint || !field.value.trim()) return;

        try {
            const res = await fetch(endpoint + encodeURIComponent(field.value.trim()));
            const data = await res.json();
            if (data.exists) {
                setFieldState(field, false, field.dataset.uniqueMessage || 'هذه القيمة مستخدمة بالفعل');
            } else {
                setFieldState(field, true, null);
            }
        } catch (_) {}
    }

    const debouncedUnique = debounce(checkUnique, 600);

    /* ── Password strength meter ── */
    function initPasswordStrength(field) {
        const meterId = field.dataset.strengthMeter;
        if (!meterId) return;

        const meter = document.getElementById(meterId);
        if (!meter) return;

        field.addEventListener('input', () => {
            const v = field.value;
            let score = 0;
            if (v.length >= 8) score++;
            if (/[A-Z]/.test(v)) score++;
            if (/[0-9]/.test(v)) score++;
            if (/[^A-Za-z0-9]/.test(v)) score++;

            const levels = ['', 'danger', 'warning', 'info', 'success'];
            const labels = ['', 'ضعيفة جداً', 'ضعيفة', 'جيدة', 'قوية'];
            meter.className = 'password-strength-bar bg-' + (levels[score] || 'secondary');
            meter.style.width = (score * 25) + '%';
            meter.textContent = labels[score] || '';
        });
    }

    /* ── Form submit validation ── */
    function initForm(form) {
        form.setAttribute('novalidate', '');

        form.querySelectorAll('[data-validate]').forEach(field => {
            field.addEventListener('blur', () => validateField(field));
            field.addEventListener('input', debounce(() => {
                if (field.classList.contains('is-invalid')) validateField(field);
            }, 300));

            if (field.dataset.uniqueEndpoint) {
                field.addEventListener('blur', () => debouncedUnique(field));
            }

            initPasswordStrength(field);
        });

        form.addEventListener('submit', (e) => {
            const fields = form.querySelectorAll('[data-validate]');
            const allValid = Array.from(fields).map(validateField).every(Boolean);
            if (!allValid) {
                e.preventDefault();
                e.stopPropagation();
                form.querySelector('.is-invalid')?.focus();
            }
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('form[data-validate-form]').forEach(initForm);
    });

    window.KinjoValidation = { validateField, setFieldState, clearFieldState };
})();
