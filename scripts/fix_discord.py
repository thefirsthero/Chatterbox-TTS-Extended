import json, urllib.request

API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MjQ2YzAzOS1iZjk3LTRiNzMtODE3ZC1iMDk4MjQxZDA4YWEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMjZjYjE0M2ItNjUxNC00ZjFiLWIwMGEtOTZlZjZmZDFiMzkwIiwiaWF0IjoxNzgyNDA4MDMxLCJleHAiOjE3ODQ5Mzc2MDB9.uR_f9EzuC8GCedXJs6MxbpD-863rZAfQdZTigCOck2A'
BASE = 'https://n8n.coraxi.com/api/v1'

def api(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header('X-N8N-API-KEY', API_KEY)
    if data:
        r.add_header('Content-Type', 'application/json')
    resp = urllib.request.urlopen(r)
    return json.loads(resp.read())

def save_workflow(wf_id):
    """Save workflow via PUT after modifying nodes"""
    wf = api('GET', f'/workflows/{wf_id}')
    body = {
        'name': wf['name'],
        'nodes': wf['nodes'],
        'connections': wf['connections'],
        'settings': {'executionOrder': 'v1'}
    }
    api('PUT', f'/workflows/{wf_id}', body)

# Messages using backtick template literals with = prefix
# This format: = `emoji text ${$json.field} more text`
# - = evaluates the expression
# - Backticks create template literal
# - ${$json.field} interpolates n8n data
# - Emojis render properly inside template literals

HEALTHY_MSG = "= `\U0001f4ca **Weekly Queue Report**\n\nQueue is healthy! \U0001f44d\n\n\u2022 \U0001f195 **${$json.new_count}** videos available\n\u2022 \u2705 ${$json.done_count} posted\n\u2022 \u274c ${$json.failed_count} failed\n\u2022 \U0001f4e6 ${$json.total} total tracked\n\nNext post: Tomorrow at 19:00 SAST`"

LOW_MSG_TEMPLATE = "= `\u26a0\ufe0f **Low Inventory Alert!**\n\n\U0001f4ca Queue Status:\n\u2022 \U0001f195 **${$json.new_count}** new videos remaining\n\u2022 \u2705 ${$json.done_count} already posted\n\u2022 \u274c ${$json.failed_count} failed\n\n\U0001f534 Only **${$json.new_count}** videos left \u2014 upload more!\n\nUpload new videos to:\n{drive}`"

CONFIGS = [
    ('34Fsiaw78YATJN2x', '1Bc6E-_w1fo_yi5gvbyAS7BDUZ5qLL4Pp'),
    ('ZkOIGGuL6SpSyTxR', '1Y-doGuk-5Waw73a1zbEYz9WkBTG16TZj'),
    ('wP7y34CxvWQCoCek', '1KX8Uq_dSlGweVgzLJFisKOYSBrettBeq'),
]

for wf_id, drive_id in CONFIGS:
    wf = api('GET', f'/workflows/{wf_id}')
    for node in wf['nodes']:
        if node['name'] == 'Send Healthy Report':
            node['parameters']['text'] = HEALTHY_MSG
        elif node['name'] == 'Send Low Inventory Alert':
            drive_link = f'https://drive.google.com/drive/u/2/folders/{drive_id}'
            node['parameters']['text'] = LOW_MSG_TEMPLATE.format(drive=drive_link)
    
    body = {
        'name': wf['name'],
        'nodes': wf['nodes'],
        'connections': wf['connections'],
        'settings': {'executionOrder': 'v1'}
    }
    api('PUT', f'/workflows/{wf_id}', body)
    print(f"Fixed: {wf['name']}")

print("\nAll Discord messages updated!")
print("Format: = `emoji text ${$json.field}` (backtick template literal)")
print("\nNext: Add header row back to AITAH sheet, then re-run Weekly Sync.")
