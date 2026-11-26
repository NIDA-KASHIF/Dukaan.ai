"""The agent engine: tools, the think-act loop, and the owner-approval gate.

Every tool that changes something outside this app (publishing to Wix,
sending a product to a customer by hand) is marked needs_approval=True.
Calling such a tool does NOT run it: it saves an approval request, and it
runs only after the owner presses Approve (dashboard) or replies
"APPROVE <number>" on WhatsApp.
"""
import json
import traceback

from . import db, llm

REGISTRY = {}  # every tool, by name, so approved actions can be run later


class Tool:
    def __init__(self, name, description, parameters, fn, needs_approval=False, summary=None):
        self.name = name
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}}
        self.fn = fn
        self.needs_approval = needs_approval
        self.summary = summary  # function(args) -> short text shown to the owner
        REGISTRY[name] = self

    def schema(self):
        desc = self.description
        if self.needs_approval:
            desc += " (The owner must approve this before it runs; you will get an approval number.)"
        return {"type": "function", "function": {"name": self.name, "description": desc, "parameters": self.parameters}}

    def call(self, args):
        if self.needs_approval:
            text = self.summary(args) if self.summary else f"{self.name}: {json.dumps(args, ensure_ascii=False)[:300]}"
            aid = db.add_approval(self.name, text, {"tool": self.name, "args": args})
            notify_owner(f"🟡 Approval #{aid} needed:\n{text}\n\nReply APPROVE {aid} or REJECT {aid}")
            return {"status": "waiting_for_owner_approval", "approval_id": aid,
                    "message": f"Saved as approval #{aid}. It will run after the owner approves it."}
        return self.fn(**args)


def tool(name, description, properties=None, required=None, needs_approval=False, summary=None):
    """Decorator to turn a Python function into an agent tool."""
    def wrap(fn):
        params = {"type": "object", "properties": properties or {}, "required": required or []}
        return Tool(name, description, params, fn, needs_approval, summary)
    return wrap


def run_approved(aid):
    """Run an approved action. Called from the dashboard or a WhatsApp 'APPROVE n'."""
    a = db.get_approval(aid)
    if not a:
        return f"Approval #{aid} not found."
    if a["status"] != "pending":
        return f"Approval #{aid} is already {a['status']}."
    payload = json.loads(a["payload"])
    t = REGISTRY.get(payload["tool"])
    if not t:
        db.set_approval(aid, "failed", "tool missing")
        return f"Approval #{aid}: tool {payload['tool']} is not available."
    try:
        result = t.fn(**payload["args"])
        db.set_approval(aid, "done", json.dumps(result, ensure_ascii=False, default=str))
        return f"✅ #{aid} done: {_short(result)}"
    except Exception as e:  # noqa: BLE001
        db.set_approval(aid, "failed", f"{e}")
        return f"❌ #{aid} failed: {e}"


def reject(aid):
    a = db.get_approval(aid)
    if not a or a["status"] != "pending":
        return f"Approval #{aid} is not pending."
    db.set_approval(aid, "rejected")
    return f"#{aid} rejected. Nothing was changed."


def _short(x, n=400):
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    return s[:n]


_owner_notifier = None


def set_owner_notifier(fn):
    global _owner_notifier
    _owner_notifier = fn


def notify_owner(text):
    if _owner_notifier:
        try:
            _owner_notifier(text)
        except Exception:  # noqa: BLE001 - a failed notification must not break the agent
            pass


class Agent:
    def __init__(self, name, system, tools=(), max_steps=10, temperature=0.4):
        self.name = name
        self.system = system
        self.tools = {t.name: t for t in tools}
        self.max_steps = max_steps
        self.temperature = temperature

    def run(self, user_text, history=None, system_extra=""):
        system = self.system if not system_extra else self.system + "\n\n" + system_extra
        messages = [{"role": "system", "content": system}]
        for h in history or []:
            if h["role"] in ("user", "assistant") and h["content"]:
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": user_text})
        schemas = [t.schema() for t in self.tools.values()] or None
        for _ in range(self.max_steps):
            msg, _provider = llm.chat(messages, tools=schemas, temperature=self.temperature)
            calls = msg.get("tool_calls")
            if not calls:
                return msg["content"].strip()
            messages.append(msg)
            for c in calls:
                name = c["function"]["name"]
                args = llm.parse_json(c["function"]["arguments"]) if c["function"]["arguments"] else {}
                t = self.tools.get(name)
                if not t:
                    result = {"error": f"Unknown tool {name}"}
                else:
                    try:
                        result = t.call(args)
                    except TypeError as e:
                        result = {"error": f"Wrong arguments for {name}: {e}"}
                    except Exception as e:  # noqa: BLE001 - report the error to the model so it can recover
                        result = {"error": str(e), "trace": traceback.format_exc(limit=1)[-300:]}
                messages.append({"role": "tool", "tool_call_id": c["id"], "name": name,
                                 "content": _short(result, 6000)})
        messages.append({"role": "user", "content": "Stop using tools now and give your final answer to the owner."})
        msg, _ = llm.chat(messages, temperature=self.temperature)
        return msg["content"].strip()
