import requests
import json
import random

# Get a new session token ONCE
token_resp = requests.get("https://opentdb.com/api_token.php?command=request")
token = token_resp.json().get("token")

all_questions = []
url_base = "https://opentdb.com/api.php?amount=50&category=18&token={}"

for _ in range(10):  # Up to 500 questions per token
    url = url_base.format(token)
    response = requests.get(url)
    data = response.json()
    if data.get('response_code') == 0 and 'results' in data:
        for item in data['results']:
            q = {
                "question": item['question'],
                "answer": item['correct_answer'],
                "type": item['type'],
                "money": 1000
            }
            if item['type'] == 'multiple':
                possible_answers = item['incorrect_answers'] + [item['correct_answer']]
                random.shuffle(possible_answers)
                q["possible_answers"] = possible_answers
            all_questions.append(q)
    elif data.get('response_code') == 5:
        print("Pool exhausted for this token. Run the script again for a new token.")
        break
    else:
        print("No results found or API error:", data)

with open("questions.json", "w") as f:
    json.dump(all_questions, f, indent=2)
