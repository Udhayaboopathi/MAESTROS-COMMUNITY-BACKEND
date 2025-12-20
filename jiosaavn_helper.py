"""Helper functions for JioSaavn API integration"""

import base64
from pyDes import des, ECB, PAD_PKCS5


def format_song(data, lyrics):
    """Format song data with decrypted URLs and proper encoding"""
    try:
        data['media_url'] = decrypt_url(data['encrypted_media_url'])
        if data['320kbps'] != "true":
            data['media_url'] = data['media_url'].replace("_320.mp4", "_160.mp4")
        data['media_preview_url'] = data['media_url'].replace(
            "_320.mp4", "_96_p.mp4").replace("_160.mp4", "_96_p.mp4").replace("//aac.", "//preview.")
    except (KeyError, TypeError):
        url = data['media_preview_url']
        url = url.replace("preview", "aac")
        if data['320kbps'] == "true":
            url = url.replace("_96_p.mp4", "_320.mp4")
        else:
            url = url.replace("_96_p.mp4", "_160.mp4")
        data['media_url'] = url

    data['song'] = format_text(data['song'])
    data['music'] = format_text(data['music'])
    data['singers'] = format_text(data['singers'])
    data['starring'] = format_text(data['starring'])
    data['album'] = format_text(data['album'])
    data["primary_artists"] = format_text(data["primary_artists"])
    data['image'] = data['image'].replace("150x150", "500x500")

    # Get lyrics only if requested
    if lyrics:
        if data['has_lyrics'] == 'true':
            # Import here to avoid circular dependency
            from routers.music import get_lyrics_by_id
            data['lyrics'] = get_lyrics_by_id(data['id'])
        else:
            data['lyrics'] = None

    try:
        data['copyright_text'] = data['copyright_text'].replace("&copy;", "©")
    except KeyError:
        pass
    
    return data


def format_album(data, lyrics):
    """Format album data with proper encoding"""
    data['image'] = data['image'].replace("150x150", "500x500")
    data['name'] = format_text(data['name'])
    data['primary_artists'] = format_text(data['primary_artists'])
    data['title'] = format_text(data['title'])
    for song in data['songs']:
        song = format_song(song, lyrics)
    return data


def format_playlist(data, lyrics):
    """Format playlist data with proper encoding"""
    data['firstname'] = format_text(data['firstname'])
    data['listname'] = format_text(data['listname'])
    for song in data['songs']:
        song = format_song(song, lyrics)
    return data


def format_text(string):
    """Format text by replacing HTML entities"""
    return string.encode().decode().replace("&quot;", "'").replace("&amp;", "&").replace("&#039;", "'")


def decrypt_url(url):
    """Decrypt JioSaavn encrypted media URLs"""
    des_cipher = des(b"38346591", ECB, b"\0\0\0\0\0\0\0\0", pad=None, padmode=PAD_PKCS5)
    enc_url = base64.b64decode(url.strip())
    dec_url = des_cipher.decrypt(enc_url, padmode=PAD_PKCS5).decode('utf-8')
    dec_url = dec_url.replace("_96.mp4", "_320.mp4")
    return dec_url
