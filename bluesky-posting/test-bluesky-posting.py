from atproto import Client, models
import json
import re
from typing import List, Dict
from PIL import Image
import piexif
import os

# Post content configuration
POST_TEXT = "Check out this awesome image! https://example.com"
IMAGE_PATH = "test.png"  # Leave empty for text-only posts
IMAGE_ALT_TEXT = "Description of the image"

def strip_exif(image_path: str):
    """Remove EXIF data from image"""
    try:
        piexif.remove(image_path)
    except:
        pass  # Not all images have EXIF data

def load_credentials(config_file):
    with open(config_file) as f:
        return json.load(f)

def parse_mentions(text: str) -> List[Dict]:
    spans = []
    mention_regex = rb"[$|\W](@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    text_bytes = text.encode("UTF-8")
    for m in re.finditer(mention_regex, text_bytes):
        spans.append({
            "start": m.start(1),
            "end": m.end(1),
            "handle": m.group(1)[1:].decode("UTF-8")
        })
    return spans

def parse_urls(text: str) -> List[Dict]:
    spans = []
    url_regex = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
    text_bytes = text.encode("UTF-8")
    for m in re.finditer(url_regex, text_bytes):
        spans.append({
            "start": m.start(1),
            "end": m.end(1),
            "url": m.group(1).decode("UTF-8"),
        })
    return spans

def parse_facets(text: str, client: Client) -> List[Dict]:
    facets = []
    
    for m in parse_mentions(text):
        try:
            did = client.com.atproto.identity.resolve_handle({'handle': m["handle"]}).did
            facets.append({
                "index": {
                    "byteStart": m["start"],
                    "byteEnd": m["end"],
                },
                "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}],
            })
        except Exception:
            continue
    
    for u in parse_urls(text):
        facets.append({
            "index": {
                "byteStart": u["start"],
                "byteEnd": u["end"],
            },
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": u["url"]},],
        })
    return facets

def upload_image(client: Client, image_path: str) -> dict:
    """Upload an image and return the blob"""
    if not os.path.exists(image_path):
        raise Exception(f"Image file not found: {image_path}")
        
    # Strip EXIF data
    strip_exif(image_path)
    
    with open(image_path, "rb") as f:
        img_bytes = f.read()
        
    # Check file size
    if len(img_bytes) > 1000000:
        raise Exception(f"Image too large: {len(img_bytes)} bytes. Maximum is 1,000,000 bytes")
    
    # Upload the image
    response = client.com.atproto.repo.upload_blob(img_bytes)
    return response.blob

def post_to_bluesky(config_file='config.json'):
    """Post content with optional image to Bluesky"""
    try:
        credentials = load_credentials(config_file)
        client = Client()
        client.login(credentials['email'], credentials['password'])
        
        # Parse rich text features
        facets = parse_facets(POST_TEXT, client)
        
        # Prepare post parameters
        post_params = {
            "text": POST_TEXT,
            "facets": facets
        }
        
        # Add image if path is provided
        if IMAGE_PATH:
            try:
                blob = upload_image(client, IMAGE_PATH)
                embed = {
                    "$type": "app.bsky.embed.images",
                    "images": [{
                        "alt": IMAGE_ALT_TEXT,
                        "image": blob
                    }]
                }
                post_params["embed"] = embed
            except Exception as e:
                print(f"Warning: Failed to upload image: {str(e)}")
                print("Continuing with text-only post...")
        
        # Create post
        response = client.send_post(**post_params)
        
        print(f"Successfully posted to Bluesky! Post URI: {response.uri}")
        return response
    except Exception as e:
        print(f"Error posting to Bluesky: {str(e)}")
        return None

if __name__ == "__main__":
    post_to_bluesky()