import express from "express";
import axios from "axios";
import * as cheerio from "cheerio";

const app = express();
app.use(express.json());

const EMAIL_RE    = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}/g;
const PHONE_RE    = /\+?\d[\d\s\-()\\.]{8,}/g;
const LINKEDIN_RE = /https?:\/\/(?:www\.)?linkedin\.com\/company\/[A-Za-z0-9\-_%]+\/?/gi;
const PERSON_RE   = /(?:contact\s*(?:person|us|name)[:\s]+|(?:Mr|Ms|Mrs|Dr)\.?\s+)([A-Z][a-z]+ [A-Z][a-z]+)/g;

// ---- Channel type keywords ----
const CHANNEL_KEYWORDS = {
  Manufacturer: ["manufacturer","manufacturing","we manufacture","our factory",
                 "production facility","our plant","fabricat","oem","odm"],
  Importer:     ["importer","import","we import","imported from","importing",
                 "customs","iec","cif","fob"],
  Wholesaler:   ["wholesaler","wholesale","bulk supply","bulk order",
                 "bulk pricing","minimum order quantity","moq"],
  Distributor:  ["distributor","distribution","authorised distributor",
                 "authorized distributor","exclusive distributor","channel partner"],
  Trader:       ["trader","trading company","trading house",
                 "commodity trading","buy and sell"],
  Retailer:     ["retailer","retail","walk-in","showroom","store",
                 "shop online","add to cart","buy now"],
};

function detectChannelType(text) {
  const lower = text.toLowerCase();
  let best = "", bestScore = 0;
  for (const [channel, keywords] of Object.entries(CHANNEL_KEYWORDS)) {
    const score = keywords.filter(kw => lower.includes(kw)).length;
    if (score > bestScore) { bestScore = score; best = channel; }
  }
  return best;
}

// ---- Company size ----
const SIZE_PATTERNS = [
  [/\b(\d{1,4})\s*[-–to]+\s*(\d{2,5})\s*(employees|staff)\b/i, (m) => `${m[1]}–${m[2]}`],
  [/\b(\d{2,5})\s*\+?\s*(employees|staff|people|professionals)\b/i, (m) => `${m[1]}+`],
  [/team\s+of\s+(\d+)/i, (m) => `team of ${m[1]}`],
  [/(1[-–]10|11[-–]50|51[-–]200|201[-–]500|501[-–]1[,.]?000|1[,.]?001[-–]5[,.]?000)\s*(employees)?/i, (m) => m[1]],
];

function detectCompanySize(text) {
  for (const [pattern, formatter] of SIZE_PATTERNS) {
    const m = text.match(pattern);
    if (m) return formatter(m);
  }
  return "";
}

// ---- Incorporation date ----
const INCORP_PATTERNS = [
  /(?:incorporated|established|founded|since|est\.?)\s*(?:in\s*)?(\d{4})/i,
  /(?:year\s+of\s+(?:incorporation|establishment|founding))[:\s]+(\d{4})/i,
  /(?:date\s+of\s+incorporation)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})/i,
];

function detectIncorporation(text) {
  for (const pat of INCORP_PATTERNS) {
    const m = text.match(pat);
    if (m) return m[1];
  }
  return "";
}

// ---- City extraction ----
const MAJOR_CITIES = [
  "Mumbai","Delhi","Bangalore","Bengaluru","Hyderabad","Ahmedabad","Chennai",
  "Kolkata","Surat","Pune","Jaipur","Lucknow","Nagpur","Indore","Thane",
  "Bhopal","Visakhapatnam","Patna","Vadodara","Ghaziabad","Ludhiana","Agra",
  "Nashik","Faridabad","Meerut","Rajkot","Varanasi","Aurangabad","Coimbatore",
  "Vijayawada","Noida","Gurgaon","Gurugram","Chandigarh","Mysore","Mysuru",
  "Amritsar","Kochi","Cochin","Ernakulam","Dubai","Abu Dhabi","Singapore",
  "Kuala Lumpur","Hong Kong","Shanghai","Beijing","London","New York",
  "Los Angeles","Toronto","Sydney","Melbourne","Frankfurt","Paris","Amsterdam",
  "Milan","Zurich",
];
const CITY_RE = new RegExp(`\\b(${MAJOR_CITIES.map(c => c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join("|")})\\b`, "i");

