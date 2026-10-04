from copy import deepcopy

class FakeSupabaseClient:
    def __init__(self, lead):
        self.leads = {lead["id"]: deepcopy(lead)}
        self.users = {}

    def select_all(self, resource, params):
        if resource != "prospects":
            raise AssertionError(f"Unexpected resource: {resource}")
        rows = [{"id": key, "data": deepcopy(value)} for key, value in self.leads.items()]
        user_filter = (params or {}).get("user_id", "")
        if user_filter.startswith("eq."):
            wanted = user_filter.removeprefix("eq.")
            rows = [row for row in rows if self.users.get(row["id"]) == wanted]
        return rows

    def request(self, method, resource, params=None, payload=None, prefer=None):
        if method == "POST" and resource == "prospects":
            rows = payload if isinstance(payload, list) else [payload]
            for row in rows:
                self.leads[row["id"]] = deepcopy(row["data"])
                self.users[row["id"]] = row.get("user_id")
            return []
        if method != "PATCH" or resource != "prospects":
            raise AssertionError(f"Unexpected request: {method} {resource}")
        lead_id = params["id"].removeprefix("eq.")
        self.leads[lead_id] = deepcopy(payload["data"])
        return [{"id": lead_id}]

def prospect():
    return {
        "id": "prospect-1",
        "name": "Onyx",
        "business": "Onyx Garage Floors",
        "phone": "+12025550123",
        "timezone": "Eastern",
        "status": "new",
        "scheduled_until": None,
        "transcript": [],
        "fields": {},
    }
