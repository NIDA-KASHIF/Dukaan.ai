"""Talk to the store manager in the terminal.

Run:  python run_chat.py
Commands:  pending  |  approve 3  |  reject 3  |  reset  |  exit
"""
import re

from dukaan import agent, db
from dukaan.llm import NoProviderError
from dukaan.skills import agents


def main():
    print("Dukaan AI — type your request (Urdu / Roman Urdu / English). 'exit' to quit.\n")
    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        low = text.lower()
        if low in ("exit", "quit"):
            break
        m = re.match(r"^(approve|reject)\s*#?(\d+)$", low)
        if m:
            print(agent.run_approved(int(m.group(2))) if m.group(1) == "approve" else agent.reject(int(m.group(2))))
            continue
        if low == "pending":
            for a in db.pending_approvals():
                print(f"\n#{a['id']}\n{a['summary']}")
            continue
        if low == "reset":
            db.clear_history("owner")
            print("New conversation.")
            continue
        hist = db.history("owner")
        db.add_message("owner", "user", text)
        try:
            reply = agents.manager().run(text, hist)
        except NoProviderError as e:
            reply = str(e)
        db.add_message("owner", "assistant", reply)
        print(f"\nDukaan AI: {reply}\n")
        pend = db.pending_approvals()
        if pend:
            print(f"(Waiting for your approval: {', '.join('#' + str(a['id']) for a in pend)} — type 'pending' to see them)\n")


if __name__ == "__main__":
    main()
