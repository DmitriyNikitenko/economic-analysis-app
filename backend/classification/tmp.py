import json, collections
d = json.load(open("data/processed/osm_classified.json", encoding="utf-8"))
print(collections.Counter(f["properties"]["classification"]["type"] for f in d["features"]).most_common())

for f in d["features"]:
    t = f["properties"]["tags"]
    if "office" in t and "shop" in t:
        print(f["properties"]["classification"]["type"], t.get("name"), t["office"], t["shop"])