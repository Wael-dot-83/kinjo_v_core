import os
import re

mapping = {
    r'usa-alert usa-alert--info usa-alert--slim': 'alert alert-info d-flex align-items-center',
    r'usa-alert usa-alert--info': 'alert alert-info',
    r'usa-alert usa-alert--error': 'alert alert-danger',
    r'usa-alert usa-alert--warning': 'alert alert-warning',
    r'usa-alert usa-alert--success': 'alert alert-success',
    r'usa-alert__body': '',
    r'usa-alert__text': 'mb-0',
    r'usa-card-group': 'row g-4',
    r'usa-card tablet:grid-col-3': 'col-12 col-md-6 col-lg-3',
    r'usa-card tablet:grid-col-4': 'col-12 col-md-6 col-lg-4',
    r'usa-card tablet:grid-col-6': 'col-12 col-md-6',
    r'usa-card': 'col-12',
    r'usa-card__container': 'card h-100 shadow-sm',
    r'usa-card__body': 'card-body',
    r'usa-card__footer': 'card-footer bg-transparent border-0',
    r'usa-button usa-button--unstyled': 'btn btn-link text-decoration-none',
    r'usa-button usa-button--outline': 'btn btn-outline-primary',
    r'usa-button usa-button--secondary': 'btn btn-secondary',
    r'usa-button': 'btn btn-primary',
    r'usa-intro': 'lead text-muted',
    r'margin-bottom-5': 'mb-5',
    r'margin-bottom-4': 'mb-4',
    r'margin-bottom-3': 'mb-3',
    r'margin-bottom-2': 'mb-2',
    r'margin-bottom-1': 'mb-1',
    r'margin-bottom-0': 'mb-0',
    r'margin-top-5': 'mt-5',
    r'margin-top-4': 'mt-4',
    r'margin-top-3': 'mt-3',
    r'margin-top-2': 'mt-2',
    r'margin-top-1': 'mt-1',
    r'margin-top-0': 'mt-0',
    r'margin-right-1': 'me-2',
    r'margin-right-2': 'me-3',
    r'margin-left-1': 'ms-2',
    r'margin-left-2': 'ms-3',
    r'margin-0': 'm-0',
    r'padding-top-0': 'pt-0',
    r'padding-x-2': 'px-3',
    r'display-flex': 'd-flex',
    r'flex-align-center': 'align-items-center',
    r'flex-justify-center': 'justify-content-center',
    r'flex-justify-between': 'justify-content-between',
    r'width-full': 'w-100',
    r'text-bold': 'fw-bold',
    r'text-center': 'text-center',
    r'font-heading-xl': 'fs-1 fw-bold',
    r'font-heading-lg': 'h3 fw-bold',
    r'font-heading-md': 'h4',
    r'font-heading-2xl': 'fs-1 fw-bolder display-5',
    r'font-sans-2xl': 'fs-1',
    r'font-sans-3xs': 'small fw-bold',
    r'text-base-darker': 'text-dark',
    r'text-base-dark': 'text-muted',
    r'text-base-light': 'text-secondary',
    r'text-primary-darker': 'text-primary',
    r'text-primary-dark': 'text-primary',
    r'text-green-darker': 'text-success',
    r'bg-primary-lighter': 'bg-primary-subtle',
    r'bg-green-light': 'bg-success-subtle',
    r'border-primary-light': 'border-primary border-opacity-25',
    r'border-green-light': 'border-success border-opacity-25',
    r'text-uppercase': 'text-uppercase',
    r'usa-table': 'table table-hover align-middle',
    r'usa-table--striped': 'table-striped',
    r'usa-table--borderless': 'table-borderless',
    r'usa-form': '',
    r'usa-label': 'form-label',
    r'usa-input': 'form-control',
    r'usa-select': 'form-select',
    r'usa-textarea': 'form-control',
    r'grid-row': 'row',
    r'grid-col-12': 'col-12',
    r'grid-col-6': 'col-6',
    r'grid-col-4': 'col-4',
    r'grid-col-3': 'col-3',
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

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Migrated {filepath}")
    else:
        print(f"No changes for {filepath}")

directory = r'd:\Final Version\templates\manager'
for filename in os.listdir(directory):
    if filename.endswith('.html'):
        migrate_file(os.path.join(directory, filename))
