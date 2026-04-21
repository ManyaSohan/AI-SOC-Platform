import requests
import random
import time

URL = "http://127.0.0.1:5000/predict"

countries = [
    "India", "USA", "Germany", "Russia",
    "China", "Brazil", "France", "UK",
    "Japan", "Canada", "Australia"
]

while True:

    data = {
        "packets": random.randint(300,2500),
        "login_fail": random.randint(0,1),
        "sql": random.randint(0,1),
        "country": random.choice(countries)   # ✅ RANDOM COUNTRY
    }

    headers = {
        "X-Forwarded-For": f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
    }

    r = requests.post(URL, json=data, headers=headers)

    print("Injected:", data)

    time.sleep(2)