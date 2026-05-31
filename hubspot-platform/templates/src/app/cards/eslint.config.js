const hubspotConfig = require("@hubspot/eslint-config-ui-extensions");

module.exports = [
  ...hubspotConfig.config,
  {
    ignores: ["node_modules/**", "dist/**"],
  },
];
