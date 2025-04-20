import requests
from bs4 import BeautifulSoup

# Target job listings page
url = "https://www.overlakecareers.org/jobs/nursing-all-specialties/"
response = requests.get(url)
soup = BeautifulSoup(response.content, "html.parser")

# Heuristic: identify all repeated job listing containers
job_containers = []

# Look for <div> with both a valid <a href> and a description
for div in soup.find_all("div"):
    if div.find("a", href=True) and div.find("span", class_="description"):
        job_containers.append(div)

# Print only the total number of listings
print(f"✅ Total job listings found: {len(job_containers)}")
