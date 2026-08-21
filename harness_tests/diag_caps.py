"""Does the served chat RECALL its seeded capabilities?"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from harness.inference.client import SPDaemonClient
from harness.inference.inference_config import InferenceConfig

SYS = ("You are Kairos, an experimental AI running locally on a single RTX 2060. You have a "
       "real working memory and can call tools. Use what you know about yourself faithfully; be concise.")
c = SPDaemonClient("http://127.0.0.1:3000")
cfg = InferenceConfig(temperature=0.0, max_tokens=60, auto_recall=True)
for q in ["How do you store things in your memory?", "Do you remember past conversations?"]:
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": q}]
    r = c.chat(messages=msgs, config=cfg).text.strip()
    print(f"Q: {q}\n  A: {' '.join(r.split())[:200]}\n", flush=True)
