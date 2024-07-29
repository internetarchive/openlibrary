/* eslint-env node */

// Make jQuery available globally for tests
import $ from 'jquery';
window.jQuery = $;
window.$ = $;

// Improve error reporting for unhandled promise rejections
process.on('unhandledRejection', (error) => {
  throw error;
});
