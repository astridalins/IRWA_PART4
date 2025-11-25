import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env


class RAGGenerator:

    PROMPT_TEMPLATE = """
        You are an expert product advisor helping users choose the best option from retrieved e-commerce products.

        ## Instructions:
        1. Identify the single best product using ALL the metadata provided (price, discount, rating, description, and retrieval score). Do NOT invent attributes that are not explicitly included in the metadata. Your justification MUST refer only to fields shown in the Retrieved Products section.
        2. Present the recommendation clearly in this format:
        - Best Product: [Product PID] [Product Name]
        - Why: [Explain in plain language why this product is the best fit, referring to specific attributes like price, features, quality, or fit to user’s needs.]
        3. If there is another product that could also work, mention it briefly as an alternative.
        4. If no product is a good fit, return ONLY this exact phrase:
        "There are no good products that fit the request based on the retrieved results."

        ## Retrieved Products:
        {retrieved_results}

        ## User Request:
        {user_query}

        ## Output Format:
        - Best Product: ...
        - Why: ...
        - Alternative (optional): ...
    """

    def generate_response(
        self, user_query: str, retrieved_results: list, top_N: int = 20
    ) -> dict:
        """
        Generate a response using the retrieved search results.
        Returns:
            dict: Contains the generated suggestion and the quality evaluation.
        """
        DEFAULT_ANSWER = "RAG is not available. Check your credentials (.env file) or account limits."

        try:
            client = Groq(
                api_key=os.environ.get("GROQ_API_KEY"),
            )
            model_name = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

            # IMPROVEMENT 2 — ADAPTIVE FILTERING (simple relevance filter)

            query_tokens = user_query.lower().split()

            filtered_results = []
            for res in retrieved_results:
                title_tokens = str(res.title).lower().split()
                # keep product if ANY query token appears in title
                if any(t in title_tokens for t in query_tokens):
                    filtered_results.append(res)

            # fallback: if all results filtered out, keep originals
            if not filtered_results:
                filtered_results = retrieved_results

            # IMPROVEMENT 1 — richer metadata for RAG input

            formatted_results = "\n".join(
                [
                    (
                        f"- PID: {res.pid}\n"
                        f"  Title: {res.title}\n"
                        f"  Description: {res.description}\n"
                        f"  Price: {res.selling_price}\n"
                        f"  Discount: {res.discount}\n"
                        f"  Rating: {res.average_rating}\n"
                        f"  Original URL: {res.external_url}\n"
                        f"  Retrieval Score: {res.ranking}"
                    )
                    for res in filtered_results[:top_N]
                ]
            )

            # Build full prompt
            prompt = self.PROMPT_TEMPLATE.format(
                retrieved_results=formatted_results,
                user_query=user_query,
            )

            # Send to LLM
            chat_completion = client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model=model_name,
            )

            generation = chat_completion.choices[0].message.content
            return generation

        except Exception as e:
            print(f"Error during RAG generation: {e}")
            return DEFAULT_ANSWER
