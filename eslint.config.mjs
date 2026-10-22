import js from "@eslint/js";
import globals from "globals";
import prettier from "eslint-config-prettier";

export default [
  {
    ignores: [
      "node_modules/**",
      ".venv/**",
      ".serena/**",
      "playwright-report/**",
      "test-results/**",
      "htmlcov/**",
    ],
  },
  {
    files: ["**/*.js", "**/*.mjs", "**/*.cjs"],
    ...js.configs.recommended,
  },
  {
    files: ["app/assistant/static/**/*.js"],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ["tests/**/*.cjs", "playwright.config.cjs", "eslint.config.mjs"],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
  prettier,
];
