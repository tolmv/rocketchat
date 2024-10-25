import httpx


async def generate_quiz(link: str, number_of_questions: int):
    url = "https://quizgecko.com/api/v1/questions"
    api_key = (
        "129|7bpapi88oWBIwmfo5TVmdxRWCYPImvFJe3w9iC3e"  # Replace with your API key
    )

    data = {
        "url": link,
        "question_type": "multiple_choice",
        "difficulty": "hard",
        "number_of_questions": number_of_questions,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()  # Raises exception for HTTP error responses
            return await response.json()
    except Exception as e:
        print(f"Error: {e}")
        # Handle the error as appropriate for your application
