// craco.config.js
const path = require("path");
require("dotenv").config();

// Check if we're in development/preview mode (not production build)
// Craco sets NODE_ENV=development for start, NODE_ENV=production for build
const isDevServer = process.env.NODE_ENV !== "production";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  // Fix webpack-dev-server v5 compatibility
  // Remove ALL deprecated options and use new API
  const evalSourceMapMiddleware = require('react-dev-utils/evalSourceMapMiddleware');
  const noopServiceWorkerMiddleware = require('react-dev-utils/noopServiceWorkerMiddleware');
  const redirectServedPath = require('react-dev-utils/redirectServedPathMiddleware');
  const paths = require('react-scripts/config/paths');
  const fs = require('fs');
  
  // Store https config before deleting
  const httpsConfig = devServerConfig.https;
  
  // Remove ALL deprecated options
  delete devServerConfig.onBeforeSetupMiddleware;
  delete devServerConfig.onAfterSetupMiddleware;
  delete devServerConfig.https;
  
  // Use server.type and server.options instead of https
  if (httpsConfig) {
    devServerConfig.server = {
      type: 'https',
      options: httpsConfig
    };
  }
  
  // Use new setupMiddlewares API
  devServerConfig.setupMiddlewares = (middlewares, devServer) => {
    // Before middlewares (was onBeforeSetupMiddleware)
    if (!devServer) {
      throw new Error('webpack-dev-server is not defined');
    }
    
    devServer.app.use(evalSourceMapMiddleware(devServer));
    
    if (fs.existsSync(paths.proxySetup)) {
      require(paths.proxySetup)(devServer.app);
    }
    
    // Add health check if enabled
    if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
      setupHealthEndpoints(devServer, healthPluginInstance);
    }
    
    // After middlewares (was onAfterSetupMiddleware)
    devServer.app.use(redirectServedPath(paths.publicUrlOrPath));
    devServer.app.use(noopServiceWorkerMiddleware(paths.publicUrlOrPath));
    
    return middlewares;
  };

  return devServerConfig;
};

// Wrap with visual edits (automatically adds babel plugin, dev server, and overlay in dev mode)
// Temporarily disabled due to webpack-dev-server compatibility
// if (isDevServer) {
//   try {
//     const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
//     webpackConfig = withVisualEdits(webpackConfig);
//   } catch (err) {
//     if (err.code === 'MODULE_NOT_FOUND' && err.message.includes('@emergentbase/visual-edits/craco')) {
//       console.warn(
//         "[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled."
//       );
//     } else {
//       throw err;
//     }
//   }
// }

module.exports = webpackConfig;
