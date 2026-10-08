"""Write the analysed categories back to WordPress.

Only posts still sitting in the default category (id 1, "Uncategorized") are
touched, so a post someone categorised by hand is never overwritten.
"""

import base64
import json
from typing import Callable, Dict

import requests

from app.wordpress import CATEGORIES_FILE, get_setting

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


def site_url() -> str:
    return get_setting("WP_SITE_URL").rstrip("/")


# Get url to id mapping
def get_posts():
    # WordPress REST API endpoint for pages
    api_endpoint = f"{site_url()}/wp-json/wp/v2/posts"

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

    return pages


# Get categories
def get_categories():
    # WordPress REST API endpoint for categories
    api_endpoint = f"{site_url()}/wp-json/wp/v2/categories"

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

    return categories


# Update wordpress page
def update_wordpress_page(post_id, categories) -> bool:
    # WordPress REST API endpoint for pages
    wp_username = get_setting("WP_USERNAME")
    wp_password = get_setting("WP_APP_PASSWORD")
    api_endpoint = f"{site_url()}/wp-json/wp/v2/posts/{post_id}"

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

    if update_response.status_code != 200:
        print(f"Failed to update page with ID: {post_id}")
        print(f"Error: {update_response.text}")
    return update_response.status_code == 200


def run_update(progress: Callable[[str], None]) -> Dict:
    """Apply ``url_to_categories.json`` to every still-uncategorised post."""
    if not CATEGORIES_FILE.exists():
        raise RuntimeError("No categories to apply yet - run the analysis first.")
    with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
        url_to_categories = json.load(f)

    categories = get_categories()
    progress(f"Total categories fetched: {len(categories)}")

    posts = get_posts()
    progress(f"Total pages fetched: {len(posts)}")

    updated, failed, without_categories = [], [], []
    for post in posts:
        if post['link'] in url_to_categories:
            cat = url_to_categories[post['link']]
            cat = [categories[c] for c in cat if c in valid_categories]
            if post['categories'] == [1]:
                if update_wordpress_page(post['id'], cat):
                    updated.append(post['link'])
                    progress(f"Updated {post['link']}")
                else:
                    failed.append(post['link'])
        else:
            without_categories.append(post['link'])

    return {"updated": updated, "failed": failed, "without_categories": without_categories}
