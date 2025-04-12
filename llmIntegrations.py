
import json
from mistralai import Mistral
import requests
api_key="guEDJaE2YX3qKA2OkrnTxfAamFFj29wX"
def extract_jobs_from_html(html_content,source_url):
    ollama_url = "http://localhost:11434/api/generate"

    system_prompt = """
    {
      "task": "Extract physician job details from HTML content into structured JSON",
      "instructions": {
        "input_handling": "Parse HTML content focusing exclusively on ONE physician-related job posting",
        "required_fields": {
          "job_title": "Exact position title ",
          "company": "Hiring organization name",
          "location": "City/State combination",
          "job_type": "Employment type (e.g., Full-time, Locum Tenens)",
          "job_summary": "3-5 sentence overview of primary responsibilities",
          "key_responsibilities": ["List of core duties", "Focus on patient care aspects"],
          "qualifications": ["Medical degree type", "Required certifications", "Experience level"],
          "benefits": ["Salary range if available", "Insurance options", "Retirement plans"],
          "application_details": {
            "deadline": "YYYY-MM-DD format if specified",
            "method": "Application instructions/portal"
          },
          "source_url": "Original job page URL"
        },
        "constraints": [
          "Ignore website navigation elements and footer content",
          "Reject content containing multiple job listings",
          "Return empty strings for missing information"
        ]
      },
    Follow these rules:
    1. Focus ONLY on the primary job listing 
    2. Extract text content while ignoring HTML tags
    3. Validate required MD/DO qualifications
    4. Structure benefits as array items
    5. Include direct source URL
    """

    client = Mistral(api_key=api_key)
    model = "mistral-large-latest"
    try:
        chat_response = client.chat.complete(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Extract job details from:\n{html_content}\nSource URL: {source_url}"
                }
            ],
            response_format={
                "type": "json_object",
            }
        )
        response = chat_response.choices[0].message.content
        print(response)
        return response
    except Exception as e:
        print('exception on llm',e)
