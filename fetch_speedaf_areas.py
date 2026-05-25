import os
import django
import sys
import json

sys.path.append("/Users/eseosa/Documents/wholeearn-ecom")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from ecom.services.speedaf import SpeedAFClient

client = SpeedAFClient()
payload = {"countryCode": "NG"}
data = client._post('/open-api/common/area/getTreeByCountryCode', payload)

if data and data.get("success"):
    raw_data = data.get("data", [])
    ng_data = raw_data if isinstance(raw_data, dict) else (raw_data[0] if raw_data else {})
    if ng_data:
        states = []
        for state in ng_data.get("children", []):
            cities = []
            for city in state.get("children", []):
                cities.append({
                    "code": city.get("code"),
                    "name": city.get("name")
                })
            states.append({
                "code": state.get("code"),
                "name": state.get("name"),
                "cities": cities
            })
        
        # Sort states by name for UI
        states = sorted(states, key=lambda x: x['name'])
        for s in states:
            s['cities'] = sorted(s['cities'], key=lambda x: x['name'])
            
        with open('/Users/eseosa/Documents/wholeearn-ecom/ecom/services/speedaf_areas.json', 'w') as f:
            json.dump(states, f)
        print("SUCCESS")
    else:
        print(f"No structural data found: {raw_data}")
else:
    print(f"FAILED: {data}")
