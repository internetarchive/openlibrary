#!/usr/bin/env node

// Usage:
// ./index.js directory-to-save-to

const mkdirp = require('mkdirp');
const puppeteer = require('puppeteer');

// const host = 'https://openlibrary.org';
const host = 'http://localhost:8080';

const tests = [
  { name: 'homepage', url: '' },
  { name: 'work', url: '/works/OL6037022W/Remix' },
  { name: 'edition', url: '/books/OL24218235M/Remix' },
  { name: 'search', url: '/search' },
  { name: 'search inside', url: '/search/inside' },
  { name: 'lists', url: '/lists' },
  { name: 'author', url: '/authors/OL1518080A/Lawrence_Lessig' },
];

// Take the directory as a command line argument.
const directory = process.argv[2];

(async function() {
  console.log(`Creating directory "${directory}"...`);
  mkdirp.sync(directory);

  const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  let page = await browser.newPage();

  page.setViewport({ width: 640, height: 1000 });

  for (let test of tests) {
    const url = host + test.url;
    console.log(`Visting "${url}"...`);
    await page.goto(url, { waitUntil: "networkidle0" });

    const filename = `${directory}/${test.name}.png`;
    console.log(`Saving screenshot to "${filename}"...`);
    await page.screenshot({ path: filename, fullPage: true });
  }

  await page.close();
  await browser.close();
})();
