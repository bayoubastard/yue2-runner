# YuE2 Runner

Cheap, fast YuE2 song generation on a spot RTX 4090 rented from Vast.ai.

## What this does

- Rents a spot RTX 4090 (~$0.35/hr) on Vast.ai
- Installs the official YuE2 pipeline (BF16, no quantization — best quality)
- Generates a song from your lyrics + style prompt
- Downloads the FLAC output to your machine
- Shuts the instance down when done

Cost: roughly a penny per song. A 3.6-minute song takes about 71 seconds on a 4090.

## Requirements

- A Vast.ai account with a payment method (card or crypto)
- A Hugging Face account (free) — the model weights download automatically on first run
- Python 3.12 on your local machine

## Setup (one time)

```bash
git clone https://github.com/bayoubastard/yue2-runner.git
cd yue2-runner
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python generate.py --style "slow acoustic grunge ballad, male vocal, weary and intimate, 1990s Seattle, fingerpicked guitar" --lyrics lyrics.txt --output my-song
```

The script will:

1. Find the cheapest available spot RTX 4090 on Vast.ai
2. Boot it, install CUDA + Python + YuE2
3. Run the generation
4. Pull the FLAC back to your machine
5. Destroy the instance

## Notes

- Spot instances can be interrupted. The script checkpoints and retries.
- Model weights are CC BY-NC 4.0 with a creator permission: individuals can monetize outputs, companies need a commercial license from the YuE2 authors.
- Don't feed it copyrighted lyrics you don't have rights to.

## License

MIT for the runner code. Model weights: see MODEL_LICENSE terms from the YuE2 authors.
