// Checks the code for mistakes that tsc doesn't catch. Formatting is
// left to Prettier.
import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import { defineConfig, globalIgnores } from 'eslint/config';
import tseslint from 'typescript-eslint';

export default defineConfig([
  // Build output and generated card data
  globalIgnores(['dist/', 'public/']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      // Hooks called in the wrong place, effects missing a dependency
      reactHooks.configs.flat.recommended,
    ],
    // These two need the types, so ESLint reads tsconfig.json for them.
    // The rest of the type-aware set is left out: it mostly flags the any
    // that JSON.parse and response.json() return.
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // A promise nothing waits for or catches: its failure goes unseen
      '@typescript-eslint/no-floating-promises': 'error',
      // A promise passed where a plain value is expected, as an async
      // function given to an onClick that ignores what it returns
      '@typescript-eslint/no-misused-promises': 'error',
      // Written for the React Compiler, which this app doesn't use: it
      // flags the usual reset to "loading" when an effect starts a fetch
      'react-hooks/set-state-in-effect': 'off',
    },
  },
]);
