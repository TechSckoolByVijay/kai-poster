"""Kai Content Board (Google Sheet): per-platform order + status for every Kai video.

Columns used: id, built, yt_/ig_/li_ order, status, posted_at, url. The next video for a platform is the
row with status "ready" and the lowest order. Env: GSHEET_TOKEN_JSON (OAuth token, Sheets scope), SHEET_ID.
"""
import datetime as dt
import json
import os
import re

PREFIX = {"youtube": "yt", "instagram": "ig", "linkedin": "li"}


def _api():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_info(json.loads(os.environ["GSHEET_TOKEN_JSON"]))
    if not creds.valid:
        creds.refresh(Request())
    return build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()


def _col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Board:
    def __init__(self):
        self.id = os.environ["SHEET_ID"]
        self.api = _api()
        self.tab = self.api.get(spreadsheetId=self.id).execute()["sheets"][0]["properties"]["title"]
        values = self.api.values().get(spreadsheetId=self.id, range=f"'{self.tab}'").execute().get("values", [])
        self.header = values[0]
        # Sheets puts a space after each line break in imported cells; strip it so comments paste cleanly
        self.rows = [{h: re.sub(r"\n +", "\n", (r[i] if i < len(r) else "")) for i, h in enumerate(self.header)}
                     for r in values[1:]]

    def next_for(self, platform):
        p = PREFIX[platform]
        ready = [r for r in self.rows if r.get(f"{p}_status", "").strip().lower() == "ready"
                 and r.get("built", "").strip().lower() == "yes" and r.get(f"{p}_order", "").strip()]
        return min(ready, key=lambda r: float(r[f"{p}_order"]), default=None)

    def mark_posted(self, vid, platform, url):
        p = PREFIX[platform]
        n = next(i for i, r in enumerate(self.rows) if r["id"] == vid) + 2   # +1 header, +1 one-based
        when = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        data = [{"range": f"'{self.tab}'!{_col(self.header.index(c) + 1)}{n}", "values": [[v]]}
                for c, v in ((f"{p}_status", "posted"), (f"{p}_posted_at", when), (f"{p}_url", url))]
        self.api.values().batchUpdate(spreadsheetId=self.id,
                                      body={"valueInputOption": "RAW", "data": data}).execute()
