import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: [".next/**", ".next-phase8d4-backup/**", "node_modules/**", "coverage/**"] },
  ...tseslint.configs.recommended,
);
