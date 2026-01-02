import json

with open('data/cache/race_202406050811.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

print('Payouts:', d['payouts'])
print('Winners:', [h for h in d['horses'] if h['finish']==1])
