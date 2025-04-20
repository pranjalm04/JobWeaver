from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse, parse_qs

# --- Heuristic Keywords & Patterns ---

# Keywords often found in <title> or <h1> of listing pages
LISTING_KEYWORDS_TITLE_H1 = [
    "career", "job", "vacancy","Career Opportunities" "opening", "opportunity", "position",
    "listing", "search jobs", "find jobs", "job openings", "job vacancies", "employment opportunities"
]
# General keywords sometimes found on listing pages (lower weight)
LISTING_KEYWORDS_GENERAL = ["filter", "sort by", "results", "found", "jobs found"]
# Keywords suggesting it's an INDIVIDUAL job page (negative indicator if prominent)
INDIVIDUAL_JOB_KEYWORDS_STRONG = ["apply now", "submit application", "job description"]

# --- Pagination Indicators ---
PAGINATION_KEYWORDS = ["next", "previous", "last", "first", "page"]
PAGINATION_CLASSES = ["pagination", "pager", "page-numbers", "page-list", "paging", "pagination-container"]
# Symbols often used in pagination links
PAGINATION_SYMBOLS = ['»', '«', '›', '‹', '>', '<']

# --- Job Item Indicators (Keywords often *within* a job listing item) ---
JOB_ITEM_INDICATORS = [
    "location", "department", "posted", "full-time", "part-time",
    "remote", "hybrid", "salary", "experience level"
]
# Common job title fragments (used in repetitive structure check)
JOB_TITLE_FRAGMENTS = [
    "Advanced Practice Provider", "Business Office Position", "Radiology Technologist Position", "analyst", "specialist", "coordinator",
    "director", "assistant", "designer", "consultant", "nurse","therapist","radiology","psychiatrist","support worker","councellor","Technologist","scientist"
]
# --- Search Form Indicators ---
SEARCH_FORM_INPUT_NAMES = [
    "keyword", "query", "q", "search", "location", "city", "state",
    "zipcode", "postal", "country", "category", "department", "jobid"
]
SEARCH_FORM_KEYWORDS = ["search jobs", "find jobs", "filter jobs"]

# --- URL Path Indicators ---
LISTING_URL_PATHS = ["/jobs", "/careers", "/vacancies", "/openings", "/search", "/job-listings", "/positions", "/employment"]

