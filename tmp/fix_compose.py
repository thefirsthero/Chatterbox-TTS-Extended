import yaml
with open("/data/coolify/services/a4c48w0wkggkwoc8s48o0w08/docker-compose.yml") as f:
    data = yaml.safe_load(f)
data["services"]["n8n"]["environment"]["N8N_COMMUNITY_PACKAGES_ENABLED"] = "true"
with open("/data/coolify/services/a4c48w0wkggkwoc8s48o0w08/docker-compose.yml", "w") as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=False)
print("Fixed")