function detectCity(text, html) {
  // Try JSON-LD address locality first
  const jsonLdMatch = html.match(/"addressLocality"\s*:\s*"([^"]{2,40})"/i);
  if (jsonLdMatch) return jsonLdMatch[1].trim();
  // Try itemprop
  const itemPropMatch = html.match(/itemprop=["']addressLocality["'][^>]*>([^<]{2,40})</i);
  if (itemPropMatch) return itemPropMatch[1].trim();
  // Fallback: known city list
  const m = text.match(CITY_RE);
  return m ? m[1] : "";
}

// ---- Country detection ----
const COUNTRY_SIGNALS = {
  India:     ["india","indian",".in","bharath","bharat"],
  UAE:       ["uae","dubai","abu dhabi","emirates","emirati"],
  USA:       ["usa","united states","america","u.s.a"],
  UK:        ["uk","united kingdom","britain","england","london"],
  Germany:   ["germany","german","deutschland"],
  Singapore: ["singapore"],
  Canada:    ["canada","canadian"],
  Australia: ["australia","australian"],
  China:     ["china","chinese","prc"],
  Italy:     ["italy","italian","italia"],
};

function detectCountry(text) {
  const lower = text.toLowerCase();
  for (const [country, signals] of Object.entries(COUNTRY_SIGNALS)) {
    if (signals.some(s => lower.includes(s))) return country;
  }
  return "";
}

// ---- Fetch single page ----
async function fetchPage(url) {
  try {
    const res = await axios.get(url, {
      timeout: 15000,
      headers: { "User-Agent": "Mozilla/5.0 (compatible; BuyeraBot/1.0)" },
      maxRedirects: 5,
    });
    return { html: res.data || "", status: res.status };
  } catch {
    return { html: "", status: 0 };
  }
}

// ---- Main crawl endpoint ----
app.post("/crawl", async (req, res) => {
  const { url } = req.body;
  if (!url) return res.json({});

  const pages = [url, url + "/contact", url + "/about", url + "/about-us", url + "/contact-us"];

  let combinedText = "";
  let combinedHtml = "";
  const emails  = new Set();
  const phones  = new Set();
  const persons = new Set();
  let linkedinUrl = "";

  for (const p of pages) {
    const { html } = await fetchPage(p);
    if (!html) continue;

    combinedHtml += html;

    const $ = cheerio.load(html);
    // Remove nav/footer/script noise
    $("nav, footer, script, style, noscript").remove();
    const text = $("body").text().replace(/\s+/g, " ").trim();
    combinedText += " " + text;

    // Emails
    (text.match(EMAIL_RE) || []).forEach(e => emails.add(e));
    // Phones
    (text.match(PHONE_RE) || []).forEach(ph => phones.add(ph.trim()));
    // Contact persons
    let pm;
    const personRegex = /(?:contact\s*(?:person|us|name)[:\s]+|(?:Mr|Ms|Mrs|Dr)\.?\s+)([A-Z][a-z]+ [A-Z][a-z]+)/g;
    while ((pm = personRegex.exec(text)) !== null) {
      persons.add(pm[1].trim());
    }
    // LinkedIn (from HTML href attributes too)
    const liMatches = html.match(LINKEDIN_RE);
    if (liMatches && !linkedinUrl) {
      linkedinUrl = liMatches[0].replace(/\/$/, "");
    }
  }

  const text = combinedText.substring(0, 6000);

  res.json({
    email:              [...emails][0]   || "",
    phone:              [...phones][0]   || "",
    contact_person:     [...persons][0]  || "",
    contact_email:      [...emails][0]   || "",
    linkedin_url:       linkedinUrl,
    content:            text,
    html:               combinedHtml.substring(0, 20000),  // for Python-side parsing
    city:               detectCity(text, combinedHtml),
    country_detected:   detectCountry(text),
    channel_type:       detectChannelType(text),
    company_size:       detectCompanySize(text),
    incorporation_date: detectIncorporation(text),
    active_website:     url,
  });
});

// ---- Health check ----
app.get("/health", (req, res) => res.json({ status: "ok" }));

app.listen(5050, () => {
  console.log("Node crawler running on http://127.0.0.1:5050");
});
