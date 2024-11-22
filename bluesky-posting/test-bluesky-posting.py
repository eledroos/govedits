from atproto import Client, models
import argparse
import json

def load_credentials(config_file):
    """Load Bluesky credentials from JSON file"""
    with open(config_file) as f:
        return json.load(f)

def create_bluesky_client(credentials):
    client = Client()
    client.login(credentials['email'], credentials['password'])
    return client

def post_to_bluesky(text, config_file='config.json'):
    """
    Post text content to Bluesky using credentials from JSON file
    
    Args:
        text (str): Content to post
        config_file (str): Path to JSON config file
    """
    try:
        credentials = load_credentials(config_file)
        client = create_bluesky_client(credentials)
        response = client.send_post(text=text)
        print(f"Successfully posted to Bluesky! Post URI: {response.uri}")
        return response
    except Exception as e:
        print(f"Error posting to Bluesky: {str(e)}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Post to Bluesky")
    parser.add_argument("text", help="Text content to post")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    
    args = parser.parse_args()
    post_to_bluesky(args.text, args.config)