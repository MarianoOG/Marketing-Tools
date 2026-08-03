# %%
import requests
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
from pydantic import BaseModel
from openai import OpenAI
import json
import os
from concurrent import futures
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# The OpenAI SDK reads OPENAI_API_KEY from the environment by default
client = OpenAI()


class ContentInfo(BaseModel):
    resumen: str
    nivel_educativo: list[str]
    area_tematica: list[str]
    etiquetas: list[str]
    satisfaccion: int
    dificultad: int
    para_docentes: bool


def extract_urls_from_sitemap(sitemap_url):
    response = requests.get(sitemap_url)
    if response.status_code != 200:
        print(f"Failed to fetch the sitemap. Status code: {response.status_code}")
        return []
    root = ET.fromstring(response.content)
    return [url.text for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]


def get_website_content(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            text = ' '.join([tag.get_text(strip=True) for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])])
            return text
        else:
            print(f"Failed to fetch content from {url}. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching content from {url}: {str(e)}")
        return None


# %%
def extract_content_info(content: str) -> ContentInfo:
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", 
             "content": "Eres un asistente especializado en analizar contenido educativo. "
                        "Para cada contenido, debes extraer la información solicitada en español."
                        "Tus respuestas deben ser en formato JSON."
                        "El resumen debe ser una descripción breve y concisa del contenido, diseñado para los motores de búsqueda."
                        "El nivel educativo debe ser uno de los siguientes: Educación Preescolar, Educación Primaria, Educación Secundaria, Educación Preparatoria, Educación Superior, Educación para Adultos."
                        "El área temática debe ser uno de los siguientes: Pedagogía, Didáctica, Tecnología Educativa, Formación Docente, Enseñanza de Idiomas, Educación Inclusiva, Educación Especial."
                        "Las etiquetas deben ser palabras o términos que describen el contenido de manera general y no deben ser nivel educativo o área temática."
                        "La satisfacción del contenido debe ser un número entre 1 y 5 que representa que tan útil es este contenido para un docente."
                        "La dificultad del contenido debe ser un número entre 1 y 5 que representa que tan difícil es este contenido para un docente."
                        "Para docentes debe ser un booleano que indica si el contenido esta dirigido a docentes."
                        "Queremos que el contenido sea de buena calidad por lo que no dudes en ser estricto con la calidad del contenido."},
            {"role": "user", 
             "content": f"Analiza el siguiente contenido y extrae la información solicitada en español:\n\n{content}"}
        ],
        temperature=0.2,
        response_format=ContentInfo
    )
    return completion.choices[0].message.parsed
    

# %%
if __name__ == "__main__":
    # %% 
    # Get urls from sitemap
    sitemap_url = f"{os.environ['WP_SITE_URL']}/post-sitemap.xml"
    extracted_urls = extract_urls_from_sitemap(sitemap_url)
    print(f"Total URLs extracted: {len(extracted_urls)}")

    # %% 
    # Read metadata.jsonl and save url in a list
    metadata = []
    if os.path.exists("metadata.jsonl"):
        with open("metadata.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                metadata.append(json.loads(line))
        processed_urls = [item["url"] for item in metadata]
        print(f"Total metadata entries: {len(processed_urls)}")
    else:
        print("metadata.jsonl file does not exist. Starting with an empty metadata list.")
        processed_urls = []

    # %% 
    # Get content from urls
    url_to_content = {}
    with futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(get_website_content, url): url for url in extracted_urls if url not in processed_urls}
        print(f"Total URLs to fetch: {len(future_to_url)}")
        for future in futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                content = future.result()
                if content:
                    url_to_content[url] = content
                    print(f"Successfully fetched content from URL: {url}")
                else:
                    print(f"Failed to fetch content from URL: {url}")
            except Exception as exc:
                print(f"An error occurred while processing URL {url}: {exc}")
        print(f"Total URLs fetched: {len(url_to_content)}")

    # %% 
    # Extract content info and save metadata
    errors = []
    with open("metadata.jsonl", "a+", encoding="utf-8") as f, open("errors.txt", "w+", encoding="utf-8") as error_file:
        for i, (url, content) in enumerate(url_to_content.items()):
            print(f"Processing URL {i+1}/{len(url_to_content)}: {url}")
            try:
                info = extract_content_info(content)
                if info:
                    info = info.dict()
                    info["url"] = url
                    json_line = json.dumps(info, ensure_ascii=False)
                    f.write(json_line + "\n")
                    f.flush()  # Ensure the data is written immediately
                    metadata.append(info)
                    print(f"Metadata for {url} saved successfully.")
            except Exception as e:
                error_msg = f"Error processing URL {url}: {str(e)}\n"
                error_file.write(error_msg)
                error_file.flush()  # Ensure the error is written immediately
                errors.append(error_msg)
                print(error_msg)
            print("-" * 50)

    print("\nProcessing complete.")
    print(f"Total metadata entries: {len(metadata)}")
    print(f"Total errors: {len(errors)}")
    print("Check errors.txt for details on any errors encountered.")

    # %%
    # Get content from urls
    tags = set()
    niveles_educativos = defaultdict(lambda: 0)
    areas_tematicas = defaultdict(lambda: 0)
    satisfaccion = defaultdict(lambda: 0)
    dificultad = defaultdict(lambda: 0)
    no_para_docentes = 0
    for item in metadata:
        if not item["para_docentes"]:
            no_para_docentes += 1
            continue

        for etiqueta in item["etiquetas"]:
            tags.add(etiqueta)

        for area in item["area_tematica"]:
            areas_tematicas[area] += 1
        
        for nivel in item["nivel_educativo"]:
            niveles_educativos[nivel] += 1

        satisfaccion[item["satisfaccion"]] += 1
        dificultad[item["dificultad"]] += 1

    print(f"\nKeywords: {len(tags)}", tags)
    print(f"\nAreas temáticas: {len(areas_tematicas)}\n")
    print(json.dumps(areas_tematicas, indent=2, ensure_ascii=False))
    print(f"\nNiveles educativos: {len(niveles_educativos)}\n")
    print(json.dumps(niveles_educativos, indent=2, ensure_ascii=False))
    print(f"\nSatisfaccion: {len(satisfaccion)}\n")
    print(json.dumps(satisfaccion, indent=2, ensure_ascii=False))
    print(f"\nDificultad: {len(dificultad)}\n")
    print(json.dumps(dificultad, indent=2, ensure_ascii=False))
    print(f"\nNo para docentes: {no_para_docentes}\n")

    # %%
    # Get a url to category from metadata
    url_to_categories = defaultdict(list)
    for item in metadata:
        if not item["para_docentes"]:
            continue

        for area in item["area_tematica"]:
            if area not in url_to_categories[item["url"]]:
                url_to_categories[item["url"]].append(area)
        
        for nivel in item["nivel_educativo"]:
            if nivel not in url_to_categories[item["url"]]:
                url_to_categories[item["url"]].append(nivel)

    print(f"\nURL to category: {len(url_to_categories)}\n")
    # Save URL to categories in a file
    with open("url_to_categories.json", "w", encoding="utf-8") as f:
        json.dump(url_to_categories, f, ensure_ascii=False, indent=2)
    print("URL to categories saved!")


# %%
