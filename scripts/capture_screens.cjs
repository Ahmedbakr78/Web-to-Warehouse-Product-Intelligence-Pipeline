const puppeteer = require('/tmp/puppeteer/node_modules/puppeteer-core');
const fs = require('fs');
const path = require('path');

const SCREENSHOTS_DIR = path.resolve(__dirname, '../docs/screenshots');

async function main() {
  // 1. Fetch JWT token
  const loginRes = await fetch('http://localhost:8000/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@example.com', password: 'Admin@12345' }),
  });
  const { access_token } = await loginRes.json();
  console.log('Got access token:', access_token.slice(0, 15) + '...');

  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    defaultViewport: { width: 1440, height: 900 },
  });

  const page = await browser.newPage();

  // Navigate to root to initialize origin
  await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });

  // Set tokens and theme in localStorage
  await page.evaluate((tok) => {
    localStorage.setItem('pip.token', tok);
    localStorage.setItem('pip.theme', 'dark');
    document.documentElement.classList.add('dark');
  }, access_token);

  const screens = [
    { name: 'dashboard-dark.png', url: 'http://localhost:5173/' },
    { name: 'analytics-dark.png', url: 'http://localhost:5173/analytics' },
    { name: 'changes-dark.png', url: 'http://localhost:5173/changes' },
    { name: 'products-dark.png', url: 'http://localhost:5173/products' },
    { name: 'pipeline-dark.png', url: 'http://localhost:5173/pipeline' },
    { name: 'quality-dark.png', url: 'http://localhost:5173/quality' },
    { name: 'sources-dark.png', url: 'http://localhost:5173/sources' },
  ];

  for (const screen of screens) {
    console.log(`Navigating to ${screen.url}...`);
    await page.goto(screen.url, { waitUntil: 'networkidle2', timeout: 15000 }).catch(() => {});
    await new Promise((r) => setTimeout(r, 2000));
    const dest = path.join(SCREENSHOTS_DIR, screen.name);
    await page.screenshot({ path: dest, fullPage: false });
    const stat = fs.statSync(dest);
    console.log(`Saved ${screen.name} (${Math.round(stat.size / 1024)} KB)`);
  }

  // Airflow captures
  console.log('Navigating to Airflow...');
  await page.authenticate({ username: 'admin', password: 'admin' });
  
  // Airflow Graph
  await page.goto('http://localhost:8080/dags/product_intelligence_pipeline/graph', {
    waitUntil: 'networkidle2',
    timeout: 15000,
  }).catch(() => {});
  await new Promise((r) => setTimeout(r, 2500));
  const graphDest = path.join(SCREENSHOTS_DIR, 'airflow-graph.png');
  await page.screenshot({ path: graphDest, fullPage: false });
  console.log(`Saved airflow-graph.png (${Math.round(fs.statSync(graphDest).size / 1024)} KB)`);

  // Airflow Grid
  await page.goto('http://localhost:8080/dags/product_intelligence_pipeline/grid', {
    waitUntil: 'networkidle2',
    timeout: 15000,
  }).catch(() => {});
  await new Promise((r) => setTimeout(r, 2500));
  const gridDest = path.join(SCREENSHOTS_DIR, 'airflow-grid.png');
  await page.screenshot({ path: gridDest, fullPage: false });
  console.log(`Saved airflow-grid.png (${Math.round(fs.statSync(gridDest).size / 1024)} KB)`);

  await browser.close();
  console.log('All screenshots completed successfully!');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
