import secrets
import string

import httpx

BASE_URL = "https://api.mail.tm"


class MailTMClient:
    def __init__(self):
        self.client = httpx.Client(timeout=20.0)

    def get_domains(self):
        r = self.client.get(f"{BASE_URL}/domains")
        r.raise_for_status()
        data = r.json()
        return data.get("hydra:member", [])

    def create_account(self, address: str, password: str):
        r = self.client.post(
            f"{BASE_URL}/accounts",
            json={"address": address, "password": password},
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()

    def get_token(self, address: str, password: str):
        r = self.client.post(
            f"{BASE_URL}/token",
            json={"address": address, "password": password},
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()["token"]

    def get_messages(self, token: str):
        r = self.client.get(
            f"{BASE_URL}/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json().get("hydra:member", [])

    def get_message(self, token: str, message_id: str):
        r = self.client.get(
            f"{BASE_URL}/messages/{message_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()


def random_string(n=12):
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def create_new_mailbox(custom_name=None, custom_password=None):
    api = MailTMClient()
    domains = api.get_domains()
    if not domains:
        raise RuntimeError("Нет доступных доменов")

    domain = domains[0]["domain"]
    username = custom_name if custom_name else random_string(12)
    password = custom_password if custom_password else random_string(16)
    address = f"{username}@{domain}"

    account = api.create_account(address, password)
    token = api.get_token(address, password)

    return {
        "id": account["id"],
        "address": address,
        "password": password,
        "token": token,
    }
