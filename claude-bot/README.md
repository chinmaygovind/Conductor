# claude-bot — ML Training for Conductor

This directory contains everything needed to train the `claude_bot` personality to play
Conductor at a high level using machine learning (not hand-coded heuristics).

## Directory Structure

```
claude-bot/
  README.md          — this file
  train.py           — main training entry point
  features.py        — game-state → feature vector extraction
  model/             — trained model artifacts (gitignored)
    claude_bot_weights.json   (or .pkl, .pt, etc.)
  data/              — game history exports for supervised pre-training (gitignored)
```

## Approach

TBD — will be decided in conversation with the user. Candidate approaches:

- **Self-play RL** (e.g., policy gradient / MCTS): simulate games, reward = final score rank
- **Supervised from human games**: extract (state, action) pairs from real game history in
  the DB, train a classifier to imitate high-scoring human play (especially fishy's games)
- **Hybrid**: supervised pre-training on human games, then RL fine-tuning via self-play

## Integration with bot.py

`bot.py:_claude_turn()` is the hook. The trained model lives in `model/` and is loaded
once at startup. If no model file exists, the bot falls back to weight-based scoring.

## Running

```bash
cd claude-bot
python train.py
```

Trained artifacts are written to `model/` and picked up automatically by `bot.py`.
