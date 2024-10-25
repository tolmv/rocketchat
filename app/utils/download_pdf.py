import httpx


async def download_file_from_google_drive(url, destination):
    # Create an async HTTP client
    async with httpx.AsyncClient() as client:
        # Sending an HTTP GET request to the URL asynchronously
        response = await client.get(url)

        # Check if the request was successful
        if response.status_code == 200:
            # Open a binary file in write mode
            with open(destination, "wb") as file:
                file.write(response.content)
            print("File downloaded successfully!")
        else:
            print(f"Failed to download file. Status code: {response.status_code}")
