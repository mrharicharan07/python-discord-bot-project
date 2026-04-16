from groq import Groq

from config import GROQ_API_KEY


client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


async def ai_check(text: str) -> str:
    if not client or not text.strip():
        return "NO"

    try:
        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Reply with only YES or NO. "
                        "Return YES only for clearly abusive, hateful, threatening, sexual harassment, "
                        "or strong profanity targeting a person/group. Return NO for harmless chat, jokes, "
                        "normal greetings, and non-abusive mentions."
                    ),
                },
                {"role": "user", "content": text[:1200]},
            ],
            max_tokens=3,
            temperature=0.0,
        )
        reply = res.choices[0].message.content.strip().upper()
        return "YES" if reply.startswith("YES") else "NO"
    except Exception as exc:
        print(f"[AI CHECK ERROR] {exc}")
        return "NO"


async def ai_reply(user_name: str, guild_name: str, text: str) -> str:
    if not client or not text.strip():
        return ""

    try:
        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Zoro, a confident but helpful Discord server bot. "
                        "Reply in one short message, max 2 sentences. "
                        "Be friendly, playful, and useful. Avoid abuse, insults, or roleplay as a human."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Server: {guild_name}\n"
                        f"User: {user_name}\n"
                        f"Message: {text[:500]}"
                    ),
                },
            ],
            max_tokens=80,
            temperature=0.7,
        )
        return res.choices[0].message.content.strip()[:300]
    except Exception as exc:
        print(f"[AI REPLY ERROR] {exc}")
        return ""
