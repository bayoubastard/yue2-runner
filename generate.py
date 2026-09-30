#!/usr/bin/env python3
"""Rent a spot RTX 4090 on Vast.ai, run YuE2, download the song, kill the box."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import paramiko
import requests

VAST_API = "https://console.vast.ai/api/v0"


def vast_headers():
    key = os.environ.get("VAST_API_KEY")
    if not key:
        print("Set VAST_API_KEY in your environment (from vast.ai account settings).", file=sys.stderr)
        sys.exit(1)
    return {"Authorization": f"Bearer {key}"}


def find_cheapest_4090():
    r = requests.get(
        f"{VAST_API}/bundles/",
        headers=vast_headers(),
        params={
            "q": json.dumps(
                {
                    "verified": {"eq": True},
                    "gpu_name": {"eq": "RTX 4090"},
                    "num_gpus": {"eq": 1},
                    "rentable": {"eq": True},
                    "reliability2": {"gte": 0.95},
                    "inet_up": {"gte": 100},
                    "cuda_vers": {"gte": "12.1"},
                    "order": [["dph_total", "asc"]],
                    "limit": 20,
                }
            ),
            "limit": 20,
        },
    )
    r.raise_for_status()
    offers = r.json().get("offers", [])
    if not offers:
        raise RuntimeError("No spot RTX 4090 offers found. Try again later.")
    return offers[0]


def create_instance(offer):
    r = requests.put(
        f"{VAST_API}/asks/{offer['id']}/",
        headers=vast_headers(),
        json={
            "client_id": "me",
            "image": "nvidia/cuda:12.4.0-base-ubuntu22.04",
            "disk": 40,
            "label": "yue2-runner",
        },
    )
    r.raise_for_status()
    return r.json()["new_contract"]


def ssh_connect(contract, timeout=600):
    host = contract["ssh_host"]
    port = contract["ssh_port"]
    user = contract["ssh_username"]
    key_path = os.path.expanduser("~/.ssh/id_rsa")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            client.connect(host, port=port, username=user, key_filename=key_path, timeout=10)
            return client
        except Exception:
            time.sleep(10)
    raise RuntimeError("SSH connection timed out")


SETUP_SCRIPT = r"""
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3.12 python3.12-venv python3-pip git wget > /dev/null
python3.12 -m venv /opt/yue2
source /opt/yue2/bin/activate
pip install -q --upgrade pip
pip install -q torch --index-url https://download.pytorch.org/whl/cu124
git clone https://github.com/multimodal-art-projection/YuE.git /opt/YuE
cd /opt/YuE
pip install -q .
"""


GENERATE_SCRIPT = r"""
source /opt/yue2/bin/activate
cd /opt/YuE
python examples/generate.py --output /tmp/yue2-out {extra_args}
"""


def run_remote(client, cmd, timeout=1800):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if code != 0:
        print(err, file=sys.stderr)
        raise RuntimeError(f"Remote command failed (exit {code}): {cmd[:80]}")
    return out


def main():
    ap = argparse.ArgumentParser(description="Generate a YuE2 song on a rented spot 4090")
    ap.add_argument("--style", required=True, help="Style prompt")
    ap.add_argument("--lyrics", required=True, help="Path to lyrics file")
    ap.add_argument("--output", default="outputs/song", help="Local output directory")
    ap.add_argument("--cot", default="full", choices=["full", "melody", "off"])
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    lyrics_text = Path(args.lyrics).read_text(encoding="utf-8")
    request = {
        "style": args.style,
        "lyrics": lyrics_text,
        "cot": args.cot,
        "seed": args.seed,
    }
    req_path = Path("song.json")
    req_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

    print("Finding cheapest spot RTX 4090...")
    offer = find_cheapest_4090()
    print(f"  offer {offer['id']}: ${offer['dph_total']:.3f}/hr, reliability {offer.get('reliability2')}")

    print("Creating instance...")
    contract = create_instance(offer)
    print(f"  contract {contract['id']}")

    try:
        print("Waiting for SSH...")
        client = ssh_connect(contract)
        print("  connected")

        print("Installing YuE2 (this takes a few minutes)...")
        run_remote(client, SETUP_SCRIPT, timeout=1200)

        sftp = client.open_sftp()
        sftp.put(str(req_path), "/tmp/song.json")
        sftp.close()

        extra = f"--request /tmp/song.json --cot {args.cot} --seed {args.seed}"
        print("Generating song...")
        run_remote(client, GENERATE_SCRIPT.format(extra_args=extra), timeout=1800)

        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"Downloading to {out_dir}...")
        sftp = client.open_sftp()
        for f in sftp.listdir("/tmp/yue2-out"):
            sftp.get(f"/tmp/yue2-out/{f}", str(out_dir / f))
        sftp.close()
        print(f"Done. Open {out_dir / 'audio.flac'}")
    finally:
        print("Destroying instance...")
        requests.delete(f"{VAST_API}/instances/{contract['id']}/", headers=vast_headers())
        print("  gone")


if __name__ == "__main__":
    main()
