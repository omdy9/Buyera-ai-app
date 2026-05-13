import express from "express";
import axios from "axios";
import * as cheerio from "cheerio";

const app = express();
app.use(express.json());

const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}/g;
const PHONE_RE = /\+?\d[\d\s\-()]{8,}/g;

async function fetchPage(url){
  try{
    const res = await axios.get(url,{
      timeout:15000,
      headers:{ "User-Agent":"Mozilla/5.0" }
    });
    return res.data;
  }catch{
    return "";
  }
}

app.post("/crawl", async(req,res)=>{

  const { url } = req.body;

  if(!url) return res.json({});

  const pages = [url, url+"/contact", url+"/about"];

  let content="";
  let emails=new Set();
  let phones=new Set();

  for(const p of pages){

    const html = await fetchPage(p);
    if(!html) continue;

    const $ = cheerio.load(html);
    const text = $("body").text();

    content += " " + text;

    (text.match(EMAIL_RE)||[]).forEach(e=>emails.add(e));
    (text.match(PHONE_RE)||[]).forEach(p=>phones.add(p));
  }

  res.json({
    email:[...emails][0]||"",
    phone:[...phones][0]||"",
    content:content.substring(0,5000)
  });

});

app.listen(5050,()=>{
  console.log("Node crawler running on http://127.0.0.1:5050");
});
