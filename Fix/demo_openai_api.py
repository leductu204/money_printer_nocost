import requests

url = "https://www.openai.fm/api/generate"

payload = {'input': 'Once upon a time, in a land full of wonders, there lived a kind little fox named Finley. ',
'prompt': 'Affect: A gentle, curious narrator with a British accent, guiding a magical, child-friendly adventure through a fairy tale world.',
'voice': 'coral',
'vibe': 'null'}
files=[

]
headers = {
  'accept': '*/*',
  'accept-language': 'vi-VN,vi;q=0.9,zh-CN;q=0.8,zh;q=0.7,fr-FR;q=0.6,fr;q=0.5,en-US;q=0.4,en;q=0.3',
  'origin': 'https://www.openai.fm',
  'priority': 'u=1, i',
  'referer': 'https://www.openai.fm/worker-444eae9e2e1bdd6edd8969f319655e70.js',
  'sec-fetch-dest': 'empty',
  'sec-fetch-mode': 'cors',
  'sec-fetch-site': 'same-origin',
  'user-agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36',
  'Cookie': '_ga=GA1.1.600869161.1743481050; _ga_NME7NXL4L0=GS1.1.1745957564.11.1.1745958401.0.0.0'
}

response = requests.request("POST", url, headers=headers, data=payload, files=files)

print(response.text)