# --- Heuristic Function ---
def check_job_listing_heuristics(html_content, url=None):
    """
    Analyzes HTML content using heuristics to determine the likelihood
    it's a job LISTING page (showing multiple jobs).

    Args:
        html_content (str): The HTML source code of the page.
        url (str, optional): The URL of the page for URL-based heuristics. Defaults to None.

    Returns:
        float: A confidence score. Higher score means more likely to be a job listing page.
               Scores > 1.0 are possible if multiple strong indicators are found.
               A threshold (e.g., 3.0 or 4.0) can be used for classification.
    """
    score = 0.0
    debug_info = [] # Store reasons for scoring changes

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        parsed_html_str = str(soup)
    except Exception as e:
        print(f"[Error] BeautifulSoup Parsing Error: {e}")
        return 0.0 # Cannot parse

    # --- 1. Title and H1/H2 Check (Weight: 1.5) ---
    page_title = soup.title.string.lower() if soup.title and soup.title.string else ""
    h1_text = ""
    if soup.h1:
        h1_text = soup.h1.get_text(" ", strip=True).lower()
    h2_texts = " ".join(h2.get_text(" ", strip=True).lower() for h2 in soup.find_all('h2', limit=5))
    h3_texts=" ".join(h3.get_text(" ", strip=True).lower() for h3 in soup.find_all('h3', limit=5))
    title_h1_h2_text = f"{page_title} {h1_text} {h2_texts} {h3_texts}"

    found_title_keyword = False
    if any(keyword in title_h1_h2_text for keyword in LISTING_KEYWORDS_TITLE_H1):
        score += 1.5
        found_title_keyword = True
        debug_info.append("(+1.5) Found strong listing keyword in Title/H1/H2")

    # Penalize if strong individual job keywords are prominent (e.g., in H1)
    if any(keyword in title_h1_h2_text for keyword in INDIVIDUAL_JOB_KEYWORDS_STRONG):
         score -= 1.0 # Reduce score if "Apply Now" or "Job Description" is the main heading
         debug_info.append("(-1.0) Found 'Apply Now'/'Job Description' style keyword in H1 (penalty)")
    if any(keyword in title_h1_h2_text for keyword in LISTING_KEYWORDS_GENERAL):
         # Add smaller score for general keywords if strong ones weren't found
         if not found_title_keyword:
              score += 0.5
              debug_info.append("(+0.5) Found general listing keyword in Title/H1/H2")


    # --- 2. URL Check (Weight: 1.0) ---
    if url:
        try:
            parsed_url = urlparse(url)
            path_lower = parsed_url.path.lower() if parsed_url.path else ""
            query_params = parse_qs(parsed_url.query)

            # Basic check for common paths
            if any(p in path_lower for p in LISTING_URL_PATHS if p != "/"): # Avoid matching root '/' alone
                 score += 1.0
                 debug_info.append(f"(+1.0) URL path ('{path_lower}') matches common listing pattern.")
            # Check for search query params common in listings
            # elif query_params and any(k.lower() in SEARCH_FORM_INPUT_NAMES for k in query_params):
            #      score += 0.7 # Slightly less score than path match
            #      debug_info.append(f"(+0.7) URL query params suggest a search results page.")
        except ValueError:
             debug_info.append("[Warn] URL parsing error.")
             pass # Ignore URL errors


    # --- 3. Pagination Control Check (Weight: 1.5) ---
    pagination_found = False
    pagination_score:float = 0.0
    # Check for specific classes on common tags
    pagination_elements = soup.find_all(['nav', 'div', 'ul'], class_=lambda x: x and any(pc.lower() in x.lower() for pc in PAGINATION_CLASSES), limit=5)
    if pagination_elements:
        pagination_score = 1.5 # High confidence if specific class found
        pagination_found = True
        debug_info.append(f"(+1.5) Found pagination element with specific class ({[e.get('class') for e in pagination_elements]})")
    else:
        # Check for keywords/symbols/numbers in links if class not found
        links = soup.find_all('a', href=True, limit=500) # Limit search space
        page_numbers_count = 0
        next_prev_sym_found = False
        next_prev_kw_found = False
        potential_pagers = [] # Check links within potential pagination divs if classes weren't specific enough

        # Heuristic: check parents for less specific classes if direct match failed
        weak_pagination_containers = soup.find_all(['div', 'ul'], class_=lambda x: x and any(kw in x.lower() for kw in ['page', 'paging', 'pager']), limit=5)
        for container in weak_pagination_containers:
             potential_pagers.extend(container.find_all('a', href=True, limit=50))

        links_to_check = list(set(links + potential_pagers)) # Combine and deduplicate

        for link in links_to_check:
            link_text = link.get_text(strip=True).lower()
            link_sym = link.get_text(strip=True)

            if not link_text and not link_sym: continue # Skip empty links

            if any(kw in link_text for kw in PAGINATION_KEYWORDS):
                 next_prev_kw_found = True
            if any(sym in link_sym for sym in PAGINATION_SYMBOLS):
                 next_prev_sym_found = True
            if re.fullmatch(r'\d{1,3}', link_text): # Match standalone numbers up to 3 digits
                page_numbers_count += 1

        if next_prev_kw_found or next_prev_sym_found:
             pagination_score += 1.0 # Good confidence
             debug_info.append(f"(+1.0) Found Next/Prev keywords or symbols in links.")
        if page_numbers_count >= 3: # Require at least 3 page numbers if no text/symbols
            pagination_score += 0.5 # Add bonus for page numbers
            debug_info.append(f"(+0.5) Found multiple ({page_numbers_count}) page number links.")

        # Cap score if only text/numbers were found
        pagination_score = min(pagination_score, 1.2) # Slightly less confidence than class-based
    if pagination_score > 0: pagination_found = True
    score += pagination_score



    # --- 4. Job Search Form Check (Weight: 1.0) ---
    forms = soup.find_all('form', limit=10)
    forms.extend(soup.find_all('div',limit=50))
    search_form_found = False
    for form in forms:
        form_text = form.get_text(" ", strip=True).lower()
        # Check for explicit "Search Jobs" buttons or labels
        if any(keyword in form_text for keyword in SEARCH_FORM_KEYWORDS):
             score += 1.0
             search_form_found = True
             debug_info.append("(+1.0) Found form with job search keywords.")
             break
        else:
            # Check for common input names/ids/placeholders
            inputs = form.find_all(['input', 'select'], limit=20)
            found_relevant_input = False
            for input_tag in inputs:
                # Combine relevant attributes into one string for searching
                attrs_text = f"{input_tag.get('name','')} {input_tag.get('id','')} {input_tag.get('placeholder','')} {input_tag.get('aria-label','')}".lower()
                if any(name in attrs_text for name in SEARCH_FORM_INPUT_NAMES):
                    found_relevant_input = True
                    break
            if found_relevant_input:
                score += 0.8 # Slightly less confident than explicit keywords
                search_form_found = True
                debug_info.append("(+0.8) Found form with relevant input names (keyword, location etc.).")
                break
    # --- 5. Repetitive Job Item Structure Check (Weight: 2.0) ---
    # More robust check: Find potential container elements and see if they repeat
    # with similar content patterns (e.g., link + location text).
    potential_item_count = 0
    # Heuristic: Look for common container tags with classes hinting at 'job', 'listing', 'item', 'card', 'result'
    # This needs refinement based on common patterns across sites.
    potential_items = []
    common_selectors = [("div", "job"), ("li", "job"), ("article", "job"), ("div", "result"), ("li", "result"),
                        ("div", "item"), ("div", "card"),
                        ("div", "Career"), ("tr", "job"), ("article","item"),("article", "career"),("div","position")]  # Added table row
    for selector in common_selectors:
        try:
            items = soup.find_all(selector[0], class_=re.compile(re.escape(selector[1]), re.IGNORECASE),limit=50)
            potential_items.extend(items)
        except Exception:
            pass

    unique_items = list({item: True for item in potential_items}.keys())

    if len(unique_items) >= 2:
        # Check if these items contain typical job info
        valid_items_count = 0
        for item in unique_items[:20]: # Check content of first 20 found items
            item_text = item.get_text(" ", strip=True).lower()
            has_link = item.find('a', href=True) is not None
            has_job_keyword = any(ind in item_text for ind in JOB_ITEM_INDICATORS)
            has_title_fragment = any(frag.lower() in item_text.lower() for frag in JOB_TITLE_FRAGMENTS)
            # Require a link and some other job-related text
            if has_link and (has_job_keyword or has_title_fragment):
                valid_items_count += 1
        # print("valid_items_count",valid_items_count)
        if valid_items_count >= 2:
             # Scale score by count, capped at max weight 2.0
             item_score = 4.0 * min(valid_items_count / 5.0, 1.0)
             score += item_score
             debug_info.append(f"(+{item_score:.1f}) Found {valid_items_count} repeating items with job-like content via selectors.")
             potential_item_count = valid_items_count # For final check
    # --- 6. Fallback Repetitive Link Check (Weight: 0.5 - only if structured check failed) ---
    # If the selector method didn't find enough items, do a simpler check for multiple job-like links
    if potential_item_count < 3:
        job_link_count = 0
        all_links = soup.find_all('a', href=True, limit=500)
        for link in all_links:
             link_text = link.get_text(strip=True)
             href = link.get('href', '')
             # Basic check: seems like title, not a simple nav link, points relatively locally
             if 1 < len(link_text.split()) < 10 and re.search(r'[a-zA-Z]', link_text) and not href.startswith(('http', '#', 'javascript:', 'mailto:')) and len(href) > 1:
                  link_text_lower = link_text.lower()
                  # Check if link text contains job title fragments
                  if any(frag in link_text_lower for frag in JOB_TITLE_FRAGMENTS):
                     job_link_count += 1
        if job_link_count >= 2: # Require more links for this weaker heuristic
            link_score = 0.5
            score += link_score
            debug_info.append(f"(+{link_score:.1f}) Fallback: Found {job_link_count} links containing job title fragments.")
    # --- Final Score & Debug ---
    final_score = round(score, 2)
    return final_score,debug_info

