from langchain_community.document_loaders import PyPDFLoader
from loguru import logger
import pdfplumber
import io
import re


def get_text_from_pdf(path) -> str:
    url_pattern = r'https?://[^\s]+'
    loader = PyPDFLoader(path)
    pages = loader.load_and_split()
    res = ''
    for i in range(len(pages) - 1):
        res += pages[i].page_content.replace('\n', " ").replace('•', ' ')
    res = res.split(" ")
    res = " ".join(res)
    parts = res.split("Желаемая должность и зарплата")
    if len(parts) == 1: 
        parts = res.split("Desired position and salary")
    if len(parts) == 1:
        return str(re.sub(url_pattern, '', res))
    # Проверка, есть ли нужная часть текста
    res = parts[1].strip()
    replaced_text = re.sub(url_pattern, '', res)
    return str(replaced_text)
