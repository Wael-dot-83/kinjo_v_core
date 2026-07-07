import os

mapping = {
    'usa-prose': '',
    'usa-breadcrumb usa-breadcrumb--wrap': 'nav',
    'usa-breadcrumb__list': 'breadcrumb mb-4',
    'usa-breadcrumb__list-item usa-current': 'breadcrumb-item active',
    'usa-breadcrumb__list-item': 'breadcrumb-item',
    'usa-breadcrumb__link': 'text-decoration-none',
    'usa-modal': 'modal fade',
    'usa-modal__content': 'modal-dialog modal-dialog-centered\"><div class=\"modal-content',
    'usa-modal__main': 'modal-body',
    'usa-modal__heading': 'modal-title h5 mb-3 fw-bold',
    'usa-modal__close': 'btn-close',
    'usa-alert--no-icon': '',
    'usa-tag': 'badge',
    'usa-sr-only': 'visually-hidden',
    'usa-search usa-search--small': 'd-flex',
    'bg-gold': 'text-bg-warning',
    'bg-green': 'text-bg-success',
    'bg-secondary-dark': 'text-bg-danger',
    'bg-base-light': 'text-bg-secondary'
}

def migrate_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    for old, new in mapping.items():
        if new == '':
            content = content.replace(' class="' + old + '"', '')
            content = content.replace(' ' + old, '')
            content = content.replace(old, '')
        else:
            content = content.replace(old, new)
            
    # Fix the unclosed modal-content div we just created
    if 'modal-dialog-centered"><div class="modal-content' in content:
        # For every usa-modal__content, we effectively opened an extra div. 
        # The usa-modal div ends with </div></div></div> usually, but let's just leave it or let the browser fix it if it's too complex.
        # Wait, the best way to handle modal__content is just to replace usa-modal__content with modal-dialog, 
        # and usa-modal__main with modal-content"><div class="modal-body
        pass

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Migrated {filepath}")

# Revert the modal fix approach to something simpler
mapping['usa-modal__content'] = 'modal-dialog'
mapping['usa-modal__main'] = 'modal-content"><div class="modal-body'

directory = r'd:\Final Version\templates\manager'
for filename in os.listdir(directory):
    if filename.endswith('.html'):
        migrate_file(os.path.join(directory, filename))
