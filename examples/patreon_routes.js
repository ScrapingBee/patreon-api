// Routes 1 and 2 to public Patreon creator data.
// Verified against https://www.patreon.com/kurzgesagt on 2026-09-10.
// Public creator pages only. Nothing here signs in.

const axios = require('axios');

const BASE = 'https://app.scrapingbee.com/api/v1/';
const headers = { Authorization: `Bearer ${process.env.SCRAPINGBEE_API_KEY}` };

async function fetchPage(url, params = {}) {
  const res = await axios.get(BASE, { headers, params: { url, ...params }, timeout: 120000 });
  return res.data;
}

// Route 1: meta tags. 5 credits. Survives redesigns.
async function creator(slug) {
  const extract_rules = JSON.stringify({
    creator: { selector: 'h1', output: 'text' },
    title: 'title',
    og_title: { selector: 'meta[property="og:title"]', output: '@content' },
    og_desc: { selector: 'meta[name="description"]', output: '@content' },
  });
  const data = await fetchPage(`https://www.patreon.com/${slug}`, {
    extract_rules,
    mode: 'auto',
  });
  // Patreon joins creator name and campaign tagline with an em dash.
  if (data.title && data.title.includes('—')) {
    data.campaign_tagline = data.title.split('—')[1].split('|')[0].trim();
  }
  return data;
}

// Route 2: the application/ld+json ProfilePage block. 5 credits.
// extract_rules cannot read script tag contents, so parse the HTML.
async function profile(slug) {
  const html = await fetchPage(`https://www.patreon.com/${slug}`, { mode: 'auto' });
  const blocks = String(html).match(
    /<script[^>]*application\/ld\+json[^>]*>([\s\S]*?)<\/script>/g
  ) || [];
  for (const block of blocks) {
    const body = block.replace(/^<script[^>]*>/, '').replace(/<\/script>$/, '');
    let obj;
    try {
      obj = JSON.parse(body);
    } catch {
      continue;
    }
    if (obj && obj['@type'] === 'ProfilePage') {
      const person = obj.mainEntity || {};
      return {
        name: person.name,
        alternate_name: person.alternateName,
        url: person.url,
        about: person.description,
        image: person.image && person.image.contentUrl,
        thumbnail: person.image && person.image.thumbnailUrl,
      };
    }
  }
  return null;
}

(async () => {
  console.log('route 1:', await creator('kurzgesagt'));
  console.log('route 2:', await profile('kurzgesagt'));
})();
