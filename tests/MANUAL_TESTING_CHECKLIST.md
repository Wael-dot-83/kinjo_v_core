# KinJo Manual Testing Checklist

## Accessibility Testing

### Screen Reader Testing (NVDA/VoiceOver/JAWS)

#### Setup
- [ ] Install NVDA (Windows): https://www.nvaccess.org/download/
- [ ] Or use VoiceOver (macOS): System Preferences > Accessibility > VoiceOver
- [ ] Or use JAWS: https://www.freedomscientific.com/products/software/jaws/

#### Dashboard Page Tests

1. **Page Load Announcement**
   - [ ] Screen reader announces page title on load
   - [ ] Main content region is identified

2. **Navigation**
   - [ ] Sidebar navigation items are announced correctly
   - [ ] Current page is indicated (e.g., "Dashboard, current page")
   - [ ] All links have descriptive text

3. **Metric Cards**
   - [ ] Each stat card value is announced (e.g., "Total Children: 589")
   - [ ] Trend indicators are announced (e.g., "up 5%")
   - [ ] Card labels are associated with values

4. **Tables**
   - [ ] Table headers are announced when navigating cells
   - [ ] Row/column context is provided
   - [ ] Action buttons in tables are accessible

5. **Charts**
   - [ ] Charts have accessible alternatives (text summary or data table)
   - [ ] Chart titles are announced

6. **Forms**
   - [ ] All form fields have labels
   - [ ] Required fields are announced
   - [ ] Error messages are announced when form validation fails

7. **Modals/Dialogs**
   - [ ] Focus moves to modal when opened
   - [ ] Modal title is announced
   - [ ] Focus is trapped within modal
   - [ ] Escape key closes modal
   - [ ] Focus returns to trigger element on close

#### Keyboard Navigation Tests

1. **Tab Order**
   - [ ] Tab order follows logical reading order
   - [ ] All interactive elements are reachable via Tab
   - [ ] No keyboard traps (can always Tab away)

2. **Focus Indicators**
   - [ ] All focused elements have visible focus indicator
   - [ ] Focus indicator has sufficient contrast

3. **Keyboard Shortcuts**
   - [ ] Dropdown menus can be operated with arrow keys
   - [ ] Enter/Space activates buttons and links
   - [ ] Escape closes dropdowns and modals

---

## Print/Export Testing

### Print Layout Testing

1. **Setup**
   - [ ] Open Dashboard: http://127.0.0.1:8000/dashboard
   - [ ] Press Ctrl+P (Windows) or Cmd+P (Mac)

2. **Layout Checks**
   - [ ] Content fits within page margins
   - [ ] No content is cut off at page breaks
   - [ ] Background colors print correctly (or gracefully degrade)
   - [ ] Charts are visible and legible

3. **RTL/Arabic Content**
   - [ ] Arabic text renders correctly
   - [ ] Right-to-left layout is preserved
   - [ ] Numbers display correctly

4. **Header/Footer**
   - [ ] Page numbers display (if configured)
   - [ ] Date/time prints (if configured)

### Export Testing

1. **PDF Export** (if implemented)
   - [ ] Click Export > PDF
   - [ ] PDF opens in viewer
   - [ ] All content is present
   - [ ] Arabic text renders correctly
   - [ ] Charts are visible
   - [ ] Links are clickable (if applicable)

2. **Excel Export** (if implemented)
   - [ ] Click Export > Excel
   - [ ] File downloads
   - [ ] Open in Excel/LibreOffice
   - [ ] Data is in correct columns
   - [ ] Arabic text displays correctly
   - [ ] Numbers are formatted correctly

3. **CSV Export** (if implemented)
   - [ ] Click Export > CSV
   - [ ] File downloads
   - [ ] UTF-8 encoding preserved (Arabic text correct)
   - [ ] Column headers present
   - [ ] Data properly escaped

---

## Browser Console Inspection (F12)

### Quick Checks

```javascript
// 1. Check for JavaScript errors
// Look in Console tab for red error messages

// 2. Check for failed network requests
// Look in Network tab for red (failed) requests

// 3. Run built-in accessibility audit
// In Chrome DevTools: Lighthouse tab > Accessibility > Generate report

// 4. Run custom accessibility audit
// Paste contents of tests/accessibility_audit.js in Console
```

### Common Issues to Look For

1. **Console Errors**
   - [ ] No JavaScript errors on page load
   - [ ] No 404 errors for resources
   - [ ] No CORS errors

2. **Network Tab**
   - [ ] All API calls return 200/2xx status
   - [ ] No slow requests (> 3 seconds)
   - [ ] No failed authentication (401/403)

3. **Performance**
   - [ ] Page load time < 3 seconds
   - [ ] No memory leaks (check Memory tab)

---

## Color Contrast Testing

### Tools
- Chrome DevTools: Inspect element > Styles > Color contrast ratio
- WebAIM Contrast Checker: https://webaim.org/resources/contrastchecker/
- Colour Contrast Analyser: https://www.tpgi.com/color-contrast-checker/

### Requirements (WCAG 2.1 AA)
- [ ] Normal text: 4.5:1 contrast ratio
- [ ] Large text (18pt+ or 14pt bold): 3:1 contrast ratio
- [ ] UI components and graphics: 3:1 contrast ratio

### Elements to Check
- [ ] Body text on background
- [ ] Link text on background
- [ ] Button text on button background
- [ ] Form field text and borders
- [ ] Error messages
- [ ] Success messages
- [ ] Warning messages
- [ ] Table headers
- [ ] Chart labels and legends

---

## RTL (Arabic) Testing

### Visual Checks
- [ ] Page layout mirrors for RTL (sidebar on right if applicable)
- [ ] Text alignment is correct (right-aligned for Arabic)
- [ ] Icons don't flip inappropriately (checkmarks, etc.)
- [ ] Numbers display correctly (may be LTR within RTL context)
- [ ] Form fields align correctly
- [ ] Dropdown arrows point correct direction

### Content Checks
- [ ] Arabic characters render correctly (no boxes/question marks)
- [ ] Diacritics display correctly
- [ ] Line breaks occur at appropriate points
- [ ] No mixed-direction text issues

---

## Test Sign-Off

| Test Area | Tester | Date | Pass/Fail | Notes |
|-----------|--------|------|-----------|-------|
| Screen Reader (NVDA) | | | | |
| Screen Reader (VoiceOver) | | | | |
| Keyboard Navigation | | | | |
| Print Layout | | | | |
| PDF Export | | | | |
| Excel Export | | | | |
| Console Errors | | | | |
| Color Contrast | | | | |
| RTL Layout | | | | |
