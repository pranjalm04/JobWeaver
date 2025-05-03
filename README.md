# PhysicianX – Physician‑Job Aggregation Pipeline

> **One‑stop pipeline for discovering, extracting, and storing physician job listings from healthcare career sites**

---

## ✨ Key Features
| Stage | What Happens |
|-------|--------------|
| **1. BFS Crawler** | Starts from seed URLs, performs breadth‑first search, respects `robots.txt`, and queues new links. |
| **2. Heuristic Scoring** | Regex + NLP rules score every fetched page; only high‑scoring “job list” pages proceed. |
| **3. Dynamic Selector Discovery** | Google Gemini 2.0 Flash inspects HTML and returns CSS selectors for:<br>• Individual job links<br>• “Next page” buttons<br>• Listing container<br>• Validation flag |
| **4. Job Detail Extraction** | For each job link:<br>1. HTML → Markdown<br>2. LLM parses Markdown into JSON (title, location, specialty, etc.). |
| **5. Data Load** | Clean JSON rows are written into **MySQL** for search, analytics, and alerts. |

---
![physicianXworkflow drawio](https://github.com/user-attachments/assets/cc1326cb-43dd-41df-833e-09641b8da1bd)
## 🛠️ Tech Stack
- **Python 3.11** — crawler, pipeline glue  
- **Playwright / Requests‑HTML** — fetching & rendering  
- **BeautifulSoup 4** — DOM parsing
- **Crawl4ai** - Crawling the webpages
- **Gemini 2.0 Flash** — selector discovery  
- **OpenAI / Anthropic** (pluggable) — Markdown → JSON extraction  






