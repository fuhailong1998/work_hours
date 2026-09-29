#!/usr/bin/env python3
"""Locate the external approval with lark-cli and inspect its form through HTTP.

This discovery stage does not save or submit an approval.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import parse_qs, urlsplit

NAME = "非常规工时调整流程"
CODE = "B598FA51-FC3B-4854-BF10-DE9EE4528D1F"
OA_HOST = "i.thundersoft.com"
SSO_HOST = "larkapproval.thundersoft.com"
OA_APP = "cli_a11b74bf89b9d00b"


def discover():
    env = dict(os.environ, LARKSUITE_CLI_NO_UPDATE_NOTIFIER="1",
               LARKSUITE_CLI_NO_SKILLS_NOTIFIER="1")
    page_token = None
    while True:
        data = {"keyword": NAME, "locale": "zh-CN", "page_size": 100}
        if page_token:
            data["page_token"] = page_token
        result = subprocess.run(
            ["lark-cli", "approval", "approvals", "search", "--as", "user",
             "--data", json.dumps(data, ensure_ascii=False)],
            capture_output=True, text=True, env=env, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        envelope = json.loads(result.stdout)
        if envelope.get("ok") is not True:
            raise RuntimeError("lark-cli did not return a successful response")
        response = envelope["data"]
        for item in response.get("approvals", []):
            if item.get("approval_code") == CODE and item.get("approval_name") == NAME:
                if item.get("is_external") is not True:
                    raise RuntimeError("Approval type changed; inspect the definition again")
                return item
        if not response.get("has_more"):
            raise RuntimeError("Target approval is not available to the current user")
        next_token = response.get("page_token")
        if not next_token or next_token == page_token:
            raise RuntimeError("Invalid pagination token")
        page_token = next_token


def browser_url(item):
    link = urlsplit(item["create_link"])
    if link.hostname != "applink.feishu.cn":
        raise RuntimeError("Unexpected approval link host")
    target = parse_qs(link.query)["url"][0]
    parsed = urlsplit(target)
    if parsed.scheme != "https" or parsed.hostname != SSO_HOST:
        raise RuntimeError("Unexpected OA login host")
    return target


def main():
    parser=argparse.ArgumentParser(description="Discover the OA workflow or inspect its HTTP schema")
    parser.add_argument('action', choices=['discover','inspect'])
    parser.add_argument('--output-dir',default='.local/oa')
    args=parser.parse_args()
    if args.action=='discover':
        print(json.dumps(discover(),ensure_ascii=False,indent=2));return
    from oa_http import get_session
    from oa_form_api import OAForm
    form=OAForm(get_session())
    schema={'base':form.base,'tables':form.tables,'linkage':form.cfg}
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=out/'schema.json';path.write_text(json.dumps(schema,ensure_ascii=False,indent=2));path.chmod(0o600)
    print(json.dumps({'status':'schema_ready','schema':str(path)},ensure_ascii=False))


if __name__=='__main__':main()
