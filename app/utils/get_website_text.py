import httpx
from fastapi import HTTPException, status


async def latest_sites(query: str) -> str:
    try:
        url = f"https://www.w3.org/services/html2txt?url=https%3A%2F%2F{query}%2F&noinlinerefs=on&nonums=on"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()

            text = response.text.replace("\n", "").replace("\r", "").strip()
            text = " ".join(text.split())
            return text
    except Exception as e:
        # You can decide how to handle the exception. Raising an HTTPException is one way.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
