# Kindergarten Import Feature

This feature allows importing kindergartens from Excel files into the database.

## Database Tables

- `imported_kindergartens`: Stores the imported kindergarten data
- `import_logs`: Tracks import operations and results

## Excel File Format

The Excel file must contain exactly these Arabic column headers:

1. اسم الروضة (عربي) - Kindergarten name in Arabic (required)
2. اسم الروضة (إنجليزي) - Kindergarten name in English (optional)
3. المحافظة - Governorate (required)
4. المدينة - City (required)
5. المنطقة - Area (optional)
6. العنوان التفصيلي - Detailed address (optional)
7. رقم الهاتف - Phone number (required)

## CLI Import

To import from a local Excel file:

```bash
python import_kindergartens.py --path "C:\Users\waelj\OneDrive - zuj.edu.jo\Desktop\final.xlsx"
```

This will:

- Read the Excel file
- Validate and normalize data
- Import records with upsert logic (update existing, insert new)
- Print a summary of the operation

## Admin Web Import

1. Navigate to `/admin/import-kindergartens`
2. Upload the `final.xlsx` file
3. The system will process the file and show results
4. View imported records at `/admin/imported-kindergartens`

## Data Validation

- **Required fields**: name_ar, governorate, city, phone
- **Phone normalization**: Removes spaces/dashes, ensures Jordan format
- **Duplicate protection**: Uses (name_ar, city, phone) as unique key
- **Error handling**: Collects per-row errors, continues processing

## API Endpoints

- `POST /admin/kindergartens/import` - Upload and import Excel file
- `GET /admin/kindergartens/imported` - List imported kindergartens with filtering
- `GET /admin/imports/logs` - View import logs

## Security

- Admin-only access for import operations
- File upload validation (Excel format only)
- Rate limiting on import operations
- Audit logging of import activities

## Dependencies

- pandas: For Excel reading
- openpyxl: Excel engine (installed with pandas)

Install if needed:

```bash
pip install pandas openpyxl
```
