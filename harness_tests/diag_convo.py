"""Diagnostic: does a system prompt fix conversational faithfulness (octopus, not dog)?"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from harness.inference.client import SPDaemonClient
from harness.inference.inference_config import InferenceConfig

SYS = (
    "You are Kairos, an experimental AI running locally. You have a working memory and "
    "can call tools. In conversation, pay close attention to what the user has told you earlier "
    "in THIS conversation and use it faithfully. Never invent, substitute, or guess a fact the "
    "user already stated -- if they said their favorite animal is an octopus, it is an octopus, "
    "not a generic guess. If you were not told something, say so rather than making it up. Be "
    "concise and direct."
)

c = SPDaemonClient("http://127.0.0.1:3000")
cfg = InferenceConfig(temperature=0.0, max_tokens=48, auto_recall=True)
history = [{"role": "system", "content": SYS}]

def turn(u):
    history.append({"role": "user", "content": u})
    r = c.chat(messages=list(history), config=cfg).text.strip()
    history.append({"role": "assistant", "content": r})
    print(f"USER: {u}\n  AI: {r}\n", flush=True)

turn("My favorite animal is the octopus.")
turn("I also really like jazz music.")
turn("Without me repeating them: what is my favorite animal, and what kind of music do I like?")
low = history[-1]["content"].lower()
print(f"=> FAITHFUL={'octopus' in low and 'jazz' in low}  (octopus AND jazz both present)")
