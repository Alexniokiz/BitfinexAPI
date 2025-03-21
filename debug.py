import requests

# Fetch funding stats for fUSD from Bitfinex public API
url = "https://api-pub.bitfinex.com/v2/book/fUSD/P0?len=25"
headers = {"accept": "application/json"}
response = requests.get(url, headers=headers)
data = response.json()

print("API Response Format:")
print("===================")
print(f"Type of data: {type(data)}")
print(f"Length of data: {len(data)}")
print("\nFirst few elements:")
for i, element in enumerate(data[:3]):
    print(f"\nElement {i}:")
    print(f"Type: {type(element)}")
    print(f"Content: {element}") 