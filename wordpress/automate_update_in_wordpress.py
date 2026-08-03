# %%
# Import libraries
import requests
import json
import base64
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def get_setting(name: str) -> str:
    """Read a required setting from the environment, failing loudly if unset."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing {name}. Copy .env.example to .env in this folder and fill it in."
        )
    return value


WP_SITE_URL = get_setting("WP_SITE_URL").rstrip("/")


# %%
# Get url to id mapping
def get_posts():
    # WordPress REST API endpoint for pages
    api_endpoint = f"{WP_SITE_URL}/wp-json/wp/v2/posts"

    # Get all pages
    pages = []
    page = 1
    per_page = 100  # Maximum allowed by WordPress API

    while True:
        response = requests.get(
            api_endpoint,
            params={'page': page, 'per_page': per_page, '_fields': 'id,link,categories'}
        )
        
        if response.status_code != 200:
            print(f"Error fetching pages: {response.status_code}")
            break

        new_pages = response.json()
        if not new_pages:
            break

        pages.extend(new_pages)
        page += 1

    print(f"Total pages fetched: {len(pages)}")
    return pages


# %%
# Get categories
def get_categories():
    # WordPress REST API endpoint for categories
    api_endpoint = f"{WP_SITE_URL}/wp-json/wp/v2/categories"

    # Get all categories
    categories = {}
    page = 1
    per_page = 100  # Maximum allowed by WordPress API

    while True:
        response = requests.get(
            api_endpoint,
            params={'page': page, 'per_page': per_page, '_fields': 'id,name'}
        )
        
        if response.status_code != 200:
            print(f"Error fetching categories: {response.status_code}")
            break

        new_categories = response.json()
        if not new_categories:
            break

        for category in new_categories:
            categories[category['name']] = category['id']

        page += 1

    print(f"Total categories fetched: {len(categories)}")
    return categories

    

# %%
# Update wordpress page
def update_wordpress_page(post_id, categories):
    # WordPress REST API endpoint for pages
    wp_username = get_setting("WP_USERNAME")
    wp_password = get_setting("WP_APP_PASSWORD")
    api_endpoint = f"{WP_SITE_URL}/wp-json/wp/v2/posts/{post_id}"

    # Prepare the update data
    update_data = {
        "categories": categories
    }

    # Encode the username and password
    credentials = f"{wp_username}:{wp_password}"
    encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
    header = {"Authorization": f"Basic {encoded_credentials}"}


    # Update the page
    update_response = requests.post(
        api_endpoint,
        headers=header,
        json=update_data
    )

    if update_response.status_code == 200:
        print(f"Successfully updated page with ID: {post_id}")
    else:
        print(f"Failed to update page with ID: {post_id}")
        print(f"Error: {update_response.text}")


# %%
# Valid categories and url_to_categories
valid_categories = (
    "Educación Preescolar",
    "Educación Primaria",
    "Educación Secundaria",
    "Educación Preparatoria",
    "Educación Superior",
    "Educación para Adultos",
    "Didáctica",
    "Pedagogía",
    "Tecnología Educativa",
    "Formación Docente",
    "Enseñanza de Idiomas",
    "Educación Inclusiva",
    "Educación Especial"
)
with open("url_to_categories.json", "r") as f:
    url_to_categories = json.load(f)

# %%
# Get categories
categories = get_categories()
print(json.dumps(categories, indent=4))


# %%
# Get url to id mapping
posts = get_posts()
print(json.dumps(posts, indent=4))

# %%
# Update wordpress
for post in posts:
    if post['link'] in url_to_categories:
        cat = url_to_categories[post['link']]
        cat = [categories[c] for c in cat if c in valid_categories]
        if post['categories'] == [1]:
            update_wordpress_page(post['id'], cat)
            print(post['link'], post['categories'])
    else:
        print(f"No categories found for {post['link']}")

# %%
