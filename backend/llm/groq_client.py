"""Groq LLM Client for AI Recommendations"""
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import GROQ_API_KEY, LLM_MODEL

try:
    from groq import Groq
except ImportError:
    Groq = None


SYSTEM_PROMPT = """You are AniVerse AI, an expert anime and manga recommendation assistant.

## YOUR CORE MISSION
Provide HIGHLY RELEVANT, PRECISE recommendations. Quality over quantity. Every suggestion must directly address what the user is looking for.

## RECOMMENDATION RULES
1. **Match the Query Exactly**: If user asks for "dark fantasy", recommend dark fantasy - not action comedy.
2. **Use Context Wisely**: Reference the "Relevant Anime/Manga" data provided. These are semantically matched to the query.
3. **Explain Your Picks**: For EACH recommendation, give 1-2 sentences on WHY it fits the request.
4. **Limit Recommendations**: Suggest 2-4 titles max per response. Be selective.
5. **Format Clearly**: Use bold for titles, include scores and genres inline.

## PERSONALIZATION (When User Profile Available)
- Reference their high-rated titles: "Since you gave Attack on Titan a 9..."
- Avoid genres from low-rated shows
- Connect new suggestions to their favorites

## RESPONSE FORMAT
When recommending, use this structure:
**[Title]** (★ score/10) - [Brief reason why this matches their request]

## ACTION HANDLING
1. **Verifying Actions**: You verify if an action (like adding to list) succeeded by checking the "=== ACTIONS EXECUTED ===" section in the context.
2. **Success**: If an action is listed there, confirm it enthusiastically (e.g., "Done! Added X to your list").
3. **Failure/No Action**: If the user asked for an action but it is NOT in the "=== ACTIONS EXECUTED ===" block, DO NOT say you did it. Instead, assume the backend failed to understand the command.
   - Ask the user to try again with valid syntax: "Add [Title] to [completed/watching/planned]"
   - Or "Rate [Title] [Score]"
4. **Ambiguity**: If the user says "Add to list" without specifying which list, ask them to specify (Completed, Watching, Planned).

Context about relevant titles will be provided below."""


class GroqClient:
    """Groq LLM client for AI-powered recommendations"""
    
    def __init__(self):
        if not Groq:
            raise ImportError("groq package not installed. Run: pip install groq")
        
        if not GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not set. Add it to your .env file")
        
        self.client = Groq(api_key=GROQ_API_KEY)
        self.model = LLM_MODEL
    
    def chat(
        self,
        user_message: str,
        context: str = "",
        history: list[dict] = None,
        max_tokens: int = 1024
    ) -> str:
        """Send a chat message and get a response"""
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        # Add context if provided
        if context:
            messages.append({
                "role": "system",
                "content": f"Here is relevant anime data from our database:\n\n{context}"
            })
        
        # Add conversation history
        if history:
            messages.extend(history)
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        # Call Groq API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        
        return response.choices[0].message.content
    
    def summarize_reviews(
        self,
        reviews: list[str],
        anime_title: str
    ) -> dict:
        """Summarize multiple reviews into pros/cons"""
        reviews_text = "\n---\n".join(reviews[:10])  # Limit to 10 reviews
        
        prompt = f"""Analyze these reviews for "{anime_title}" and provide:
1. Overall sentiment (positive/negative/mixed)
2. Top 3 pros (things reviewers loved)
3. Top 3 cons (things reviewers criticized)
4. A 2-3 sentence summary
5. Aspect scores (1-10) for: story, animation, characters, music, enjoyment

Reviews:
{reviews_text}

Respond in JSON format:
{{
    "sentiment": "positive|negative|mixed",
    "pros": ["pro1", "pro2", "pro3"],
    "cons": ["con1", "con2", "con3"],
    "summary": "...",
    "aspects": {{"story": 8, "animation": 9, ...}}
}}"""
        
        response = self.chat(prompt, max_tokens=512)
        
        # Parse JSON response (with fallback)
        import json
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {
                "sentiment": "mixed",
                "pros": [],
                "cons": [],
                "summary": response,
                "aspects": {}
            }
    
    def generate_recommendation_reason(
        self,
        user_query: str,
        anime_data: dict
    ) -> str:
        """Generate a personalized reason why an anime matches the user's request"""
        prompt = f"""The user asked: "{user_query}"

This anime was matched:
- Title: {anime_data.get('title', 'Unknown')}
- Genres: {anime_data.get('genres', 'Unknown')}
- Score: {anime_data.get('score', 'N/A')}

In 1-2 sentences, explain why this anime matches what the user is looking for. Be specific about the connection."""
        
        return self.chat(prompt, max_tokens=150)


# Singleton
_client: Optional[GroqClient] = None


def get_llm_client() -> GroqClient:
    """Get or create LLM client instance"""
    global _client
    if _client is None:
        _client = GroqClient()
    return _client
