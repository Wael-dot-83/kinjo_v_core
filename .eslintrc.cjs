module.exports = {
  root: true,
  env: {
    browser: true,
    es2021: true,
    node: true,
  },
  extends: ["eslint:recommended"],
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "script",
  },
  ignorePatterns: ["node_modules/", "venv/", ".venv/", "htmlcov/", "tests/"],
  globals: {
    AdminI18n: "readonly",
    AuthService: "readonly",
    AuthStorage: "readonly",
    Chart: "readonly",
    Tablesort: "readonly",
    api: "readonly",
    bootstrap: "readonly",
    fetchWithAuth: "readonly",
    showToast: "readonly",
  },
  rules: {
    "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    "no-dupe-class-members": "off",
  },
};
