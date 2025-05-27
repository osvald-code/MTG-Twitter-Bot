import requests
from requests_oauthlib import OAuth1
import json
import tweepy
import re
import os
import time
import cv2
import functions_framework

#post strings
initial_post = "The random card of the day is: "
flavor_default = "\nooo it has flavor:\n"
flavor_exception = "\nthis card has flavor, but it's too long :c\n"
tags_post = "\n#mtg #magicthegathering"


#get keys
api_key = os.environ.get("API_KEY")
api_secret = os.environ.get("API_SECRET")
access_token = os.environ.get("ACCESS_TOKEN")
access_token_secret = os.environ.get("ACCESS_TOKEN_SECRET")

def is_valid_art(image_status):
        print("card image status: ",  image_status)
        return (image_status=="highres_scan") or (image_status=="lowres")

def is_two_faced(layout_type):
    if( (layout_type == "transform") or (layout_type == "modal_dfc") or (layout_type == "meld") or (layout_type == "reversible_card") ):
        print("card is twoface")
        return True
    return False

def is_valid_layout(layout_type):
    print("card layout type: ",  layout_type)
    return not ( (layout_type == "token") or (layout_type == "double_faced_token") or (layout_type == "emblem") or (layout_type == "art_series") )

#seeks card appropriate for bot
def get_valid_card():
    max_attempts = 5
    attempts = 0
    is_valid_card = False
    url = "https://api.scryfall.com/cards/random"
    print("Accessing Card Database")
    while((attempts < max_attempts) and (not is_valid_card)):
        if attempts>1:
            time.sleep(0.1)
        attempts+=1
        print("Attempt #",attempts)
        card_data = requests.get(url).json()
        card_lang = card_data["lang"]
        print("card language:",  card_lang)
        card_layout = card_data["layout"]
        card_img_status = card_data["image_status"]
        card_type = card_data["type_line"]
        is_basic_land = ((card_type[0:10])=="Basic Land")
        is_valid_card = (card_lang == "en") and (is_valid_art(card_img_status)) and (is_valid_layout(card_layout) and (not is_basic_land))
        print("Card is valid format: ", is_valid_card)
    return card_data

def get_image_data(card_data):
    img_data = [None, None]
    if is_two_faced(card_data["layout"]):
        card_pic1=card_data["card_faces"][0]["image_uris"]["border_crop"]
        card_pic2=card_data["card_faces"][1]["image_uris"]["border_crop"]
        img_data[0] = requests.get(card_pic1).content
        img_data[1] = requests.get(card_pic2).content
    else:
        card_pic = card_data["image_uris"]["border_crop"]
        img_data[0] = requests.get(card_pic).content
    return img_data

def get_media_ids(img_data):
    tweepy_auth = tweepy.OAuth1UserHandler(
        "{}".format(api_key),
        "{}".format(api_secret),
        "{}".format(access_token),
        "{}".format(access_token_secret),
    )
    tweepy_api = tweepy.API(tweepy_auth)
    if not (img_data[1] is None):
        with open("/tmp/cardpic1.jpg", "wb") as handler:
            handler.write(img_data[0])
        with open("/tmp/cardpic2.jpg", "wb") as handler:
            handler.write(img_data[1])
        img_1 = cv2.imread("/tmp/cardpic1.jpg")
        img_2 = cv2.imread("/tmp/cardpic2.jpg")
        im_h = cv2.hconcat([img_1,img_2])
        cv2.imwrite("/tmp/cardpic.jpg",im_h)
    else:
        with open("/tmp/cardpic.jpg", "wb") as handler:
            handler.write(img_data[0])
    post = tweepy_api.simple_upload("/tmp/cardpic.jpg")
    text = str(post)
    media_id = re.search("media_id=(.+?),", text).group(1)
    payload = {"media": {"media_ids": ["{}".format(media_id)]}}
    if os.path.exists("/tmp/cardpic.1"):
        os.remove("/tmp/cardpic.1")
    if os.path.exists("/tmp/cardpic.2"):
        os.remove("/tmp/cardpic2.jpg")
    os.remove("/tmp/cardpic.jpg")
    return payload

def connect_to_oauth(api_key, api_secret, acccess_token, access_token_secret):
    url = "https://api.twitter.com/2/tweets"
    auth = OAuth1(api_key, api_secret, acccess_token, access_token_secret)
    return url, auth

def get_card_text(card_data):
    print("getting card text")
    flavor_text= ""
    name = card_data["name"]
    text = initial_post + name
    if ("flavor_text" in card_data):
        flavor_text = flavor_default + card_data["flavor_text"]
        if(len(text+flavor_text + tags_post)>229):
            flavor_text = flavor_exception
    text = text + flavor_text + tags_post
    return text

def format_payload(card_text, media_ids):
    media_ids["text"] = card_text
    return media_ids

def post(payload):
    url, auth = connect_to_oauth(
        api_key, api_secret, access_token, access_token_secret
    )
    response = requests.post(
        url=url,
        auth=auth,
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    return response.json()

# Triggered from a message on a Cloud Pub/Sub topic.
@functions_framework.cloud_event
def hello_pubsub(cloud_event):
    card_data = get_valid_card()
    if (card_data is None):
        print("Card data not found")
        return "Card data not found"
    card_text = get_card_text(card_data)
    print("Card Text: " + card_text)
    image_data = get_image_data(card_data)
    media_ids = get_media_ids(image_data)
    payload = format_payload(card_text,media_ids)
    result = post(payload)
    print(json.dumps(result, indent=4, sort_keys=True))
    return "Success"
