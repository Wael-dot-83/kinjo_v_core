/**
 * Accessibility Audit Script for KinJo Dashboard
 * Run in browser console (F12) or with Node.js + Puppeteer
 *
 * Usage in browser console:
 *   1. Open http://127.0.0.1:8000/dashboard
 *   2. Press F12 to open DevTools
 *   3. Paste this entire script in Console tab
 *   4. Results will be logged to console
 */

(function runAccessibilityAudit() {
    const results = {
        passed: [],
        warnings: [],
        errors: []
    };

    console.log('%c=== KinJo Accessibility Audit ===', 'font-size: 16px; font-weight: bold; color: #0d6efd;');

    // 1. Check for missing alt text on images
    const images = document.querySelectorAll('img');
    images.forEach((img, i) => {
        if (!img.alt && !img.getAttribute('aria-hidden')) {
            results.errors.push(`Image #${i + 1} missing alt text: ${img.src.substring(0, 50)}...`);
        }
    });
    if (images.length === 0 || results.errors.filter(e => e.includes('Image')).length === 0) {
        results.passed.push(`All ${images.length} images have alt text or are decorative`);
    }

    // 2. Check for form labels
    const inputs = document.querySelectorAll('input, select, textarea');
    inputs.forEach((input, i) => {
        const id = input.id;
        const hasLabel = id && document.querySelector(`label[for="${id}"]`);
        const hasAriaLabel = input.getAttribute('aria-label') || input.getAttribute('aria-labelledby');
        const hasPlaceholder = input.placeholder;

        if (!hasLabel && !hasAriaLabel && !hasPlaceholder) {
            results.errors.push(`Input #${i + 1} (${input.type || 'text'}) missing label`);
        }
    });
    if (results.errors.filter(e => e.includes('Input')).length === 0) {
        results.passed.push(`All ${inputs.length} form inputs have labels`);
    }

    // 3. Check for empty links
    const links = document.querySelectorAll('a');
    links.forEach((link, i) => {
        const text = link.textContent.trim();
        const ariaLabel = link.getAttribute('aria-label');
        const title = link.title;

        if (!text && !ariaLabel && !title) {
            results.errors.push(`Link #${i + 1} is empty (no text or aria-label): ${link.href}`);
        }
    });
    if (results.errors.filter(e => e.includes('Link')).length === 0) {
        results.passed.push(`All ${links.length} links have accessible text`);
    }

    // 4. Check for empty buttons
    const buttons = document.querySelectorAll('button, [role="button"]');
    buttons.forEach((btn, i) => {
        const text = btn.textContent.trim();
        const ariaLabel = btn.getAttribute('aria-label');
        const title = btn.title;

        if (!text && !ariaLabel && !title) {
            results.errors.push(`Button #${i + 1} is empty (no text or aria-label)`);
        }
    });
    if (results.errors.filter(e => e.includes('Button')).length === 0) {
        results.passed.push(`All ${buttons.length} buttons have accessible text`);
    }

    // 5. Check heading hierarchy
    const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
    let lastLevel = 0;
    let headingIssues = 0;
    headings.forEach((h, i) => {
        const level = parseInt(h.tagName[1]);
        if (level > lastLevel + 1 && lastLevel !== 0) {
            results.warnings.push(`Heading level skipped: h${lastLevel} -> h${level} ("${h.textContent.substring(0, 30)}...")`);
            headingIssues++;
        }
        lastLevel = level;
    });
    if (headingIssues === 0) {
        results.passed.push(`Heading hierarchy is correct (${headings.length} headings)`);
    }

    // 6. Check for page title
    if (document.title) {
        results.passed.push(`Page has title: "${document.title}"`);
    } else {
        results.errors.push('Page is missing a title');
    }

    // 7. Check for lang attribute
    const lang = document.documentElement.lang;
    if (lang) {
        results.passed.push(`Page has lang attribute: "${lang}"`);
    } else {
        results.errors.push('Page is missing lang attribute on <html>');
    }

    // 8. Check for ARIA landmarks
    const landmarks = {
        main: document.querySelector('main, [role="main"]'),
        nav: document.querySelector('nav, [role="navigation"]'),
        banner: document.querySelector('header, [role="banner"]'),
        contentinfo: document.querySelector('footer, [role="contentinfo"]')
    };

    Object.entries(landmarks).forEach(([name, el]) => {
        if (el) {
            results.passed.push(`ARIA landmark present: ${name}`);
        } else {
            results.warnings.push(`ARIA landmark missing: ${name}`);
        }
    });

    // 9. Check color contrast (basic check for text)
    const textElements = document.querySelectorAll('p, span, div, td, th, li, a, button, label');
    let lowContrastCount = 0;
    textElements.forEach(el => {
        const style = window.getComputedStyle(el);
        const color = style.color;
        const bg = style.backgroundColor;

        // Basic check - if text is very light gray on white
        if (color === 'rgb(200, 200, 200)' || color === 'rgb(211, 211, 211)') {
            lowContrastCount++;
        }
    });
    if (lowContrastCount > 0) {
        results.warnings.push(`${lowContrastCount} elements may have low color contrast`);
    } else {
        results.passed.push('No obvious color contrast issues detected');
    }

    // 10. Check for skip link
    const skipLink = document.querySelector('a[href="#main"], a[href="#content"], .skip-link');
    if (skipLink) {
        results.passed.push('Skip navigation link present');
    } else {
        results.warnings.push('Consider adding a skip navigation link');
    }

    // 11. Check tables for headers
    const tables = document.querySelectorAll('table');
    tables.forEach((table, i) => {
        const headers = table.querySelectorAll('th');
        if (headers.length === 0) {
            results.warnings.push(`Table #${i + 1} has no header cells (th)`);
        } else {
            results.passed.push(`Table #${i + 1} has ${headers.length} header cells`);
        }
    });

    // 12. Check for focus indicators
    const focusableElements = document.querySelectorAll('a, button, input, select, textarea, [tabindex]');
    results.passed.push(`${focusableElements.length} focusable elements found`);

    // 13. RTL Support check (important for Arabic)
    const rtlElements = document.querySelectorAll('[dir="rtl"]');
    const htmlDir = document.documentElement.dir;
    if (htmlDir === 'rtl' || rtlElements.length > 0) {
        results.passed.push(`RTL support: ${htmlDir === 'rtl' ? 'Page-level' : rtlElements.length + ' elements'}`);
    } else {
        results.warnings.push('No RTL direction set (important for Arabic content)');
    }

    // Print results
    console.log('%c\nPASSED (' + results.passed.length + '):', 'color: green; font-weight: bold;');
    results.passed.forEach(p => console.log('  ✓ ' + p));

    console.log('%c\nWARNINGS (' + results.warnings.length + '):', 'color: orange; font-weight: bold;');
    results.warnings.forEach(w => console.log('  ⚠ ' + w));

    console.log('%c\nERRORS (' + results.errors.length + '):', 'color: red; font-weight: bold;');
    results.errors.forEach(e => console.log('  ✗ ' + e));

    // Summary
    console.log('%c\n=== SUMMARY ===', 'font-size: 14px; font-weight: bold;');
    console.log(`Passed: ${results.passed.length}`);
    console.log(`Warnings: ${results.warnings.length}`);
    console.log(`Errors: ${results.errors.length}`);

    const score = Math.round((results.passed.length / (results.passed.length + results.warnings.length + results.errors.length)) * 100);
    console.log(`%cAccessibility Score: ${score}%`, `color: ${score >= 80 ? 'green' : score >= 60 ? 'orange' : 'red'}; font-weight: bold;`);

    return results;
})();
